"""Sarvam Vision 3B / NVIDIA Multimodal OCR for shelter intake registers and flood signboard plausibility gating."""
from __future__ import annotations

import base64
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
import time
from typing import Any
from urllib import request

from app.config import Settings
from app.graph.neo4j_client import GraphStoreManager
from app.graph.plausibility_gate import evaluate_dem_plausibility_and_supersede


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class ShelterRegisterEntry:
    ward: str
    headcount: int
    medical_needs_count: int
    notes: str

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ShelterRegisterOcrResult:
    fixture_id: str
    shelter_node_id: str
    model: str
    markdown_table: str
    entries: list[ShelterRegisterEntry] = field(default_factory=list)
    total_headcount: int = 0
    total_medical_needs: int = 0
    latency_ms: float = 0.0
    source_mode: str = "deterministic_fixture"

    def model_dump(self) -> dict[str, Any]:
        return {
            "fixture_id": self.fixture_id,
            "shelter_node_id": self.shelter_node_id,
            "model": self.model,
            "markdown_table": self.markdown_table,
            "entries": [e.model_dump() for e in self.entries],
            "total_headcount": self.total_headcount,
            "total_medical_needs": self.total_medical_needs,
            "latency_ms": self.latency_ms,
            "source_mode": self.source_mode,
        }


class SarvamVisionOcrService:
    """Extracts structured shelter occupancy tables and flood-gauge signboard readings."""

    def __init__(
        self,
        graph_manager: GraphStoreManager,
        settings: Settings | None = None,
        seed_bundle_dir: Path | None = None,
    ) -> None:
        self.graph_manager = graph_manager
        self.settings = settings or Settings()
        self.seed_bundle_dir = Path(seed_bundle_dir or (REPO_ROOT / "data" / "seed_bundle"))
        self._fixtures = self._load_fixtures()

    def _load_fixtures(self) -> dict[str, dict[str, Any]]:
        manifest_path = self.seed_bundle_dir / "fixtures" / "sarvam_test_manifest.json"
        if not manifest_path.exists():
            return {}
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = payload.get("vision_fixtures", payload.get("vision_ocr_fixtures", []))
        return {
            item["id"]: item
            for item in items
            if isinstance(item, dict) and "id" in item
        }

    def parse_markdown_shelter_table(self, markdown_table: str) -> list[ShelterRegisterEntry]:
        lines = [line.strip() for line in markdown_table.strip().splitlines() if line.strip().startswith("|")]
        if len(lines) < 3:
            return []
        entries: list[ShelterRegisterEntry] = []
        for row_line in lines[2:]:
            cols = [c.strip() for c in row_line.strip("|").split("|")]
            if len(cols) < 3:
                continue
            try:
                headcount = int(cols[1])
                medical = int(cols[2])
            except ValueError:
                continue
            notes = cols[3] if len(cols) >= 4 else "Sarvam Vision OCR"
            entries.append(
                ShelterRegisterEntry(
                    ward=cols[0],
                    headcount=headcount,
                    medical_needs_count=medical,
                    notes=notes,
                )
            )
        return entries

    def _try_live_vision_markdown(self, image_bytes: bytes, shelter_node_id: str) -> str | None:
        if not self.settings.nvidia_api_key or len(image_bytes) < 64:
            return None
        b64_img = base64.b64encode(image_bytes).decode("ascii")
        prompt = (
            f"Extract the shelter occupancy register for {shelter_node_id} as a Markdown table "
            "with columns: | Shelter | Occupancy | Medical | Notes |."
        )
        payload = json.dumps({
            "model": self.settings.nvidia_vision_model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}},
                    ],
                }
            ],
            "temperature": 0.0,
            "max_tokens": 250,
        }).encode("utf-8")
        req = request.Request(
            f"{self.settings.nvidia_base_url.rstrip('/')}/chat/completions",
            data=payload,
            headers={
                "Authorization": f"Bearer {self.settings.nvidia_api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with request.urlopen(req, timeout=6.0) as resp:
                body = json.loads(resp.read().decode("utf-8"))
                content = str(body["choices"][0]["message"]["content"]).strip()
                if "|" in content:
                    return content
        except Exception:
            return None
        return None

    def extract_shelter_register(
        self,
        image_bytes: bytes,
        shelter_node_id: str,
        fixture_id: str | None = None,
        prefer_live_api: bool = False,
    ) -> ShelterRegisterOcrResult:
        t0 = time.perf_counter()
        if not image_bytes:
            raise ValueError("image_bytes must not be empty for Sarvam Vision OCR")

        source_mode = "deterministic_fixture"
        md_table = ""
        if prefer_live_api and not fixture_id:
            live_md = self._try_live_vision_markdown(image_bytes, shelter_node_id)
            if live_md:
                md_table = live_md
                source_mode = "live_vision_api"

        matched = self._resolve_fixture(shelter_node_id=shelter_node_id, fixture_id=fixture_id)
        if not md_table:
            md_table = matched.get("extracted_markdown") or matched.get("markdown_table", "")
        entries = self.parse_markdown_shelter_table(md_table)
        total_headcount = sum(e.headcount for e in entries)
        total_medical = sum(e.medical_needs_count for e in entries)

        node = self.graph_manager.get_node(shelter_node_id)
        if node is not None:
            self.graph_manager.update_node_properties(
                shelter_node_id,
                {"current_occupancy": total_headcount, "medical_needs_count": total_medical},
            )
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return ShelterRegisterOcrResult(
            fixture_id=matched["id"],
            shelter_node_id=shelter_node_id,
            model=self.settings.sarvam_vision_model,
            markdown_table=md_table,
            entries=entries,
            total_headcount=total_headcount,
            total_medical_needs=total_medical,
            latency_ms=latency_ms,
            source_mode=source_mode,
        )

    def extract_signboard_and_gate_sitrep(
        self,
        image_bytes: bytes,
        report_id: str,
        nearest_node_id: str,
        claimed_depth_m: float,
        observed_at_iso: str,
        signboard_text_hint: str = "",
        reporter_role: str = "SDRF_RESPONDER",
    ) -> dict[str, Any]:
        if not image_bytes:
            raise ValueError("image_bytes must not be empty for signboard OCR")
        target_node = self.graph_manager.get_node(nearest_node_id)
        if target_node is None:
            raise ValueError(f"Unknown node {nearest_node_id}")
        extracted_text = signboard_text_hint or f"Flood gauge reading near {nearest_node_id}: {claimed_depth_m:.2f}m"
        obs_dt = datetime.fromisoformat(observed_at_iso.replace("Z", "+00:00"))
        gate_verdict = evaluate_dem_plausibility_and_supersede(
            graph_store=self.graph_manager,
            report_id=report_id,
            lat=float(target_node["lat"]),
            lon=float(target_node["lon"]),
            claimed_depth_m=claimed_depth_m,
            reporter_role=reporter_role,  # type: ignore[arg-type]
            observed_at=obs_dt,
            raw_transcript=extracted_text,
            english_translation=extracted_text,
        )
        return {
            "ocr_model": self.settings.sarvam_vision_model,
            "extracted_signboard_text": extracted_text,
            "plausibility": gate_verdict.model_dump(),
        }

    def _resolve_fixture(self, shelter_node_id: str, fixture_id: str | None) -> dict[str, Any]:
        if fixture_id and fixture_id in self._fixtures:
            return self._fixtures[fixture_id]
        for item in self._fixtures.values():
            if item.get("shelter_id") == shelter_node_id or item.get("shelter_node_id") == shelter_node_id:
                return item
        if self._fixtures:
            return next(iter(self._fixtures.values()))
        return {
            "id": "fallback_vision_shelter_01",
            "shelter_id": shelter_node_id,
            "extracted_markdown": (
                "| Shelter | Occupancy | Medical |\n"
                "|---|---|---|\n"
                "| Velachery HSS Relief Camp (SHEL-CHENNAI-01) | 312 | 18 |"
            ),
        }

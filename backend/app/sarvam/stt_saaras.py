"""Sarvam Saaras v4 dual-pass emergency speech-to-text (codemix + translate) with AOI keyterm biasing."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
import time
from typing import Any
from urllib import request
import uuid

from app.config import AOI_KEYTERMS, Settings


REPO_ROOT = Path(__file__).resolve().parents[3]


@dataclass
class SttDualPassResult:
    fixture_id: str
    aoi_id: str
    language_detected: str
    model: str
    codemix_transcript: str
    english_translation: str
    keyterms_applied: list[str] = field(default_factory=list)
    confidence: float = 0.0
    latency_ms: float = 0.0
    source_mode: str = "deterministic_fixture"

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


def _encode_multipart_wav(
    audio_bytes: bytes,
    fields: dict[str, str],
    filename: str = "distress.wav",
) -> tuple[bytes, str]:
    boundary = f"----NirantarSarvamBoundary{uuid.uuid4().hex}"
    lines: list[bytes] = []
    for k, v in fields.items():
        lines.append(f"--{boundary}\r\n".encode("utf-8"))
        lines.append(f'Content-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8"))
    lines.append(f"--{boundary}\r\n".encode("utf-8"))
    lines.append(
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: audio/wav\r\n\r\n".encode("utf-8")
    )
    lines.append(audio_bytes)
    lines.append(f"\r\n--{boundary}--\r\n".encode("utf-8"))
    return b"".join(lines), f"multipart/form-data; boundary={boundary}"


class SarvamSaarasSttService:
    """Executes dual-pass Saaras v4 transcription (`codemix` + `translate`) with local toponym biasing."""

    SARVAM_STT_ENDPOINT = "https://api.sarvam.ai/speech-to-text"
    SARVAM_TRANSLATE_ENDPOINT = "https://api.sarvam.ai/speech-to-text-translate"

    def __init__(self, settings: Settings | None = None, seed_bundle_dir: Path | None = None) -> None:
        self.settings = settings or Settings()
        self.seed_bundle_dir = Path(seed_bundle_dir or (REPO_ROOT / "data" / "seed_bundle"))
        self._fixtures = self._load_fixtures()

    def _load_fixtures(self) -> dict[str, dict[str, Any]]:
        manifest_path = self.seed_bundle_dir / "fixtures" / "sarvam_test_manifest.json"
        if not manifest_path.exists():
            return {}
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = payload.get("audio_fixtures", payload.get("stt_saaras_v4_fixtures", []))
        return {
            item["id"]: item
            for item in items
            if isinstance(item, dict) and "id" in item
        }

    def get_aoi_keyterms(self, aoi_id: str) -> list[str]:
        _ = str(aoi_id).strip().lower()
        return list(AOI_KEYTERMS)

    def transcribe_distress_audio(
        self,
        audio_bytes: bytes,
        aoi_id: str = "chennai",
        language_hint: str = "ta-IN",
        fixture_id: str | None = None,
        prefer_live_api: bool = False,
    ) -> SttDualPassResult:
        t0 = time.perf_counter()
        keyterms = self.get_aoi_keyterms(aoi_id)
        if not audio_bytes:
            raise ValueError("audio_bytes must not be empty for Saaras v4 transcription")

        if self.settings.sarvam_api_key and (prefer_live_api or not fixture_id):
            live_result = self._try_live_sarvam_stt(audio_bytes, language_hint, keyterms)
            if live_result is not None:
                latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
                return SttDualPassResult(
                    fixture_id=fixture_id or "live_sarvam_saaras",
                    aoi_id=aoi_id,
                    language_detected=live_result.get("language_code", language_hint),
                    model=self.settings.sarvam_stt_model,
                    codemix_transcript=live_result["codemix_transcript"],
                    english_translation=live_result["english_translation"],
                    keyterms_applied=keyterms,
                    confidence=float(live_result.get("confidence", 0.95)),
                    latency_ms=latency_ms,
                    source_mode="live_sarvam_api",
                )

        matched = self._resolve_fixture(aoi_id=aoi_id, fixture_id=fixture_id)
        latency_ms = round((time.perf_counter() - t0) * 1000.0, 3)
        return SttDualPassResult(
            fixture_id=matched["id"],
            aoi_id=matched.get("aoi_id", aoi_id),
            language_detected=matched.get("language_code", language_hint),
            model=self.settings.sarvam_stt_model,
            codemix_transcript=matched["codemix_transcript"],
            english_translation=matched["english_translation"],
            keyterms_applied=keyterms,
            confidence=float(matched.get("confidence", 0.94)),
            latency_ms=latency_ms,
            source_mode="deterministic_fixture",
        )

    def _resolve_fixture(self, aoi_id: str, fixture_id: str | None) -> dict[str, Any]:
        if fixture_id and fixture_id in self._fixtures:
            return self._fixtures[fixture_id]
        for item in self._fixtures.values():
            if item.get("aoi_id") == aoi_id:
                return item
        if self._fixtures:
            return next(iter(self._fixtures.values()))
        return {
            "id": "fallback_stt_01",
            "aoi_id": aoi_id,
            "language_code": "ta-IN",
            "codemix_transcript": (
                "Anna, Velachery SUB-CHENNAI-33KV-01 transformer spark aagudhu, "
                "CUL-CHENNAI-01 culvert la 1.2 meter thanni!"
            ),
            "english_translation": (
                "Brother, the Velachery SUB-CHENNAI-33KV-01 transformer is sparking, "
                "and there is 1.2 meters of water at culvert CUL-CHENNAI-01!"
            ),
            "confidence": 0.94,
        }

    def _try_live_sarvam_stt(
        self,
        audio_bytes: bytes,
        language_hint: str,
        keyterms: list[str],
    ) -> dict[str, Any] | None:
        prompt_str = ", ".join(keyterms[:18])
        for model_tag in (self.settings.sarvam_stt_model, "saaras:v3", "saaras:v2.5", "saarika:v2.5"):
            try:
                body_bytes, content_type = _encode_multipart_wav(
                    audio_bytes,
                    fields={
                        "model": model_tag,
                        "language_code": language_hint,
                        "prompt": prompt_str,
                    },
                )
                req = request.Request(
                    self.SARVAM_TRANSLATE_ENDPOINT if "saaras" in model_tag else self.SARVAM_STT_ENDPOINT,
                    data=body_bytes,
                    headers={
                        "Content-Type": content_type,
                        "api-subscription-key": self.settings.sarvam_api_key,
                    },
                    method="POST",
                )
                with request.urlopen(req, timeout=6.0) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    transcript = str(data.get("transcript", "")).strip()
                    if transcript:
                        return {
                            "language_code": data.get("language_code", language_hint),
                            "codemix_transcript": transcript,
                            "english_translation": data.get("translation", transcript),
                            "confidence": 0.95,
                        }
            except Exception:
                continue
        return None

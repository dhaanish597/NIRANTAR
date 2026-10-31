"""Minimal, byte-safe text-only updater for ICONIX_RMKSIH26SW127.pptx.

1. Starts from the untouched `ICONIX_RMKSIH26SW127_original_backup.pptx`.
2. Never parses or re-serializes XML with ElementTree — performs exact string replacements only inside
   `<a:t>...</a:t>` tags so 100% of XML namespaces, coordinates, font sizes, colors, runs, layouts,
   and all 44 project images/SVG icons (`image3.png`..`image46.png`, `image8.svg`..`image28.svg`)
   stay byte-for-byte identical to the original file.
3. Cleanly strips the `<p:pic>...</p:pic>` blocks that reference `image1.png` and `image2.png`
   (the Smart India Hackathon 2022/2026 logos) so no SIH logo or box appears on any slide.
"""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import struct
import zlib
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKUP_PATH = REPO_ROOT / "data" / "ppt_visuals" / "ICONIX_RMKSIH26SW127_original_backup.pptx"
OUT_MAIN = REPO_ROOT / "ICONIX_RMKSIH26SW127.pptx"
OUT_COPY = REPO_ROOT / "NIRANTAR_HACKFRONT_INDIA_2026.pptx"


def _make_1x1_white_png() -> bytes:
    def _chunk(chunk_type: bytes, data: bytes) -> bytes:
        crc = zlib.crc32(chunk_type + data) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + chunk_type + data + struct.pack(">I", crc)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)  # 1x1 RGB
    idat = zlib.compress(b"\x00\xff\xff\xff")  # filter 0, RGB(255, 255, 255)
    return b"\x89PNG\r\n\x1a\n" + _chunk(b"IHDR", ihdr) + _chunk(b"IDAT", idat) + _chunk(b"IEND", b"")


WHITE_1X1_PNG = _make_1x1_white_png()


def _strip_sih_logo_pics(xml_str: str, slide_filename: str) -> str:
    # In all 6 slides, rId3 is ../media/image2.png (SIH 2026 top-right logo).
    # In slide1.xml, rId2 is ../media/image1.png (SIH 2022 right logo).
    target_rids = {"rId3"}
    if slide_filename.endswith("slide1.xml"):
        target_rids.add("rId2")

    def _replacer(match: re.Match[str]) -> str:
        block = match.group(0)
        for rid in target_rids:
            if f'r:embed="{rid}"' in block:
                return ""
        return block

    return re.sub(r"<p:pic\b.*?</p:pic>", _replacer, xml_str, flags=re.DOTALL)


SLIDE_TEXT_REPLACEMENTS: dict[str, list[tuple[str, str]]] = {
    "ppt/slides/slide1.xml": [
        ("<a:t>SMART INDIA HACKATHON 2026</a:t>", "<a:t>HACKFRONT INDIA 2026</a:t>"),
        (
            "<a:t>Problem Statement ID      -   SIH26001</a:t>",
            "<a:t>Innovation Track          -   Open Innovation (Neo4j &amp; Sarvam AI)</a:t>",
        ),
        (
            "<a:t>Theme                               -   Disaster Management</a:t>",
            "<a:t>Theme                               -   Disaster Resilience &amp; Deep Tech</a:t>",
        ),
        (
            "<a:t>PS Category                     -   Software</a:t>",
            "<a:t>Category                          -   Software &amp; Autonomous Robotics</a:t>",
        ),
        (
            "<a:t>Team ID                            -   RMKSIH26SW127</a:t>",
            "<a:t>League Phase                  -   Diagnose · Design · Deploy</a:t>",
        ),
        (
            "<a:t>AI-Based Early Warning and  Landslide Risk Monitoring System in NER </a:t>",
            "<a:t>AI &amp; Neo4j GraphRAG Early Warning and Cascade Monitoring System </a:t>",
        ),
    ],
    "ppt/slides/slide2.xml": [
        ("<a:t>@SIH Idea submission- Template</a:t>", "<a:t>hackFront India 2026</a:t>"),
        (
            "<a:t>Build an AI-powered early warning system for landslide-prone NER areas using rainfall, soil moisture and terrain data</a:t>",
            "<a:t>Build an AI and Neo4j GraphRAG early warning system using rainfall, soil moisture, and DEM terrain data</a:t>",
        ),
        (
            "<a:t>monitor vulnerable roads, villages and infrastructure, and support timely alerts and evacuation decisions.</a:t>",
            "<a:t>monitor vulnerable roads, substations, hospitals, and villages for timely Sarvam voice alerts and evacuations.</a:t>",
        ),
        (
            "<a:t>Fuse rainfall, soil moisture and terrain with hyperlocal slope thresholds to estimate landslide risk</a:t>",
            "<a:t>Fuse rainfall, soil moisture, and DEM physics with a 4-layer Neo4j multiplex graph to model hazard risk</a:t>",
        ),
        (
            "<a:t>predict road isolation, route failure and the operational evacuation window</a:t>",
            "<a:t>predict 3-hop infrastructure cascades, road isolation, and hospital backup windows</a:t>",
        ),
        (
            "<a:t>aware risk, action cards and shelter routing.</a:t>",
            "<a:t>aware risk, Sarvam voice alerts, and A* routing.</a:t>",
        ),
        (
            "<a:t>Does not predict road or community isolation.</a:t>",
            "<a:t>Misses 3-hop power, water, and road cascades.</a:t>",
        ),
        (
            "<a:t>Predictive road-isolation intelligence.</a:t>",
            "<a:t>Neo4j 3-hop cascade &amp; road-isolation graph.</a:t>",
        ),
        (
            "<a:t>Dynamic safe-evacuation window</a:t>",
            "<a:t>Dynamic evacuation &amp; ICU backup window.</a:t>",
        ),
        (
            "<a:t>Explainable, confidence-aware AI.</a:t>",
            "<a:t>DEM physics gate + zero-hallucination AI.</a:t>",
        ),
        (
            "<a:t> Action cards + hazard aware shelter routing.</a:t>",
            "<a:t> Sarvam voice cards + A* shelter routing.</a:t>",
        ),
        (
            '<a:t> AI "Emergency Commander" chatbot.</a:t>',
            "<a:t> 4-Agent GraphRAG Copilot + UAV/USV loop.</a:t>",
        ),
    ],
    "ppt/slides/slide3.xml": [
        ("<a:t> • InSAR • Risk Thresholds</a:t>", "<a:t> • Llama 3.1 • GraphRAG Agents</a:t>"),
        ("<a:t>GIS • Runout Modelling • Road Isolation</a:t>", "<a:t>Neo4j GDS • DEM Gate • A* Road Routing</a:t>"),
        ("<a:t>  • PostgreSQL/</a:t>", "<a:t> • Neo4j AuraDB • </a:t>"),
        ("<a:t>SMS • Cell Broadcast • Voice • BLE/Wi-Fi</a:t>", "<a:t>Sarvam STT/TTS • CAP • UAV/USV • BLE</a:t>"),
        ("<a:t> Citizen photo reports</a:t>", "<a:t> Sarvam STT &amp; Vision OCR</a:t>"),
        ("<a:t>   InSAR creep layer</a:t>", "<a:t>   Neo4j 3-hop cascade</a:t>"),
        ("<a:t>   SHAP: why alert fired</a:t>", "<a:t>   4-Agent GraphRAG trace</a:t>"),
        ("<a:t> Multilingual voice</a:t>", "<a:t> Sarvam Bulbul TTS</a:t>"),
    ],
    "ppt/slides/slide4.xml": [
        ("<a:t>, InSAR, DEM)</a:t>", "<a:t>, Neo4j, Sarvam)</a:t>"),
        ("<a:t>Multilingual voice support</a:t>", "<a:t>Sarvam Saaras &amp; Bulbul voice</a:t>"),
        ("<a:t>Prioritised inspections </a:t>", "<a:t>UAV/USV choke-point checks </a:t>"),
    ],
    "ppt/slides/slide5.xml": [
        ("<a:t>@SIH Idea submission- Template</a:t>", "<a:t>hackFront India 2026</a:t>"),
        ("<a:t>Emergency Priority Score </a:t>", "<a:t>3-Hop Cascade &amp; ICU Priority </a:t>"),
        ("<a:t>Rescue resource prioritisation </a:t>", "<a:t>CoE-AWRDS UAV/USV verification </a:t>"),
        ("<a:t>Action-ready recommendations</a:t>", "<a:t>Zero-hallucination GraphRAG cards</a:t>"),
        ("<a:t>Predict vulnerable road segments </a:t>", "<a:t>GDS choke-point &amp; road isolation </a:t>"),
        ("<a:t>Safe Alternate Routing</a:t>", "<a:t>Risk-Budgeted A* Safe Routing</a:t>"),
    ],
    "ppt/slides/slide6.xml": [
        ("<a:t>@SIH Idea submission - Template</a:t>", "<a:t>hackFront India 2026</a:t>"),
        ("<a:t>@SIH Idea submission- Template</a:t>", "<a:t>hackFront India 2026</a:t>"),
    ],
}


def apply_minimal_updates() -> None:
    if not BACKUP_PATH.exists():
        raise FileNotFoundError(f"Original backup not found at {BACKUP_PATH}")

    tmp_out = REPO_ROOT / "data" / "ppt_visuals" / "minimal_clean.pptx"
    with zipfile.ZipFile(BACKUP_PATH, "r") as zin, zipfile.ZipFile(
        tmp_out, "w", compression=zipfile.ZIP_DEFLATED
    ) as zout:
        for item in zin.infolist():
            fname = item.filename
            raw_bytes = zin.read(fname)

            if fname in ("ppt/media/image1.png", "ppt/media/image2.png"):
                zout.writestr(item, WHITE_1X1_PNG)
            elif fname in SLIDE_TEXT_REPLACEMENTS:
                xml_str = raw_bytes.decode("utf-8")
                xml_str = _strip_sih_logo_pics(xml_str, fname)
                for old_str, new_str in SLIDE_TEXT_REPLACEMENTS[fname]:
                    if old_str not in xml_str:
                        raise ValueError(f"Expected tag {old_str!r} not found in {fname}")
                    xml_str = xml_str.replace(old_str, new_str, 1)
                zout.writestr(item, xml_str.encode("utf-8"))
            elif ("slideMaster" in fname or "slideLayout" in fname or "docProps/" in fname) and fname.endswith(".xml"):
                xml_str = raw_bytes.decode("utf-8")
                xml_str = xml_str.replace("@SIH Idea submission- Template", "hackFront India 2026")
                xml_str = xml_str.replace("@SIH Idea submission - Template", "hackFront India 2026")
                xml_str = xml_str.replace("SMART INDIA HACKATHON 2026", "HACKFRONT INDIA 2026")
                xml_str = xml_str.replace("SMART INDIA HACKATHON", "HACKFRONT INDIA")
                zout.writestr(item, xml_str.encode("utf-8"))
            else:
                zout.writestr(item, raw_bytes)

    shutil.copy2(tmp_out, OUT_MAIN)
    shutil.copy2(tmp_out, OUT_COPY)
    tmp_out.unlink(missing_ok=True)
    print(f"Successfully wrote clean minimal PPTX to {OUT_MAIN} and {OUT_COPY}")


if __name__ == "__main__":
    apply_minimal_updates()

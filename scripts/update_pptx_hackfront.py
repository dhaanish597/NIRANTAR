"""Updates ICONIX_RMKSIH26SW127.pptx in place (and writes NIRANTAR_HACKFRONT_INDIA_2026.pptx).

- Preserves the exact 6-slide template, layouts, fonts, colors, and all project images/icons
  (`image3.png`..`image46.png` and `image8.svg`..`image28.svg`).
- Replaces all Smart India Hackathon (SIH) logos (`image1.png`, `image2.png`) and SIH text/footers
  with hackFront India 2026 branding.
- Adds 4 new visual diagrams (`image47.png`..`image50.png`) showcasing the new NIRANTAR 2.0 features
  (Neo4j 4-Layer Multiplex Graph, Neuro-Symbolic 4-Agent Orchestrator, Sovereign Sarvam AI Voice/Vision,
  and IIIT Delhi CoE-AWRDS UAV/USV Robotics + UN SDG 6/11/13 Scorecard).
- Applies strict humanizer rules to all slide copy (plain, concrete engineering prose; zero AI stock words;
  zero em/en dashes; exact metrics from the codebase).
"""
from __future__ import annotations

from pathlib import Path
import shutil
import uuid
import xml.etree.ElementTree as ET
import zipfile


REPO_ROOT = Path(__file__).resolve().parents[1]
PPTX_PATH = REPO_ROOT / "ICONIX_RMKSIH26SW127.pptx"
ALT_PPTX_PATH = REPO_ROOT / "NIRANTAR_HACKFRONT_INDIA_2026.pptx"
VISUALS_DIR = REPO_ROOT / "data" / "ppt_visuals"
BACKUP_PATH = VISUALS_DIR / "ICONIX_RMKSIH26SW127_original_backup.pptx"

P_NS = "http://schemas.openxmlformats.org/presentationml/2006/main"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
REL_PKG_NS = "http://schemas.openxmlformats.org/package/2006/relationships"

ET.register_namespace("p", P_NS)
ET.register_namespace("a", A_NS)
ET.register_namespace("r", R_NS)


def _set_shape_paragraphs(sp: ET.Element, new_paragraphs: list[str]) -> None:
    """Updates paragraph text inside a shape while preserving original `<a:pPr>` and `<a:rPr>` formatting."""
    tx_body = sp.find(f"{{{P_NS}}}txBody")
    if tx_body is None:
        return
    paras = tx_body.findall(f"{{{A_NS}}}p")
    if not paras:
        return

    for idx, p_el in enumerate(paras):
        text_val = new_paragraphs[idx] if idx < len(new_paragraphs) else ""
        runs = p_el.findall(f"{{{A_NS}}}r")
        if runs:
            first_r = runs[0]
            t_el = first_r.find(f"{{{A_NS}}}t")
            if t_el is None:
                t_el = ET.SubElement(first_r, f"{{{A_NS}}}t")
            t_el.text = text_val
            for extra_r in runs[1:]:
                p_el.remove(extra_r)
        elif text_val:
            r_el = ET.SubElement(p_el, f"{{{A_NS}}}r")
            t_el = ET.SubElement(r_el, f"{{{A_NS}}}t")
            t_el.text = text_val


def _set_shape_off_ext(
    sp: ET.Element,
    x: int | None = None,
    y: int | None = None,
    cx: int | None = None,
    cy: int | None = None,
) -> None:
    xfrm = sp.find(f"{{{P_NS}}}spPr/{{{A_NS}}}xfrm")
    if xfrm is None:
        return
    off = xfrm.find(f"{{{A_NS}}}off")
    ext = xfrm.find(f"{{{A_NS}}}ext")
    if off is not None:
        if x is not None:
            off.set("x", str(x))
        if y is not None:
            off.set("y", str(y))
    if ext is not None:
        if cx is not None:
            ext.set("cx", str(cx))
        if cy is not None:
            ext.set("cy", str(cy))


def _append_picture_to_slide(
    slide_root: ET.Element,
    rels_root: ET.Element,
    pic_id: int,
    pic_name: str,
    rel_id: str,
    media_filename: str,
    x: int,
    y: int,
    cx: int,
    cy: int,
) -> None:
    rel_el = ET.SubElement(rels_root, f"{{{REL_PKG_NS}}}Relationship")
    rel_el.set("Id", rel_id)
    rel_el.set("Type", "http://schemas.openxmlformats.org/officeDocument/2006/relationships/image")
    rel_el.set("Target", f"../media/{media_filename}")

    sp_tree = slide_root.find(f"{{{P_NS}}}cSld/{{{P_NS}}}spTree")
    if sp_tree is None:
        return

    pic_xml = f"""
    <p:pic xmlns:p="{P_NS}" xmlns:a="{A_NS}" xmlns:r="{R_NS}">
      <p:nvPicPr>
        <p:cNvPr id="{pic_id}" name="{pic_name}"/>
        <p:cNvPicPr><a:picLocks noChangeAspect="1"/></p:cNvPicPr>
        <p:nvPr/>
      </p:nvPicPr>
      <p:blipFill>
        <a:blip r:embed="{rel_id}"/>
        <a:stretch><a:fillRect/></a:stretch>
      </p:blipFill>
      <p:spPr>
        <a:xfrm>
          <a:off x="{x}" y="{y}"/>
          <a:ext cx="{cx}" cy="{cy}"/>
        </a:xfrm>
        <a:prstGeom prst="rect"><a:avLst/></a:prstGeom>
      </p:spPr>
    </p:pic>
    """
    sp_tree.append(ET.fromstring(pic_xml.strip()))


def _update_slide1(root: ET.Element) -> None:
    updates: dict[str, list[str]] = {
        "4": ["", "NIRANTAR 2.0"],
        "8": ["HACKFRONT INDIA 2026"],
        "10": [
            "Innovation League        -   hackFront India 2026",
            "Project Title            -  ",
            "",
            "Innovation Theme         -   Open Source & Innovation (Open Route)",
            "Technology Tracks        -   Neo4j GraphRAG • Sarvam AI",
            "Knowledge Partner        -   IIIT Delhi CoE-AWRDS (UAV / USV)",
            "Team Name                -   ICONIX",
        ],
        "3": [
            "Multiplex GraphRAG, Sovereign Voice & Robotics Early Warning System ",
            "- NIRANTAR 2.0 (PRAVAH)",
        ],
    }
    for sp in root.findall(f".//{{{P_NS}}}sp"):
        nv = sp.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
        sid = nv.attrib.get("id") if nv is not None else ""
        if sid in updates:
            _set_shape_paragraphs(sp, updates[sid])


def _update_slide2(root: ET.Element, rels_root: ET.Element) -> None:
    updates: dict[str, list[str]] = {
        "4": ["NIRANTAR 2.0 (PRAVAH)"],
        "5": ["Predict the cascade. Verify on the ground. Route people to safety."],
        "11": [
            "Heavy rain and landslides across Indian hills and coastal basins cut roads, flood 33kV substations, and isolate hospitals and villages in minutes. Control rooms receive noisy, code-mixed distress calls and lack a connected view of how one flooded culvert cascades across power, water, and evacuation routes."
        ],
        "12": [
            "Combine rainfall, InSAR terrain creep, and DEM hydrology with a 4-layer Neo4j knowledge graph, a 4-agent GraphRAG copilot, Sarvam AI voice and vision intake, and IIIT Delhi CoE-AWRDS drone/sonar verification to track 3-hop infrastructure cascades, hospital backup clocks, and safe A* evacuation routes."
        ],
        "35": ["@hackFront India 2026 · Where U Elevate"],
        "48": ["PROBLEM & SOLUTION OVERVIEW"],
        "87": [
            "A flooded culvert or tripped 33kV substation cuts hospital power and water within hours.",
            "Regional weather alerts miss slope-level road cuts and single-point-of-failure bridges.",
            "Control rooms get code-mixed Tamil, Malayalam, and Hindi calls that standard ASR mangles.",
            "Panic or spoofed citizen reports can misdirect rescue teams without terrain physics checks.",
            "Cut-off villages need offline BLE/Wi-Fi mesh alerts and local-language voice instructions.",
            "",
        ],
        "89": [
            "Neo4j 4-layer multiplex graph tracks 3-hop cascades and hospital ICU generator fuel clocks.",
            "GDS Tarjan articulation points + Risk-Budgeted A* routing bypass flooded road junctions.",
            "DEM hydrostatic physics gate + [:SUPERSEDES] lineage reject spoofed ridge-top flood claims.",
            "Sarvam Saaras v4 codemix STT, Sarvam Vision shelter OCR, and <250ms Bulbul v4-flash alerts.",
            "4-agent GraphRAG copilot (0% hallucinated IDs) + CoE-AWRDS UAV/USV waypoint dispatch.",
            "",
        ],
    }
    for sp in root.findall(f".//{{{P_NS}}}sp"):
        nv = sp.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
        sid = nv.attrib.get("id") if nv is not None else ""
        if sid in updates:
            _set_shape_paragraphs(sp, updates[sid])

    _append_picture_to_slide(
        root,
        rels_root,
        pic_id=201,
        pic_name="Nirantar2 Multiplex Strip",
        rel_id="rId99",
        media_filename="image47.png",
        x=6150000,
        y=5720000,
        cx=5750000,
        cy=580000,
    )


def _update_slide3(root: ET.Element, rels_root: ET.Element) -> None:
    updates: dict[str, list[str]] = {
        "59": ["IMD • GPM-IMERG • Sentinel-1 • SMAP • SRTM DEM • OSM"],
        "17923": ["XGBoost • NVIDIA NIM (Llama 3.1 70B/8B) • Multi-Agent GraphRAG"],
        "17931": ["GRAPH & GIS"],
        "17935": ["Neo4j AuraDB • GDS Centrality • DEM Gate • A* Routing"],
        "17947": ["FastAPI • Neo4j Cypher/Vector • ", "PostGIS • WebSockets"],
        "17959": ["React 19 • MapLibre GL • Multiplex & Agent Trace UI"],
        "17967": ["VOICE & ROBOTICS"],
        "17971": ["Sarvam Saaras v4 & Bulbul v4 • CoE-AWRDS UAV/USV • BLE"],
        "9": ["    Rainfall IMD · IMERG"],
        "10": [" Sentinel-1 · SMAP · SRTM DEM"],
        "13": ["       Sarvam Saaras v4 & Vision OCR"],
        "20": ["3.HUMAN & ROBOTIC CHECK - DDMA + CoE-AWRDS"],
        "15": ["2 · AI & GRAPH ENGINE"],
        "16": ["XGBoost + DEM ", "Hydrostatic Gate"],
        "17": ["   Neo4j 4-Layer Multiplex Graph"],
        "18": ["      3-Hop Cascade · GDS SPOF ·\nRisk-Budgeted A*"],
        "36": [" SACHET / CAP 1.2 XML"],
        "37": ["  Cell broadcast + SMS"],
        "38": [" Sarvam Bulbul v4 (<250ms)"],
        "25": ["           3-Hop Cascade + P1/P2/P3"],
        "26": ["    Counterfactual What-If"],
        "27": ["   4-Agent Copilot (0% Halluc.)"],
        "28": ["Audit Trail + [:SUPERSEDES]"],
        "29": ["CoE-AWRDS UAV/USV GeoJSON · GSI · IMD · 112"],
        "42": ["6.CITIZEN & FIELD LOOP"],
        "43": ["   Escalation alert\nGreen→Yellow→Orange→Red"],
        "44": ["           Action card + Bulbul v4 local voice"],
        "45": [" Risk-Budgeted A* safe route\noffline maps"],
        "46": ["   Works offline BLE / Wi-Fi Direct mesh"],
        "47": ["           USV Sonar & citizen report to DDMA"],
    }
    for sp in root.findall(f".//{{{P_NS}}}sp"):
        nv = sp.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
        sid = nv.attrib.get("id") if nv is not None else ""
        if sid in updates:
            _set_shape_paragraphs(sp, updates[sid])

    _append_picture_to_slide(
        root,
        rels_root,
        pic_id=301,
        pic_name="NeuroSymbolic Agent Loop Diagram",
        rel_id="rId99",
        media_filename="image48.png",
        x=3964325,
        y=5230000,
        cx=5540000,
        cy=850000,
    )


def _update_slide4(root: ET.Element) -> None:
    updates: dict[str, list[str]] = {
        "27": [
            "Operational Outcome",
            "↓ Cascade blind spots",
            "↑ ICU & shelter survival time",
            "↑ Verified rescue routing",
        ],
        "44": [
            "VALUE PROPOSITION",
            "177 multiplex nodes & 360 edges ",
            "across Chennai, Wayanad & Aizawl ",
            "Early cascade → verified action ",
            "Diagnose → Design → Deploy",
            "",
        ],
        "45": [
            "KEY BENCHMARKS",
            "100% Recall@3 on 3-hop infrastructure cascades",
            "0.00% citation hallucination via set-membership gate",
            "<250ms vernacular voice alerts via Sarvam Bulbul v4",
            "",
        ],
        "46": [
            "Operational Outcome",
            "↓ Cascade blind spots",
            "↑ ICU & shelter survival time",
            "↑ Verified rescue routing",
            "",
        ],
        "47": [
            "CHANNELS & DELIVERY",
            "DEOC Workspace - Multiplex & Trace",
            "Field Robotics - CoE-AWRDS UAV/USV",
            "",
        ],
        "48": [
            "Offline-first - BLE/Wi-Fi mesh maps",
            "Sovereign Voice - Sarvam STT/TTS & CAP",
            "",
        ],
        "49": [
            "DEPLOYMENT ADVANTAGE",
            "Zero-dependency offline fallback",
            "Physics-gated crowd report filtering",
            "Fits DDMA, SDRF & smart-city ops",
        ],
        "2": [
            "COST  STRUCTURE",
            "Satellite & DEM → Open public feeds",
            "Graph & AI → Neo4j AuraDB + 8B/70B NIM",
            "Field Robotics → Targeted SPOF sorties",
            "Integration → CAP 1.2 & Sarvam REST APIs",
            "Maintenance → Auto [:SUPERSEDES] updates",
        ],
        "5": [
            "TECHNICAL FEASIBILITY ",
            "Dual-mode Neo4j AuraDB + local mirror",
            "4-agent GraphRAG + DEM physics gate",
            "Plugs into SACHET CAP 1.2 & Sarvam AI.",
        ],
        "8": [
            " OPERATIONAL FEASIBILITY",
            "Tracks hospital ICU DG backup clocks",
            "Sarvam Vision reads shelter registers",
            "1-click UAV/USV GeoJSON mission orders",
            "Auditable Created→Approved→Ack trail",
        ],
        "17": [
            "SOCIAL & LINGUISTIC FIT",
            "Covers Chennai, Wayanad, Aizawl & Tupul",
            "Saaras v4 handles code-mixed distress calls",
            "Bulbul v4-flash + v3 local voice alerts",
            "Offline-first for cut-off settlements",
            "",
        ],
    }
    for sp in root.findall(f".//{{{P_NS}}}sp"):
        nv = sp.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
        sid = nv.attrib.get("id") if nv is not None else ""
        if sid in updates:
            _set_shape_paragraphs(sp, updates[sid])


def _update_slide5(root: ET.Element, rels_root: ET.Element) -> None:
    updates: dict[str, list[str]] = {
        "5": ["@hackFront India 2026 · Where U Elevate"],
        "3": [
            "LIFE SAFETY & HEALTHCARE (SDG 3 & 11)",
            "Tracks 3-hop substation-to-hospital ICU power cascades (3.19h DG clock)",
            "Protects 608 critical occupants per basin with offline-first alerts",
            "AUTONOMOUS FIELD VERIFICATION (IIIT DELHI CoE-AWRDS)",
            "GDS Tarjan articulation points rank single-point-of-failure culverts",
            "Dispatches UAV thermal & USV sonar 4-waypoint GeoJSON sorties",
            "TRUSTED GRAPHRAG & SOVEREIGN VOICE (SARVAM AI)",
            "Set-membership citation gate blocks 100% of hallucinated node IDs",
            "Saaras v4 codemix STT + <250ms Bulbul v4-flash local voice alerts",
            "CLEAN WATER & CLIMATE RESILIENCE (SDG 6 & 13)",
            "Saves 3,312 potable-water person-hours per urban/hill flood cascade",
            "Delivers +57.5 min cascade lead time & Risk-Budgeted A* routing",
            "",
            "",
        ],
    }
    for sp in root.findall(f".//{{{P_NS}}}sp"):
        nv = sp.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
        sid = nv.attrib.get("id") if nv is not None else ""
        if sid in updates:
            _set_shape_paragraphs(sp, updates[sid])

    _append_picture_to_slide(
        root,
        rels_root,
        pic_id=501,
        pic_name="UN SDG 6 11 13 Scorecard Banner",
        rel_id="rId99",
        media_filename="image49.png",
        x=680000,
        y=5620000,
        cx=6250000,
        cy=660000,
    )


def _update_slide6(root: ET.Element, rels_root: ET.Element) -> None:
    updates: dict[str, list[str]] = {
        "4": ["LIVE PROTOTYPE & RESEARCH REFERENCES"],
        "39": ["@hackFront India 2026 · Where U Elevate"],
        "17": ["@hackFront India 2026 · Where U Elevate"],
        "6": [
            'M. J. S et al., "Evaluating ML Algorithms for Landslide Prediction in Northeast India," Intl. Conf. on Computational Robotics, Testing and Engineering Evaluation (ICCRTEE), 2025.'
        ],
        "8": [
            'S. Anand, M. V. Ramesh et al., "LLM and MCP Enabled AI Agent for Autonomous Multi-Lingual Alerts for Coastal Communities," IEEE, 2025.'
        ],
        "10": [
            'Neo4j Graph Data Science (GDS) & HybridCypherRetriever: Tarjan Articulation Points, Brandes Betweenness Centrality, and 3-Hop Cascade Blast-Radius Traversal, 2026.'
        ],
        "22": [
            'Sarvam AI Sovereign Multimodal Stack: Saaras v4 Codemix Speech-to-Text, Sarvam Vision 3B Shelter Register OCR, and Bulbul v4-flash (<250ms) Vernacular TTS, 2026.'
        ],
        "24": [
            'IIIT Delhi & ISB CoE-AWRDS: Autonomous Aerial (UAV) and Water Surface (USV) Robotics for Flood/Landslide Choke-Point Bathymetry and UN SDG 6, 11, 13 Resilience, 2026.'
        ],
    }

    # Reposition [1]..[5] labels and reference text boxes into the right column below the new NIRANTAR 2.0 UI panel
    label_y = {
        "41": 3480000,
        "42": 4040000,
        "43": 4600000,
        "44": 5160000,
        "45": 5720000,
    }
    ref_y = {
        "6": 3480000,
        "8": 4040000,
        "10": 4600000,
        "22": 5160000,
        "24": 5720000,
    }

    for sp in root.findall(f".//{{{P_NS}}}sp"):
        nv = sp.find(f"{{{P_NS}}}nvSpPr/{{{P_NS}}}cNvPr")
        sid = nv.attrib.get("id") if nv is not None else ""
        if sid in updates:
            _set_shape_paragraphs(sp, updates[sid])
        if sid in label_y:
            _set_shape_off_ext(sp, x=8140000, y=label_y[sid], cx=420000, cy=320000)
        if sid in ref_y:
            _set_shape_off_ext(sp, x=8580000, y=ref_y[sid], cx=3450000, cy=520000)

    _append_picture_to_slide(
        root,
        rels_root,
        pic_id=601,
        pic_name="NIRANTAR 2.0 Multiplex and Agent Trace UI",
        rel_id="rId99",
        media_filename="image50.png",
        x=8140000,
        y=1142371,
        cx=3880000,
        cy=2250000,
    )


def _replace_sih_in_master_and_layouts(raw_xml: bytes) -> bytes:
    text = raw_xml.decode("utf-8")
    text = text.replace("@SIH Idea submission- Template", "@hackFront India 2026 · Where U Elevate")
    text = text.replace("@SIH Idea submission - Template", "@hackFront India 2026 · Where U Elevate")
    text = text.replace("SMART INDIA HACKATHON", "HACKFRONT INDIA")
    return text.encode("utf-8")


def build_updated_presentation() -> None:
    if not BACKUP_PATH.exists():
        shutil.copy2(PPTX_PATH, BACKUP_PATH)

    src_pptx = BACKUP_PATH
    out_tmp = VISUALS_DIR / f"updated_{uuid.uuid4().hex}.pptx"

    with zipfile.ZipFile(src_pptx, "r") as zin:
        slides_xml: dict[str, ET.Element] = {}
        rels_xml: dict[str, ET.Element] = {}
        for i in range(1, 7):
            s_path = f"ppt/slides/slide{i}.xml"
            r_path = f"ppt/slides/_rels/slide{i}.xml.rels"
            slides_xml[s_path] = ET.fromstring(zin.read(s_path))
            rels_xml[r_path] = ET.fromstring(zin.read(r_path))

        _update_slide1(slides_xml["ppt/slides/slide1.xml"])
        _update_slide2(slides_xml["ppt/slides/slide2.xml"], rels_xml["ppt/slides/_rels/slide2.xml.rels"])
        _update_slide3(slides_xml["ppt/slides/slide3.xml"], rels_xml["ppt/slides/_rels/slide3.xml.rels"])
        _update_slide4(slides_xml["ppt/slides/slide4.xml"])
        _update_slide5(slides_xml["ppt/slides/slide5.xml"], rels_xml["ppt/slides/_rels/slide5.xml.rels"])
        _update_slide6(slides_xml["ppt/slides/slide6.xml"], rels_xml["ppt/slides/_rels/slide6.xml.rels"])

        with zipfile.ZipFile(out_tmp, "w", compression=zipfile.ZIP_DEFLATED) as zout:
            for item in zin.infolist():
                fname = item.filename
                if fname == "ppt/media/image1.png":
                    zout.writestr(item, (VISUALS_DIR / "hackfront_card_slide1.png").read_bytes())
                elif fname == "ppt/media/image2.png":
                    zout.writestr(item, (VISUALS_DIR / "hackfront_header_badge.png").read_bytes())
                elif fname in slides_xml:
                    xml_bytes = ET.tostring(slides_xml[fname], encoding="utf-8", xml_declaration=True)
                    zout.writestr(item, xml_bytes)
                elif fname in rels_xml:
                    xml_bytes = ET.tostring(rels_xml[fname], encoding="utf-8", xml_declaration=True)
                    zout.writestr(item, xml_bytes)
                elif ("slideMaster" in fname or "slideLayout" in fname or "docProps/" in fname) and fname.endswith(".xml"):
                    zout.writestr(item, _replace_sih_in_master_and_layouts(zin.read(fname)))
                else:
                    zout.writestr(item, zin.read(fname))

            # Add the 4 new feature visual diagrams into ppt/media/
            zout.writestr("ppt/media/image47.png", (VISUALS_DIR / "visual_slide2_multiplexstrip.png").read_bytes())
            zout.writestr("ppt/media/image48.png", (VISUALS_DIR / "visual_slide3_agentloop.png").read_bytes())
            zout.writestr("ppt/media/image49.png", (VISUALS_DIR / "visual_slide5_sdg_scorecard.png").read_bytes())
            zout.writestr("ppt/media/image50.png", (VISUALS_DIR / "visual_slide6_multiplex_ui.png").read_bytes())

    shutil.copy2(out_tmp, PPTX_PATH)
    shutil.copy2(out_tmp, ALT_PPTX_PATH)
    out_tmp.unlink(missing_ok=True)
    print(f"Updated {PPTX_PATH} and {ALT_PPTX_PATH}")


if __name__ == "__main__":
    build_updated_presentation()

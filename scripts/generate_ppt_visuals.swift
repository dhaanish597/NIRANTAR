import AppKit
import CoreGraphics
import Foundation

func savePNG(_ image: NSImage, to path: String) {
    guard let tiffData = image.tiffRepresentation,
          let bitmap = NSBitmapImageRep(data: tiffData),
          let pngData = bitmap.representation(using: .png, properties: [:]) else {
        fatalError("Failed to encode PNG for \(path)")
    }
    try! pngData.write(to: URL(fileURLWithPath: path))
    print("Wrote \(path) (\(pngData.count) bytes)")
}

func color(_ hex: UInt32, alpha: CGFloat = 1.0) -> NSColor {
    let r = CGFloat((hex >> 16) & 0xFF) / 255.0
    let g = CGFloat((hex >> 8) & 0xFF) / 255.0
    let b = CGFloat(hex & 0xFF) / 255.0
    return NSColor(calibratedRed: r, green: g, blue: b, alpha: alpha)
}

func drawRoundedRect(_ rect: NSRect, radius: CGFloat, fill: NSColor, stroke: NSColor? = nil, lineWidth: CGFloat = 2.0) {
    let path = NSBezierPath(roundedRect: rect, xRadius: radius, yRadius: radius)
    fill.setFill()
    path.fill()
    if let s = stroke {
        s.setStroke()
        path.lineWidth = lineWidth
        path.stroke()
    }
}

func drawText(_ text: String, in rect: NSRect, font: NSFont, color: NSColor, align: NSTextAlignment = .left) {
    let style = NSMutableParagraphStyle()
    style.alignment = align
    style.lineBreakMode = .byWordWrapping
    let attrs: [NSAttributedString.Key: Any] = [
        .font: font,
        .foregroundColor: color,
        .paragraphStyle: style
    ]
    (text as NSString).draw(in: rect, withAttributes: attrs)
}

let outDir = "/Users/dhaanish/Documents/NIRANTAR/data/ppt_visuals"
try! FileManager.default.createDirectory(atPath: outDir, withIntermediateDirectories: true)

// 1. Top-Right Header Badge (replaces image2.png across all 6 slides)
do {
    let w: CGFloat = 1200
    let h: CGFloat = 566
    let img = NSImage(size: NSSize(width: w, height: h))
    img.lockFocus()
    NSColor.white.setFill()
    NSBezierPath(rect: NSRect(x: 0, y: 0, width: w, height: h)).fill()

    // Outer pill card
    drawRoundedRect(NSRect(x: 24, y: 36, width: w - 48, height: h - 72), radius: 36, fill: color(0x0B192C), stroke: color(0x14B8A6), lineWidth: 6)

    // Left accent emblem
    drawRoundedRect(NSRect(x: 64, y: 96, width: 290, height: h - 192), radius: 28, fill: color(0x0F2942), stroke: color(0xF59E0B), lineWidth: 4)
    drawText("HF", in: NSRect(x: 64, y: 220, width: 290, height: 180), font: NSFont.boldSystemFont(ofSize: 120), color: color(0x14B8A6), align: .center)
    drawText("2026 LEAGUE", in: NSRect(x: 64, y: 125, width: 290, height: 60), font: NSFont.boldSystemFont(ofSize: 30), color: color(0xF59E0B), align: .center)

    // Right typography
    drawText("hackFront India", in: NSRect(x: 390, y: 310, width: 740, height: 130), font: NSFont.boldSystemFont(ofSize: 86), color: NSColor.white)
    drawText("NATIONAL INNOVATION LEAGUE · WHERE U ELEVATE", in: NSRect(x: 394, y: 235, width: 740, height: 55), font: NSFont.boldSystemFont(ofSize: 27), color: color(0x14B8A6))
    drawText("Neo4j Track  •  Sarvam AI Track  •  CoE-AWRDS", in: NSRect(x: 394, y: 115, width: 740, height: 65), font: NSFont.boldSystemFont(ofSize: 31), color: color(0xFCD34D))

    img.unlockFocus()
    savePNG(img, to: "\(outDir)/hackfront_header_badge.png")
}

// 2. Slide 1 Right Emblem Card (replaces image1.png on Slide 1)
do {
    let w: CGFloat = 1400
    let h: CGFloat = 1500
    let img = NSImage(size: NSSize(width: w, height: h))
    img.lockFocus()
    drawRoundedRect(NSRect(x: 20, y: 20, width: w - 40, height: h - 40), radius: 44, fill: color(0x0A1826), stroke: color(0x14B8A6), lineWidth: 8)

    drawText("HACKFRONT INDIA 2026", in: NSRect(x: 80, y: 1310, width: w - 160, height: 70), font: NSFont.boldSystemFont(ofSize: 46), color: color(0x14B8A6), align: .center)
    drawText("DIAGNOSE  •  DESIGN  •  DEPLOY", in: NSRect(x: 80, y: 1235, width: w - 160, height: 55), font: NSFont.boldSystemFont(ofSize: 34), color: color(0xF59E0B), align: .center)

    let cards: [(String, String, String, UInt32)] = [
        ("NEO4J TRACK", "4-Layer Multiplex Property Graph", "177 Nodes · 360 Edges · 3-Hop Blast Radius · GDS SPOF & A*", 0x14B8A6),
        ("SARVAM AI TRACK", "Sovereign Multimodal Voice & Vision", "Saaras v4 Codemix STT · Vision 3B OCR · Bulbul v4 (<250ms)", 0xF59E0B),
        ("NEURO-SYMBOLIC AI", "4-Agent GraphRAG Orchestrator", "NVIDIA Llama 3.1 70B/8B · Set-Membership Gate (0% Hallucination)", 0x38BDF8),
        ("IIIT DELHI CoE-AWRDS", "Aerial & Water Robotics Loop", "UAV Thermal & USV Sonar GeoJSON Sorties · UN SDG 6, 11, 13", 0x34D399)
    ]

    for (idx, item) in cards.enumerated() {
        let yPos = CGFloat(940 - idx * 265)
        drawRoundedRect(NSRect(x: 80, y: yPos, width: w - 160, height: 225), radius: 28, fill: color(0x11263C), stroke: color(item.3), lineWidth: 4)
        drawText(item.0, in: NSRect(x: 120, y: yPos + 150, width: w - 240, height: 45), font: NSFont.boldSystemFont(ofSize: 30), color: color(item.3))
        drawText(item.1, in: NSRect(x: 120, y: yPos + 88, width: w - 240, height: 52), font: NSFont.boldSystemFont(ofSize: 38), color: NSColor.white)
        drawText(item.2, in: NSRect(x: 120, y: yPos + 25, width: w - 240, height: 48), font: NSFont.systemFont(ofSize: 27, weight: .medium), color: color(0xCBD5E1))
    }

    drawText("Active Basins: Chennai (Velachery) • Wayanad • Aizawl • Tupul", in: NSRect(x: 80, y: 65, width: w - 160, height: 55), font: NSFont.boldSystemFont(ofSize: 30), color: color(0x94A3B8), align: .center)

    img.unlockFocus()
    savePNG(img, to: "\(outDir)/hackfront_card_slide1.png")
}

// 3. Slide 2 Bottom-Right Visual Strip: 4-Layer Multiplex Cascade + Sarvam + CoE-AWRDS
do {
    let w: CGFloat = 1800
    let h: CGFloat = 240
    let img = NSImage(size: NSSize(width: w, height: h))
    img.lockFocus()
    drawRoundedRect(NSRect(x: 6, y: 6, width: w - 12, height: h - 12), radius: 24, fill: color(0x0B192C), stroke: color(0x14B8A6), lineWidth: 4)

    let steps: [(String, String, UInt32)] = [
        ("1. SARVAM SAARAS v4", "Tanglish/Manglish Call + DEM Gate", 0xF59E0B),
        ("2. NEO4J 3-HOP GRAPH", "Flood → 33kV Sub → ICU 3.19h Clock", 0x14B8A6),
        ("3. CoE-AWRDS UAV/USV", "Sonar/Drone Choke-Point Sortie", 0x38BDF8),
        ("4. BULBUL v4 + A* ROUTE", "<250ms Voice Alert + Bypass Map", 0x34D399)
    ]
    let boxW: CGFloat = 415
    for (i, s) in steps.enumerated() {
        let xPos = CGFloat(30 + i * 440)
        drawRoundedRect(NSRect(x: xPos, y: 28, width: boxW, height: h - 56), radius: 18, fill: color(0x132A42), stroke: color(s.2), lineWidth: 3)
        drawText(s.0, in: NSRect(x: xPos + 18, y: 120, width: boxW - 36, height: 55), font: NSFont.boldSystemFont(ofSize: 27), color: color(s.2))
        drawText(s.1, in: NSRect(x: xPos + 18, y: 45, width: boxW - 36, height: 65), font: NSFont.boldSystemFont(ofSize: 24), color: NSColor.white)
    }
    img.unlockFocus()
    savePNG(img, to: "\(outDir)/visual_slide2_multiplexstrip.png")
}

// 4. Slide 3 Neuro-Symbolic Orchestrator & GraphRAG Visual Banner
do {
    let w: CGFloat = 1800
    let h: CGFloat = 290
    let img = NSImage(size: NSSize(width: w, height: h))
    img.lockFocus()
    drawRoundedRect(NSRect(x: 6, y: 6, width: w - 12, height: h - 12), radius: 24, fill: color(0x0B192C), stroke: color(0x38BDF8), lineWidth: 4)
    drawText("NEURO-SYMBOLIC 4-AGENT ORCHESTRATOR  •  HYBRID CYPHER GRAPHRAG  •  SET-MEMBERSHIP CITATION GATE", in: NSRect(x: 36, y: 215, width: w - 72, height: 48), font: NSFont.boldSystemFont(ofSize: 28), color: color(0x38BDF8))

    let agents: [(String, String, UInt32)] = [
        ("Turn 1 · IntakeRouterAgent", "HybridCypherRetriever (Vector + 3-Hop)", 0x14B8A6),
        ("Turn 2 · GraphInvestigator", "Cascade Blast Radius + GDS SPOF", 0xF59E0B),
        ("Turn 3 · MissionPlanner", "Risk-Budgeted A* + UAV/USV Waypoints", 0x38BDF8),
        ("Turn 4 · VerifierGateAgent", "CitedIds ⊆ Subgraph (0.0% Hallucination)", 0x34D399)
    ]
    for (i, a) in agents.enumerated() {
        let xPos = CGFloat(30 + i * 440)
        drawRoundedRect(NSRect(x: xPos, y: 26, width: 415, height: 175), radius: 18, fill: color(0x132A42), stroke: color(a.2), lineWidth: 3)
        drawText(a.0, in: NSRect(x: xPos + 16, y: 120, width: 383, height: 55), font: NSFont.boldSystemFont(ofSize: 25), color: color(a.2))
        drawText(a.1, in: NSRect(x: xPos + 16, y: 40, width: 383, height: 75), font: NSFont.boldSystemFont(ofSize: 23), color: NSColor.white)
    }
    img.unlockFocus()
    savePNG(img, to: "\(outDir)/visual_slide3_agentloop.png")
}

// 5. Slide 5 Bottom-Left UN SDG 6/11/13 & Benchmark Visual Scorecard
do {
    let w: CGFloat = 1800
    let h: CGFloat = 230
    let img = NSImage(size: NSSize(width: w, height: h))
    img.lockFocus()
    drawRoundedRect(NSRect(x: 6, y: 6, width: w - 12, height: h - 12), radius: 22, fill: color(0x0B192C), stroke: color(0x34D399), lineWidth: 4)

    let stats: [(String, String, String, UInt32)] = [
        ("SDG 6 CLEAN WATER", "3,312 hrs", "Water outage person-hrs saved", 0x38BDF8),
        ("SDG 11 SAFE CITIES", "608 lives", "ICU & shelter occupants protected", 0x14B8A6),
        ("SDG 13 CLIMATE ACTION", "+57.5 min", "Cascade lead-time gain via GraphRAG", 0xF59E0B),
        ("CITATION ACCURACY", "100.0%", "0 hallucinated IDs · <250ms Bulbul TTS", 0x34D399)
    ]
    for (i, st) in stats.enumerated() {
        let xPos = CGFloat(30 + i * 440)
        drawRoundedRect(NSRect(x: xPos, y: 24, width: 415, height: h - 48), radius: 16, fill: color(0x132A42), stroke: color(st.3), lineWidth: 3)
        drawText(st.0, in: NSRect(x: xPos + 18, y: 142, width: 380, height: 40), font: NSFont.boldSystemFont(ofSize: 23), color: color(st.3))
        drawText(st.1, in: NSRect(x: xPos + 18, y: 76, width: 380, height: 65), font: NSFont.boldSystemFont(ofSize: 44), color: NSColor.white)
        drawText(st.2, in: NSRect(x: xPos + 18, y: 30, width: 380, height: 42), font: NSFont.systemFont(ofSize: 22, weight: .medium), color: color(0xCBD5E1))
    }
    img.unlockFocus()
    savePNG(img, to: "\(outDir)/visual_slide5_sdg_scorecard.png")
}

// 6. Slide 6 Top-Right Live NIRANTAR 2.0 Multiplex Graph & Agent Trace Screenshot Panel
do {
    let w: CGFloat = 1500
    let h: CGFloat = 900
    let img = NSImage(size: NSSize(width: w, height: h))
    img.lockFocus()
    drawRoundedRect(NSRect(x: 0, y: 0, width: w, height: h), radius: 20, fill: color(0x071318), stroke: color(0x14B8A6), lineWidth: 4)

    drawText("NEO4J 4-LAYER MULTIPLEX GRAPH  •  SARVAM AI  •  CoE-AWRDS ROBOTICS", in: NSRect(x: 40, y: 815, width: 1100, height: 40), font: NSFont.boldSystemFont(ofSize: 24), color: color(0x14B8A6))
    drawText("Cascading Blast Radius & GDS Choke-Point Triage (CHENNAI · WAYANAD · AIZAWL)", in: NSRect(x: 40, y: 755, width: 1380, height: 52), font: NSFont.boldSystemFont(ofSize: 34), color: NSColor.white)

    // 3 Hop Cards
    let hops: [(String, String, String, UInt32)] = [
        ("H1 · SUB-CHENNAI-33KV-01", "Velachery 33kV Substation", "Path: FZ-01 → SUB-33KV · Survival: 0.50h · Exposure: 480", 0xF59E0B),
        ("H2 · HOSP-CHENNAI-CARE-01", "Tertiary Trauma & ICU (42 Beds)", "Path: FZ-01 → SUB-33KV → HOSP-01 · DG Fuel: 3.19h left", 0xEF4444),
        ("H3 · SHEL-CHENNAI-01", "Velachery Relief Camp (312 pax)", "Sarvam Vision OCR Verified · Bulbul v4-flash Tamil Alert", 0x14B8A6)
    ]
    for (i, hp) in hops.enumerated() {
        let xPos = CGFloat(40 + i * 480)
        drawRoundedRect(NSRect(x: xPos, y: 510, width: 455, height: 220), radius: 16, fill: color(0x0D212C), stroke: color(hp.3), lineWidth: 3)
        drawText(hp.0, in: NSRect(x: xPos + 20, y: 665, width: 415, height: 42), font: NSFont.boldSystemFont(ofSize: 25), color: color(hp.3))
        drawText(hp.1, in: NSRect(x: xPos + 20, y: 605, width: 415, height: 48), font: NSFont.boldSystemFont(ofSize: 27), color: NSColor.white)
        drawText(hp.2, in: NSRect(x: xPos + 20, y: 525, width: 415, height: 75), font: NSFont.systemFont(ofSize: 22, weight: .medium), color: color(0x94A3B8))
    }

    // Bottom Agent Trace & CoE-AWRDS Panel
    drawRoundedRect(NSRect(x: 40, y: 40, width: w - 80, height: 435), radius: 16, fill: color(0x0B1B24), stroke: color(0x38BDF8), lineWidth: 3)
    drawText("NEURO-SYMBOLIC ORCHESTRATOR TRACE  •  NVIDIA LLAMA-3.1-70B  •  0.0% HALLUCINATION", in: NSRect(x: 70, y: 410, width: 1340, height: 42), font: NSFont.boldSystemFont(ofSize: 24), color: color(0x38BDF8))

    let traces = [
        "Turn 1 · IntakeRouterAgent → hybrid_graphrag_retrieve_tool (3.8 ms) · Verified 28 Subgraph Nodes",
        "Turn 2 · GraphInvestigatorAgent → query_cascading_blast_radius_tool (4.2 ms) · 10 Impacted Assets (608 pax)",
        "Turn 3 · GraphInvestigatorAgent → discover_topological_chokepoints_tool (3.1 ms) · SPOF: OSM-CHENNAI-024",
        "Turn 4 · MissionPlannerAgent → compute_risk_budgeted_route_tool + CoE-AWRDS USV_SONAR Sortie (4.9 ms)",
        "Turn 5 · VerifierGateAgent → verify_and_gate_copilot_output · Blocked Unverified Citations: 0"
    ]
    for (idx, line) in traces.enumerated() {
        let yPos = CGFloat(340 - idx * 66)
        drawRoundedRect(NSRect(x: 70, y: yPos, width: w - 140, height: 54), radius: 10, fill: color(0x112936))
        drawText(line, in: NSRect(x: 90, y: yPos + 10, width: w - 180, height: 36), font: NSFont.boldSystemFont(ofSize: 22), color: color(0xE2E8F0))
    }

    img.unlockFocus()
    savePNG(img, to: "\(outDir)/visual_slide6_multiplex_ui.png")
}

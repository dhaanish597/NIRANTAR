# SIH26001 — Technical Architecture Reference
### AI-Based Early Warning & Landslide Risk Monitoring System (NER) — for diagram generation

Consolidated from all six project files. Organized by architectural layer, top (data) to bottom (dissemination/audit), so each section maps to a box/swimlane in a diagram.

---

## 0. End-to-End Pipeline (top-level flow)

```
Data Ingestion (IMD + NASA SMAP + Sentinel-1 InSAR + DEM + OSM + GSI/NESAC/Bhuvan inventories)
        │
        ▼
AI Risk Engine (LHASA-style XGBoost + Hyperlocal Rainfall Thresholds)
        │
        ▼
   Failure Probability (per slope unit, 0–1)
        │
        ▼
   Impact & Network Analysis
        ├── Landslide Runout Impact Zone
        ├── Road Blockage / Bridge Failure Risk
        └── Village Isolation Index (RII)
        │
        ▼
   Evacuation Priority Engine (EPS → P1/P2/P3 tiers)
        │
        ▼
   Dynamic Risk-Aware Routing Engine (edge-cost recalculation)
        │
        ▼
   Actionable Village Action Card (multilingual, voice)
        │
        ▼
   Resilient Dissemination Pipeline (SACHET/CAP, Cell Broadcast, offline PWA, BLE mesh)
        │
        ▼
   Timestamped DDMA Acknowledgement / Audit Trail
```

An alternate framing (from the evacuation-solutions research) adds a tracking loop after dissemination:

```
Hazard intelligence → risk score → impact assessment → road-isolation prediction →
evacuation window → safe-route computation → shelter selection → human-approved action →
multilingual/offline dissemination → evacuation tracking → post-event accountability
```

---

## 1. Data Sources / Ingestion Layer

| Source | Data provided | Access |
|---|---|---|
| IMD API (api.imd.gov.in) | District nowcast, rainfall, warnings, highway nowcast | Public, IP-whitelisting friction |
| NASA GPM/IMERG | Real-time + antecedent rainfall | NASA Earthdata login, free |
| NASA SMAP / ESA CCI / ERA5 (Copernicus CDS) | Satellite-derived surface soil moisture (software-only sensor substitute) | Earthdata / Copernicus CDS, free |
| Copernicus Sentinel-1 (C-band SAR) | InSAR deformation input | Copernicus Data Space, free |
| Copernicus Sentinel-2 (optical) | Land cover, change detection, InSAR-optical fusion | Free |
| DEM (CartoDEM, SRTM 30m, ALOS PALSAR 12.5m, NASADEM, Copernicus DEM 30m) | Slope, curvature, terrain geometry | OpenTopography / Survey of India |
| GSI Bhukosh / NLSM | 1:50,000 static susceptibility maps, 91,000-event inventory (33,904 field-validated) | Registration |
| NESAC NERDRR / Bhuvan / NDEM | Regional hazard zonation, historical landslide atlas (~80,000 events) | Registration |
| OpenStreetMap (OSM) | NER road network graph (nodes = villages/intersections, edges = road segments) | ODbL, attribution required |
| Shelter/critical-infrastructure layers | Hospitals, schools, shelters, bridges (from ASDMA-style state GIS) | State GIS / manual curation |
| Citizen crowdsourced reports | Geotagged crack/road-blockage photos & video | In-app upload (PS clause e) |
| Google Earth Engine | Bulk processing platform for S1/S2/DEM at scale | Free for research |

**Software-only workaround (core constraint of the "Software" category):** no physical soil-moisture or pore-pressure sensors are deployed. SMAP/ESA-CCI surface soil moisture + IMERG antecedent rainfall is used as the mathematical surrogate for subsurface wetness — the same substitution NASA's operational LHASA v2 uses.

---

## 2. AI / ML Processing Layer

### 2.1 Core probabilistic risk engine
- **Architecture:** XGBoost classifier, modeled on **NASA LHASA v2** (open source, GSC-18595-1), 1 km grid.
- **Inputs:** slope, distance-to-faults, lithologic strength, current + antecedent IMERG rainfall, SMAP soil moisture, snow mass (where relevant).
- **Output:** probabilistic nowcast per discrete slope unit (not binary), allowing false-positive/false-negative threshold tuning.
- **Fusion:** combined with hyperlocal, per-slope rainfall threshold formulas (see §2.2) rather than static district-level thresholds.
- **Reference benchmark:** LHASA v2 was reported (Stanley et al., 2021) as twice as likely to predict historical landslide occurrence as LHASA v1 at the same false-positive rate.

### 2.2 Region-specific rainfall threshold formulas (NE Himalaya)
- **Intensity–Duration (I-D) threshold:**
  `I = 5.8294 × D^(−0.4141)`
  where I = rainfall intensity (mm/h), D = rainfall duration (hours).
- **Event/Moisture–Duration (E-D) threshold:**
  `E = −11.10 + 0.62 × D`
  where E = cumulative event rainfall (mm), valid for 24 ≤ D ≤ 1440 hours.
- **Sikkim (Lanta Khola / N-Sikkim Highway):** slide risk when normalized cumulative rainfall > 250 mm over 15 days.
- **Kalimpong (Darjeeling):** a 48-hr cumulative of ~36.7 mm can trigger.
- **Shimla (NW Himalaya, contrast case):** `I = 7.20 × D^(−0.26)`, ~110 mm/30-day antecedent.

### 2.3 Static susceptibility modeling
- Logistic regression, frequency ratio, weights-of-evidence, Random Forest, XGBoost, SVM, ANN.
- AHP/MCDA for data-scarce districts (Darjeeling AHP benchmark: ROC-AUC 96.8%, success rate 81.3%).

### 2.4 Event detection / scar segmentation (post-event + inventory update)
- **Architecture:** CNN-based segmentation — U-Net, ResU-Net, DeepLab, U-Net++.
- **Benchmark dataset:** Landslide4Sense (3,799–4,884 patches; 14 bands = 12 Sentinel-2 bands + ALOS slope + DEM).
- **Baseline performance:** ResU-Net F1 ≈ 0.73 (official benchmark); newer variants (RMAU-Net, ASK-UNet++, LandslideSegNet) report higher F1/mIoU.
- **Known issue:** extreme class imbalance (~2–2.5% landslide pixels) → requires weighted cross-entropy (e.g., 1:4) or focal loss.
- Note: NESAC-affiliated research reports 92.36% accuracy for automated scar detection — this is *isolated post-event detection*, not operational early-warning accuracy; keep these separate in any diagram/labeling.

### 2.5 Temporal / sequence models
- LSTM / GRU / Temporal Fusion Transformer for rainfall and InSAR displacement time series.
- Multi-task DL optimized for accuracy *near the warning threshold* rather than overall residual minimization.

### 2.6 Advanced / future-scope models
- Graph Neural Networks (GNN) for spatial dependency between adjacent slope units.
- Physics-informed neural networks coupling infinite-slope stability equations with ML.
- Transfer learning / EO foundation models for data-scarce NER districts: Prithvi-100M (NASA/IBM), Clay, SatMAE, Presto.

### 2.7 Trust / explainability layer
- **SHAP** (SHapley Additive exPlanations) attribution — shows % contribution of antecedent rain, soil saturation, slope aspect, SAR displacement to each risk score.
- **Spatial cross-validation** (never random split — inflates AUC in spatially autocorrelated data).
- Report AUC-ROC alongside real-world false-alarm cost, not accuracy alone.

---

## 3. InSAR Deformation Sub-Layer (flagship differentiator)

- **Source:** Sentinel-1 C-band SAR, free, 6–12 day revisit.
- **Methods:** Persistent Scatterer Interferometry (PSI), Small Baseline Subset (SBAS), Distributed Scatterer interferometry (e.g., SqueeSAR) — DS methods needed because dense NER vegetation causes PS-point decorrelation.
- **Mitigation for vegetation decorrelation:** DS interferometry + Sentinel-1/2 optical feature-tracking fusion.
- **Explicit scope limitation:** detects mm-scale annual precursory creep on **slow-moving, deep-seated** slopes only — does **not** catch sudden shallow rainfall-triggered debris flows (which are the majority of NER fatal events and are instead covered by the rainfall-threshold engine).
- **Evidence anchor:** Irshalwadi showed ~12 mm/yr precursory creep pre-failure; South Lhonak moraine showed >15 m/yr displacement 2016–2023 pre-collapse — both undetected operationally at the time.

---

## 4. Impact & Network Analysis Layer

### 4.1 Landslide runout modeling
- DEM geometry + empirical volume–runout relationships → predicted debris travel distance/impact envelope downslope.
- Flags structures/roads intersecting the runout path.

### 4.2 Road Network Isolation Index (RII)
- **Graph model:** OSM road network represented as dynamic weighted graph `G = (V, E)`; V = intersections/villages, E = road segments.
- **Dynamic edge cost:**
  `C_edge = L_edge × (1 + α·P_landslide + β·S_slope)`
  where `L_edge` = physical road segment length, `P_landslide ∈ [0,1]` = AI-predicted failure probability of the adjacent slope, `S_slope` = terrain steepness, `α, β` = scaling constants.
- **Edge severance rule:** if `P_landslide` exceeds a critical threshold, the edge is dynamically removed from the routable graph.
- Computes topological graph connectivity to identify villages at risk of isolation and estimates expected isolation duration based on road hierarchy and alternate-path availability.

---

## 5. Evacuation Priority Engine (EPE)

- **Evacuation Priority Score (EPS):**
  `EPS = w1·P_landslide + w2·E_pop + w3·RII + w4·(1 − A_shelter)`
  where `E_pop` = population exposure, `RII` = isolation index (from §4.2), `A_shelter ∈ [0,1]` = safe shelter accessibility, `w1–w4` = normalized weight coefficients.
- **Output tiers:** P1 (Immediate Mandatory Evacuation) / P2 (Evacuation Ready) / P3 (Watch Status).
- Purpose: lets DDMAs allocate limited rescue resources across multiple simultaneously-affected settlements.

---

## 6. Dynamic Risk-Aware Routing Engine

- Recalculates routing-graph edge weights in real time using §4.2's `C_edge` formula.
- Segments intersecting a predicted runout envelope get heavy cost penalties or are treated as fully blocked (infinite cost).
- Distinguishing feature vs. plain shortest-path/OSMnx-Dijkstra/A* routers (used in reference open-source projects like AI Disaster Evacuation Planner, SafeRoute AI): routes are **predictive** — a segment currently open but likely to fail before evacuees arrive is avoided, not just currently-hazardous segments.
- Related open-source reference patterns worth citing as prior art (not to be copied as USPs): FireABM, EMBER, AgentEvac, PyroRL (agent-based / RL evacuation simulation, mostly wildfire-domain).

---

## 7. Decision Support / Output Generation Layer

- **Village Action Cards:** plain-language instructions — where to go, which road to avoid, nearest shelter, what to do now.
- **Multi-Stage Operational Risk Escalation Cards:** Green Watch → Yellow Pre-Alert → Orange Evacuation Ready → Red Evacuate Immediately (replaces static High/Medium/Low heatmaps).
- **Multilingual voice synthesis:** AI4Bharat Bhashini + IndicTrans2 (translation, 22 languages incl. Meitei script) + Indic-Parler-TTS / Indic-TTS (voice) — target languages: Assamese, Bodo, Khasi, Garo, Mizo, Meitei (Manipuri), Nagamese, Nepali.
- **AI Emergency Commander / "What-If" Simulator:** lets DDMA officials adjust rainfall-intensity sliders (e.g., simulate 250 mm/12h) to model future failure distribution, road severance, and isolation cascades — explicitly **human-in-the-loop decision support**, not autonomous evacuation authority.
- **Explainable risk score + false-alarm-cost tuning slider:** SHAP attribution shown per alert; interactive threshold slider lets officials balance false-positive vs. false-negative operational cost.
- **Time-to-critical-risk estimation:** for slow-moving slopes (InSAR trendline + cumulative rainfall saturation curve) — framed as an "estimated safe evacuation window," not an exact time-of-failure claim.

---

## 8. Dissemination Layer (last-mile / offline-first)

- **Primary integration (not rebuild):** NDMA SACHET, built on Common Alerting Protocol (CAP v1.2); interfaces with C-DOT Cell Broadcast, telecom SMS gateways, mobile app, browser, RSS, TV/radio.
- **Cell Broadcast:** operates via control channel, requires no cellular data connection — critical for zero-signal valleys.
- **Offline-first PWA:** built on MapLibre vector tiles + GeoPackage local storage for full map/route caching without connectivity.
- **Phone-to-phone mesh:** Bluetooth Low Energy (BLE) and Wi-Fi Direct store-and-forward propagation between devices in zero-connectivity zones.
- **SMS gateway:** requires TRAI DLT registration.
- **Connectivity context driving this layer's necessity:** ~1,841 of 45,934 NER villages have no mobile coverage at all; ~2,847 lack 4G (state breakdown: Manipur 189 uncovered, Meghalaya 141, Nagaland 107, Mizoram 52, Assam 163, Tripura 7, Sikkim 6).

---

## 9. Governance / Audit Trail Layer

- **Timestamped chain of custody per alert:**
  `Alert Created (AI flag) → Approved by DDMA (officer) → Disseminated (dispatch) → Village Handset Acknowledged (delivery %)`
- **Fields tracked per alert record:** Alert ID, source data provenance, model confidence, approving officer, delivery status, acknowledgement status, action taken, post-event review outcome.
- Directly addresses the "who presses the button" accountability gap (the documented Wayanad 2024 failure mode — a warning existed ~16 hrs ahead but was not acted on).

---

## 10. Crowdsourcing / Field Reporting Layer

- Citizens and field officials upload geotagged photos/videos of cracks, slope movement, or blocked roads (PS clause e).
- **On-device computer-vision quality filter** suppresses spam/duplicate/low-quality submissions before they reach the DDMA queue, so crowdsourced input is trusted ground truth rather than noise.
- Feeds back into inventory updates and post-event threshold retraining.

---

## 11. External System Integration Layer (integrate, do not replace)

| System | Role in architecture | Integration point |
|---|---|---|
| GSI Bhusanket / Bhooskhalan / NLFC | Regional rainfall-threshold bulletins, 1:10K susceptibility, crowdsourced inventory | Upstream data input to Risk Engine; also a peer bulletin to cross-reference |
| NESAC NERDRR / FLEWS | NER-focused remote sensing, hazard zonation, experimental EWS (flood-mature, landslide-nascent) | Upstream regional hazard layer; potential regional hosting/integration partner |
| ISRO / NRSC Bhuvan, NDEM | National landslide atlas, GIS visualization, 72-hr corridor forecasts, national disaster GIS/decision-support (risk-zone ID, shelter ID, route planning) | Upstream inventory + baseline GIS decision-support layer |
| IMD API | District rainfall/nowcast/warnings, highway nowcast | Upstream meteorological input |
| NDMA SACHET / CAP 1.2 / C-DOT Cell Broadcast | National alert dissemination pipe (134+ billion SMS sent, 19+ languages, all 36 states/UTs) | Downstream dissemination channel (§8) |
| Amrita A-LEWS (and similar state/IIT sensor networks) | Hyper-local physical WSN (pore-pressure, tilt, strain, moisture sensors) on instrumented slopes | Optional — via a **sensor-agnostic ingestion REST API** (P2 scale-up), not required for MVP |
| ERSS-112 | National emergency response/dispatch backbone (GIS location, vehicle tracking, geo-fencing, routing) | Downstream response-coordination integration, not core to MVP |
| ASDMA / state DM GIS (Mizoram, Nagaland, Assam) | State-level critical-infrastructure and shelter layers | Upstream shelter/infrastructure data source |

---

## 12. Technology Stack

| Component | Technology |
|---|---|
| ML / modeling | Python — XGBoost, PyTorch, TensorFlow |
| EO / satellite processing | Google Earth Engine Python API |
| Geospatial database & serving | PostGIS + GeoServer (OGC WMS/WFS/WMTS standards) |
| Backend API | FastAPI |
| Frontend | React Progressive Web App (PWA) |
| Mapping / offline tiles | MapLibre vector tiles, GeoPackage local storage |
| Edge inference (mobile) | TensorFlow Lite / ONNX, running on low-cost Android devices |
| Road-graph routing | OSM-based graph (OSMnx/NetworkX-style), Dijkstra/A*-derived dynamic-cost routing |
| Multilingual NLP/voice | AI4Bharat Bhashini, IndicTrans2 (translation), Indic-Parler-TTS / Indic-TTS (speech) |
| Alert dissemination | SACHET CAP v1.2, C-DOT Cell Broadcast, SMS gateway (TRAI DLT) |
| Offline mesh | Bluetooth Low Energy (BLE), Wi-Fi Direct |
| Cloud | Cloud backend with offline-sync support for remote regions |

---

## 13. Datasets Reference

- GSI Bhukosh inventory — 91,000 landslide events (33,904 field-validated)
- NASA Global Landslide Catalog (GLC) / COOLR — LHASA validation inventories
- Landslide4Sense — segmentation benchmark (Iburi, Kodagu, Gorkha, Taiwan events)
- CAS Landslide Dataset, HR-GLDD — additional detection training data
- ISRO/NRSC Landslide Atlas — ~80,000 historical events, 1998–2022

---

## 14. Feature Build Phases (useful for annotating MVP vs. future-scope layers on the diagram)

**Phase 0 — MVP / Must-have (all P0):**
1. Integrated AI Risk Engine (§2.1–2.2)
2. Road Isolation Risk Index (§4.2)
3. Village Action Cards + DDMA Audit Trail (§7, §9)
4. Offline-First PWA + CAP/SMS Fallback (§8)

**Phase 1 — High-value / Flagship (P1):**
5. Multilingual Voice Synthesis (§7)
6. InSAR Pre-Failure Creep Layer (§3) — flagship differentiator
7. Crowdsourced Photo Quality Scoring (§10)

**Phase 2 — Scale-up (P2):**
8. Sensor-Agnostic Ingestion Engine (§11 — optional physical-sensor REST API)
9. False-Alarm-Cost Tuning Slider (§7)

**Explicitly out of scope (do not build):** custom IoT/soil-moisture hardware (violates Software category), a from-scratch alert-dissemination pipe (integrate SACHET instead), a generic pan-India model (must stay NER-tuned), unsubstantiated "99% accuracy" claims.

---

## 15. Quick Component Summary (for diagram node labels)

- **Inputs:** IMD, IMERG, SMAP/ESA-CCI/ERA5, Sentinel-1/2, DEM, OSM, GSI/NESAC/Bhuvan inventories, shelter data, citizen photo reports
- **Core AI:** XGBoost risk engine (LHASA-style) + hyperlocal I-D/E-D thresholds + SHAP explainability
- **Deformation module:** Sentinel-1 InSAR (PSI/SBAS/DS) — slow/deep-seated slopes only
- **Impact modules:** Runout envelope, Road Isolation Index (RII), Evacuation Priority Score (EPS)
- **Decision engine:** Dynamic risk-aware routing (C_edge), Village action cards, Escalation-stage cards, What-if simulator
- **Dissemination:** SACHET/CAP 1.2, Cell Broadcast, Offline PWA, BLE/Wi-Fi Direct mesh, SMS
- **Governance:** Timestamped audit trail (Created → Approved → Disseminated → Acknowledged)
- **External integrations (peer systems, not replaced):** GSI, NESAC, Bhuvan/NDEM, IMD, SACHET, A-LEWS (optional), ERSS-112

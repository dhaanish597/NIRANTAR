# SIH26001 — AI-Based Early Warning & Landslide Risk Monitoring System for the North Eastern Region (NER): Team Source-of-Truth Reference

**Problem Statement:** SIH26001 | Ministry: MDoNER | Category: **Software** | Theme: Disaster Management | Deadline: 20 September 2026

---

## TL;DR
- **The winning insight: the bottleneck is not prediction, it is the last mile and the accountability gap.** India already runs several landslide/flood warning systems — GSI's National Landslide Forecasting Centre (NLFC), NESAC's FLEWS, NDMA's SACHET/Cell Broadcast — yet people keep dying because warnings are (a) *regional, not slope-specific*, (b) *do not reach the last village*, and (c) *have no accountable chain from a bulletin to an actual evacuation*. Build an integrated decision-and-dissemination platform that closes those gaps for NER, entirely on existing public data feeds — not "yet another prediction model."
- **The single strongest software-only differentiator is Sentinel-1 InSAR "pre-failure creep" detection** (weeks of lead time for slow/deep-seated slides) fused with hyperlocal rainfall thresholds and a **road-network isolation-risk index** ("which villages get cut off"). None of the current government systems operationalize these for NER, and both map directly onto MDoNER's stated concern about connectivity.
- **Open the pitch with Wayanad 2024** (a warning was issued ~16 hours ahead and was not acted on; 200–400+ dead) as the accountability hook — then immediately pivot to NER cases (Tupul 2022, Aizawl 2024, Sikkim GLOF 2023) so the domain jury sees regional fidelity, not a generic Kerala project.

---

## Key Findings
1. **The problem is the last mile, not the science.** At Wayanad (30 July 2024), the Hume Centre for Ecology & Wildlife Biology (Kalpetta), which runs 200+ weather stations, issued a landslide alert at ~9 AM on 29 July — roughly 16 hours before the disaster — and it did not translate into evacuation; the district administration reportedly denied receiving it. India's flagship GSI landslide forecasting centre had gone operational only two weeks earlier and covers almost no NER districts.
2. **NER is systematically under-served.** ~18.8% of India's landslides occur in the NE Himalaya and 64 of India's 147 landslide-affected districts are in the North East — yet as of the 2025 monsoon only **Nagaland** (Kohima, Peren, Dimapur) and **Sikkim** (6 districts) receive even *experimental* GSI bulletins. Assam, Arunachal Pradesh, Manipur, Meghalaya, Mizoram and Tripura get **none**; GSI's own roadmap defers most of NER to "Phase-II by 2030."
3. **Software-only is a genuine constraint but not fatal.** You cannot deploy soil-moisture sensors, but you can *consume* satellite-derived soil moisture (NASA SMAP, ESA CCI), IMERG/GPM rainfall, Sentinel-1 InSAR and Sentinel-2 optical — the exact stack NASA's operational LHASA model uses. Where software creates a real data gap (in-situ pore pressure), the honest workaround is satellite proxies + InSAR + crowdsourcing.
4. **A credible reference architecture already exists to copy: NASA LHASA v2** (XGBoost, 1 km grid, open source) which per Stanley et al. (Frontiers in Earth Science, 2021) was "twice as likely to predict the occurrence of historical landslides as LHASA version 1, given the same global false positive rate." Add **Landslide4Sense** (ResU-Net segmentation benchmark) and India/NER-specific rainfall thresholds.
5. **The alerting rails already exist — integrate, don't rebuild.** NDMA's CAP-based SACHET has delivered 134+ billion SMS in 19+ Indian languages and is operational in all 36 states/UTs; the C-DOT Cell Broadcast system launched 2 May 2026. Your value-add is the *landslide-specific triggering logic and last-mile action layer* on top of these pipes.

---

## Details

### 1. Disaster case studies and human cost (the evidence base)

Every claim below is drawn from peer-reviewed papers, GSI/ISRO reports, or credible outlets (The Hindu, Down To Earth, Mongabay, Deccan Herald, Science, Springer *Landslides*, Eos).

| Event | Date | Deaths | Warning status & documented failure mode |
|---|---|---|---|
| **Wayanad (Mundakkai–Chooralmala–Punchirimattom), Kerala** | 30 Jul 2024 | Official ~298 + 32 declared dead; Wikipedia 420; academic estimates 254–392 | IMD **orange** (not red) alert; Hume Centre alert ~16 hrs prior reportedly not acted on; Puthumala gauge recorded ~572 mm/48 hr; night-time (02:00–04:30 IST); failure initiated on a **pre-existing 2020 crack**; debris flow peaked ~28 m/s, ~8 km runout; Punapuzha bridge collapse isolated Mundakkai. 53+ children among dead. |
| **Sikkim South Lhonak GLOF (Teesta-III)** | 3–4 Oct 2023 | 55 confirmed + 74 missing (~129) | Landslide-triggered GLOF: ~14.7 M m³ frozen moraine collapsed into lake → ~20 m wave → moraine breach → ~50 M m³ released → Teesta-III dam destroyed before gates could open (~00:30). **No operational EWS on the lake.** Sattar et al. (2021) had modelled this exact GLOF; moraine showed >15 m/yr displacement 2016–2023 (detectable precursor). Mongabay: "No early warning system and insufficient dam safety turned Sikkim flood deadly." |
| **Tupul/Noney, Manipur** | 30 Jun 2022 | 61 (29–30 Territorial Army + civilians) | Railway construction site (Jiribam–Imphal line); **no warning**; two-phase failure ~12:30 AM & 6 AM; 705.5 mm rain May–Jun (130% above decadal avg); NLSM had the bench as low/moderate susceptibility though back-slopes were moderate-high; blocked Ijai river creating dam hazard. |
| **Aizawl quarry + multiple landslides, Mizoram** | 28 May 2024 | 27–34 (state total; 33 bodies recovered per academic study) | Cyclone Remal; IMD red/orange alerts existed but **no slope-specific warning**; ~6 AM stone-quarry collapse (Melthum–Hlimen); NH-6 cut at Hunthar, **Aizawl isolated from the country**; 253.7 mm/3 days in Aizawl; cemeteries destroyed. |
| **Irshalwadi, Raigad, Maharashtra** | 19 Jul 2023 | 27 (+57 missing) | Village **NOT on GSI's landslide-prone list** (NLSM had it "low susceptibility"); ~499–500 mm over 3 days; CM: "This village was not on the list." Sabale/others: **InSAR later revealed ~12 mm/yr precursory creep** — detectable in hindsight. |
| **Malin, Pune, Maharashtra** | 30 Jul 2014 | 151 | Early morning, residents asleep; deforestation + altered (wheat) farming + quarrying; village not flagged; first spotted by a passing bus driver. |
| **Taliye, Raigad** | 22 Jul 2021 | 84–85 | >300–350 mm in 2–3 days; Western Ghats debris flow. |
| **Kedarnath, Uttarakhand** | Jun 2013 | ~4,000+ (multi-hazard) | Reference "event-based" inventory in ISRO Atlas. |
| **Chamoli/Rishiganga** | 7 Feb 2021 | ~200 | Rock/ice avalanche → flash flood; no EWS; in NRSC rapid-response atlas. |

**Cross-cutting failure patterns (the design brief writes itself from these):**
- **Night-time initiation** (Wayanad, Sikkim, Tupul, Aizawl) → alerts must reach sleeping people (loud cell-broadcast tone, sirens).
- **Events on slopes/villages NOT on official lists** (Irshalwadi, Malin, Taliye) → static 1:50,000 susceptibility maps are insufficient; need *dynamic* + InSAR.
- **Warnings that were regional/coarse** (IMD district colour codes) not slope-specific → the core gap.
- **A warning existed but did not convert to evacuation** (Wayanad) → the accountability gap.
- **Road/bridge loss isolating villages and blocking rescue** (Mundakkai bridge, Aizawl NH-6, Tupul Ijai dam) → the isolation-risk index is the MDoNER-relevant differentiator.

### 2. Existing government solutions and why they underperform

| System | What it does | Documented weakness (your critique) |
|---|---|---|
| **GSI LEWS / NLFC** (National Landslide Forecasting Centre, Kolkata, launched 19 Jul 2024) | Daily rainfall-threshold landslide bulletins; **operational** for Darjeeling, Kalimpong, Nilgiris; **experimental** for 21 districts/8 states in 2025; national coverage targeted 2030; grew from LANDSLIP project (India-UK-Italy, 2016–2021) | **Regional, not slope-specific.** LANDSLIP co-lead Prof. Bruce Malamud (Durham): locals "want to know forecasts house by house. We had to explain to the district collectors… that we were giving them forecasts over a region." Bulletins are taluk/sub-division level for 48 hrs. **No published false-alarm rate** (a transparency gap). GSI's Saibal Ghosh: site-specific sensors are "cost-prohibitive" for 87,000+ active landslides, and experimental bulletins are "not to be shared with the public." NER largely deferred to Phase-II (2030). |
| **NLSM (National Landslide Susceptibility Mapping)** | 1:50,000 macro-scale maps; ~4.3 lakh sq km, 19 states/UTs; ~91,000-landslide inventory (33,904 field-validated) on Bhukosh | Scale too coarse for village decisions; Irshalwadi & Malin sat in low/moderate zones yet failed catastrophically. Static, not dynamic; no temporal trigger. |
| **NRSC/ISRO Landslide Atlas (Feb 2023)** | ~80,000 landslides 1998–2022; ranks 147 districts by socio-economic exposure; on Bhuvan; NDEM geoportal | Historical inventory, **not real-time prediction**. NER **de-prioritized on socio-economic risk** ("not particularly vulnerable… due to lower population density") despite highest event frequency — the structural reason NER is under-served. |
| **IMD** | District colour-coded warnings; nowcasts; Mausam/Meghdoot/Damini apps; public API (api.imd.gov.in — city/district forecast, district nowcast/rainfall/warnings, highway nowcast) | District-level not slope-level; **Doppler radar gaps in NER**; Mausam app poorly rated (~2.6 stars, "totally broken" reviews); Kerala CM called the Wayanad rain forecast "way off the mark." API has IP-whitelisting friction. |
| **NDMA SACHET + Cell Broadcast** | CAP-based integrated alert system (C-DOT); 134+ billion SMS in 19+ languages; all 36 states/UTs; new Cell Broadcast launched 2 May 2026 (English/Hindi/regional, loud tone, no internet needed) | **It is a pipe, not a decision system.** Depends on someone authoring the right geo-targeted alert; no landslide-specific triggering logic; no village-action content. |
| **NESAC FLEWS (Assam)** | Satellite + WRF + HEC-HMS flood EWS since 2009; ~75–85% success; 24–36 hr lead; revenue-circle/village-cluster level; NER-DRR node at NESAC | **Flood-focused, not landslide**; Assam-centric; landslide node nascent; NESAC has done landslide hazard zonation for Guwahati only. |
| **Academic/pilot** (IIT Mandi/iIoTs; Amrita WSN, Munnar & Sikkim — among the world's first deployed landslide EWS) | Slope-specific sensor networks; iIoTs claims "99% at 3 hrs, 90–92% at 24 hrs" | **Hardware-based, tiny spatial coverage, cost-prohibitive to scale.** The "99%" is a startup self-report, not independently validated. Not a software play. |

**The accountability gap ("who presses the button") — your biggest exploitable opening:** Even a correct bulletin has no guaranteed chain to a village evacuation. After Wayanad, the Centre and Kerala publicly blamed each other over whether a warning was issued/heeded. GSI disseminates experimental bulletins by WhatsApp/social media to District Magistrates who "sometimes" forward them to grassroots groups (per SaveTheHills' Praful Rao). Former NDMA advisor Brig. (Retd) B.K. Khanna: the Wayanad tragedy "exposed a lack of community and village-level warning systems." Kerala's Jan-2025 launch of the "Kavacham" siren/beacon network is an implicit admission of the prior last-mile gap.

### 3. The last-mile & evacuation-failure problem (design constraints)
- **Connectivity (use real numbers in the pitch):** Of 45,934 NER villages, ~42,093 have mobile coverage and ~40,663 have 4G — leaving roughly **1,841 villages with no coverage** and **~2,847 without 4G** (Feb 2026 data, via DoT/Parliament and *The Sentinel*). State gaps (Feb 2026): Manipur 189 uncovered, Meghalaya 141, Nagaland 107, Mizoram 52, Assam 163, Tripura 7, Sikkim 6. Rural teledensity nationally is ~58% vs ~125% urban. **→ Mandates offline-first design + SMS/cell-broadcast fallback.**
- **Language:** NER has hundreds of languages/dialects; alerts must be multilingual — Assamese, Bodo, Khasi, Garo, Mizo, Meitei (Manipuri), Nagamese, Nepali. Use **Bhashini / AI4Bharat IndicTrans2 (22 languages, MIT) + Indic-Parler-TTS/Indic-TTS (MIT)**; IndicTrans2 explicitly supports Meitei (Meitei script) and other low-resource NER languages.
- **Behavioural (from warning-response literature):** alert fatigue from false alarms; night-time events; distrust of authorities; livestock/property concerns; no identified safe shelters; unclear chain of command from IMD/GSI bulletin to village action. **→ Village "action cards," post-event feedback loops, and explicit false-alarm-cost tuning.**

### 4. Science & data foundations
- **Rainfall thresholds (NER-specific — cite these to impress geologists):**
 - NE Himalaya intensity–duration (ID) threshold: **I = 5.8294 × D^−0.4141** (frequentist method, TRMM 2007–2016; *J. Earth Syst. Sci.*).
 - NE Himalaya moisture/event–duration threshold: **E(mm) = −11.10 + 0.62·D(hr)** for 24 < D < 1440 hr (490 rain-driven landslides, 2006–2019, non-crossing quantile regression; NHESS). Guwahati (26.14°N) and Shillong (25.58°N) need *higher* cumulative rain than surrounding hotspots.
 - Sikkim (Lanta Khola, N-Sikkim Highway): sliding predicted when **normalized cumulative rainfall > 250 mm over 15 days**.
 - Kalimpong (Darjeeling): a **48-hr event of ~36.7 mm cumulative** can trigger; Shimla (NW Himalaya, for contrast): I = 7.20·D^−0.26, ~110 mm/30-day antecedent.
- **Satellite soil moisture / rainfall (software-only workarounds for the "sensor" clause):** NASA **SMAP**, **ESA CCI** soil moisture, **ERA5** (found the most suitable gridded precipitation alternative to gauges in the Himalaya); NASA **GPM/IMERG** rainfall.
- **DEMs / terrain:** CartoDEM, SRTM (30 m), **ALOS PALSAR (12.5 m)**, NASADEM, Copernicus DEM (30 m); OpenTopography; Survey of India.
- **InSAR — the flagship opportunity:** **Sentinel-1** C-band, free, 6–12 day revisit; **PSI/SBAS/distributed-scatterer** methods detect mm/yr slow deformation. Proof it matters: Irshalwadi showed ~12 mm/yr precursory creep; South Lhonak moraine >15 m/yr 2016–2023 before collapse; Karakoram Highway PSI found deformation 0–364 mm/yr and 29 new landslides. **Honest caveat:** vegetation decorrelation limits coherence in humid NER; use distributed-scatterer methods + optical fusion + European-Ground-Motion-Service-style pre-processed products; multi-temporal InSAR is proven for *ex-post* monitoring but is still emerging for *ex-ante* early warning (Springer, *Landslides* 2022).
- **Reference model — NASA LHASA v2 (study this closely):** XGBoost at 1 km; inputs = slope, distance-to-faults, lithologic strength, antecedent + current IMERG rainfall, SMAP soil moisture, snow mass; **probabilistic** nowcast (lets you tune false-negative/positive tradeoff); adds a population/road **exposure** layer; open-source (NASA GSC-18595-1). Per Stanley et al. (2021), it was "twice as likely to predict the occurrence of historical landslides as LHASA version 1, given the same global false positive rate." **This is the architecture to localize for NER.** Global Landslide Catalog / COOLR are its validation inventories.

### 5. AI/ML state of the art (with honest accuracy framing)
- **Susceptibility (static):** logistic regression, frequency ratio, weights-of-evidence, random forest, XGBoost, SVM, ANN; AHP/MCDA for data-scarce districts (Darjeeling AHP: ROC AUC 96.8%, success-rate 81.3%). Sharma et al. (2024) national susceptibility map is the current India reference.
- **Detection/segmentation (event mapping & inventory update):** CNN, **U-Net / ResU-Net / DeepLab / U-Net++** on Sentinel-2. **Landslide4Sense** benchmark (3,799–4,884 patches; 14 bands = 12 S2 + ALOS slope + DEM; Iburi/Kodagu/Gorkha/Taiwan). Official study: **ResU-Net best (F1 ≈ 0.73)**; later work (RMAU-NET, ASK-UNet++, LandslideSegNet) reports higher F1/mIoU. **Extreme class imbalance** (~2–2.5% landslide pixels) → weighted cross-entropy (e.g., 1:4), focal loss.
- **Temporal:** LSTM/GRU/**Temporal Fusion Transformer** for rainfall & displacement series; multi-task DL to optimize accuracy *near the warning threshold* (Strnad et al. 2025, Urbas landslide) — more useful than minimizing overall residual.
- **Advanced/novel:** Graph Neural Networks for spatial dependency between slopes; **physics-informed NNs** coupling infinite-slope stability with ML; **transfer learning / EO foundation models** (Prithvi-100M NASA/IBM, Clay, SatMAE, Presto) for data-scarce NER districts.
- **Trust & rigor (this wins geologist judges):** **SHAP** for explainability; **spatial cross-validation** (never random split — inflates AUC); report **AUC-ROC AND real-world false-alarm cost**; be deliberate about **negative-sample selection**.
- **Datasets:** Landslide4Sense, CAS Landslide Dataset, HR-GLDD, GSI Bhukosh inventory (91,000), NASA Global Landslide Catalog / COOLR.

### 6. Innovative ideas to beat existing solutions (ranked by leverage × feasibility × demo impact)

| Idea | Why it beats existing systems | Hackathon feasibility |
|---|---|---|
| **Road-network isolation-risk index** ("which villages get cut off & for how long") using OSM road graph + hazard scored on each segment | No government system does this; directly serves MDoNER's connectivity mandate; huge demo impact; explains Aizawl NH-6 & Mundakkai bridge failures | **High** — graph analysis on OSM, pre-computable |
| **Village-level "action card"** (where to go, which road to avoid, nearest safe shelter) instead of an abstract risk colour | Fixes the last-mile/accountability gap directly; what a villager actually needs | **High** |
| **DDMA decision-support + accountability audit trail** ("who was warned, who acknowledged, who acted, when") | Directly closes the "who presses the button" gap exposed by Wayanad; MDoNER would adopt | **High** |
| **Offline-first PWA + SMS/cell-broadcast fallback + Bluetooth/Wi-Fi-Direct store-and-forward mesh** (software-only, no LoRa hardware) | Works in NER's ~1,841 no-coverage villages | **Medium-High** |
| **Multilingual TTS voice alerts** via Bhashini/IndicTrans2/Indic-TTS for low-literacy NER languages | Real barrier; strong "Digital India / sovereign AI" story for judges | **High** |
| **InSAR pre-failure creep detection** (weeks of lead for slow slides) | Lead time no rainfall-threshold system offers; Irshalwadi/South Lhonak proof | **Medium** — use GEE / pre-processed ground-motion products; full PSI is hard in 36 hrs (position as flagship + future scope) |
| **Hyperlocal dynamic rainfall thresholds** learned per-slope vs per-district | Fewer false alarms than GSI's regional bulletins | **Medium** |
| **Crowdsourced geotagged crack/blocked-road photos + on-device CV filter** (answers PS clause e) | Fills the sensor gap with citizens; noise-filtered so DDMAs trust it | **Medium-High** |
| **False-alarm-cost tuning as an explicit product feature** (slider on probability threshold) | Pre-empts the top geologist objection; shows rigor | **High** |
| **Road-blockage proxies:** bus/truck GPS + telecom signalling drop + social-media/news scraping for rapid event detection | Cheap near-real-time ground truth without hardware | **Medium** |

### 7. Judge's perspective & winning strategy
- **SIH judging criteria (official):** novelty/originality, complexity, clarity, **feasibility, practicability, sustainability, scale of impact, user experience, future scope** — scored ~1–20 per criterion, weighted to 100 across rounds. Post-SIH, the ministry gets lifetime free access and IP stays with the team (so pitch it as adoptable).
- **What MDoNER actually wants:** something *deployable* that protects NER connectivity and lives; **regional fidelity**; low cost; **integrates with** GSI/IMD/NDMA/NESAC rather than replacing them.
- **What a GSI/NESAC/IMD/NDMA jury will immediately poke:** overclaimed AI accuracy in front of geologists; ignoring InSAR vegetation limits; pretending to replace GSI; hand-waving false-alarm cost; a "pan-India" model that isn't NER-tuned.
- **Demo strategy (8–10 min):** (1) open with the Wayanad accountability failure — one slide, one number (a warning existed, ~16 hrs, still 200+ dead); (2) pivot to a live NER map with the **isolation-risk index** lighting up a highway; (3) fire a **village action card** in Mizo/Meitei with voice; (4) show the **DDMA audit trail**; (5) present accuracy **honestly** with SHAP + the false-alarm-cost slider; (6) close on **SACHET integration** (you plug into the national pipe). Live demo > slides.

### 8. Implementation reference (APIs, datasets, licensing)

| Resource | Use | Access / licence |
|---|---|---|
| **IMD API** (api.imd.gov.in) | Rainfall, district nowcast/warnings, highway nowcast | Public; note IP-whitelisting friction; attribute IMD |
| **NASA GPM/IMERG** | Rainfall (current + antecedent) | NASA Earthdata login, free |
| **NASA SMAP / ESA CCI / ERA5 (CDS)** | Satellite soil moisture (the "sensor" workaround) | Earthdata / Copernicus CDS, free |
| **Copernicus Sentinel-1/2** | InSAR + optical | Copernicus Data Space, free/open |
| **Google Earth Engine** | Process S1/S2/DEM at scale | Free for research |
| **Bhuvan / NRSC / NDEM** | Landslide Atlas, LHZ maps, DEM, exposure | Registration |
| **OpenStreetMap** | NER road network graph | ODbL (attribution) |
| **Bhashini / AI4Bharat IndicTrans2, Indic-Parler-TTS** | Multilingual text + voice alerts | MIT / Apache 2.0 |
| **NASA LHASA v2** | Reference model / starter code | Open source (GSC-18595-1) |
| **Landslide4Sense / COOLR / GLC** | Training + validation data | Open |
| **NDMA SACHET / CAP 1.2** | Alert dissemination | Govt integration (position as partner) |
| **SMS gateway + TRAI DLT** | SMS alerts | DLT registration required |
| **MapmyIndia/Mappls or MapLibre + vector tiles** | Low-bandwidth maps | Freemium / open |

**Suggested tech stack:** Python (XGBoost / PyTorch), Google Earth Engine Python API, PostGIS + GeoServer (OGC WMS/WFS/WMTS), FastAPI backend, React **PWA** with **MapLibre vector tiles** for low bandwidth, edge inference (TF-Lite/ONNX) on cheap Android, cloud with offline sync.

**Honest data gaps & workarounds (say these out loud — it builds credibility):** no real-time in-situ soil moisture/pore pressure in NER → SMAP/ESA-CCI + InSAR proxy; InSAR vegetation decorrelation → distributed-scatterer + optical fusion, and scope InSAR to slow/deep-seated slides only; sparse rain-gauge density → IMERG/ERA5; landslide-inventory reporting bias → foundation-model transfer learning.

### 9. Policy, funding & adoption context (shows you understand deployment)
- **NLRMP (National Landslide Risk Mitigation Project):** ₹1,000 crore for 15 states from the National Disaster Mitigation Fund (NDMF), approved Nov 2024; **₹378 crore earmarked for the 8 NE states** (Arunachal, Assam, Manipur, Meghalaya, Mizoram, Nagaland, Sikkim, Tripura). Predecessor: Landslide Risk Mitigation Scheme (LRMS, 2019, ₹43.91 cr).
- **15th Finance Commission (2021–26):** NDMF ₹13,693 cr + SDMF ₹32,030.60 cr; NDRMF total ₹68,463 cr; GLOF risk management ₹150 cr (4 states); urban flood ₹3,075.65 cr (7 cities).
- **National Landslide Risk Management Strategy** (NDMA, 27 Sep 2019); NDMA Landslide Hazard Management Guidelines (2009); **Aapda Mitra** (100,000 community volunteers, 350 districts).
- **MDoNER levers:** NESIDS, PM-DevINE, North Eastern Council (NEC); **NESAC** is the natural regional integration/hosting partner.
- **Standards to cite:** CAP 1.2, OGC WMS/WFS/WMTS, Sendai Framework indicators, ISO 22320.

---

## Recommendations

**Build these 8 highest-leverage features (in priority order):**
1. **Road-network isolation-risk index** + a lightweight digital twin of the NER highway network (NH-6, NH-29, etc.) — your signature, MDoNER-aligned differentiator.
2. **Integrated risk engine** = LHASA-style XGBoost (IMERG rainfall + SMAP soil moisture + terrain/lithology) fused with **hyperlocal, per-slope rainfall thresholds**, output as probabilistic risk.
3. **Village-level action cards** + shelter routing that avoids hazard-flagged road segments.
4. **Offline-first PWA** + SMS/cell-broadcast fallback + Bluetooth/Wi-Fi-Direct store-and-forward.
5. **Multilingual voice + text alerts** via Bhashini/IndicTrans2/Indic-TTS.
6. **DDMA decision-support + accountability audit trail** (warned → acknowledged → acted → timestamped).
7. **InSAR creep-detection module** as the "wow"/future-scope differentiator (scoped to slow/deep-seated slides).
8. **Crowdsourced crack/blocked-road photo ingestion** with on-device CV filtering (answers PS clause e).

**Deliberately do NOT build:** custom IoT/soil-moisture sensors (violates "Software" category); a from-scratch alerting pipe (integrate SACHET/Cell Broadcast); a pan-India generic model (stay NER-tuned); any "99% accurate prediction" claim (it will be destroyed by a geologist judge).

**Strongest one-line pitch/hook:** *"We don't just predict landslides — we make sure the warning reaches the last village and tells them exactly where to go, before the road is gone."*

**Most compelling opening case study:** **Wayanad, 30 July 2024** — a warning was issued ~16 hours ahead and still 200+ people died because it never became an evacuation. Then pivot within 30 seconds to **Tupul (Manipur, 2022), Aizawl (Mizoram, 2024) and the Sikkim GLOF (2023)** to prove NER focus.

**Top 10 hard judge questions — with suggested answers:**
1. **How is this different from GSI's LEWS?** → GSI is *regional* and has *no last-mile*; we add slope-level InSAR, a road-isolation index, and an accountable dissemination + audit layer — and we *feed from* GSI/IMD, not replace them.
2. **You're software-only — how do you get soil moisture without sensors?** → Satellite soil moisture (NASA SMAP, ESA CCI) + InSAR deformation proxy, exactly like NASA's operational LHASA model.
3. **What's your accuracy and false-alarm rate?** → We report honest AUC-ROC with *spatial* cross-validation and an explicit false-alarm-cost slider; we optimize for lead time near the warning threshold, not a headline number. (GSI itself publishes no false-alarm rate.)
4. **Will it work with no network?** → Offline-first PWA, SMS + cell-broadcast, and phone-to-phone store-and-forward for the ~1,841 uncovered NER villages.
5. **Which NER languages, really?** → Bhashini/IndicTrans2 covers Assamese, Meitei, Mizo, Khasi, Garo, Nagamese, Nepali, Bodo — with TTS voice for low literacy.
6. **How does a bulletin become an evacuation?** → Village action cards + a DDMA workflow with a timestamped audit trail (who was warned/acknowledged/acted) — the exact gap Wayanad exposed.
7. **InSAR in vegetated NER — does it even work?** → Distributed-scatterer methods + optical fusion; we scope InSAR to slow/deep-seated slides and are explicit that it does *not* catch sudden shallow debris flows.
8. **How does it scale and get funded?** → ₹378 cr is already earmarked for NE states under NLRMP; we integrate with NESAC/GSI/IMD and use only open data, so recurring cost is low.
9. **Data licensing?** → All open/free — Copernicus, NASA Earthdata, OSM (ODbL), Bhashini (MIT/Apache), IMD API.
10. **Won't false alarms erode trust like everywhere else?** → Yes, which is why false-alarm cost is a first-class product feature plus a post-event community feedback loop that retrains thresholds.

---

## Caveats (flag these; do not paper over them)
- **Wayanad death toll varies by source** — official ~298 + 32 declared dead; Wikipedia 420; peer-reviewed estimates 254–392. Cite it as a range ("200–400+"); do not assert a single number.
- **Sikkim GLOF toll:** 55 confirmed + 74 missing (~129); some early/secondary reports say 92+. Use "55 confirmed, 74 missing."
- **iIoTs/IIT-Mandi "99% accuracy"** is a startup self-report, not independently validated — attribute carefully or omit.
- **No published GSI false-alarm rate exists** — this is a transparency gap you can note, not evidence that GSI is accurate.
- **InSAR pre-failure detection works for slow/deep-seated slides, NOT sudden shallow debris flows** — most NER killer events (Wayanad-type debris flows) are rainfall-triggered and fast, so do not overclaim universal "weeks of lead time." Position InSAR as one layer among several.
- **NER GSI coverage correction:** it is *not* "Kohima only" — the 2025 experimental set includes Nagaland (Kohima, Peren, Dimapur) and Sikkim (6 districts); but the six remaining NER states have zero coverage, which is the point that matters.
- **NESAC FLEWS success figures (75–85%)** are self-reported program metrics for *floods*, not independently audited landslide performance.
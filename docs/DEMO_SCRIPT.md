# ICONIX SIH Demo Script

## Full version (about 8 minutes)

**0:00 - Problem.** “The problem is not only predicting landslides. The harder problem is knowing who will be isolated, which road will fail, what action should be taken, and whether the warning reaches the community.”

**0:45 - System.** Open the officer console. Identify the map, risk hierarchy, impact and isolation panels, Action Card, Commander, and Audit. State that the system is advisory and a human officer approves dissemination.

**1:15 - Aizawl replay.** Select `Aizawl 2024`. Point out `REPLAY / RECONSTRUCTED DATA` and `HELD-OUT CASE STUDY`. This is an accelerated reconstruction, not live weather.

**1:30-3:30 - Escalation.** Advance the replay. Explain the chain: rainfall accumulation drives the XGBoost/threshold fusion; SHAP explains the model output; runout intersects road geometry; severed road edges change network connectivity; RII and EPS rank affected villages. Call out the NH-6/Hunthar case-study road event only as documented ground truth, not as a claim of live prediction.

**3:30 - Action Card.** Open a P1/P2 card. Show the real village name, risk probability, reasons, affected roads, shelter route, and the safe evacuation window range. Any population shown is labelled as a WorldPop estimate; missing values are not invented.

**4:30 - DDMA approval.** Open Announce, review the card, and approve it as the officer. Show that approval is separate from AI recommendation. The channel rows are explicitly simulated/demo integrations; CAP is generated locally.

**5:30 - Offline.** With the application already loaded and cached, disable Wi-Fi/Ethernet on the demo machine. Reload the citizen surface. Show the alert, cached route, local shelters/contacts, and the persistent offline queue state. Explain that replay uses only local scenario, model, terrain, road, and map assets.

**6:15 - Trust.** Open the explanation/provenance view. Show probability, confidence heuristic, SHAP drivers, source, timestamp, resolution, and the exact label `Surface proxy (top 5 cm)` where applicable. Move the false-alarm-cost control only where measured evaluation values are available; otherwise show `Not measured`.

**7:00 - What-if.** Open What-if and identify `COUNTERFACTUAL SIMULATION`. Run 100 mm, 250 mm, and 400 mm cases. Explain that each request calls the same backend Pipeline and returns model/physics-derived risk, runout, road severance, isolation, priority, and route results. It is not a forecast and never overwrites replay state.

**7:45 - Close.** “Prediction is only the first step. ICONIX connects prediction to impact, decision, communication, and accountability.”

## Compressed version (about 3 minutes)

1. Open Aizawl 2024 and point out `REPLAY / RECONSTRUCTED DATA`.
2. Advance the replay: rainfall -> risk -> runout -> road severance -> isolation -> priority.
3. Open the Action Card, show a real village/road/shelter route, and approve it as DDMA.
4. Show the simulated channel records and one alert ID in Audit.
5. Disconnect the network and show the citizen alert/route still available.
6. Run one What-if comparison and close with the message above.

## Judge questions

**How is ICONIX different from GSI's landslide early-warning work?** GSI susceptibility is a hazard layer. ICONIX combines dynamic rainfall/model risk with runout, road-network severance, village isolation, evacuation priority, risk-aware routing, human approval, offline delivery, and an audit chain.

**How is soil moisture estimated without dedicated sensors?** The current UI labels it honestly as a software-derived `Surface proxy (top 5 cm)`. It is not presented as measured deep soil moisture.

**What is the model accuracy?** The authoritative artifact reports approximately ROC-AUC 0.696 and PR-AUC 0.500, plus threshold-specific metrics. We do not claim a single “95% accuracy” number.

**What is the false-alarm rate?** Use the threshold-specific evaluation artifact. If a requested operating point is not measured, the answer is `Not measured`, not an estimate.

**Why XGBoost?** It performs well on mixed tabular terrain features, handles missing lithology/curvature values natively, is fast enough for local inference, and is reproducible with a pinned artifact.

**Why FastAPI?** It provides typed request/response contracts, WebSocket ticks, and a small local service that runs without cloud dependencies.

**Why offline-first?** A warning is most valuable when connectivity is degraded. Replay, model, terrain, road graph, PMTiles/hillshade, action cards, routes, and queues are local.

**Why phone-to-phone/mesh if broadcasts exist?** Mesh is a last-mile resilience option for local acknowledgement and forwarding when central connectivity is intermittent; it complements rather than replaces official broadcasts.

**What happens when the network returns?** Queued citizen actions/reports retry through the offline store, successful items are marked once, failures remain queued, and the last successful sync time is updated from a real response.

**What if the AI is wrong?** It is advisory, not autonomous authority. A DDMA officer reviews and approves. The system preserves model provenance, uncertainty language, route assumptions, and a tamper-evident audit trail.

## Honest boundaries

Wayanad 2024 and Tupul 2022 are historical reconstructed replays. NVIDIA Commander, SMS, cell broadcast, IVRS, and mesh channels are optional or simulated integrations. Sentinel-1 InSAR, crowdsourced image CV, GLOF, and broad multi-hazard expansion remain future scope.

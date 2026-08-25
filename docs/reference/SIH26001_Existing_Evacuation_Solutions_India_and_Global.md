# SIH 26001 — Existing Emergency Evacuation Solutions: India & Global

Research summary for the AI-Based Early Warning & Landslide Risk Monitoring System in NER

**Prepared:** 23 August 2026

## Executive Summary

- Emergency evacuation technology is already a mature and rapidly developing field. India has major national components such as NDEM, ERSS-112 and NDMA SACHET, while state systems provide GIS assets, shelters and operational procedures. International examples include Japan's location-aware evacuation apps, South Korea's Emergency Ready ecosystem, U.S. evacuation-zone and evacuation-management platforms, and research/open-source systems for dynamic routing and simulation.
- The key implication for SIH 26001 is that a generic 'evacuation app' or shortest-path router is not sufficiently novel. A stronger proposition is a landslide-specific, predictive and risk-aware evacuation layer for NER that integrates hazard forecasts with road failure probability, village isolation, shelter capacity, critical infrastructure, evacuation windows, field intelligence and official decision workflows.

## India — Major Existing Solutions

- NDEM (National Database for Emergency Management): ISRO/NRSC disaster GIS and decision-support ecosystem. Its documented capabilities include risk-zone identification, relief-shelter identification, evacuation planning, route planning, proximity/route analysis, infrastructure analysis and emergency information support. This means GIS evacuation planning already exists nationally; the opportunity is to make it dynamic, landslide-specific and last-mile oriented.
- ERSS-112: India's Emergency Response Support System. It supports emergency calls and digital requests, GIS-based location and dispatch, emergency vehicle tracking, geo-fencing and routing/shortest-path functions. It is a response/dispatch backbone rather than a landslide-specific predictive evacuation engine.
- NDMA SACHET / CAP Integrated Alert System: national geo-targeted disaster alert dissemination across multiple channels and languages. It is an alerting pipe and does not by itself solve the full chain of hazard interpretation, evacuation-route computation, shelter selection and action accountability.
- ASDMA (Assam): state disaster-management GIS and information services include mapped critical assets such as hospitals, police stations, schools, shelters, bridges and other infrastructure, alongside disaster reporting and preparedness services. Assam is therefore an important example of existing state-level GIS capability.
- NER state disaster-management plans: official planning documents in states such as Mizoram and Nagaland recognize GIS-based evacuation routes, shelters, critical infrastructure and response resources. These are important operational requirements, but they are not equivalent to a continuously updated, AI-driven public evacuation navigator.

## Global — Operational Examples

- Japan — Hiroshima Emergency Evacuation Guide: location-aware evacuation information, nearby functioning shelters and route guidance. The important lesson is that the destination should be an operationally usable shelter, not merely the geographically nearest shelter.
- Japan — Oita Disaster Prevention App: combines hazard maps, sediment-disaster/flood information, evacuation-route guidance, road information, push notifications, current-location risk information and offline functionality. This demonstrates that offline evacuation assistance is operationally feasible.
- Japan — NERV: aggregates location-specific disaster information and maps and provides alerts and community-oriented information. It demonstrates the value of combining multiple hazards and local information rather than presenting isolated warnings.
- South Korea — Emergency Ready: provides disaster alerts and maps of civil-defence shelters, emergency medical centres, fire stations, police stations and other emergency facilities, with multilingual information.
- United States — FEMA app/ecosystem: provides disaster alerts, shelter information and preparedness/recovery guidance. The U.S. model is highly distributed across federal, state, county and private systems rather than being one universal evacuation-routing application.
- United States — Zonehaven / evacuation-zone management: demonstrates operational zone-based evacuation management, helping authorities issue phased evacuation orders and manage traffic rather than evacuating an entire community indiscriminately.
- United States — San Bernardino County evacuation platform: demonstrates evacuation-status and accountability concepts, including visibility into who has evacuated and who remains/has not been reached.
- New Zealand — tsunami evacuation planning: official guidance emphasizes that evacuation routes should consider congestion and safety, not simply shortest distance. This supports risk-aware route optimization.
- United States — NIST wildfire evacuation guidance: emphasizes that evacuation routes can fail during fast-moving disasters and therefore communities should consider temporary refuge options when evacuation becomes impossible.

## Open Source / Research Implementations

- FireABM (CyberGIS): agent-based wildfire evacuation simulation with road networks, evacuees, wildfire spread, progressive road closures and rerouting. Useful as a reference for the SIH what-if simulator.
- EMBER: open-source wildfire evacuation recommendation project combining risk assessment, route optimization, real-time information, GIS visualization and AI-oriented components. It demonstrates that AI-assisted evacuation recommendations are already being explored.
- AgentEvac: agent-based wildfire evacuation simulation using AI/LLM-driven agents for departure, route and destination decisions under uncertainty. Useful for studying human behaviour and simulation, but it is not the same as an official emergency-command system.
- AI Disaster Evacuation Planner: open-source routing examples using OpenStreetMap/OSMnx/NetworkX and graph algorithms such as Dijkstra and A*. This demonstrates that basic dynamic evacuation routing is technically accessible and should not itself be presented as the core USP.
- SafeRoute AI and related projects: hazard-aware route planning that incorporates hazards such as flood, fire and landslide into road-network routing. These projects reinforce the need for SIH differentiation beyond simple hazard avoidance.
- PyroRL: reinforcement-learning environment for wildfire evacuation. Useful as research inspiration, but RL is probably unnecessary complexity for an SIH prototype unless a specific optimization problem requires it.

## What Existing Systems Already Solve

- Disaster alerts: solved at national scale in India and several other countries.
- GIS hazard mapping: mature.
- Static evacuation planning and shelter identification: mature.
- Shortest/optimal emergency routing: mature.
- Basic dynamic/hazard-aware routing: already demonstrated in research and open-source projects.
- Multilingual emergency alerts: operational in several countries and in India's national alert ecosystem.
- Offline evacuation assistance: demonstrated in Japan.
- Crowdsourced/local disaster information: demonstrated in several systems.
- Agent-based evacuation simulation: established research area.
- AI-assisted evacuation recommendations: emerging, with commercial and open-source examples.

## Where the Real Gap Remains for SIH 26001

- The strongest remaining gap is integration: connect landslide risk prediction to road-network consequences, village isolation, evacuation windows, shelters, critical infrastructure and government action workflows.
- Road isolation intelligence is especially relevant to MDoNER. Instead of only asking where a landslide may occur, calculate which road segments may fail, which villages become isolated, for how long, and which alternative routes remain viable.
- Predictive route failure is stronger than ordinary dynamic routing: the system should avoid routes that are currently open but likely to become unsafe before evacuees reach them.
- Evacuation accountability is another useful gap: warned → acknowledged → order issued → alert disseminated → evacuation progress → shelter occupancy → unresolved population.
- An AI Emergency Commander should be framed as human-in-the-loop decision support, not autonomous government authority. It should summarize the situation, explain recommendations, simulate alternatives and require authorized human approval.
- Offline-first operation remains highly relevant to remote NER. The system can cache maps, shelters, routes and emergency instructions and synchronize reports when connectivity returns.

## Comparison With Proposed SIH Features

- Risk score + explainability: keep it. It is foundational, but not sufficient as a USP.
- Dynamic evacuation routing: keep it, but make it predictive and hazard-aware rather than shortest-path only.
- Time-to-disaster countdown: use more defensible terminology such as 'estimated safe evacuation window' or 'estimated time-to-critical-risk'; avoid claiming exact landslide timing.
- Critical infrastructure map: keep it, but connect infrastructure exposure to road isolation, population impact and response priority.
- AI Emergency Commander: strong feature if positioned as human-in-the-loop decision support.
- What-if simulator: strong differentiator for official decision-making; compare 'evacuate now' vs 'wait' vs alternative routes/shelters.
- Low/no internet mode: keep it; particularly relevant for NER.
- Crowdsourced intelligence: keep it, ideally with geotagged photos/reports and verification/filtering.
- Multilingual alerts: keep it; make alerts actionable, not merely translated.

## Recommended Product Positioning

- Do not pitch the system as 'another evacuation app' or 'Google Maps for disasters.'
- Recommended positioning: 'Predictive, Risk-Aware Evacuation and Emergency Decision Support for Landslide-Prone NER.'
- Core flow: Hazard intelligence → risk score → impact assessment → road-isolation prediction → evacuation window → safe-route computation → shelter selection → human-approved action → multilingual/offline dissemination → evacuation tracking → post-event accountability.
- Integrate rather than rebuild: NDEM for national GIS/disaster information where available; SACHET/other government alert rails for dissemination; ERSS-112/state control rooms for response; OpenStreetMap or approved road data for routing; satellite/weather sources for hazard intelligence.
- Do not claim that dynamic evacuation routing, multilingual alerts, offline apps, AI routing or GIS evacuation planning are entirely new. The genuine differentiation should be the NER-specific integration of landslide prediction, predictive road failure/isolation, evacuation-window estimation and accountable government decision support.

## Important Caveats

- Existing government capabilities change over time; integration availability and API access must be verified before implementation.
- Open-source repositories can be demonstrations or research prototypes rather than operational systems. Repository existence does not prove field deployment or accuracy.
- AI evacuation research often focuses on wildfire or flood scenarios. Transfer to landslides requires careful hazard modelling.
- An evacuation route that is safe now may become unsafe later. This is a core reason to combine route planning with the landslide-risk forecast.
- Do not let an AI agent autonomously order evacuations. Keep an authorized officer in the decision loop.
- Do not claim universal prediction of exact landslide time. Use probabilistic risk and estimated operational windows.

## Selected Sources / Further Reading

- ISRO/NRSC NDEM: https://www.isro.gov.in/DBEM.html
- NDEM brochure: https://ndrf.nrsc.gov.in/documents/downloads/v4/BROCHURE_NDEM_v4.0.pdf
- ERSS-112: https://112.gov.in/features
- NDMA SACHET: https://sachet.ndma.gov.in/
- CDOT CAP Integrated Alert System: https://deveservices.dot.gov.in/products/cap-integrated-alert-system
- Assam State Disaster Management Authority: https://asdma.assam.gov.in/
- Hiroshima Emergency Evacuation Guide: https://www.city.hiroshima.lg.jp/english/everyday/1029824/1009688.html
- Oita Disaster Prevention App: https://play.google.com/store/apps/details?id=jp.oita.pref.bousai
- NERV: https://nerv.app/en/about.html
- FEMA App: https://www.ready.gov/fema-app
- CyberGIS FireABM: https://github.com/cybergis/FireABM_Modeling_Notebook
- AgentEvac: https://github.com/denoslab/AgentEvac
- AI Disaster Evacuation Planner: https://github.com/peelajanu/AI-Disaster-Evacuation-Planner
- SafeRoute AI: https://github.com/PRAVITH10/SafeRoute_AI
- PyroRL: https://github.com/sisl/PyroRL
- NIST wildfire evacuation guidance: https://www.nist.gov/news-events/news/2025/04/nist-updates-critical-wildfire-evacuation-and-sheltering-guidance
- NACo San Bernardino evacuation platform: https://www.naco.org/news/technology-upgrade-boosts-disaster-evacuation-process

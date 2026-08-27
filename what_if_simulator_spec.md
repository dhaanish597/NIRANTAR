# NIRANTAR What-If Hazard & Stress Simulator: Full Technical Specification & Architecture Guide

**System:** NIRANTAR (SIH26001) — AI-Based Landslide Early Warning & Risk Monitoring System  
**Module:** What-If Hazard Simulator (DDMA Pre-positioning & Stress-Testing Engine)  
**Target User:** District Disaster Management Authority (DDMA) Officers & Operational Planners  

---

## 1. Executive Summary & Design Vision

The **What-If Simulator** allows disaster managers to test hypothetical meteorological, geological, and environmental scenarios before an actual disaster occurs. It enables predictive stress-testing: *"What happens to our district roads and remote settlements if we experience a 250 mm downpour on pre-saturated soil near an active fault zone?"*

The system operates with a **strict isolation guarantee**:
- It runs on a **throwaway pipeline instance**.
- Synthetic stress runs **never touch live map state** and **never emit real audit events** to avoid false alarms.

---

## 2. Frontend Architecture & UI Specifications

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│ WHAT-IF STRESS SIMULATOR | DDMA PRE-POSITIONING ENGINE             AOI: Aizawl        │
├────────────────────────────────────────┬───────────────────────────────────────────────┤
│                                        │  [Status Bar: SEVERE HAZARD | 4/9 Roads Cut]  │
│  LEFT PANEL: MULTI-PARAMETRIC CONTROLS │───────────────────────────────────────────────│
│                                        │                                               │
│  1. Slope Angle / Terrain              │              GIS PREDICTIVE MAP               │
│     [Slider: 15° - 55°]                │                                               │
│                                        │   - Dynamic 500m Risk Grid                    │
│  2. Fault Distance & Lithology         │   - Zoom-Responsive Vector Roads              │
│     [Slider: 0.2km - 15km]             │     * Zoom 9-11: Major National Corridors     │
│     [Buttons: Weak / Med / Strong]     │     * Zoom 12+: Full Arterial & Local Network │
│                                        │   - Severed Road Highlights (Glow / Dashed)   │
│  3. Antecedent Rainfall (7-30d)        │   - Village Status Pins (Normal vs Isolated)  │
│     [Slider: 0mm - 350mm]              │   - Safe Evacuation Pathways (Dijkstra)       │
│                                        │   - Fault Buffer Zone Outline                 │
│  4. Current IMERG Rainfall             │                                               │
│     [Rainfall: 10mm - 500mm]           │  ┌─────────────────────────────────────────┐  │
│     [Duration: 1h - 48h]               │  │ [TOUCH/CLICK PRONE AREA INSPECTOR]      │  │
│                                        │  │ Cell: Durtlang Escarpment (Hunthar)     │  │
│  5. SMAP Soil Moisture (Saturation %)  │  │ P_fail: 84.2% (CRITICAL FAILURE)        │  │
│     [Slider: 10% - 100%]               │  │ Top Driver: Slope (47°) + IMERG Rate    │  │
│                                        │  │ NH-6 Status: SEVERED                    │  │
│  6. Snow Mass / Spring Melt (SWE)      │  │ Isolated: 6,400 Residents at risk       │  │
│     [Slider: 0mm - 150mm SWE]          │  └─────────────────────────────────────────┘  │
│                                        │                                               │
│  7. Population & Road Exposure Layer   │  [Layer Toggles]                    [Legend]  │
│     [Toggle: On/Off | Weight: 0.5-2.0x]│                                               │
│                                        │                                               │
│  [Run Full Backend Simulation Button]  │                                               │
└────────────────────────────────────────┴───────────────────────────────────────────────┘
```

### 2.1 Left Panel: Parameter Definitions
1. **Slope Angle / Terrain Gradient**:
   - Range: $15^\circ$ (gentle valley) to $55^\circ$ (near-vertical escarpment).
   - Affects gravitational shear stress via $\sin(\theta)$.
2. **Distance to Faults / Lithologic Strength**:
   - Proximity Slider: $0.1\text{ km}$ to $15.0\text{ km}$ from known fault traces.
   - Lithology Selector: Weak Shales / Sandstone / Competent Gneiss.
3. **Antecedent Rainfall (Multi-day cumulative)**:
   - Range: $0\text{ mm}$ to $350\text{ mm}$ (7-to-30-day prior accumulation).
   - Models ground pre-saturation and water-table rise.
4. **Current IMERG Rainfall & Duration**:
   - Total volume: $10\text{ mm}$ to $600\text{ mm}$.
   - Duration: $1\text{ h}$ to $48\text{ h}$.
   - Computes rainfall intensity $I = \text{rain} / \text{duration}$ (mm/h).
5. **SMAP Soil Moisture**:
   - Range: $10\%$ to $100\%$ volumetric topsoil saturation.
6. **Snow Mass (SWE) / Spring Melt**:
   - Range: $0\text{ mm}$ to $150\text{ mm}$ snow-water equivalent with melt contribution switch (for Sikkim / high-altitude North East).
7. **Population / Road Exposure Layer**:
   - Toggle switch with exposure multiplier ($0.5\times$ to $2.0\times$) highlighting critical NH-6/SH transport lifelines.

### 2.2 Right Panel: Map & Interaction Design
1. **Zoom-Dependent Road Network Rendering**:
   - **Low Zoom (Zoom 8–11)**: Renders primary lifelines (National Highways, Trunk corridors).
   - **High Zoom (Zoom 12–17)**: Automatically reveals tertiary access roads, village branch links, and bridge crossings.
   - **Severed State**: Roads with intersecting critical failure risk ($P_{\text{fail}} > 0.55$) render in high-contrast flashing red with dashed line markers.
2. **Touch/Click Prone Area Inspector (Detailed Info)**:
   - Touching/clicking any cell or prone zone reveals an instant drawer showing:
     - Failure probability ($P_{\text{fail}}$) & Escalation Stage (Watch / Pre-Alert / Ready / Evacuate Now).
     - Dominant driver (e.g. *"84% driven by extreme IMERG intensity combined with 47° slope"*).
     - Elevation, terrain curvature, and fault distance.
     - Severed road names and affected downstream settlements.

---

## 3. Backend Architecture & Endpoints

### 3.1 Backend Endpoints Specification

#### Endpoint 1: Run What-If Simulation
- **Route:** `POST /api/whatif/simulate`
- **Purpose:** Executes the full end-to-end ML, physics threshold, road graph severance, and settlement isolation pipeline on a synthetic observation frame.
- **Isolation Guarantee:** Runs inside a transient `Pipeline()` instance; never writes to the persistent audit log or `/ws/ticks`.

##### Request Body (`application/json`):
```json
{
  "aoi_id": "aizawl",
  "rainfall_mm": 240.0,
  "duration_hours": 12.0,
  "slope_modifier_deg": 34.0,
  "distance_to_fault_km": 3.5,
  "lithology": "weak",
  "antecedent_rainfall_mm": 80.0,
  "soil_moisture_pct": 45.0,
  "snow_mass_mm": 0.0,
  "snow_melt_active": false,
  "exposure_weight": 1.0
}
```

##### Response Body (`application/json`):
```json
{
  "request": {
    "aoi_id": "aizawl",
    "rainfall_mm": 240.0,
    "duration_hours": 12.0
  },
  "assumptions": [
    "Rainfall applied uniformly across AOI terrain grid.",
    "Constant intensity for the simulated storm duration.",
    "Road severance calculated using debris runout intersection over OSM road graph."
  ],
  "cell_count": 2912,
  "summary": {
    "hazard_level": "SEVERE",
    "severed_road_count": 4,
    "total_road_count": 9,
    "isolated_village_count": 3,
    "total_village_count": 9,
    "population_at_risk": 14200,
    "failure_distribution": {
      "GREEN": 2100,
      "YELLOW": 512,
      "ORANGE": 200,
      "RED": 100
    }
  },
  "tick": {
    "t": "2026-08-27T14:45:00+05:30",
    "mode": "live",
    "aoi_id": "aizawl",
    "cell_risks": [
      {
        "cell_id": "aizawl_040_026",
        "p_fail": 0.842,
        "threshold_exceedance": 2.41,
        "confidence": 0.88,
        "attributions": [
          { "feature": "rainfall_intensity", "contribution": 0.45 },
          { "feature": "slope", "contribution": 0.38 },
          { "feature": "fault_proximity", "contribution": 0.17 }
        ],
        "model_version": "xgb_terrain_v1"
      }
    ],
    "road_risks": [
      {
        "edge_id": "road_nh6_hunthar",
        "name": "NH-6 (Hunthar Chasm)",
        "p_blocked": 0.92,
        "severed": true,
        "is_bridge": false,
        "contributing_cells": ["aizawl_040_026"]
      }
    ],
    "isolations": [
      {
        "village_id": "aizawl_040_026",
        "name": "Durtlang",
        "population": 6400,
        "p_isolated": 0.89,
        "isolated_now": true,
        "alternate_route_exists": true,
        "est_duration_hours": 18.0,
        "severed_links": ["road_nh6_hunthar"]
      }
    ],
    "priorities": [
      {
        "village_id": "aizawl_040_026",
        "tier": "P1",
        "eps": 0.865,
        "rank": 1,
        "components": {
          "p_fail": 0.84,
          "population": 0.72,
          "isolation": 0.89,
          "shelter_access": 0.65
        }
      }
    ],
    "new_action_cards": [
      {
        "alert_id": "sim-card-durtlang",
        "village_id": "aizawl_040_026",
        "stage": "RED",
        "headline": "Immediate Evacuation Recommended for Durtlang",
        "reason_plain": "Extreme rainfall exceeding slope threshold with high likelihood of NH-6 severance.",
        "shelter_name": "Durtlang College Shelter",
        "roads_to_avoid": ["NH-6 at Hunthar"],
        "route": {
          "village_id": "aizawl_040_026",
          "shelter_id": "shelter_durtlang_college",
          "shelter_name": "Durtlang College Shelter",
          "distance_m": 1420,
          "est_walk_minutes": 22,
          "avoided_roads": ["NH-6"],
          "geometry": {
            "type": "LineString",
            "coordinates": [[92.717, 23.731], [92.720, 23.735], [92.724, 23.737]]
          }
        }
      }
    ]
  }
}
```

---

#### Endpoint 2: Get Road Network GeoJSON with Multi-Zoom Hierarchy
- **Route:** `GET /api/whatif/roads/{aoi_id}`
- **Purpose:** Serves the detailed vector road network with metadata tags (National Highway, State Highway, Local Arterial) so the frontend map displays progressive detail on zoom.

##### Response Body (`application/json`):
```json
{
  "type": "FeatureCollection",
  "features": [
    {
      "type": "Feature",
      "geometry": {
        "type": "LineString",
        "coordinates": [[92.712, 23.725], [92.719, 23.733], [92.728, 23.741]]
      },
      "properties": {
        "edge_id": "nh6_sec_1",
        "name": "NH-6 Aizawl-Silchar Corridor",
        "highway_type": "trunk",
        "min_zoom": 9,
        "criticality": "high",
        "intersecting_cells": ["aizawl_040_026", "aizawl_022_001"]
      }
    }
  ]
}
```

---

#### Endpoint 3: Get Cell Terrain Inspection Details
- **Route:** `GET /api/whatif/cell/{aoi_id}/{cell_id}`
- **Purpose:** Fetches static geomorphological characteristics (DEM slope, elevation, aspect, TWI, lithology class, fault distance) for deep inspection when a user touches/clicks a cell.

##### Response Body (`application/json`):
```json
{
  "cell_id": "aizawl_040_026",
  "aoi_id": "aizawl",
  "name": "Durtlang / Hunthar Escarpment",
  "center": { "lat": 23.7307, "lon": 92.7173 },
  "elevation_m": 1280.0,
  "slope_deg": 46.8,
  "aspect": "NW",
  "topographic_wetness_index": 7.42,
  "distance_to_fault_km": 1.15,
  "lithology_class": "weak_shale_siltstone",
  "land_cover": "vegetated_slope",
  "nearest_village": "Durtlang",
  "connected_roads": ["NH-6 (Hunthar)"]
}
```

---

## 4. Multi-Parametric Physical & Machine Learning Formulation

When a simulation is requested, the backend calculates failure probabilities using a fused formulation:

### 4.1 Rainfall Exceedance ($R$)
Empirical NE-Himalayan Intensity-Duration curve:
$$I = \frac{\text{Rainfall (mm)} + 0.8 \cdot \text{Snowmelt (mm)}}{\text{Duration (h)}}$$
$$I_{\text{crit}} = 5.8294 \cdot D^{-0.4141}$$
$$R = \frac{I}{I_{\text{crit}}}$$

### 4.2 Slope Shear Stress Factor ($F_{\text{slope}}$)
$$F_{\text{slope}} = \left(\frac{\sin(\theta)}{\sin(35^\circ)}\right)^{1.35}$$

### 4.3 Fault Proximity & Lithology Factor ($F_{\text{geo}}$)
$$F_{\text{geo}} = K_{\text{lith}} \cdot \left(1 + \frac{1.8}{1 + d_{\text{fault}}^{0.8}}\right)$$
*where $K_{\text{lith}} \in \{1.35 \text{ (Weak)}, 1.0 \text{ (Moderate)}, 0.7 \text{ (Competent)}\}$*

### 4.4 Antecedent Saturation & Soil Moisture Factor ($F_{\text{moisture}}$)
$$F_{\text{moisture}} = 1.0 + 0.55 \cdot \left(\frac{\text{Antecedent Rain (mm)}}{150}\right) + 0.65 \cdot \left(\frac{\text{Soil Moisture \%}}{50} - 1.0\right)$$

### 4.5 Combined Failure Probability ($P_{\text{fail}}$)
$$P_{\text{fail}} = 1 - \exp\left(-0.52 \cdot R \cdot F_{\text{slope}} \cdot F_{\text{geo}} \cdot F_{\text{moisture}}\right), \quad P_{\text{fail}} \in [0.02, 0.99]$$

---

## 5. Step-by-Step Backend Implementation Guide

### Step 1: Create the Extended What-If Schema
In `backend/app/schemas/whatif.py`, define the extended input parameters:
```python
class WhatIfSimulationRequest(BaseModel):
    aoi_id: str = "aizawl"
    rainfall_mm: float = Field(gt=0, le=1000)
    duration_hours: float = Field(gt=0, le=168)
    slope_modifier_deg: float | None = None
    distance_to_fault_km: float | None = None
    lithology: Literal["weak", "moderate", "competent"] = "weak"
    antecedent_rainfall_mm: float = 0.0
    soil_moisture_pct: float = 45.0
    snow_mass_mm: float = 0.0
    snow_melt_active: bool = false
    exposure_weight: float = 1.0
```

### Step 2: Implement Synthetic Frame Builder with Multi-Parameters
In `backend/app/api/whatif.py`, update `build_synthetic_frame()` to populate:
- `antecedent_7d`, `antecedent_15d`, `antecedent_30d` from `antecedent_rainfall_mm`.
- `soil_moisture` from `soil_moisture_pct`.
- Snowmelt water equivalent added directly to the effective rainfall intensity.

### Step 3: Wire Road Graph & Inspection Handlers
1. In `backend/app/api/whatif.py`, implement `load_road_features(aoi_id)` reading from `data/osm/<aoi>_graph.pkl` or GeoJSON and tagging lines with zoom hierarchy.
2. Implement `inspect_cell_terrain(aoi_id, cell_id)` reading static attributes from `data/static/<aoi>/cells.gpkg`.

### Step 4: Register Routes in `api/routes.py`
Mount the endpoints:
- `POST /api/whatif/simulate`
- `GET /api/whatif/roads/{aoi_id}`
- `GET /api/whatif/cell/{aoi_id}/{cell_id}`

### Step 5: Test Determinism & Pipeline Isolation
Run automated tests verifying:
1. Re-running the simulation with identical inputs produces byte-identical results.
2. No synthetic events are added to `app.state.pipeline.audit_log`.
3. Degraded fallback succeeds when optional static layers are unavailable.

---

## 6. Summary of Deliverables

| Area | Feature | Description |
|---|---|---|
| **Frontend Left** | Multi-Parametric Controls | Sliders for Slope, Fault Distance/Lithology, Antecedent Rain, IMERG Rain, SMAP Soil Moisture, Snow Mass, Exposure Layer. |
| **Frontend Right** | GIS Predictive Map | Zoom-responsive vector roads, dynamic 500m risk cells, severed road highlights, village isolation pins, safe evacuation routes. |
| **Frontend UX** | Touch Inspector | Instant detailed property drawer upon touching/clicking any prone cell or village. |
| **Backend API** | `POST /api/whatif/simulate` | Executes throwaway pipeline over terrain grid with real ML + physical threshold calculations. |
| **Backend Data** | `GET /api/whatif/roads/{id}` & `/cell/{id}` | Provides hierarchical vector road geometry and granular cell inspection data. |

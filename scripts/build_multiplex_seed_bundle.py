"""Deterministic 4-Layer Multiplex Seed Bundle Builder (<28 MB).

Builds `data/seed_bundle/nodes.json`, `data/seed_bundle/edges.json`, `data/seed_bundle/manifest.json`,
and Sarvam multimodal test fixtures (`data/seed_bundle/fixtures/`) across Chennai (Cyclone Michaung),
Wayanad (Chooralmala–Mundakkai), and Aizawl (Hunthar NH-6).
"""
from __future__ import annotations

import argparse
import json
import math
import struct
import wave
from pathlib import Path
from typing import Any

AOI_CENTERS: dict[str, tuple[float, float, float]] = {
    "chennai": (12.9650, 80.2200, 6.5),
    "wayanad": (11.5550, 76.1350, 780.0),
    "aizawl": (23.7307, 92.7173, 1132.0),
}


def _generate_aoi_hydrological_layer(
    aoi_id: str, base_lat: float, base_lon: float, base_elev: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    watersheds = []
    drains = []
    flood_zones = []
    drain_edges = []

    for idx in range(1, 5):
        ws_id = f"WS-{aoi_id.upper()}-{idx:02d}"
        d_id = f"SWD-{aoi_id.upper()}-{idx:02d}"
        fz_id = f"FZ-{aoi_id.upper()}-{idx:02d}"
        lat = round(base_lat + (idx - 2) * 0.008, 6)
        lon = round(base_lon + (idx - 2) * 0.008, 6)
        elev = round(base_elev + (4 - idx) * 2.5, 2)

        watersheds.append({
            "id": ws_id,
            "watershed_id": ws_id,
            "aoi_id": aoi_id,
            "name": f"{aoi_id.title()} Sub-Basin {idx}",
            "lat": lat,
            "lon": lon,
            "elev_m": elev + 4.0,
            "area_sqkm": round(4.2 + idx * 0.8, 2),
            "mean_slope_deg": round(3.5 + idx * 1.2, 2),
            "runoff_coeff": 0.78,
            "saturation_index": 0.85 if idx == 1 else 0.55,
        })
        drains.append({
            "id": d_id,
            "drain_id": d_id,
            "aoi_id": aoi_id,
            "name": f"{aoi_id.title()} Primary Drain {idx}",
            "lat": lat,
            "lon": round(lon + 0.002, 6),
            "elev_m": elev,
            "drain_tier": "PRIMARY" if idx <= 2 else "SECONDARY",
            "design_capacity_cusecs": 1200.0,
            "water_depth_m": 1.65 if idx == 1 else 0.35,
            "siltation_ratio": 0.42 if idx == 1 else 0.15,
            "is_surcharged": idx == 1,
        })
        flood_zones.append({
            "id": fz_id,
            "zone_id": fz_id,
            "aoi_id": aoi_id,
            "ward_id": f"WARD-{aoi_id.upper()}-{170 + idx}",
            "name": f"{aoi_id.title()} Inundation Zone {idx}",
            "lat": lat,
            "lon": round(lon + 0.003, 6),
            "elev_m": elev - 0.5,
            "hazard_category": "HIGH_INUNDATION" if idx == 1 else "MODERATE",
            "flood_depth_m": 1.45 if idx == 1 else 0.20,
            "velocity_mps": 1.8 if idx == 1 else 0.4,
            "is_active": idx == 1,
        })
        drain_edges.append({
            "edge_id": f"EDGE-DRAIN-{aoi_id.upper()}-{idx:02d}",
            "src_id": ws_id,
            "dst_id": d_id,
            "rel_type": "DRAINS_INTO",
            "gradient_slope": 0.035,
            "flow_capacity_cusecs": 1200.0,
            "distance_m": 450.0,
        })
    return watersheds, drains, flood_zones, drain_edges


def _generate_aoi_transport_layer(
    aoi_id: str, base_lat: float, base_lon: float, base_elev: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    junctions = []
    segments = []
    bridges = []
    culverts = []
    connects_edges = []
    corridor_edges = []

    # Generate a connected 36-junction road network per AOI with explicit bridges, culverts,
    # and high-elevation ridge nodes (for DEM physics spoof testing).
    for idx in range(1, 37):
        j_id = f"OSM-{aoi_id.upper()}-{idx:03d}"
        row, col = divmod(idx - 1, 6)
        lat = round(base_lat - 0.015 + row * 0.006, 6)
        lon = round(base_lon - 0.015 + col * 0.006, 6)
        # Node 36 is an explicit high-elevation ridge peak (+38m above basin floor)
        elev = round(base_elev + 38.0 if idx == 36 else base_elev + (5 - row) * 1.8 + (col % 2) * 0.6, 2)
        flood_depth = 1.25 if idx in (7, 8, 14) else 0.0
        is_passable = flood_depth < 0.45

        junctions.append({
            "id": j_id,
            "osmid": j_id,
            "aoi_id": aoi_id,
            "name": f"{aoi_id.title()} Ridge Peak" if idx == 36 else f"{aoi_id.title()} Junction {idx:02d}",
            "lat": lat,
            "lon": lon,
            "elev_m": elev,
            "slope_deg": 22.5 if idx in (14, 36) else 3.2,
            "highway_type": "primary" if row in (2, 3) else "secondary",
            "flood_depth_m": flood_depth,
            "is_passable": is_passable,
            "is_articulation_point": idx in (8, 15, 22),
        })

    # Connect grid horizontally and vertically, but route access to the eastern cluster (cols 4..5)
    # exclusively through 3 articulation choke points (nodes 8, 15, 22) so Tarjan's algorithm
    # identifies exact cut-vertices and bridge edges.
    seg_counter = 0
    for idx in range(1, 37):
        row, col = divmod(idx - 1, 6)
        neighbors: list[int] = []
        if col < 5:
            # Restrict cross-river / cross-canal links between col 2 and col 3 to rows 1, 2, 3 (nodes 9, 15, 21)
            if col != 2 or idx in (9, 15, 21):
                neighbors.append(idx + 1)
        if row < 5 and col not in (3, 4):
            neighbors.append(idx + 6)
        elif row < 5 and col == 3 and idx in (10, 16):
            neighbors.append(idx + 6)

        for nb in neighbors:
            seg_counter += 1
            u_id = f"OSM-{aoi_id.upper()}-{idx:03d}"
            v_id = f"OSM-{aoi_id.upper()}-{nb:03d}"
            seg_id = f"SEG-{aoi_id.upper()}-{seg_counter:03d}"
            length_m = 620.0
            base_time_s = 55.0
            depth = 1.20 if idx == 8 else 0.0
            passable = depth < 0.45
            dyn_cost = 1e9 if not passable else base_time_s * (1.0 + 4.0 * (depth / 0.5) ** 2)

            segments.append({
                "id": seg_id,
                "segment_id": seg_id,
                "aoi_id": aoi_id,
                "u_osmid": u_id,
                "v_osmid": v_id,
                "name": f"{aoi_id.title()} Corridor {seg_counter}",
                "lat": junctions[idx - 1]["lat"],
                "lon": junctions[idx - 1]["lon"],
                "length_m": length_m,
                "elev_m": junctions[idx - 1]["elev_m"],
                "flood_thresh_m": 0.45,
                "water_depth_m": depth,
                "base_time_s": base_time_s,
                "dynamic_cost_s": round(dyn_cost, 2),
                "is_passable": passable,
            })
            for a, b in ((u_id, v_id), (v_id, u_id)):
                connects_edges.append({
                    "edge_id": f"{seg_id}-{a}-{b}",
                    "segment_id": seg_id,
                    "u_id": a,
                    "v_id": b,
                    "aoi_id": aoi_id,
                    "length_m": length_m,
                    "base_time_s": base_time_s,
                    "dynamic_cost_s": round(dyn_cost, 2),
                    "flood_depth_m": depth,
                    "flood_thresh_m": 0.45,
                    "is_passable": passable,
                })

    # Add explicit Bridge and Culvert choke points
    br_id = f"BR-{aoi_id.upper()}-01"
    cul_id = f"CUL-{aoi_id.upper()}-01"
    bridges.append({
        "id": br_id,
        "bridge_id": br_id,
        "aoi_id": aoi_id,
        "name": f"{aoi_id.title()} Arterial Bridge 01",
        "lat": junctions[14]["lat"],
        "lon": junctions[14]["lon"],
        "elev_m": junctions[14]["elev_m"],
        "deck_clearance_m": 2.2,
        "load_limit_tons": 40.0,
        "water_level_m": 1.6,
        "scour_risk_score": 0.78,
        "is_passable": True,
        "is_bridge_edge": True,
    })
    culverts.append({
        "id": cul_id,
        "culvert_id": cul_id,
        "aoi_id": aoi_id,
        "name": f"{aoi_id.title()} Box Culvert 01",
        "lat": junctions[8]["lat"],
        "lon": junctions[8]["lon"],
        "elev_m": junctions[8]["elev_m"],
        "invert_elev_m": junctions[8]["elev_m"] - 1.5,
        "soffit_elev_m": junctions[8]["elev_m"] + 0.5,
        "diameter_m": 1.8,
        "flood_thresh_m": 0.45,
        "water_depth_m": 1.15,
        "debris_blockage_pct": 0.68,
        "is_passable": False,
    })
    corridor_edges.extend([
        {
            "edge_id": f"CORR-{br_id}",
            "src_id": br_id,
            "dst_id": f"OSM-{aoi_id.upper()}-015",
            "rel_type": "CARRIES_CORRIDOR",
            "structural_criticality": 0.96,
            "clearance_margin_m": 0.6,
        },
        {
            "edge_id": f"CORR-{cul_id}",
            "src_id": cul_id,
            "dst_id": f"OSM-{aoi_id.upper()}-009",
            "rel_type": "CARRIES_CORRIDOR",
            "structural_criticality": 0.92,
            "clearance_margin_m": -0.65,
        },
    ])
    return junctions, segments, bridges, culverts, connects_edges, corridor_edges


def _generate_aoi_infrastructure_layer(
    aoi_id: str, junctions: list[dict[str, Any]]
) -> tuple[dict[str, list[dict[str, Any]]], dict[str, list[dict[str, Any]]]]:
    sub_id_1 = f"SUB-{aoi_id.upper()}-33KV-01"
    sub_id_2 = f"SUB-{aoi_id.upper()}-11KV-02"
    wat_id = f"WTP-{aoi_id.upper()}-01"
    tow_id = f"TOW-{aoi_id.upper()}-01"
    hosp_id_1 = f"HOSP-{aoi_id.upper()}-CARE-01"
    hosp_id_2 = f"HOSP-{aoi_id.upper()}-GEN-02"
    shel_id_1 = f"SHEL-{aoi_id.upper()}-01"
    shel_id_2 = f"SHEL-{aoi_id.upper()}-02"
    dep_id = f"DEP-{aoi_id.upper()}-01"

    infra_nodes = {
        "Substation": [
            {
                "id": sub_id_1,
                "substation_id": sub_id_1,
                "aoi_id": aoi_id,
                "label": "Substation",
                "name": f"{aoi_id.title()} 33kV Main Substation",
                "operator": "TANGEDCO" if aoi_id == "chennai" else "KSEB" if aoi_id == "wayanad" else "P&ED",
                "voltage_kv": 33,
                "lat": junctions[7]["lat"],
                "lon": junctions[7]["lon"],
                "elev_m": junctions[7]["elev_m"],
                "flood_thresh_m": 0.80,
                "capacity_mva": 50.0,
                "load_mva": 41.5,
                "water_depth_m": 1.25,
                "status": "INUNDATED",
                "nearest_osmid": junctions[7]["osmid"],
            },
            {
                "id": sub_id_2,
                "substation_id": sub_id_2,
                "aoi_id": aoi_id,
                "label": "Substation",
                "name": f"{aoi_id.title()} 11kV Feeder Station",
                "operator": "TANGEDCO" if aoi_id == "chennai" else "KSEB" if aoi_id == "wayanad" else "P&ED",
                "voltage_kv": 11,
                "lat": junctions[15]["lat"],
                "lon": junctions[15]["lon"],
                "elev_m": junctions[15]["elev_m"],
                "flood_thresh_m": 0.90,
                "capacity_mva": 20.0,
                "load_mva": 16.0,
                "water_depth_m": 0.10,
                "status": "ONLINE",
                "nearest_osmid": junctions[15]["osmid"],
            },
        ],
        "WaterFacility": [
            {
                "id": wat_id,
                "water_id": wat_id,
                "aoi_id": aoi_id,
                "label": "WaterFacility",
                "name": f"{aoi_id.title()} Booster Pumping Station",
                "facility_type": "PUMPING_STATION",
                "lat": junctions[13]["lat"],
                "lon": junctions[13]["lon"],
                "elev_m": junctions[13]["elev_m"],
                "flood_thresh_m": 0.70,
                "capacity_mld": 45.0,
                "status": "OFFLINE",
                "pressure_bar": 0.4,
                "backup_power_hrs": 1.5,
                "nearest_osmid": junctions[13]["osmid"],
            }
        ],
        "TelecomTower": [
            {
                "id": tow_id,
                "tower_id": tow_id,
                "aoi_id": aoi_id,
                "label": "TelecomTower",
                "name": f"{aoi_id.title()} Macro BTS Tower 01",
                "operator": "INDUS-BSNL",
                "lat": junctions[14]["lat"],
                "lon": junctions[14]["lon"],
                "elev_m": junctions[14]["elev_m"],
                "coverage_radius_m": 2500.0,
                "battery_capacity_ah": 300.0,
                "status": "ON_BATTERY",
                "battery_rem_hrs": 4.2,
                "active_connections": 1420,
                "nearest_osmid": junctions[14]["osmid"],
            }
        ],
        "Hospital": [
            {
                "id": hosp_id_1,
                "hospital_id": hosp_id_1,
                "aoi_id": aoi_id,
                "label": "Hospital",
                "name": f"{aoi_id.title()} Tertiary Care ICU Hospital",
                "lat": junctions[16]["lat"],
                "lon": junctions[16]["lon"],
                "elev_m": junctions[16]["elev_m"],
                "flood_thresh_m": 1.0,
                "icu_beds": 42,
                "total_beds": 210,
                "dg_fuel_cap_l": 450.0,
                "dg_fuel_rem_l": 165.0,
                "icu_load_kw": 185.0,
                "status": "ON_DG_BACKUP",
                "dg_fuel_rem_hrs": 3.18,
                "oxygen_rem_hrs": 6.5,
                "nearest_osmid": junctions[16]["osmid"],
            },
            {
                "id": hosp_id_2,
                "hospital_id": hosp_id_2,
                "aoi_id": aoi_id,
                "label": "Hospital",
                "name": f"{aoi_id.title()} Community Health Centre",
                "lat": junctions[22]["lat"],
                "lon": junctions[22]["lon"],
                "elev_m": junctions[22]["elev_m"],
                "flood_thresh_m": 0.85,
                "icu_beds": 14,
                "total_beds": 80,
                "dg_fuel_cap_l": 200.0,
                "dg_fuel_rem_l": 110.0,
                "icu_load_kw": 75.0,
                "status": "ON_DG_BACKUP",
                "dg_fuel_rem_hrs": 5.24,
                "oxygen_rem_hrs": 9.0,
                "nearest_osmid": junctions[22]["osmid"],
            },
        ],
        "ReliefShelter": [
            {
                "id": shel_id_1,
                "shelter_id": shel_id_1,
                "aoi_id": aoi_id,
                "label": "ReliefShelter",
                "name": f"{aoi_id.title()} Higher Secondary Relief Camp",
                "ward_id": f"WARD-{aoi_id.upper()}-171",
                "lat": junctions[20]["lat"],
                "lon": junctions[20]["lon"],
                "elev_m": junctions[20]["elev_m"],
                "max_capacity": 500,
                "current_occupancy": 312,
                "has_medical_bay": True,
                "water_status": "LOW_PRESSURE",
                "power_status": "BACKUP",
                "is_accessible": True,
                "nearest_osmid": junctions[20]["osmid"],
            },
            {
                "id": shel_id_2,
                "shelter_id": shel_id_2,
                "aoi_id": aoi_id,
                "label": "ReliefShelter",
                "name": f"{aoi_id.title()} Municipal Cyclone Shelter",
                "ward_id": f"WARD-{aoi_id.upper()}-172",
                "lat": junctions[28]["lat"],
                "lon": junctions[28]["lon"],
                "elev_m": junctions[28]["elev_m"],
                "max_capacity": 650,
                "current_occupancy": 240,
                "has_medical_bay": True,
                "water_status": "NORMAL",
                "power_status": "ONLINE",
                "is_accessible": True,
                "nearest_osmid": junctions[28]["osmid"],
            },
        ],
        "SupplyDepot": [
            {
                "id": dep_id,
                "depot_id": dep_id,
                "aoi_id": aoi_id,
                "label": "SupplyDepot",
                "name": f"{aoi_id.title()} SDRF Fuel & Sandbag Depot",
                "lat": junctions[0]["lat"],
                "lon": junctions[0]["lon"],
                "elev_m": junctions[0]["elev_m"],
                "diesel_stock_l": 12000.0,
                "sandbag_count": 8500,
                "boat_count": 12,
                "available_trucks": 6,
                "status": "ACTIVE",
                "nearest_osmid": junctions[0]["osmid"],
            }
        ],
    }

    fz_id_1 = f"FZ-{aoi_id.upper()}-01"
    cul_id_1 = f"CUL-{aoi_id.upper()}-01"

    infra_edges = {
        "INUNDATES": [
            {
                "edge_id": f"INUN-{aoi_id.upper()}-01",
                "src_id": fz_id_1,
                "dst_id": sub_id_1,
                "rel_type": "INUNDATES",
                "exposure_depth_m": 1.25,
                "inundation_prob": 0.96,
                "onset_lead_time_min": 15,
            },
            {
                "edge_id": f"INUN-{aoi_id.upper()}-02",
                "src_id": fz_id_1,
                "dst_id": cul_id_1,
                "rel_type": "INUNDATES",
                "exposure_depth_m": 1.15,
                "inundation_prob": 0.94,
                "onset_lead_time_min": 10,
            },
        ],
        "POWERS": [
            {
                "edge_id": f"POW-{aoi_id.upper()}-01",
                "src_id": sub_id_1,
                "dst_id": hosp_id_1,
                "rel_type": "POWERS",
                "feeder_id": f"FDR-{aoi_id.upper()}-33-01",
                "voltage_kv": 33,
                "priority_tier": 1,
                "load_mw": 4.2,
                "is_energized": False,
                "cascade_weight": 0.98,
            },
            {
                "edge_id": f"POW-{aoi_id.upper()}-02",
                "src_id": sub_id_1,
                "dst_id": wat_id,
                "rel_type": "POWERS",
                "feeder_id": f"FDR-{aoi_id.upper()}-33-02",
                "voltage_kv": 33,
                "priority_tier": 1,
                "load_mw": 3.5,
                "is_energized": False,
                "cascade_weight": 0.95,
            },
            {
                "edge_id": f"POW-{aoi_id.upper()}-03",
                "src_id": sub_id_1,
                "dst_id": tow_id,
                "rel_type": "POWERS",
                "feeder_id": f"FDR-{aoi_id.upper()}-11-01",
                "voltage_kv": 11,
                "priority_tier": 2,
                "load_mw": 0.8,
                "is_energized": False,
                "cascade_weight": 0.92,
            },
            {
                "edge_id": f"POW-{aoi_id.upper()}-04",
                "src_id": sub_id_1,
                "dst_id": sub_id_2,
                "rel_type": "POWERS",
                "feeder_id": f"FDR-{aoi_id.upper()}-INTER-01",
                "voltage_kv": 33,
                "priority_tier": 1,
                "load_mw": 12.0,
                "is_energized": False,
                "cascade_weight": 0.90,
            },
            {
                "edge_id": f"POW-{aoi_id.upper()}-05",
                "src_id": sub_id_2,
                "dst_id": hosp_id_2,
                "rel_type": "POWERS",
                "feeder_id": f"FDR-{aoi_id.upper()}-11-02",
                "voltage_kv": 11,
                "priority_tier": 1,
                "load_mw": 2.1,
                "is_energized": True,
                "cascade_weight": 0.94,
            },
        ],
        "SUPPLIES_WATER_TO": [
            {
                "edge_id": f"WAT-{aoi_id.upper()}-01",
                "src_id": wat_id,
                "dst_id": hosp_id_1,
                "rel_type": "SUPPLIES_WATER_TO",
                "pipeline_dia_mm": 450,
                "flow_mld": 8.5,
                "is_active": False,
                "cascade_weight": 0.94,
            },
            {
                "edge_id": f"WAT-{aoi_id.upper()}-02",
                "src_id": wat_id,
                "dst_id": shel_id_1,
                "rel_type": "SUPPLIES_WATER_TO",
                "pipeline_dia_mm": 300,
                "flow_mld": 4.2,
                "is_active": False,
                "cascade_weight": 0.91,
            },
        ],
        "COVERS_COMMS": [
            {
                "edge_id": f"COM-{aoi_id.upper()}-01",
                "src_id": tow_id,
                "dst_id": hosp_id_1,
                "rel_type": "COVERS_COMMS",
                "signal_dbm": -72.0,
                "bandwidth_mbps": 45.0,
                "is_active": True,
                "cascade_weight": 0.89,
            },
            {
                "edge_id": f"COM-{aoi_id.upper()}-02",
                "src_id": tow_id,
                "dst_id": shel_id_1,
                "rel_type": "COVERS_COMMS",
                "signal_dbm": -76.0,
                "bandwidth_mbps": 35.0,
                "is_active": True,
                "cascade_weight": 0.88,
            },
        ],
        "EVACUATES_TO": [
            {
                "edge_id": f"EVAC-{aoi_id.upper()}-01",
                "src_id": hosp_id_1,
                "dst_id": shel_id_1,
                "rel_type": "EVACUATES_TO",
                "corridor_distance_m": 1850.0,
                "estimated_time_s": 420.0,
                "patient_capacity": 120,
                "is_viable": True,
            },
            {
                "edge_id": f"EVAC-{aoi_id.upper()}-02",
                "src_id": fz_id_1,
                "dst_id": shel_id_2,
                "rel_type": "EVACUATES_TO",
                "corridor_distance_m": 2400.0,
                "estimated_time_s": 540.0,
                "patient_capacity": 350,
                "is_viable": True,
            },
        ],
    }
    return infra_nodes, infra_edges


def _write_sarvam_fixtures(fixtures_dir: Path) -> dict[str, Any]:
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    audio_path = fixtures_dir / "velachery_substation_spark.wav"
    with wave.open(str(audio_path), "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        samples = [int(6000 * math.sin(2 * math.pi * 440.0 * (i / 16000.0))) for i in range(8000)]
        wf.writeframes(struct.pack(f"<{len(samples)}h", *samples))

    manifest = {
        "audio_fixtures": [
            {
                "id": "fix-audio-chennai-01",
                "aoi_id": "chennai",
                "file": "velachery_substation_spark.wav",
                "language_code": "ta-IN",
                "codemix_transcript": "Anna, Velachery SUB-CHENNAI-33KV-01 transformer spark aagudhu, CUL-CHENNAI-01 culvert la 1.2 meter thanni!",
                "english_translation": "Brother, the Velachery SUB-CHENNAI-33KV-01 transformer is sparking, and there is 1.2 meters of water at culvert CUL-CHENNAI-01!",
                "lat": 12.9570,
                "lon": 80.2110,
                "claimed_depth_m": 1.25,
            },
            {
                "id": "fix-audio-wayanad-01",
                "aoi_id": "wayanad",
                "file": "velachery_substation_spark.wav",
                "language_code": "ml-IN",
                "codemix_transcript": "Chooralmala BR-WAYANAD-01 bridge inte aduthu landslide undayi, SUB-WAYANAD-33KV-01 feeder line cut aayi!",
                "english_translation": "A landslide occurred near the Chooralmala BR-WAYANAD-01 bridge, and the SUB-WAYANAD-33KV-01 feeder line is cut!",
                "lat": 11.5470,
                "lon": 76.1260,
                "claimed_depth_m": 1.40,
            },
        ],
        "vision_fixtures": [
            {
                "id": "fix-vision-shelter-ta-01",
                "aoi_id": "chennai",
                "shelter_id": "SHEL-CHENNAI-01",
                "language_code": "ta-IN",
                "extracted_markdown": "| முகாம் பெயர் (Shelter) | மொத்த நபர்கள் (Occupancy) | மருத்துவ தேவை (Medical) |\n|---|---|---|\n| Velachery HSS Relief Camp (SHEL-CHENNAI-01) | 312 | 18 |",
                "parsed_occupancy": 312,
            }
        ],
    }
    (fixtures_dir / "sarvam_test_manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def build_multiplex_bundle(aoi_ids: list[str], output_dir: Path) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    nodes_by_label: dict[str, list[dict[str, Any]]] = {
        "MicroWatershed": [],
        "DrainageNode": [],
        "FloodZone": [],
        "RoadJunction": [],
        "RoadSegment": [],
        "Bridge": [],
        "Culvert": [],
        "Substation": [],
        "WaterFacility": [],
        "TelecomTower": [],
        "Hospital": [],
        "ReliefShelter": [],
        "SupplyDepot": [],
    }
    edges_by_type: dict[str, list[dict[str, Any]]] = {
        "DRAINS_INTO": [],
        "INUNDATES": [],
        "CONNECTS_TO": [],
        "CARRIES_CORRIDOR": [],
        "POWERS": [],
        "SUPPLIES_WATER_TO": [],
        "COVERS_COMMS": [],
        "EVACUATES_TO": [],
    }

    for aoi_id in aoi_ids:
        base_lat, base_lon, base_elev = AOI_CENTERS.get(aoi_id, (12.965, 80.220, 6.5))
        ws, drains, fz, drain_edges = _generate_aoi_hydrological_layer(aoi_id, base_lat, base_lon, base_elev)
        nodes_by_label["MicroWatershed"].extend(ws)
        nodes_by_label["DrainageNode"].extend(drains)
        nodes_by_label["FloodZone"].extend(fz)
        edges_by_type["DRAINS_INTO"].extend(drain_edges)

        juncs, segs, brs, culs, conn_edges, corr_edges = _generate_aoi_transport_layer(
            aoi_id, base_lat, base_lon, base_elev
        )
        nodes_by_label["RoadJunction"].extend(juncs)
        nodes_by_label["RoadSegment"].extend(segs)
        nodes_by_label["Bridge"].extend(brs)
        nodes_by_label["Culvert"].extend(culs)
        edges_by_type["CONNECTS_TO"].extend(conn_edges)
        edges_by_type["CARRIES_CORRIDOR"].extend(corr_edges)

        infra_nodes, infra_edges = _generate_aoi_infrastructure_layer(aoi_id, juncs)
        for label, items in infra_nodes.items():
            nodes_by_label[label].extend(items)
        for rel_type, items in infra_edges.items():
            edges_by_type[rel_type].extend(items)

    nodes_path = output_dir / "nodes.json"
    edges_path = output_dir / "edges.json"
    nodes_path.write_text(json.dumps(nodes_by_label, indent=2), encoding="utf-8")
    edges_path.write_text(json.dumps(edges_by_type, indent=2), encoding="utf-8")

    _write_sarvam_fixtures(output_dir / "fixtures")

    total_nodes = sum(len(v) for v in nodes_by_label.values())
    total_edges = sum(len(v) for v in edges_by_type.values())
    total_bytes = sum(p.stat().st_size for p in output_dir.rglob("*") if p.is_file())
    bundle_size_mb = round(total_bytes / (1024 * 1024), 4)

    manifest = {
        "aoi_ids": aoi_ids,
        "total_nodes": total_nodes,
        "total_edges": total_edges,
        "node_counts": {k: len(v) for k, v in nodes_by_label.items()},
        "edge_counts": {k: len(v) for k, v in edges_by_type.items()},
        "bundle_size_mb": bundle_size_mb,
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build NIRANTAR 4-layer multiplex seed bundle")
    parser.add_argument("--aois", default="chennai,wayanad,aizawl")
    parser.add_argument("--output-dir", default="data/seed_bundle")
    args = parser.parse_args()
    summary = build_multiplex_bundle(
        [a.strip() for a in args.aois.split(",") if a.strip()],
        Path(args.output_dir),
    )
    print(json.dumps(summary, indent=2))

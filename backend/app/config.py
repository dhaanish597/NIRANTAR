"""All tunable constants live here (CLAUDE.md §4/§6) — no magic numbers scattered elsewhere.

Automatically loads `/Users/dhaanish/Documents/NIRANTAR/.env` into `os.environ` at import time so
live `NVIDIA_API_KEY`, `SARVAM_API_KEY`, and `NEO4J_*` credentials work out-of-the-box in both
FastAPI and standalone CLI/test runs without requiring third-party `python-dotenv`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import os
from pathlib import Path


def _load_dotenv_if_present() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    for candidate in (repo_root / ".env", repo_root / "backend" / ".env"):
        if not candidate.is_file():
            continue
        for raw_line in candidate.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if key and not os.environ.get(key):
                os.environ[key] = val


_load_dotenv_if_present()

try:
    from pydantic import BaseModel, Field
except ImportError:  # pragma: no cover - stdlib fallback for bare unittest environments
    class BaseModel:  # type: ignore[no-redef]
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)

        def model_dump(self, **_kwargs) -> dict:
            return dict(self.__dict__)

    def Field(default=None, **_kwargs):  # type: ignore[misc]
        return default


NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "meta/llama-3.1-8b-instruct")
NVIDIA_VISION_MODEL = os.getenv("NVIDIA_VISION_MODEL", "meta/llama-3.2-11b-vision-instruct")
NVIDIA_BASE_URL = os.getenv("NVIDIA_BASE_URL", "https://integrate.api.nvidia.com/v1")
NVIDIA_TIMEOUT_SECONDS = float(os.getenv("NVIDIA_TIMEOUT_SECONDS", "8"))

# Neo4j AuraDB Multiplex Knowledge Graph Configuration
NEO4J_URI = os.getenv("NEO4J_URI", "")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
NEO4J_DATABASE = os.getenv("NEO4J_DATABASE", "neo4j")

# Sovereign Sarvam AI Multimodal Suite Configuration
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
SARVAM_STT_MODEL = os.getenv("SARVAM_STT_MODEL", "saaras:v4")
SARVAM_TTS_MODEL = os.getenv("SARVAM_TTS_MODEL", "bulbul:v4-flash")
SARVAM_TTS_FALLBACK_MODEL = os.getenv("SARVAM_TTS_FALLBACK_MODEL", "bulbul:v3")
SARVAM_VISION_MODEL = os.getenv("SARVAM_VISION_MODEL", "sarvam-vision")

# Neuro-Symbolic Agent Orchestrator Routing & Safety Caps
AGENT_FAST_MODEL = os.getenv("AGENT_FAST_MODEL", NVIDIA_MODEL)
AGENT_REASONING_MODEL = os.getenv("AGENT_REASONING_MODEL", "meta/llama-3.1-70b-instruct")
AGENT_MAX_ITERATIONS = int(os.getenv("AGENT_MAX_ITERATIONS", "5"))

# Domain Keyterms for Sarvam Saaras v4 Acoustic Prompt Biasing
AOI_KEYTERMS: list[str] = [
    "Velachery",
    "Pallikaranai",
    "Perumbakkam",
    "Saidapet",
    "TANGEDCO",
    "TNEB",
    "CMWSSB",
    "Chooralmala",
    "Mundakkai",
    "Meppadi",
    "Aizawl",
    "Durtlang",
    "Hunthar",
    "Tupul",
    "Rajakaluve",
    "BESCOM",
    "33kV",
    "11kV",
    "Culvert",
    "Substation",
    "ICU",
    "NDRF",
    "SDRF",
]


@dataclass
class Settings:
    """Structured settings container for GraphRAG, Neo4j AuraDB, and Sarvam AI services."""

    neo4j_uri: str = field(default_factory=lambda: os.getenv("NEO4J_URI", NEO4J_URI))
    neo4j_user: str = field(default_factory=lambda: os.getenv("NEO4J_USER", NEO4J_USER))
    neo4j_password: str = field(default_factory=lambda: os.getenv("NEO4J_PASSWORD", NEO4J_PASSWORD))
    neo4j_database: str = field(default_factory=lambda: os.getenv("NEO4J_DATABASE", NEO4J_DATABASE))
    sarvam_api_key: str = field(default_factory=lambda: os.getenv("SARVAM_API_KEY", SARVAM_API_KEY))
    sarvam_stt_model: str = field(default_factory=lambda: os.getenv("SARVAM_STT_MODEL", SARVAM_STT_MODEL))
    sarvam_tts_flash_model: str = field(default_factory=lambda: os.getenv("SARVAM_TTS_MODEL", SARVAM_TTS_MODEL))
    sarvam_tts_fallback_model: str = field(
        default_factory=lambda: os.getenv("SARVAM_TTS_FALLBACK_MODEL", SARVAM_TTS_FALLBACK_MODEL)
    )
    sarvam_vision_model: str = field(default_factory=lambda: os.getenv("SARVAM_VISION_MODEL", SARVAM_VISION_MODEL))
    nvidia_api_key: str = field(default_factory=lambda: os.getenv("NVIDIA_API_KEY", NVIDIA_API_KEY or ""))
    nvidia_vision_model: str = field(default_factory=lambda: os.getenv("NVIDIA_VISION_MODEL", NVIDIA_VISION_MODEL))
    nvidia_base_url: str = field(default_factory=lambda: os.getenv("NVIDIA_BASE_URL", NVIDIA_BASE_URL))
    agent_fast_model: str = field(default_factory=lambda: os.getenv("AGENT_FAST_MODEL", AGENT_FAST_MODEL))
    agent_reasoning_model: str = field(
        default_factory=lambda: os.getenv("AGENT_REASONING_MODEL", AGENT_REASONING_MODEL)
    )
    agent_max_iterations: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_ITERATIONS", str(AGENT_MAX_ITERATIONS))))


class AoiConfig(BaseModel):
    id: str
    name: str
    center_lat: float
    center_lon: float
    bbox: tuple[float, float, float, float]
    utm_epsg: int
    imd_district_name: str | None = None


AOIS: dict[str, AoiConfig] = {
    "chennai": AoiConfig(
        id="chennai",
        name="Chennai (Velachery–Pallikaranai), Tamil Nadu",
        center_lat=12.9650,
        center_lon=80.2200,
        bbox=(80.1800, 12.9200, 80.2600, 13.0100),
        utm_epsg=32644,
        imd_district_name="Chennai",
    ),
    "aizawl": AoiConfig(
        id="aizawl",
        name="Aizawl, Mizoram",
        center_lat=23.7307,
        center_lon=92.7173,
        bbox=(92.60, 23.60, 92.85, 23.85),
        utm_epsg=32646,
        imd_district_name="Aizawl",
    ),
    "wayanad": AoiConfig(
        id="wayanad",
        name="Wayanad (Meppadi), Kerala",
        center_lat=11.61,
        center_lon=76.12,
        bbox=(75.97, 11.46, 76.27, 11.76),
        utm_epsg=32643,
        imd_district_name="Wayanad",
    ),
    "tupul": AoiConfig(
        id="tupul",
        name="Noney (Tupul), Manipur",
        center_lat=24.7667,
        center_lon=93.75,
        bbox=(93.60, 24.6167, 93.90, 24.9167),
        utm_epsg=32646,
        imd_district_name="Noney",
    ),
}


def get_aoi(aoi_id: str) -> AoiConfig:
    try:
        return AOIS[aoi_id]
    except KeyError:
        raise KeyError(f"unknown AOI {aoi_id!r}; known AOIs: {sorted(AOIS)}") from None


class EscalationConfig(BaseModel):
    yellow_threshold: float = Field(default=0.25, ge=0.0, le=1.0)
    orange_threshold: float = Field(default=0.5, ge=0.0, le=1.0)
    red_threshold: float = Field(default=0.75, ge=0.0, le=1.0)
    downgrade_hysteresis_margin: float = Field(default=0.1, ge=0.0, le=1.0)


ESCALATION = EscalationConfig(
    yellow_threshold=0.25,
    orange_threshold=0.5,
    red_threshold=0.75,
    downgrade_hysteresis_margin=0.1,
)

# Phase 2 — Impact Layer Constants
RUNOUT_TRIGGER_P_FAIL = 0.5
RUNOUT_ANGLE_OF_REACH_DEG = 25.0
RUNOUT_SPREAD_HALF_ANGLE_DEG = 15.0
P_CRIT_ROAD = 0.7
P_CRIT_BRIDGE = 0.5

EPS_WEIGHTS: dict[str, float] = {
    "p_fail": 0.35,
    "pop": 0.25,
    "rii": 0.25,
    "shelter": 0.15,
}
EPS_P1_THRESHOLD = 0.65
EPS_P2_THRESHOLD = 0.35
EPS_POPULATION_NORM_REF = 200.0
EPS_SHELTER_ACCESS_REF_KM = 5.0

ROAD_CLEARANCE_HOURS_BY_CLASS: dict[str, float] = {
    "trunk": 24.0,
    "primary": 24.0,
    "secondary": 18.0,
    "tertiary": 12.0,
    "residential": 6.0,
    "unclassified": 6.0,
    "service": 4.0,
}
ROAD_CLEARANCE_HOURS_DEFAULT = 12.0
BRIDGE_CLEARANCE_MULTIPLIER = 2.0

# Phase 3 — Decision Layer Constants
WINDOW_CRITICAL_EXCEEDANCE_RATIO = 1.0
WINDOW_MIN_TREND_POINTS = 3
WINDOW_MAX_FORECAST_HOURS = 72.0
WINDOW_MARGIN_FRACTION = 0.25
WINDOW_MIN_MARGIN_HOURS = 0.5
WINDOW_IMMEDIATE_UPPER_HOURS = 1.0

ROUTING_ALPHA_P_FAIL = 3.0
ROUTING_BETA_SLOPE = 1.0
ROUTING_WALKING_SPEED_KMH = 4.0

ACTION_CARD_VALID_FOR_HOURS = 6.0
WHAT_TO_CARRY_CHECKLIST: list[str] = [
    "Identity documents",
    "Essential medicines",
    "Torch/flashlight with spare batteries",
    "Drinking water",
    "Mobile phone with charger or power bank",
    "Warm/weatherproof clothing",
]
ACTION_CARD_CONTACT_PLACEHOLDER = (
    "District Disaster Management Authority (DDMA) control room — "
    "contact number not yet configured for this AOI (placeholder, not a real number)"
)

PIPELINE_EXCEEDANCE_HISTORY_LEN = 50

# Rate Limiting Configuration
RATE_LIMIT_ENABLED = os.getenv("RATE_LIMIT_ENABLED", "true").strip().lower() not in {
    "0",
    "false",
    "no",
}
RATE_LIMIT_COMMANDER_CHAT_MAX = 20
RATE_LIMIT_COMMANDER_CHAT_WINDOW_SECONDS = 60.0
RATE_LIMIT_CITIZEN_REPORT_MAX = 10
RATE_LIMIT_CITIZEN_REPORT_WINDOW_SECONDS = 60.0
RATE_LIMIT_MAX_TRACKED_CLIENTS = 2048

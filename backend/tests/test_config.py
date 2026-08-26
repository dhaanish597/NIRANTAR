"""Contract test for config.py."""
from __future__ import annotations

import pytest

from app.config import AOIS, get_aoi


def test_aizawl_aoi_is_registered():
    aoi = get_aoi("aizawl")
    assert aoi.id == "aizawl"
    assert aoi.bbox[0] < aoi.center_lon < aoi.bbox[2]  # center inside bbox, lon
    assert aoi.bbox[1] < aoi.center_lat < aoi.bbox[3]  # center inside bbox, lat


def test_unknown_aoi_raises_with_known_ids_listed():
    with pytest.raises(KeyError, match="aizawl"):
        get_aoi("does-not-exist")


def test_aois_dict_matches_get_aoi():
    for aoi_id in AOIS:
        assert get_aoi(aoi_id) is AOIS[aoi_id]


@pytest.mark.parametrize("aoi_id", ["wayanad", "tupul"])
def test_new_aoi_is_registered_with_center_inside_bbox(aoi_id: str):
    """BUILD_PLAN.md tasks 4.4/4.5's own commit notes flagged this exact gap: 'aoi_id: wayanad/
    tupul is NOT registered in backend/app/config.py'. Closed here."""
    aoi = get_aoi(aoi_id)
    assert aoi.id == aoi_id
    assert aoi.bbox[0] < aoi.center_lon < aoi.bbox[2]
    assert aoi.bbox[1] < aoi.center_lat < aoi.bbox[3]


def test_wayanad_utm_zone_is_43n():
    # floor((76.12 + 180) / 6) + 1 == 43 (WGS 84 / UTM zone 43N covers 72-78E)
    assert get_aoi("wayanad").utm_epsg == 32643


def test_tupul_utm_zone_is_46n_same_as_aizawl():
    # floor((93.75 + 180) / 6) + 1 == 46 (WGS 84 / UTM zone 46N covers 90-96E) -- same zone as
    # Aizawl (92.7E), since Noney (93.75E) is geographically close and falls in the same zone.
    assert get_aoi("tupul").utm_epsg == 32646

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

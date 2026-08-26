"""Direct contract test for ingest/live/earthdata_common.py (extracted from imerg.py in task 1.7
so smap.py doesn't duplicate the cross-host-redirect Basic Auth fix — see that module's docstring
for the full rationale). imerg.py's and smap.py's own test suites already exercise this
indirectly through `_EarthdataSession`; this file tests the shared module directly so the
contract stands on its own regardless of either adapter's internals changing later."""
from __future__ import annotations

from app.ingest.live.earthdata_common import EarthdataSession, EARTHDATA_HOST_SUFFIXES, HDF5_MAGIC


def test_hdf5_magic_is_the_real_signature():
    # The canonical 8-byte HDF5 file signature (HDF Group spec) — every real .h5/.HDF5 file
    # starts with exactly these bytes.
    assert HDF5_MAGIC == b"\x89HDF\r\n\x1a\n"
    assert len(HDF5_MAGIC) == 8


class TestEarthdataSessionAuthForwarding:
    def test_keeps_auth_within_gesdisc(self):
        session = EarthdataSession("user", "pass")

        class FakeRequest:
            headers = {"Authorization": "Basic xyz"}
            url = "https://gpm1.gesdisc.eosdis.nasa.gov/data/some/granule.HDF5"

        session.rebuild_auth(FakeRequest(), response=None)
        assert "Authorization" in FakeRequest.headers

    def test_keeps_auth_within_nsidc(self):
        session = EarthdataSession("user", "pass")

        class FakeRequest:
            headers = {"Authorization": "Basic xyz"}
            url = "https://n5eil01u.ecs.nsidc.org/SMAP/SPL3SMP_E.006/2026.08.25/granule.h5"

        session.rebuild_auth(FakeRequest(), response=None)
        assert "Authorization" in FakeRequest.headers

    def test_keeps_auth_at_the_login_host(self):
        session = EarthdataSession("user", "pass")

        class FakeRequest:
            headers = {"Authorization": "Basic xyz"}
            url = "https://urs.earthdata.nasa.gov/oauth/redirect"

        session.rebuild_auth(FakeRequest(), response=None)
        assert "Authorization" in FakeRequest.headers

    def test_strips_auth_outside_the_trusted_family(self):
        session = EarthdataSession("user", "pass")

        class FakeRequest:
            headers = {"Authorization": "Basic xyz"}
            url = "https://evil.example.com/steal"

        session.rebuild_auth(FakeRequest(), response=None)
        assert "Authorization" not in FakeRequest.headers

    def test_no_auth_header_present_is_a_noop(self):
        session = EarthdataSession("user", "pass")

        class FakeRequest:
            headers: dict = {}
            url = "https://evil.example.com/steal"

        session.rebuild_auth(FakeRequest(), response=None)  # must not raise
        assert FakeRequest.headers == {}

    def test_credentials_stored_as_basic_auth_tuple(self):
        session = EarthdataSession("alice", "s3cr3t")
        assert session.auth == ("alice", "s3cr3t")


def test_host_suffix_list_covers_both_daacs_and_login_host():
    # "eosdis.nasa.gov" (GES DISC), "nsidc.org" (NSIDC DAAC), "earthdata.nasa.gov" (the
    # urs.earthdata.nasa.gov login host every redirect round-trips through) must all be present —
    # DAAC-agnostic on purpose, see module docstring.
    assert "eosdis.nasa.gov" in EARTHDATA_HOST_SUFFIXES
    assert "nsidc.org" in EARTHDATA_HOST_SUFFIXES
    assert "earthdata.nasa.gov" in EARTHDATA_HOST_SUFFIXES

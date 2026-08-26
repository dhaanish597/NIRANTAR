"""Shared NASA Earthdata Login (EDL) plumbing for `ingest/live/` adapters that download from an
EOSDIS DAAC over HTTPS with HTTP Basic Auth (GES DISC for `imerg.py`, task 1.6; NSIDC DAAC for
`smap.py`, task 1.7). Extracted here (session 2026-08-26, task 1.7) instead of duplicated a second
time — both DAACs are fronted by the same `urs.earthdata.nasa.gov` login redirect and both hit the
exact same `requests` cross-host-redirect Authorization-header-stripping problem `imerg.py`'s
module docstring documents in detail.

`imerg.py` still exposes `_EarthdataSession`/`HDF5_MAGIC` at module scope (re-exported from here)
so its existing tests, which monkeypatch/reference those names directly on `imerg`, keep working
unchanged — this is a pure extraction, not a behaviour change, and `imerg.py`'s own 18-test suite
was re-run after this refactor to confirm that (see this session's commit).
"""
from __future__ import annotations

from urllib.parse import urlparse

import requests

# Every NASA EOSDIS DAAC (GES DISC for IMERG, NSIDC DAAC for SMAP, ...) authenticates through the
# same Earthdata Login service and redirects back through the requesting DAAC's own host — so the
# trusted-host family is DAAC-agnostic, not GES-DISC-specific, despite imerg.py's original naming.
EARTHDATA_HOST_SUFFIXES = ("earthdata.nasa.gov", "eosdis.nasa.gov", "nsidc.org")

HDF5_MAGIC = b"\x89HDF\r\n\x1a\n"


class EarthdataSession(requests.Session):
    """Re-attaches HTTP Basic Auth across redirects within the Earthdata/EOSDIS/NSIDC host family.

    `requests` strips the Authorization header on any cross-host redirect by default (a
    deliberate security default, same one `curl` needs `--location-trusted` to override). NASA
    DAAC downloads (GES DISC, NSIDC DAAC, ...) redirect through `urs.earthdata.nasa.gov` and back
    to the originating DAAC host, so without this override every download attempt gets a silent
    401. Confirmed necessary against a real GES DISC request in task 1.6 (see imerg.py's module
    docstring) — NSIDC DAAC is documented (NSIDC user guide, SPL3SMP_E v5, section "Temporal
    Information") to require the identical Earthdata Login account, so the same fix applies; not
    independently re-verified against a live NSIDC redirect in this session because outbound
    network access to `n5eil01u.ecs.nsidc.org` was itself blocked in this environment (see
    smap.py's module docstring) — the fix is the DAAC-agnostic part of the mechanism (`requests`'
    own redirect behaviour), not something NSIDC-specific that could differ.
    """

    def __init__(self, username: str, password: str):
        super().__init__()
        self.auth = (username, password)

    def rebuild_auth(self, prepared_request, response) -> None:
        headers = prepared_request.headers
        if "Authorization" not in headers:
            return
        redirect_host = urlparse(prepared_request.url).hostname or ""
        if any(redirect_host.endswith(suffix) for suffix in EARTHDATA_HOST_SUFFIXES):
            return  # still within the trusted family — keep the header
        del headers["Authorization"]

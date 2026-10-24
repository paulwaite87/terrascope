#!/usr/bin/env python3
"""SoilMoistureCollector.collect() against stubbed NASA responses, in a temporary workdir,
asserted on the stored grid and its granule (lib/soil_moisture.py's loader) -- never on
collector internals. The CMR search answer is the real recorded one
(tests/fixtures/smap_cmr_latest.json, 2026-10-22) and the OPeNDAP answers are built in
the real chunked DAP4 layout (see test_soil_moisture_opendap.py) around a small grid, with
GRID_SHAPE patched to match. Prior art: test_aurora_collector.py's stubbed-_get style."""

import copy
import json
import zlib
from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from terrascope.collectors.base import CollectorBase
from terrascope.collectors.soil_moisture import SoilMoistureCollector
from terrascope.db.process_status_adapter import FakeProcessStatusAdapter
from terrascope.lib import soil_moisture as sm

CMR = json.loads((Path(__file__).parent / "fixtures" / "smap_cmr_latest.json").read_text())
GRANULE_ID = "G4384203835-NSIDC_CPRD"  # the recorded newest granule, 2026-10-20 21:00Z
SHAPE = (3, 4)


@pytest.fixture(autouse=True)
def small_grid_and_token(monkeypatch):
    monkeypatch.setattr(sm, "GRID_SHAPE", SHAPE)
    monkeypatch.setenv("EARTHDATA_TOKEN", "secret-token")


class FakeResponse:
    def __init__(self, *, doc=None, content=b""):
        self._doc = doc
        self.content = content if doc is None else json.dumps(doc).encode()

    def json(self):
        return self._doc


def chunk(flags, payload):
    return bytes([flags]) + len(payload).to_bytes(3, "big") + payload


def dap(values):
    data = np.asarray(values, dtype="<f4").tobytes()
    crc = zlib.crc32(data).to_bytes(4, "little")
    return chunk(0x04, b"<Dataset/>") + chunk(0x04, data + crc) + chunk(0x05, b"")


PERCENTILE = np.array([[10.0, 50.0, 90.0, -9999.0], [0.0, 100.0, 25.5, -9999.0], [75.0, 5.0, 60.0, 33.0]])
LAT_COLUMN = np.array([[60.0], [10.0], [-40.0]])  # latitude by row, north first
LON_ROW = np.array([[-135.0, -45.0, 45.0, 135.0]])  # longitude by column


def granule(granule_id=GRANULE_ID, start="2026-10-20T21:00:00.000Z"):
    doc = copy.deepcopy(CMR)
    entry = doc["feed"]["entry"][0]
    entry["id"], entry["time_start"] = granule_id, start
    return doc


class Nasa:
    """Stand-in for CMR plus OPeNDAP, routing on the URL like the real servers."""

    def __init__(self, cmr=None, percentile=PERCENTILE, fail=None):
        self.cmr = granule() if cmr is None else cmr
        self.percentile = percentile
        self.fail = fail  # substring of a URL to make fail like a failed fetch
        self.urls = []
        self.headers = []

    def __call__(self, url, **kwargs):
        self.urls.append(url)
        self.headers.append(kwargs.get("headers", {}))
        if self.fail and self.fail in url:
            return None
        if "cmr.earthdata.nasa.gov" in url:
            return FakeResponse(doc=self.cmr)
        if "sm_rootzone_pctl" in url:
            return FakeResponse(content=dap(self.percentile))
        if "cell_lat" in url:
            return FakeResponse(content=dap(LAT_COLUMN))
        if "cell_lon" in url:
            return FakeResponse(content=dap(LON_ROW))
        raise AssertionError(f"unexpected request: {url}")

    def opendap_calls(self):
        return [u for u in self.urls if "opendap.earthdata.nasa.gov" in u]


def make_collector(workdir):
    c = SoilMoistureCollector.__new__(SoilMoistureCollector)
    c.settings = {}

    def fake_get_setting(section, key, default=None):
        if section == "common" and key == "workdir":
            return workdir
        return default

    c.config = MagicMock()
    c.config.get_setting.side_effect = fake_get_setting
    c.datasource_url = MagicMock(return_value=sm.CMR_GRANULES_URL)
    c.process_status_adapter = FakeProcessStatusAdapter()
    return c


def run_collect(c, nasa):
    with patch.object(CollectorBase, "_get", side_effect=nasa):
        c.collect()


def stored(tmp_path):
    return sm.load_soil_moisture(sm.soil_moisture_cache_path(str(tmp_path)))


def test_the_newest_granule_is_stored_with_its_grid_vectors_and_time(tmp_path):
    c = make_collector(str(tmp_path))

    run_collect(c, Nasa())

    percentile, lat, lon, granule_id, start = stored(tmp_path)
    assert percentile.shape == SHAPE
    assert percentile[0, 0] == 10.0 and percentile[1, 1] == 100.0 and percentile[2, 3] == 33.0
    assert np.isnan(percentile[0, 3]) and np.isnan(percentile[1, 3])  # the -9999 fill is no data
    np.testing.assert_array_equal(lat, [60.0, 10.0, -40.0])
    np.testing.assert_array_equal(lon, [-135.0, -45.0, 45.0, 135.0])
    assert granule_id == GRANULE_ID
    assert start == "2026-10-20T21:00:00Z"


def test_only_the_one_variable_and_its_coordinate_slices_are_requested_with_the_token(tmp_path):
    nasa = Nasa()

    run_collect(make_collector(str(tmp_path)), nasa)

    calls = nasa.opendap_calls()
    assert len(calls) == 3
    assert any("dap4.ce=/Geophysical_Data/sm_rootzone_pctl" in u and "%5B" not in u for u in calls)
    assert any("/cell_lat%5B0:2%5D%5B0%5D" in u for u in calls)  # first column, every row
    assert any("/cell_lon%5B0%5D%5B0:3%5D" in u for u in calls)  # first row, every column
    assert all(u.startswith(
        "https://opendap.earthdata.nasa.gov/collections/C3480440870-NSIDC_CPRD/granules/"
        "SMAP_L4_SM_gph_20261020T223000_Vv8013_001.h5_u9loH5HD.dap?"
    ) for u in calls)
    opendap_headers = [h for u, h in zip(nasa.urls, nasa.headers) if "opendap" in u]
    assert all(h["Authorization"] == "Bearer secret-token" for h in opendap_headers)


def test_a_granule_already_held_is_not_downloaded_again(tmp_path):
    c = make_collector(str(tmp_path))
    run_collect(c, Nasa())
    second = Nasa()

    run_collect(c, second)

    assert second.opendap_calls() == []
    assert stored(tmp_path)[3] == GRANULE_ID


def test_a_newer_granule_replaces_the_stored_one(tmp_path):
    c = make_collector(str(tmp_path))
    run_collect(c, Nasa())
    newer = np.full(SHAPE, 42.0)

    run_collect(
        c,
        Nasa(cmr=granule("G9999-NSIDC_CPRD", "2026-10-21T00:00:00.000Z"), percentile=newer),
    )

    percentile, _, _, granule_id, start = stored(tmp_path)
    assert granule_id == "G9999-NSIDC_CPRD"
    assert start == "2026-10-21T00:00:00Z"
    assert (percentile == 42.0).all()


@pytest.mark.parametrize(
    "broken",
    [
        {"fail": "cmr.earthdata.nasa.gov"},  # the search itself failed
        {"fail": "sm_rootzone_pctl"},  # the data request failed
        {"fail": "cell_lat"},  # a coordinate request failed
        {"percentile": np.ones((2, 2))},  # wrong-shaped array
    ],
    ids=["search-fails", "data-fails", "coordinates-fail", "wrong-shape"],
)
def test_a_failed_or_malformed_fetch_leaves_the_previous_data_and_is_reported(tmp_path, broken):
    c = make_collector(str(tmp_path))
    run_collect(c, Nasa())

    # Raised so the orchestrator records a failure (Data Status shows the error rather
    # than reporting a stale layer as freshly updated), same as AuroraCollector.
    with pytest.raises(RuntimeError):
        run_collect(
            c,
            Nasa(cmr=granule("G9999-NSIDC_CPRD", "2026-10-21T00:00:00.000Z"), **broken),
        )

    _, _, _, granule_id, start = stored(tmp_path)
    assert granule_id == GRANULE_ID
    assert start == "2026-10-20T21:00:00Z"


def test_a_truncated_stream_leaves_the_previous_data_and_is_reported(tmp_path):
    class CutShort(Nasa):
        def __call__(self, url, **kwargs):
            r = super().__call__(url, **kwargs)
            if "sm_rootzone_pctl" in url:
                return FakeResponse(content=r.content[:-9])  # lose the end and its checksum
            return r

    c = make_collector(str(tmp_path))
    run_collect(c, Nasa())

    with pytest.raises(RuntimeError):
        run_collect(c, CutShort(cmr=granule("G9999-NSIDC_CPRD", "2026-10-21T00:00:00.000Z")))

    assert stored(tmp_path)[3] == GRANULE_ID


def test_a_search_with_no_granules_is_reported(tmp_path):
    c = make_collector(str(tmp_path))

    with pytest.raises(RuntimeError):
        run_collect(c, Nasa(cmr={"feed": {"entry": []}}))


def test_without_a_token_nothing_is_requested_or_stored(tmp_path, monkeypatch):
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    nasa = Nasa()

    run_collect(make_collector(str(tmp_path)), nasa)

    assert nasa.urls == []
    assert not Path(sm.soil_moisture_cache_path(str(tmp_path))).exists()

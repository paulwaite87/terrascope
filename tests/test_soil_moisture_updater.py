#!/usr/bin/env python3
"""SoilMoistureUpdater (tasks/soil_moisture.py): the collector's cached SMAP percentile grid
-> the raw data texture the GPU fill layer reads (the diverging colour ramp and opacity
are applied in the browser), plus the sidecar carrying the granule time shown. The cache is
a small synthetic grid in the real layout (rows north first, unevenly spaced latitudes, NaN
where the product has no value). Asserted on the PNG that lands on disk, decoded with the
16-bit R*256+G convention of lib/texture.py's encode_frames: a 0.1 degree equirectangular
texture, row 0 at the north pole, column 0 at -180. Prior art: test_sea_ice_updater.py."""

import json
import os
import time

import numpy as np
from PIL import Image

from terrascope.lib.soil_moisture import save_soil_moisture, soil_moisture_cache_path
from terrascope.tasks.soil_moisture import SoilMoistureUpdater

LAT = np.array([60.0, 10.0, -40.0])               # north first, 50 degrees apart
LON = np.array([-135.0, -45.0, 45.0, 135.0])      # 90 degrees apart
NAN = np.nan
PERCENTILE = np.array([
    [10.0, 50.0, 90.0, NAN],
    [0.0, 100.0, 25.0, NAN],
    [75.0, 5.0, 60.0, 33.0],
])


def make_updater(workdir):
    u = SoilMoistureUpdater.__new__(SoilMoistureUpdater)
    u.workdir = str(workdir)
    u.section = "soil_moisture"
    u.output_path = str(workdir / "data" / "soil_moisture.png")
    return u


def cache(workdir, percentile=PERCENTILE, granule="G1-NSIDC_CPRD", start="2026-10-20T21:00:00Z"):
    save_soil_moisture(soil_moisture_cache_path(str(workdir)), percentile, LAT, LON, granule, start)


def decoded(path):
    """The texture as percentile 0..100 (float) and its alpha channel."""
    px = np.asarray(Image.open(path)).astype(np.float64)
    return (px[..., 0] * 256 + px[..., 1]) / 65535 * 100, px[..., 3]


def at(tex, lat, lon):
    """The pixel for a latitude and longitude in the 0.1 degree north-first texture."""
    return tex[int((90 - lat) / 0.1), int((lon + 180) / 0.1)]


def test_the_grid_is_drawn_north_first_from_minus_180_on_a_fixed_percentile_scale(tmp_path):
    cache(tmp_path)
    u = make_updater(tmp_path)

    u.run()

    tex, alpha = decoded(u.output_path)
    assert tex.shape == (1800, 3600)
    assert round(at(tex, 60, -135)) == 10    # top row of the grid, far-west column
    assert round(at(tex, 60, -45)) == 50
    assert round(at(tex, 10, -45)) == 100    # the wettest value reaches the top of the scale
    assert round(at(tex, 10, -135)) == 0     # and the driest the bottom
    assert round(at(tex, -40, 135)) == 33
    assert at(alpha, 60, -135) > 0


def test_each_value_covers_the_ground_nearest_to_it_out_to_the_dateline(tmp_path):
    cache(tmp_path)
    u = make_updater(tmp_path)

    u.run()

    tex, _ = decoded(u.output_path)
    # Rows are 60N and 10N: 36N is nearer 60N, 34N nearer 10N (the halfway line is 35N).
    assert round(at(tex, 36, -135)) == 10
    assert round(at(tex, 34, -135)) == 0
    # The westmost and eastmost columns belong to the -135 and +135 columns.
    assert round(at(tex, 60, -179.9)) == 10
    assert round(at(tex, -40, 179.9)) == 33


def test_cells_with_no_value_and_the_ground_beyond_the_grid_are_transparent(tmp_path):
    cache(tmp_path)
    u = make_updater(tmp_path)

    u.run()

    tex, alpha = decoded(u.output_path)
    assert at(alpha, 60, 135) == 0       # NaN: the product has no percentile here
    assert at(alpha, 10, 135) == 0
    assert at(alpha, 89.9, 0) == 0       # beyond the northernmost row (north of 85N)
    assert at(alpha, -85.0, 0) == 0      # beyond the southernmost row (south of -65)
    assert at(alpha, 10, -45) > 0        # a cell with a value is drawn


def test_the_granule_time_shown_is_written_beside_the_texture(tmp_path):
    cache(tmp_path, start="2026-10-20T21:00:00Z")
    u = make_updater(tmp_path)

    u.run()

    with open(tmp_path / "data" / "soil_moisture_meta.json") as f:
        meta = json.load(f)
    assert meta["soil_moisture"] == {"time": "2026-10-20T21:00:00Z"}


def test_nothing_is_rendered_before_the_cache_exists(tmp_path):
    u = make_updater(tmp_path)

    u.run()

    assert not os.path.exists(u.output_path)


def test_the_texture_is_rerendered_only_when_the_cache_is_newer(tmp_path):
    cache(tmp_path)
    u = make_updater(tmp_path)
    u.run()
    past = time.time() - 3600
    os.utime(u.output_path, (past, past))  # pretend the render is an hour old
    os.utime(soil_moisture_cache_path(str(tmp_path)), (past - 60, past - 60))  # ...cache older

    u.run()
    assert os.path.getmtime(u.output_path) == past  # nothing newer: left alone

    cache(tmp_path, percentile=np.full((3, 4), 80.0), granule="G2-NSIDC_CPRD",
          start="2026-10-21T00:00:00Z")
    u.run()
    assert os.path.getmtime(u.output_path) > past
    assert round(at(decoded(u.output_path)[0], 60, -135)) == 80
    with open(tmp_path / "data" / "soil_moisture_meta.json") as f:
        assert json.load(f)["soil_moisture"] == {"time": "2026-10-21T00:00:00Z"}

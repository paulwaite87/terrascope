#!/usr/bin/env python3
"""Soil Moisture layer rendering (Updater): SoilMoistureCollector's cached SMAP root-zone
soil moisture percentile (lib/soil_moisture.py) encoded as a raw data texture for
ui/modules/soil_moisture.js, issue #312's client-side-palette convention -- the diverging
colour ramp and opacity are applied in the browser, so neither re-renders anything here.

The percentile is encoded over a FIXED 0-100 domain, so a colour always means the same
thing from day to day. The source is the 9 km EASE-Grid 2.0 equal-area grid (rows
unevenly spaced in latitude, northernmost row about 84.66 N); it is resampled, each pixel
taking its nearest source cell, onto the 0.1 degree equirectangular grid the GPU fill
mesh samples (row 0 at the north pole, column 0 at -180). Pixels with no source value,
and those beyond the first and last source row, encode as transparent. A sidecar
carries the granule's time for the legend.
"""
import logging
import os

import numpy as np

from terrascope.lib.config import TerrascopeConfig
from terrascope.lib.soil_moisture import load_soil_moisture, soil_moisture_cache_path
from terrascope.lib.texture import encode_frames
from .common import MapData, Updater

logger = logging.getLogger(__name__)

# Percentile. Mirrored by ui/modules/soil_moisture.js's ENCODE_DOMAIN.
ENCODE_DOMAIN = (0.0, 100.0)
TEXTURE_STEP_DEG = 0.1


def _nearest_index(axis: np.ndarray, targets: np.ndarray):
    """For each target, the index of the nearest value in `axis` (ascending) and whether
    the target lies within that end cell's reach (half a spacing beyond the last value)."""
    right = np.clip(np.searchsorted(axis, targets), 1, len(axis) - 1)
    nearest = np.where(targets - axis[right - 1] <= axis[right] - targets, right - 1, right)
    half_first = (axis[1] - axis[0]) / 2
    half_last = (axis[-1] - axis[-2]) / 2
    inside = (targets >= axis[0] - half_first) & (targets <= axis[-1] + half_last)
    return nearest, inside


def texture_field(percentile: np.ndarray, lat: np.ndarray, lon: np.ndarray) -> np.ndarray:
    """The percentile grid (rows by `lat`, columns by `lon`, NaN = no data) as a
    (1800, 3600) north-first, -180-first field; NaN where there is nothing to draw."""
    n_rows = int(round(180 / TEXTURE_STEP_DEG))
    n_cols = int(round(360 / TEXTURE_STEP_DEG))
    tex_lat = 90.0 - TEXTURE_STEP_DEG * (np.arange(n_rows) + 0.5)
    tex_lon = -180.0 + TEXTURE_STEP_DEG * (np.arange(n_cols) + 0.5)

    lat_order = np.argsort(lat)
    lon_order = np.argsort(lon)
    grid = np.asarray(percentile, dtype=np.float32)[np.ix_(lat_order, lon_order)]
    row, row_ok = _nearest_index(np.asarray(lat, dtype=np.float64)[lat_order], tex_lat)
    col, col_ok = _nearest_index(np.asarray(lon, dtype=np.float64)[lon_order], tex_lon)

    field = grid[np.ix_(row, col)]
    field[~row_ok, :] = np.nan
    field[:, ~col_ok] = np.nan
    return field


class SoilMoistureUpdater(Updater):
    def __init__(self, config: TerrascopeConfig, map_data: MapData):
        super().__init__(config, "soil_moisture", map_data)

    def run(self, max_hours=None):
        # max_hours is a no-op: one latest granule, nothing per forecast hour.
        cache_path = soil_moisture_cache_path(self.workdir)
        if not os.path.exists(cache_path):
            return
        # Nothing render-relevant is configurable (the palette is client-side), so the
        # cache's mtime is the whole freshness check.
        sig = self._settings_signature({})
        if self._is_render_fresh(self.output_path, [cache_path], sig):
            return
        percentile, lat, lon, _granule_id, start = load_soil_moisture(cache_path)
        encode_frames([texture_field(percentile, lat, lon)], self.output_path, *ENCODE_DOMAIN)
        self._write_meta_sidecar("soil_moisture_meta.json", "soil_moisture", {"time": start})
        self._write_render_signature(self.output_path, sig)
        logger.info(f"{self.section}: rendered soil moisture texture for {start}.")

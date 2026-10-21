#!/usr/bin/env python3
"""so2_volcanic gets its own colour palette, deliberately non-overlapping with
_AQI_COLORS (the palette every other air_quality variable, so2 included, uses) --
both can be shown on the map at once (Air Quality's own SO2 picker option AND
Volcano Properties' Smoke Plume are independent toggles), so a shared colour scale
would make it impossible to tell which patch of colour is which data source. Pure
colour-list assertions, no matplotlib figure or netCDF data involved -- see
test_air_quality_mercator_prewarp.py's docstring for why plot()'s rendering
internals aren't unit-tested here either.
"""
from terrascope.tasks.air_quality import (
    _AQI_CMAP, _AQI_COLORS, _CMAP, _DUST_COLORS, _VOLCANIC_SO2_COLORS,
)


def test_so2_volcanic_has_its_own_cmap_entry():
    assert "so2_volcanic" in _CMAP
    assert _CMAP["so2_volcanic"] is not _AQI_CMAP


def test_every_other_variable_falls_back_to_the_shared_aqi_cmap():
    for variable in ("pm2_5", "pm10", "aod", "so2"):
        assert _CMAP.get(variable, _AQI_CMAP) is _AQI_CMAP


def test_volcanic_so2_palette_shares_no_colour_with_the_aqi_palette():
    assert set(c.lower() for c in _VOLCANIC_SO2_COLORS).isdisjoint(
        set(c.lower() for c in _AQI_COLORS)
    )


def _luminance(hex_colour):
    r, g, b = (int(hex_colour[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def test_dust_has_its_own_cmap_entry():
    assert "dust" in _CMAP
    assert _CMAP["dust"] is not _AQI_CMAP


def test_dust_palette_runs_from_pale_sand_to_dark_brown():
    luminances = [_luminance(c) for c in _DUST_COLORS]

    assert luminances == sorted(luminances, reverse=True)  # strictly darker, step by step
    assert len(set(luminances)) == len(luminances)
    assert luminances[0] > 200  # a pale sand at the thin end
    assert luminances[-1] < 70  # a dark brown at the dense end

#!/usr/bin/env python3
"""Config-UI validation for the Soil Moisture layer (see test_config_field_specs.py for
the validator's own contract) and its data source on the Data Status page."""

import json
from pathlib import Path

from terrascope.collectors import CACHE_COLLECTORS
from terrascope.collectors.soil_moisture import SoilMoistureCollector
from terrascope.routes.field_specs import FIELD_SPECS, section_label, validate_against_specs

TEMPLATE = Path(__file__).parent.parent / "config" / "terrascope.json.tmpl"


def test_the_shipped_template_defaults_pass_validation_and_ship_disabled():
    template = json.loads(TEMPLATE.read_text())

    assert validate_against_specs({"soil_moisture": template["soil_moisture"]}) == []
    section = template["soil_moisture"]
    assert section["enabled"] is False
    assert section["opacity"] == 70
    assert section["runs_per_day"] == 4  # 3-hourly granules, published days late


def test_the_cmr_search_is_a_listed_data_source_the_collector_is_gated_by():
    template = json.loads(TEMPLATE.read_text())
    collector = template["data_collector"]

    assert collector["datasources"]["soil_moisture"] == (
        "https://cmr.earthdata.nasa.gov/search/granules.json"
    )
    assert collector["channel_enabled"]["soil_moisture"] is True
    assert SoilMoistureCollector in CACHE_COLLECTORS


def test_enabled_and_opacity_are_per_viewer_settings():
    assert FIELD_SPECS[("soil_moisture", "enabled")].personalizable
    assert FIELD_SPECS[("soil_moisture", "opacity")].personalizable


def test_opacity_must_be_a_percentage():
    assert validate_against_specs({"soil_moisture": {"opacity": 101}}) != []
    assert validate_against_specs({"soil_moisture": {"opacity": 60}}) == []


def test_the_section_is_titled_by_its_layer_name():
    assert section_label("soil_moisture") == "Soil Moisture"

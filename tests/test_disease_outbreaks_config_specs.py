#!/usr/bin/env python3
"""Config-UI validation for the Disease Outbreaks layer (see test_config_field_specs.py for
the validator's own contract) and its data source on the Data Status page."""

import json
from pathlib import Path

from terrascope.collectors import COLLECTORS
from terrascope.collectors.disease_outbreaks import DiseaseOutbreaksCollector
from terrascope.routes.field_specs import FIELD_SPECS, section_label, validate_against_specs

TEMPLATE = Path(__file__).parent.parent / "config" / "terrascope.json.tmpl"


def test_the_shipped_template_defaults_pass_validation_and_ship_disabled():
    template = json.loads(TEMPLATE.read_text())

    errors = validate_against_specs(
        {"disease_outbreaks": template["disease_outbreaks"], "housekeeper": template["housekeeper"]}
    )

    assert errors == []
    section = template["disease_outbreaks"]
    assert section["enabled"] is False
    assert section["active_days"] == 45
    assert section["runs_per_day"] == 4  # a few reports a month, so polling is cheap
    assert template["housekeeper"]["disease_outbreaks_expiry_days"] == 180


def test_the_who_api_is_a_listed_data_source_the_collector_is_gated_by():
    template = json.loads(TEMPLATE.read_text())
    collector = template["data_collector"]

    assert collector["datasources"]["disease_outbreaks"] == "https://www.who.int/api/news/diseaseoutbreaknews"
    assert collector["channel_enabled"]["disease_outbreaks"] is True
    assert DiseaseOutbreaksCollector in COLLECTORS


def test_enabled_and_the_window_are_per_viewer_settings():
    assert FIELD_SPECS[("disease_outbreaks", "enabled")].personalizable
    assert FIELD_SPECS[("disease_outbreaks", "active_days")].personalizable


def test_the_window_must_stay_within_the_housekeepers_retention():
    # Retention defaults to 180 days: a longer window would promise reports already pruned.
    assert validate_against_specs({"disease_outbreaks": {"active_days": 0}}) != []
    assert validate_against_specs({"disease_outbreaks": {"active_days": 181}}) != []
    assert validate_against_specs({"disease_outbreaks": {"active_days": 1}}) == []
    assert validate_against_specs({"disease_outbreaks": {"active_days": 180}}) == []


def test_the_section_is_titled_by_its_layer_name():
    assert section_label("disease_outbreaks") == "Disease Outbreaks"

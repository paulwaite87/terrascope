#!/usr/bin/env python3
"""Config-UI validation for dust as an Air Quality variable (see
test_config_field_specs.py for the validator's own contract)."""

import json
from pathlib import Path

from terrascope.routes.field_specs import FIELD_SPECS, validate_against_specs

TEMPLATE = Path(__file__).parent.parent / "config" / "terrascope.json.tmpl"


def test_dust_is_a_selectable_air_quality_variable():
    spec = FIELD_SPECS[("air_quality", "variable")]

    assert "dust" in [value for value, _ in spec.options]
    assert validate_against_specs({"air_quality": {"variable": "dust"}}) == []


def test_the_shipped_template_defaults_dust_to_a_minimum_of_a_tenth():
    template = json.loads(TEMPLATE.read_text())

    assert template["air_quality"]["dust_min"] == 0.1
    assert validate_against_specs({"air_quality": template["air_quality"]}) == []


def test_the_dust_minimum_cannot_exceed_the_gradient_ceiling():
    # A minimum above the fixed 1.5 ceiling would hide the whole layer.
    assert validate_against_specs({"air_quality": {"dust_min": 1.5}}) == []
    assert validate_against_specs({"air_quality": {"dust_min": 1.6}}) != []
    assert validate_against_specs({"air_quality": {"dust_min": -0.1}}) != []


def test_the_dust_minimum_is_a_shared_setting_because_it_is_baked_into_the_render():
    assert FIELD_SPECS[("air_quality", "dust_min")].personalizable is False

#!/usr/bin/env python3
"""EARTHDATA_TOKEN gate for the soil_moisture layer: SMAP's OPeNDAP service needs the
Earthdata bearer token for every request, so without one the whole layer is shown as
deactivated in the config page -- the same RULE__missing_* shape as air_quality's
CDSAPI_KEY gate (see test_air_quality_config_gate.py and routes/config.py)."""
import json
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from terrascope.api import app
from terrascope.db.user_settings_adapter import FakeUserSettingsAdapter
from terrascope.lib.auth import SESSION_COOKIE_NAME
from terrascope.lib.config import TerrascopeConfig
from terrascope.routes.auth import get_user_adapter
from terrascope.routes.config import get_user_settings_adapter
from tests.conftest import make_signed_in_session

client = TestClient(app)


@pytest.fixture(autouse=True)
def _admin_session():
    fake, token = make_signed_in_session(is_admin=True)
    app.dependency_overrides[get_user_adapter] = lambda: fake
    app.dependency_overrides[get_user_settings_adapter] = lambda: FakeUserSettingsAdapter()
    client.cookies.set(SESSION_COOKIE_NAME, token)


def _with_temp_config(tmp_path, initial: dict):
    tmp_config = tmp_path / "terrascope.json"
    tmp_config.write_text(json.dumps(initial))
    return patch(
        "terrascope.routes.config.load_config",
        return_value=TerrascopeConfig(str(tmp_config)),
    ), tmp_config


def test_get_config_disables_the_layer_when_the_token_is_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("EARTHDATA_TOKEN", raising=False)
    patcher, _ = _with_temp_config(tmp_path, {"soil_moisture": {"enabled": True}})
    with patcher:
        resp = client.get("/api/config")

    data = resp.json()["data"]["soil_moisture"]
    assert data["RULE__missing_earthdata_token"] is True
    assert data["enabled"] is False


def test_get_config_leaves_the_layer_alone_when_the_token_is_present(tmp_path, monkeypatch):
    monkeypatch.setenv("EARTHDATA_TOKEN", "some-token")
    patcher, _ = _with_temp_config(tmp_path, {"soil_moisture": {"enabled": True}})
    with patcher:
        resp = client.get("/api/config")

    data = resp.json()["data"]["soil_moisture"]
    assert "RULE__missing_earthdata_token" not in data
    assert data["enabled"] is True


def test_update_config_strips_the_rule_flag_before_saving(tmp_path):
    patcher, tmp_config = _with_temp_config(tmp_path, {"soil_moisture": {"enabled": True}})
    with patcher:
        resp = client.post(
            "/api/config",
            json={"soil_moisture": {"enabled": True, "RULE__missing_earthdata_token": True}},
        )

    assert resp.status_code == 200
    saved = json.loads(tmp_config.read_text())
    assert "RULE__missing_earthdata_token" not in saved["soil_moisture"]


def test_config_page_has_a_toggle_and_a_warning_for_the_gate():
    html = client.get("/config").text

    assert 'id="soil_moisture__enabled"' in html
    assert 'id="key-warn-earthdata-sm"' in html
    assert "data.soil_moisture.RULE__missing_earthdata_token" in html

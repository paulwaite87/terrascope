#!/usr/bin/env python3
"""Guard against DiseaseOutbreaksAdapter Real/Fake drift (the pattern
test_gdacs_adapter_real_vs_fake.py established): the same contract scenarios run against the
SQLAlchemy adapter (a throwaway postgis container migrated with `alembic upgrade head`) and
FakeDiseaseOutbreaksAdapter. Everything is asserted through the adapters' public methods,
never by querying tables. The current-outbreak rule itself is tested through the collector
(test_disease_outbreaks_collector.py); here only storage and pruning are compared."""

import contextlib
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy.orm import sessionmaker

from terrascope.db.disease_outbreaks_adapter import DiseaseOutbreaksAdapter, FakeDiseaseOutbreaksAdapter


def _make_adapter(kind, real_db):
    if kind == "real":
        TestSession = sessionmaker(bind=real_db)
        return DiseaseOutbreaksAdapter(), patch("terrascope.db.disease_outbreaks_adapter.Session", TestSession)
    return FakeDiseaseOutbreaksAdapter(), contextlib.nullcontext()


def make_report(**over):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    report = {
        "don_id": "TEST-DON1", "title": "Cholera - Kenya", "disease": "Cholera", "key": "cholera",
        "kind": "countries", "countries": ["Kenya"], "ended": [], "ends_unplaced": False,
        "published": now - timedelta(days=2), "modified": now - timedelta(days=2),
        "summary": "A cholera outbreak.\r\nSecond paragraph.", "url_name": "test-don1-cholera-kenya",
    }
    report.update(over)
    # Each scenario is its own disease: the real database is shared across tests, and the
    # latest report per (disease, country) wins, so equal diseases would supersede each other.
    report["key"] = over.get("key") or report["don_id"].lower()
    return report


def served(adapter, among, **kwargs):
    """Feature properties served, limited to the don_ids in `among` -- the real database is
    shared across tests, so rows other tests created must not leak into this one."""
    body = json.loads(adapter.get_current_as_geojson(**kwargs))
    features = [f for f in body["features"] if f["properties"]["don_id"] in among]
    unplaced = [u for u in body["unplaced"] if u["don_id"] in among]
    return features, unplaced


@pytest.mark.parametrize("kind", ["real", "fake"])
def test_a_stored_report_is_served_as_a_point_at_its_country_with_its_whole_summary(kind, real_db):
    adapter, ctx = _make_adapter(kind, real_db)
    with ctx:
        adapter.upsert_report(make_report(don_id="TEST-A1", countries=["Kenya", "Uganda"]))
        features, unplaced = served(adapter, {"TEST-A1"})

    assert sorted(f["properties"]["country"] for f in features) == ["Kenya", "Uganda"]
    assert unplaced == []
    props = features[0]["properties"]
    assert props["summary"] == "A cholera outbreak.\r\nSecond paragraph."
    assert props["countries"] == ["Kenya", "Uganda"]
    assert props["url"].endswith("/item/test-don1-cholera-kenya")
    assert features[0]["geometry"]["type"] == "Point"


@pytest.mark.parametrize("kind", ["real", "fake"])
def test_upserting_the_same_report_updates_it_in_place(kind, real_db):
    adapter, ctx = _make_adapter(kind, real_db)
    with ctx:
        adapter.upsert_report(make_report(don_id="TEST-B1", summary="first"))
        adapter.upsert_report(make_report(don_id="TEST-B1", summary="second", countries=["Kenya"]))
        features, _ = served(adapter, {"TEST-B1"})

    assert len(features) == 1
    assert features[0]["properties"]["summary"] == "second"


@pytest.mark.parametrize("kind", ["real", "fake"])
def test_an_unplaceable_report_is_served_in_the_unplaced_list(kind, real_db):
    adapter, ctx = _make_adapter(kind, real_db)
    with ctx:
        adapter.upsert_report(
            make_report(don_id="TEST-C1", title="Yellow fever - Global", disease="Yellow fever",
                        key="yellow fever", kind="unplaceable", countries=[])
        )
        features, unplaced = served(adapter, {"TEST-C1"})

    assert features == []
    assert [u["disease"] for u in unplaced] == ["Yellow fever"]


@pytest.mark.parametrize("kind", ["real", "fake"])
def test_an_ended_country_is_stored_and_honoured(kind, real_db):
    adapter, ctx = _make_adapter(kind, real_db)
    with ctx:
        adapter.upsert_report(make_report(don_id="TEST-D1", key="marburg", disease="Marburg",
                                          countries=["Ethiopia"], ended=["Ethiopia"]))
        features, _ = served(adapter, {"TEST-D1"})

    assert features == []


@pytest.mark.parametrize("kind", ["real", "fake"])
def test_pruning_deletes_only_reports_older_than_the_retention_period(kind, real_db):
    now = datetime.now(timezone.utc).replace(microsecond=0)
    adapter, ctx = _make_adapter(kind, real_db)
    with ctx:
        adapter.upsert_report(make_report(don_id="TEST-E1", key="old", published=now - timedelta(days=200)))
        adapter.upsert_report(make_report(don_id="TEST-E2", key="new", published=now - timedelta(days=100)))
        deleted = adapter.prune_expired(180)
        features, _ = served(adapter, {"TEST-E1", "TEST-E2"}, active_days=365)

    assert deleted >= 1
    assert {f["properties"]["don_id"] for f in features} == {"TEST-E2"}

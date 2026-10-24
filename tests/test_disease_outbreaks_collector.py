#!/usr/bin/env python3
"""Ingest-to-HTTP tests for the Disease Outbreaks layer: DiseaseOutbreaksCollector.collect()
runs against a recording of the real WHO Disease Outbreak News API
(tests/fixtures/disease_outbreaks/don_page.json: eleven real items, fetched 2026-10-24 with the
collector's own $select), with CollectorBase._get patched, fills the in-memory
FakeDiseaseOutbreaksAdapter, and every assertion is on what the layer's HTTP route then
serves -- never on adapter internals. The clock is pinned (the layer is about "now"), usually
to 2026-10-24 12:00 UTC, the day the fixture was recorded. Prior art: test_gdacs_collector.py.

The fixture's items, newest first: DON622 Ebola (Bundibugyo) DRC/Kenya/Nigeria 23 Oct;
DON618 MERS Saudi Arabia 15 Oct; DON620 pneumonia of undetermined cause, Russia 10 Oct;
DON619 Ebola DRC 8 Oct (superseded by DON622); DON614 Ebola DRC 1 Aug, whose summary says
UGANDA declared its own end; DON613 Ebola DRC and Uganda 17 Jul, the report that named Uganda; DON609 Nipah India 25 Jun; DON610 Yellow fever - Global 24 Jun;
DON601 hantavirus cruise-ship cluster, Multi-country, 13 May; DON592 Marburg Ethiopia 26 Jan,
which declares the end of that outbreak; 1998DON236 cholera Sri Lanka, a legacy archive item
bulk-dated 14 Mar 2024 with an empty summary."""

import copy
import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from terrascope.api import app
from terrascope.collectors.base import CollectorBase
from terrascope.collectors.disease_outbreaks import DiseaseOutbreaksCollector
from terrascope.db.disease_outbreaks_adapter import FakeDiseaseOutbreaksAdapter
from terrascope.routes.disease_outbreaks import get_disease_outbreaks_adapter

PAGE = json.loads((Path(__file__).parent / "fixtures" / "disease_outbreaks" / "don_page.json").read_text())
DAY = datetime(2026, 10, 24, 12, 0, tzinfo=timezone.utc)
API = "https://www.who.int/api/news/diseaseoutbreaknews"


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    set_clock(monkeypatch, DAY)


def set_clock(monkeypatch, now):
    monkeypatch.setattr("terrascope.lib.disease_outbreaks._now", lambda: now)


class FakeResponse:
    def __init__(self, payload):
        self._payload = payload
        self.text = json.dumps(payload)

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


def make_collector():
    c = DiseaseOutbreaksCollector.__new__(DiseaseOutbreaksCollector)
    c.settings = {}
    c.disease_outbreaks_adapter = FakeDiseaseOutbreaksAdapter()
    c.datasource_url = MagicMock(return_value=API)
    c.config = MagicMock()
    c.config.get_setting.side_effect = lambda section, key, default=None: default
    return c


def run_collect(c, response, calls=None):
    """collect() with the WHO API answering `response` (a payload dict; None behaves like a
    failed fetch, which is what CollectorBase._get returns for any HTTP/connection error)."""

    def fake_get(url, **kwargs):
        if calls is not None:
            calls.append((url, dict(kwargs.get("params", {}))))
        return None if response is None else FakeResponse(response)

    with patch.object(CollectorBase, "_get", side_effect=fake_get):
        c.collect()
    app.dependency_overrides[get_disease_outbreaks_adapter] = lambda: c.disease_outbreaks_adapter


def served(client, c, response=PAGE, **params):
    run_collect(c, response)
    resp = client.get("/api/disease_outbreaks/geojson", params=params)
    assert resp.status_code == 200
    return resp.json()


def markers(body):
    return {(f["properties"]["disease"], f["properties"]["country"]) for f in body["features"]}


def page_with(*extra, drop=()):
    page = copy.deepcopy(PAGE)
    page["value"] = [e for e in page["value"] if e["DonId"] not in drop] + list(extra)
    return page


EBOLA = "Ebola disease caused by Bundibugyo virus"


def test_today_the_current_outbreaks_are_marked_in_every_country_they_name(client):
    body = served(client, make_collector())

    assert markers(body) == {
        (EBOLA, "Dem. Rep. Congo"), (EBOLA, "Kenya"), (EBOLA, "Nigeria"),
        ("Middle East respiratory syndrome coronavirus", "Saudi Arabia"),
        ("Pneumonia of undetermined etiology", "Russia"),
    }
    assert body["unplaced"] == []


def test_a_marker_sits_at_the_countrys_label_point(client):
    body = served(client, make_collector())

    saudi = next(f for f in body["features"] if f["properties"]["country"] == "Saudi Arabia")
    assert saudi["geometry"] == {"type": "Point", "coordinates": [44.99, 23.5]}


def test_a_marker_carries_the_latest_reports_whole_summary_date_and_link(client):
    body = served(client, make_collector())

    drc = next(f["properties"] for f in body["features"] if f["properties"]["country"] == "Dem. Rep. Congo")
    # DON622 (23 Oct), not DON619 (8 Oct): the later report supersedes the earlier one.
    assert drc["don_id"] == "2026-DON622"
    assert drc["published"] == "2026-10-23T15:48:48Z"
    assert drc["summary"].startswith("Since the publication of the previous Disease Outbreak News on 8 October 2026")
    # the whole summary, paragraph breaks included, not an excerpt
    whole = next(e["Summary"] for e in PAGE["value"] if e["DonId"] == "2026-DON622")
    assert drc["summary"] == whole.strip() and len(drc["summary"]) > 1800 and "\r\n" in drc["summary"]
    assert drc["url"] == "https://www.who.int/emergencies/disease-outbreak-news/item/2026-DON622"
    assert drc["countries"] == ["Dem. Rep. Congo", "Kenya", "Nigeria"]


def test_the_link_uses_the_reports_url_name_which_is_not_always_its_id(client):
    body = served(client, make_collector())

    mers = next(f["properties"] for f in body["features"] if f["properties"]["country"] == "Saudi Arabia")
    assert mers["don_id"] == "2026-DON618"
    assert mers["url"] == (
        "https://www.who.int/emergencies/disease-outbreak-news/item/"
        "middle-east-respiratory-syndrome-coronavirus---kingdom-of-saudi-arabia"
    )


def test_only_outbreaks_reported_within_the_window_are_current(client, monkeypatch):
    c = make_collector()

    twelve_days = served(client, c, active_days=12)
    one_day = client.get("/api/disease_outbreaks/geojson", params={"active_days": 1}).json()
    wide = client.get("/api/disease_outbreaks/geojson", params={"active_days": 150}).json()

    # 12 days back from 24 Oct reaches 12 Oct: Ebola (23 Oct) and MERS (15 Oct), not the 10 Oct pneumonia.
    assert markers(twelve_days) == {
        (EBOLA, "Dem. Rep. Congo"), (EBOLA, "Kenya"), (EBOLA, "Nigeria"),
        ("Middle East respiratory syndrome coronavirus", "Saudi Arabia"),
    }
    assert markers(one_day) == {(EBOLA, "Dem. Rep. Congo"), (EBOLA, "Kenya"), (EBOLA, "Nigeria")}
    # 150 days reaches back to late May: the Nipah report (25 Jun) is now current too.
    assert ("Nipah virus disease", "India") in markers(wide)


def test_the_window_defaults_to_45_days(client):
    c = make_collector()
    run_collect(c, PAGE)

    default = client.get("/api/disease_outbreaks/geojson").json()

    assert ("Nipah virus disease", "India") not in markers(default)  # 121 days old
    assert len(default["features"]) == 5


def test_a_reports_that_declares_the_outbreak_over_removes_its_marker(client, monkeypatch):
    set_clock(monkeypatch, datetime(2026, 1, 30, 12, 0, tzinfo=timezone.utc))

    body = served(client, make_collector())

    # DON592 (26 Jan) is 4 days old but says Ethiopia declared the end of the outbreak.
    assert body["features"] == []
    assert body["unplaced"] == []


def test_a_country_whose_end_is_declared_in_a_later_summary_loses_its_marker_the_others_keep_theirs(client, monkeypatch):
    c = make_collector()
    set_clock(monkeypatch, datetime(2026, 7, 20, 12, 0, tzinfo=timezone.utc))
    before = served(client, c)
    set_clock(monkeypatch, datetime(2026, 8, 2, 12, 0, tzinfo=timezone.utc))
    after = client.get("/api/disease_outbreaks/geojson").json()

    ebola = lambda body: {m for m in markers(body) if m[0] == EBOLA}
    # DON613 (17 Jul) names the DRC and Uganda.
    assert ebola(before) == {(EBOLA, "Dem. Rep. Congo"), (EBOLA, "Uganda")}
    # DON614 (1 Aug) is titled for the DRC alone, but its summary says the Ministry of Health
    # of Uganda declared the end of the outbreak on 28 July: Uganda's marker goes, the DRC's
    # stays (and shows DON614, the later report).
    assert ebola(after) == {(EBOLA, "Dem. Rep. Congo")}
    drc = next(f["properties"] for f in after["features"] if f["properties"]["disease"] == EBOLA)
    assert drc["don_id"] == "2026-DON614"


def test_a_country_left_out_of_a_newer_report_keeps_its_own_latest_report_until_it_ages_out(client):
    older = copy.deepcopy(PAGE["value"][0])
    older.update(DonId="2026-DON600", UrlName="2026-DON600", Title="Cholera, Kenya and Uganda",
                 PublicationDate="2026-10-20T10:00:00Z", LastModified="2026-10-20T10:00:00Z")
    newer = copy.deepcopy(older)
    newer.update(DonId="2026-DON601X", UrlName="2026-DON601X", Title="Cholera - Uganda",
                 PublicationDate="2026-10-22T10:00:00Z", LastModified="2026-10-22T10:00:00Z")

    body = served(client, make_collector(), page_with(older, newer))

    by_country = {f["properties"]["country"]: f["properties"]["don_id"]
                  for f in body["features"] if f["properties"]["disease"] == "Cholera"}
    # Uganda's latest is the 22 Oct report; Kenya was only named by the 20 Oct one.
    assert by_country == {"Uganda": "2026-DON601X", "Kenya": "2026-DON600"}


def test_a_global_report_is_listed_as_not_on_the_map_instead_of_marked(client, monkeypatch):
    set_clock(monkeypatch, datetime(2026, 6, 26, 12, 0, tzinfo=timezone.utc))

    body = served(client, make_collector())

    assert markers(body) == {("Nipah virus disease", "India")}
    # Newest first: the Global yellow fever report (24 Jun) and, 44 days old, the multi-country
    # hantavirus cluster (13 May).
    assert [(u["disease"], u["don_id"]) for u in body["unplaced"]] == [
        ("Yellow fever", "2026-DON610"),
        ("Hantavirus cluster linked to cruise ship travel", "2026-DON601"),
    ]
    unplaced = body["unplaced"][0]
    assert unplaced["published"].startswith("2026-06-24T")
    assert unplaced["summary"] and unplaced["url"].endswith("/item/2026-DON610")


def test_reports_published_after_the_clock_are_not_yet_current(client, monkeypatch):
    set_clock(monkeypatch, datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc))

    body = served(client, make_collector(), active_days=365)

    assert markers(body) == set()


def test_a_legacy_archive_item_with_no_summary_is_ignored(client, monkeypatch):
    set_clock(monkeypatch, datetime(2024, 3, 20, 12, 0, tzinfo=timezone.utc))

    body = served(client, make_collector(), active_days=30)

    # 1998DON236 (cholera, Sri Lanka) is dated 14 Mar 2024 -- within the window -- but is empty.
    assert body["features"] == [] and body["unplaced"] == []


def test_a_title_naming_no_known_country_is_skipped_without_failing_the_run(client):
    odd = copy.deepcopy(PAGE["value"][0])
    odd["DonId"], odd["UrlName"], odd["Title"] = "2026-DON700", "2026-DON700", "Mystery illness - Atlantis"
    odd["PublicationDate"] = "2026-10-22T10:00:00Z"

    body = served(client, make_collector(), page_with(odd))

    assert ("Mystery illness", "Atlantis") not in markers(body)
    assert len(body["features"]) == 5 and body["unplaced"] == []


def test_collecting_twice_does_not_duplicate_markers(client):
    c = make_collector()
    run_collect(c, PAGE)

    body = served(client, c)

    assert len(body["features"]) == 5


def test_the_collector_asks_for_the_newest_hundred_with_only_the_fields_it_uses(client):
    calls = []
    c = make_collector()

    run_collect(c, PAGE, calls=calls)

    url, params = calls[0]
    assert url == API
    assert params["$top"] == 100
    assert params["$orderby"] == "PublicationDate desc"
    assert set(params["$select"].split(",")) == {
        "DonId", "Title", "PublicationDate", "LastModified", "UrlName", "Summary",
    }


@pytest.mark.parametrize(
    "broken",
    [None, {"error": {"code": "BadRequest"}}, {"value": "nope"}, {"value": [{"DonId": "x"}]}],
    ids=["fetch-fails", "error-document", "value-not-a-list", "item-missing-fields"],
)
def test_a_failed_or_garbled_response_leaves_the_stored_reports_and_is_reported(client, broken):
    c = make_collector()
    before = served(client, c)

    # Raised so the orchestrator records a failure (Data Status shows the error rather than
    # reporting a stale layer as freshly updated).
    with pytest.raises(RuntimeError):
        run_collect(c, broken)

    after = client.get("/api/disease_outbreaks/geojson").json()
    assert markers(after) == markers(before) and len(after["features"]) == 5

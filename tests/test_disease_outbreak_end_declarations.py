#!/usr/bin/env python3
"""ended_countries(): which countries a WHO summary says have declared their outbreak over.
Run against the real summaries in tests/fixtures/disease_outbreaks/don_page.json plus a few
worded the way WHO words them. A phrase such as a 42-day countdown ("will only be declared
over if no new infections arise") is NOT a declaration."""

import json
from pathlib import Path

from terrascope.lib.disease_outbreaks import ended_countries

PAGE = json.loads((Path(__file__).parent / "fixtures" / "disease_outbreaks" / "don_page.json").read_text())
SUMMARY = {e["DonId"]: e["Summary"] for e in PAGE["value"]}


def test_a_single_country_declaration_ends_that_country():
    ended, nameless = ended_countries(SUMMARY["2026-DON592"], ["Ethiopia"])

    assert ended == ["Ethiopia"] and nameless is False


def test_a_declaration_by_another_country_does_not_end_the_reports_own():
    # DON614 is titled for the DRC; its summary says the Ministry of Health of Uganda
    # declared the end of the outbreak "in the country".
    ended, nameless = ended_countries(SUMMARY["2026-DON614"], ["Dem. Rep. Congo"])

    assert ended == ["Uganda"] and nameless is False


def test_an_ongoing_outbreaks_summary_ends_nobody():
    for don_id, countries in (("2026-DON622", ["Dem. Rep. Congo", "Kenya", "Nigeria"]),
                              ("2026-DON618", ["Saudi Arabia"]), ("2026-DON613", ["Dem. Rep. Congo", "Uganda"])):
        assert ended_countries(SUMMARY[don_id], countries) == ([], False), don_id


def test_a_countdown_is_not_a_declaration():
    text = "The outbreak will only be declared over if no new infections arise during the 42-day countdown."

    assert ended_countries(text, ["Rwanda"]) == ([], False)


def test_a_formal_country_name_is_read_as_the_maps_country():
    text = "On 1 March, the Ministry of Health of the United Republic of Tanzania declared the end of the outbreak."

    assert ended_countries(text, ["Tanzania"]) == (["Tanzania"], False)


def test_longer_country_names_win_over_the_shorter_ones_inside_them():
    text = "Papua New Guinea declared the end of the outbreak."

    assert ended_countries(text, ["Papua New Guinea"]) == (["Papua New Guinea"], False)


def test_a_declaration_naming_no_country_ends_the_reports_own_countries():
    text = "WHO declared the end of the outbreak after two incubation periods."

    assert ended_countries(text, ["Rwanda"]) == (["Rwanda"], False)


def test_a_declaration_naming_no_country_in_a_report_with_none_is_flagged_nameless():
    text = "WHO declared the end of the event."

    assert ended_countries(text, []) == ([], True)

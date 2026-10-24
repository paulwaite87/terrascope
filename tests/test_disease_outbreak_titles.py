#!/usr/bin/env python3
"""parse_title(): WHO Disease Outbreak News titles -> (disease, countries, kind). The
feed carries no coordinates; the place is only in the title, in a dozen hand-typed
styles. Every title below is copied verbatim from the live feed (2024-2026), and the
expected values are written by hand, not derived. Countries are the map's own names
(Natural Earth's, as in lib/country_places.py), e.g. WHO's "Kingdom of Saudi Arabia" is
"Saudi Arabia" and its "Democratic Republic of the Congo" is "Dem. Rep. Congo".

kind: "countries" (one or more recognised countries, so markers), "unplaceable" (Global,
Multi-country, a WHO region, or no location at all: the legend list), "unrecognised"
(a location is named but is none of ours: skipped and logged)."""

import pytest

from terrascope.lib.country_places import COUNTRY_PLACES
from terrascope.lib.disease_outbreaks import parse_title

CASES = [
    # separators: spaced hyphen, en dash, glued on either side, none
    ("Middle East respiratory syndrome coronavirus - Kingdom of Saudi Arabia",
     "Middle East respiratory syndrome coronavirus", ["Saudi Arabia"], "countries"),
    ("Ebola disease caused by Bundibugyo virus – Democratic Republic of the Congo",
     "Ebola disease caused by Bundibugyo virus", ["Dem. Rep. Congo"], "countries"),
    ("Marburg virus disease– United Republic of Tanzania",
     "Marburg virus disease", ["Tanzania"], "countries"),
    ("Marburg virus disease- Ethiopia", "Marburg virus disease", ["Ethiopia"], "countries"),
    ("Marburg Virus Disease–United Republic of Tanzania",
     "Marburg Virus Disease", ["Tanzania"], "countries"),
    ("Human infection caused by avian Influenza A(H5N2)-Mexico",
     "Human infection caused by avian Influenza A(H5N2)", ["Mexico"], "countries"),
    # WHO's formal names
    ("Pneumonia of undetermined etiology - the Russian Federation",
     "Pneumonia of undetermined etiology", ["Russia"], "countries"),
    ("Avian Influenza A(H9N2)- Viet Nam", "Avian Influenza A(H9N2)", ["Vietnam"], "countries"),
    ("Dengue – Iran (Islamic Republic of)", "Dengue", ["Iran"], "countries"),
    ("Chapare haemorrhagic fever- the Plurinational State of Bolivia",
     "Chapare haemorrhagic fever", ["Bolivia"], "countries"),
    ("Marburg virus disease– The Republic of Rwanda",
     "Marburg virus disease", ["Rwanda"], "countries"),
    ("Measles - Republic of Korea", "Measles", ["South Korea"], "countries"),
    ("Avian Influenza A(H5N5)- United States of America",
     "Avian Influenza A(H5N5)", ["United States of America"], "countries"),
    # several countries: comma, "and", ampersand
    ("Ebola disease caused by Bundibugyo virus, Democratic Republic of the Congo, Kenya and Nigeria",
     "Ebola disease caused by Bundibugyo virus", ["Dem. Rep. Congo", "Kenya", "Nigeria"], "countries"),
    ("Ebola disease caused by Bundibugyo virus, Democratic Republic of the Congo & Uganda",
     "Ebola disease caused by Bundibugyo virus", ["Dem. Rep. Congo", "Uganda"], "countries"),
    ("Rift Valley fever- Mauritania and Senegal",
     "Rift Valley fever", ["Mauritania", "Senegal"], "countries"),
    # a place inside the disease part must not be mistaken for the location
    ("Cluster of community deaths in Basankusu, Equateur- Democratic Republic of the Congo",
     "Cluster of community deaths in Basankusu, Equateur", ["Dem. Rep. Congo"], "countries"),
    # not placeable: global, multi-country, WHO regions
    ("Yellow fever - Global", "Yellow fever", [], "unplaceable"),
    ("Chikungunya virus disease- Global situation", "Chikungunya virus disease", [], "unplaceable"),
    ("Hantavirus cluster linked to cruise ship travel, Multi-country",
     "Hantavirus cluster linked to cruise ship travel", [], "unplaceable"),
    ("Hantavirus outbreak linked to cruise ship travel, Multi-locations",
     "Hantavirus outbreak linked to cruise ship travel", [], "unplaceable"),
    ("Diphtheria - African Region (AFRO)", "Diphtheria", [], "unplaceable"),
    # no location in the title at all
    ("Rabies", "Rabies", [], "unplaceable"),
    ("Avian Influenza A(H9N2)", "Avian Influenza A(H9N2)", [], "unplaceable"),
    # a location is named but it is not one of ours
    ("Mystery illness - Atlantis", "Mystery illness", [], "unrecognised"),
]


@pytest.mark.parametrize("title,disease,countries,kind", CASES, ids=[c[0][:60] for c in CASES])
def test_a_real_title_is_split_into_disease_countries_and_kind(title, disease, countries, kind):
    parsed = parse_title(title)

    assert parsed.disease == disease
    assert parsed.countries == countries
    assert parsed.kind == kind


def test_one_unrecognised_country_among_recognised_ones_is_dropped_not_fatal():
    parsed = parse_title("Cholera - Kenya and Atlantis")

    assert parsed.countries == ["Kenya"]
    assert parsed.kind == "countries"


def test_every_country_a_title_can_resolve_to_is_one_the_map_has():
    names = {name for name, *_ in COUNTRY_PLACES}
    for _title, _disease, countries, _kind in CASES:
        assert set(countries) <= names


def test_diseases_that_differ_only_in_case_or_spacing_share_a_key():
    a = parse_title("Marburg virus disease – Rwanda")
    b = parse_title("Marburg  Virus Disease- Rwanda")

    assert a.key == b.key


def test_a_country_whose_own_name_contains_a_dash_is_not_split_at_it():
    parsed = parse_title("Cholera - Guinea-Bissau")

    assert parsed.disease == "Cholera"
    assert parsed.countries == ["Guinea-Bissau"]

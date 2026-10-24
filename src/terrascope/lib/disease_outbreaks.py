#!/usr/bin/env python3
"""Disease Outbreaks layer data: the World Health Organization's Disease Outbreak News
(DON), from its OData news API (no key). The feed carries no coordinates -- where an
outbreak is happens to be only in the report's title, hand-typed in a dozen styles
("Marburg virus disease- Ethiopia", "Ebola ..., Democratic Republic of the Congo, Kenya
and Nigeria", "Avian Influenza A(H9N2)- Viet Nam") -- so parse_title() pulls out the
disease and the countries named, which the collector then puts on the map at each
country's label point (lib/country_places.py).

WHO writes countries by their formal names; the map uses Natural Earth's (often
abbreviated) ones, so _ALIASES maps the formal forms ("Kingdom of Saudi Arabia", "Viet
Nam", "Central African Republic") onto them.
"""
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from terrascope.lib.country_places import COUNTRY_PLACES

DON_API_URL = "https://www.who.int/api/news/diseaseoutbreaknews"
DON_PAGE_URL = "https://www.who.int/emergencies/disease-outbreak-news"
PAGE_SIZE = 100  # the API refuses a larger $top

# A dash of any of the three kinds, with or without the spaces around it.
_DASH = re.compile(r"\s*[-–—]\s*")
# "Global", "Multi-country", "Multi-locations", "African Region (AFRO)", "WHO Region"...
_UNPLACEABLE = re.compile(r"\b(global|multi[- ]?(country|countries|location|locations|region|regional)|region|afro|emro|searo|wpro|paho|euro)\b", re.I)
_SPLIT = re.compile(r"\s*(?:,|&)\s*")

# WHO's formal names (lower-case, accents removed, a leading "the" ignored) -> the map's.
_ALIASES = {
    "kingdom of saudi arabia": "Saudi Arabia",
    "russian federation": "Russia",
    "democratic republic of the congo": "Dem. Rep. Congo",
    "democratic republic of congo": "Dem. Rep. Congo",
    "drc": "Dem. Rep. Congo",
    "republic of the congo": "Congo",
    "united republic of tanzania": "Tanzania",
    "republic of tanzania": "Tanzania",
    "viet nam": "Vietnam",
    "iran (islamic republic of)": "Iran",
    "islamic republic of iran": "Iran",
    "plurinational state of bolivia": "Bolivia",
    "bolivarian republic of venezuela": "Venezuela",
    "republic of korea": "South Korea",
    "democratic people's republic of korea": "North Korea",
    "lao people's democratic republic": "Laos",
    "syrian arab republic": "Syria",
    "republic of moldova": "Moldova",
    "turkiye": "Turkey",
    "united states": "United States of America",
    "usa": "United States of America",
    "united kingdom of great britain and northern ireland": "United Kingdom",
    "uk": "United Kingdom",
    "occupied palestinian territory": "Palestine",
    "state of palestine": "Palestine",
    "central african republic": "Central African Rep.",
    "dominican republic": "Dominican Rep.",
    "south sudan": "S. Sudan",
    "equatorial guinea": "Eq. Guinea",
    "bosnia and herzegovina": "Bosnia and Herz.",
    "antigua and barbuda": "Antigua and Barb.",
    "saint kitts and nevis": "St. Kitts and Nevis",
    "saint vincent and the grenadines": "St. Vin. and Gren.",
    "sao tome and principe": "São Tomé and Principe",
    "eswatini": "eSwatini",
    "kingdom of eswatini": "eSwatini",
    "cote d'ivoire": "Côte d'Ivoire",
    "cape verde": "Cabo Verde",
    "timor leste": "Timor-Leste",
    "micronesia (federated states of)": "Micronesia",
    "federated states of micronesia": "Micronesia",
    "netherlands (kingdom of the)": "Netherlands",
    "the netherlands": "Netherlands",
    "the gambia": "Gambia",
    "west bank and gaza strip": "Palestine",
    "hong kong sar": "Hong Kong",
    "china, hong kong sar": "Hong Kong",
    "taiwan, province of china": "Taiwan",
    "swaziland": "eSwatini",
    "burma": "Myanmar",
    "czech republic": "Czechia",
    "macedonia": "North Macedonia",
}
# "Republic of Rwanda", "Kingdom of Morocco" -> "Rwanda", "Morocco" once the title is stripped.
_FORMAL_PREFIX = re.compile(r"^(?:the )?(?:republic of|kingdom of|state of|federal republic of|islamic republic of|people's republic of)\s+")


def _fold(text: str) -> str:
    """Lower-case, accents removed, curly apostrophes straight, spaces collapsed."""
    text = unicodedata.normalize("NFKD", text.replace("’", "'"))
    text = "".join(c for c in text if not unicodedata.combining(c))
    return " ".join(text.lower().split())


_BY_NAME = {_fold(name): name for name, *_ in COUNTRY_PLACES}


def lookup_country(text: str) -> str | None:
    """The map's name for a country as WHO writes it, or None."""
    key = _fold(text)
    for candidate in (key, re.sub(r"^the ", "", key)):
        if candidate in _BY_NAME:
            return _BY_NAME[candidate]
        if candidate in _ALIASES:
            return _ALIASES[candidate]
        stripped = _FORMAL_PREFIX.sub("", candidate)
        if stripped != candidate and (stripped in _BY_NAME or stripped in _ALIASES):
            return _BY_NAME.get(stripped) or _ALIASES[stripped]
    return None


@dataclass
class ParsedTitle:
    disease: str
    countries: list = field(default_factory=list)
    kind: str = "unplaceable"          # "countries" | "unplaceable" | "unrecognised"
    unmatched: list = field(default_factory=list)  # location words that matched nothing

    @property
    def key(self) -> str:
        """Groups reports of one disease: case and spacing ignored."""
        return " ".join(self.disease.lower().split())


def _chunks(location: str) -> list:
    """The place names in a location string: split on commas and ampersands, then on
    "and" only where the chunk is not itself a country ("Trinidad and Tobago")."""
    names = []
    for chunk in _SPLIT.split(location):
        if not chunk:
            continue
        if lookup_country(chunk) or _UNPLACEABLE.search(chunk):
            names.append(chunk)
        else:
            names.extend(p for p in re.split(r"\s+and\s+", chunk) if p)
    return names


def _resolve(location: str):
    """(countries, unmatched, unplaceable) for a location string."""
    countries, unmatched, unplaceable = [], [], False
    for name in _chunks(location):
        found = lookup_country(name)
        if found:
            if found not in countries:
                countries.append(found)
        elif _UNPLACEABLE.search(name):
            unplaceable = True
        else:
            unmatched.append(name.strip())
    return countries, unmatched, unplaceable


def _classify(disease: str, location: str) -> ParsedTitle:
    countries, unmatched, unplaceable = _resolve(location)
    if countries:
        return ParsedTitle(disease, countries, "countries", unmatched)
    if unplaceable and not unmatched:
        return ParsedTitle(disease, [], "unplaceable")
    return ParsedTitle(disease, [], "unrecognised", unmatched)


def parse_title(title: str) -> ParsedTitle:
    """Split a DON title into its disease and the countries it names. A dash-delimited
    tail ("... - Kenya and Nigeria") is the location; failing that, the first
    comma-separated part from which everything that follows names a place or is
    Global/Multi-country/a region ("..., Democratic Republic of the Congo, Kenya"). A title
    that names no place at all is "unplaceable"; one that names a place that is none
    of the map's countries is "unrecognised" (skipped and logged by the collector)."""
    text = " ".join(title.split())
    # The separating dash is the last one whose tail names a place: "Guinea-Bissau" and
    # "Multi-country" carry dashes of their own.
    dashes = [d for d in _DASH.finditer(text) if not text[: d.start()].lower().endswith("multi")]
    for dash in reversed(dashes):
        disease, location = text[: dash.start()].strip(), text[dash.end():].strip()
        if not location:
            continue
        countries, unmatched, unplaceable = _resolve(location)
        if countries or (unplaceable and not unmatched):
            return _classify(disease, location)

    parts = [p.strip() for p in text.split(",")]
    for i in range(1, len(parts)):
        location = ", ".join(parts[i:])
        countries, unmatched, unplaceable = _resolve(location)
        if countries or (unplaceable and not unmatched):
            return _classify(", ".join(parts[:i]), location)

    if dashes and text[dashes[-1].end():].strip():
        # A location is named but none of it is a country (or a global/regional word).
        last = dashes[-1]
        return _classify(text[: last.start()].strip(), text[last.end():].strip())
    return ParsedTitle(text, [], "unplaceable")


# ---------------------------------------------------------------------------------------
# Reports: parsing one API item, and deciding which outbreaks are current.

_END_DECLARED = re.compile(r"declared (?:the )?end of", re.I)
_SENTENCE_BREAK = re.compile(r"(?<=[.!?])\s+")
_UTC_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _now() -> datetime:
    """The clock the current-outbreak rule reads (a seam for the tests)."""
    return datetime.now(timezone.utc)


def _parse_time(value) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"not a timestamp: {value!r}")
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def report_url(url_name: str) -> str:
    return f"{DON_PAGE_URL}/item/{url_name}"


def _country_forms():
    """(pattern, forms): one pattern over every way WHO's text names a country (the map's
    names and the aliases), longest first so "Papua New Guinea" is not read as "Guinea",
    and the map name each form stands for."""
    forms = {_fold(name): name for name, *_ in COUNTRY_PLACES}
    forms.update({alias: name for alias, name in _ALIASES.items()})
    ordered = sorted(forms, key=len, reverse=True)
    pattern = re.compile(r"(?<![\w])(?:" + "|".join(re.escape(f) for f in ordered) + r")(?![\w])")
    return pattern, forms


_MENTION, _FORMS = _country_forms()


def ended_countries(summary: str, title_countries: list):
    """Which countries a summary says have declared their outbreak over, and whether it is
    an end declaration that names no country at all. A sentence such as "On 28 July, the
    Ministry of Health of Uganda declared the end of the BVD outbreak in the country"
    ends Uganda -- even in a report titled for another country, which carries on. A
    declaration naming no country applies to the report's own countries."""
    ended, nameless = [], False
    for sentence in _SENTENCE_BREAK.split(summary or ""):
        if not _END_DECLARED.search(sentence):
            continue
        named = [_FORMS[m.group(0)] for m in _MENTION.finditer(_fold(sentence))]
        if named:
            ended += [c for c in named if c not in ended]
        elif title_countries:
            ended += [c for c in title_countries if c not in ended]
        else:
            nameless = True
    return ended, nameless


def build_report(item: dict, expiry_days: float, log=None):
    """A stored report from one API item, or None when it is to be ignored: no summary (the
    legacy archive), older than the retention period, or a location that is none of ours.
    Raises ValueError when the item is not shaped like a report at all."""
    try:
        don_id, title = str(item["DonId"]), str(item["Title"])
        published = _parse_time(item["PublicationDate"])
        modified = _parse_time(item.get("LastModified") or item["PublicationDate"])
        summary = (item["Summary"] or "").strip()
        url_name = str(item["UrlName"])
    except (KeyError, TypeError) as e:
        raise ValueError(f"not a Disease Outbreak News item: {e!r}") from e
    if not summary or published < _now() - timedelta(days=expiry_days):
        return None
    parsed = parse_title(title)
    if parsed.kind == "unrecognised":
        if log:
            log(f"Disease outbreaks: {don_id} {title!r}: no country matched {parsed.unmatched}; skipped.")
        return None
    ended, nameless = ended_countries(summary, parsed.countries)
    return {
        "don_id": don_id, "title": title, "disease": parsed.disease, "key": parsed.key,
        "countries": parsed.countries, "ended": ended, "ends_unplaced": nameless,
        "kind": parsed.kind, "published": published, "modified": modified,
        "summary": summary, "url_name": url_name,
    }


def current_reports(reports: list, active_days: float):
    """(placed, unplaced): the reports that make outbreaks current right now.

    placed is a list of (report, country): for each (disease, country), the latest report
    naming that country, if it was published within `active_days` and the country has not
    been declared over at or since it (by that report's own summary or a later report's).
    unplaced is the same per disease for reports that name no single country. Reports
    dated in the future are ignored."""
    now = _now()
    cutoff = now - timedelta(days=active_days)
    reports = [r for r in reports if r["published"] <= now]
    latest, ended_at, latest_unplaced = {}, {}, {}
    for r in reports:
        for country in r["countries"]:
            key = (r["key"], country)
            if key not in latest or r["published"] > latest[key]["published"]:
                latest[key] = r
        for country in r["ended"]:
            key = (r["key"], country)
            if key not in ended_at or r["published"] > ended_at[key]:
                ended_at[key] = r["published"]
        if r["kind"] == "unplaceable":
            if r["key"] not in latest_unplaced or r["published"] > latest_unplaced[r["key"]]["published"]:
                latest_unplaced[r["key"]] = r
    def is_current(key, country, r):
        ended = ended_at.get((key, country))
        return r["published"] >= cutoff and not (ended is not None and ended >= r["published"])

    ordered = sorted(latest.items(), key=lambda kv: (-kv[1]["published"].timestamp(), kv[0]))
    placed = [(r, country) for (key, country), r in ordered if is_current(key, country, r)]
    unplaced = [
        r for r in sorted(latest_unplaced.values(), key=lambda r: r["published"], reverse=True)
        if r["published"] >= cutoff and not r["ends_unplaced"]
    ]
    return placed, unplaced


def current_as_geojson(reports: list, active_days: float) -> str:
    """The current outbreaks as a GeoJSON FeatureCollection -- one Point per placed country
    at the country's label point -- with the not-on-the-map reports in a foreign member,
    `unplaced`."""
    places = {name: (lon, lat) for name, _iso2, lon, lat in COUNTRY_PLACES}
    placed, unplaced = current_reports(reports, active_days)

    def common(r):
        return {
            "don_id": r["don_id"], "title": r["title"], "disease": r["disease"],
            "published": r["published"].strftime(_UTC_FORMAT), "summary": r["summary"],
            "url": report_url(r["url_name"]),
        }

    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": list(places[country])},
            "properties": {**common(r), "country": country, "countries": r["countries"]},
        }
        for r, country in placed
        if country in places
    ]
    return json.dumps(
        {"type": "FeatureCollection", "features": features, "unplaced": [common(r) for r in unplaced]},
        ensure_ascii=False,
    )

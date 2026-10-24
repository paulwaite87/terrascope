#!/usr/bin/env python3
"""WHO Disease Outbreak News -> database.

Pure data (no render): each cycle asks WHO's news API for the 100 newest reports, parses
each (lib/disease_outbreaks.py: the countries a title names, whether the summary declares an
outbreak over) and upserts them, so the table accumulates the history. Which reports make an
outbreak "current" is decided when the route is read, so a change to the window needs no
re-collection. The frontend reads it via /api/disease_outbreaks -- the browser never calls WHO.

A page is validated whole before anything is stored: a failed, truncated or garbled response
raises (so _drive() records it and Data Status shows the error) and leaves the stored reports
as they were. Reports with an empty summary (WHO's legacy archive, bulk-dated in 2024),
older than the retention period, or naming a place that is none of the map's countries are
skipped.
"""
import logging

from terrascope.collectors.base import CollectorBase
from terrascope.db.disease_outbreaks_adapter import DiseaseOutbreaksAdapter
from terrascope.lib.disease_outbreaks import DON_API_URL, DON_PAGE_URL, PAGE_SIZE, build_report

logger = logging.getLogger(__name__)

# Only what the layer uses -- the full items carry six HTML sections that run to megabytes.
_SELECT = "DonId,Title,PublicationDate,LastModified,UrlName,Summary"
DEFAULT_EXPIRY_DAYS = 180


class DiseaseOutbreaksCollector(CollectorBase):
    section = "disease_outbreaks"
    channel_key = "disease_outbreaks"
    datasource_key = "disease_outbreaks"
    display_label = "WHO Disease Outbreak News"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.disease_outbreaks_adapter = DiseaseOutbreaksAdapter()

    def source_url(self) -> str | None:
        """Overridden: WHO's Disease Outbreak News page, not the API."""
        return DON_PAGE_URL

    def collect(self) -> None:
        expiry = float(
            self.config.get_setting("housekeeper", "disease_outbreaks_expiry_days", DEFAULT_EXPIRY_DAYS)
        )
        url = self.datasource_url(self.datasource_key) or DON_API_URL
        r = self._get(
            url,
            params={"$orderby": "PublicationDate desc", "$top": PAGE_SIZE, "$select": _SELECT},
            timeout=60,
        )
        if r is None:
            raise RuntimeError("Disease outbreaks: the WHO request failed")
        try:
            items = r.json()["value"]
            if not isinstance(items, list):
                raise ValueError("'value' is not a list")
            reports = [
                report
                for item in items
                if (report := build_report(item, expiry, logger.warning)) is not None
            ]
        except (ValueError, KeyError, TypeError) as e:
            raise RuntimeError(f"Disease outbreaks: unusable WHO response ({e!r})") from e

        for report in reports:
            self.disease_outbreaks_adapter.upsert_report(report)
        logger.info(f"Disease outbreaks: stored {len(reports)} of {len(items)} report(s).")

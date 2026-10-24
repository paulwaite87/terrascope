#!/usr/bin/env python3
"""NASA SMAP L4 root-zone soil moisture percentile -> file cache.

Each cycle asks NASA's public CMR search for the newest SPL4SMGP granule and, unless the
cache already holds that granule, reads one variable from it over OPeNDAP with the
Earthdata token: `sm_rootzone_pctl` (about 25 MB, against 145 MB for the granule) plus
one column of cell latitudes and one row of cell longitudes (the grid is regular in
each). The cache is one npz under {workdir}/data that the soil moisture updater
(terrascope.tasks.soil_moisture) renders; this collector's only job is to keep it fresh.

A failure of any kind raises RuntimeError so the orchestrator's _drive() records it and
Data Status shows the error; the stored data is only ever replaced after everything has
been fetched and validated. With no EARTHDATA_TOKEN nothing is requested.

Collection is UNCONDITIONAL of the layer's `enabled` flag (frontend visibility only).
"""
import logging

import numpy as np

from terrascope.collectors.base import CollectorBase
from terrascope.lib import soil_moisture as sm
from terrascope.lib.flood_risk import resolve_earthdata_token

logger = logging.getLogger(__name__)

_VARIABLE = "/Geophysical_Data/sm_rootzone_pctl"
_SERVICE_REL = "/service#"


def _newest_granule(doc) -> dict:
    """{'id', 'start', 'opendap'} from CMR's granule search answer. ValueError if the
    answer has no granule or no OPeNDAP link."""
    try:
        entry = doc["feed"]["entry"][0]
        opendap = next(
            link["href"]
            for link in entry["links"]
            if link.get("rel", "").endswith(_SERVICE_REL) and "opendap" in link["href"]
        )
        return {"id": entry["id"], "start": sm.normalise_time(entry["time_start"]), "opendap": opendap}
    except (KeyError, IndexError, StopIteration, TypeError) as e:
        raise ValueError(f"no usable SMAP granule in the CMR answer ({e!r})") from e


class SoilMoistureCollector(CollectorBase):
    section = "soil_moisture"
    channel_key = "soil_moisture"
    datasource_key = "soil_moisture"
    display_label = "NASA SMAP Soil Moisture"

    def source_url(self) -> str | None:
        """Overridden: the dataset's landing page, not the search API."""
        return sm.SMAP_PAGE_URL

    def _array(self, opendap: str, constraint: str, shape: tuple, token: str) -> np.ndarray:
        url = f"{opendap}.dap?dap4.ce={constraint}"
        r = self._get(url, timeout=300, headers={"Authorization": f"Bearer {token}"})
        if r is None:
            raise RuntimeError(f"Soil moisture: request failed: {url}")
        try:
            return sm.parse_dap4_float32(r.content, shape)
        except ValueError as e:
            raise RuntimeError(f"Soil moisture: {url}: {e}") from e

    def collect(self) -> None:
        token = resolve_earthdata_token("Soil moisture")
        if token is None:
            return
        search = self.datasource_url(self.datasource_key) or sm.CMR_GRANULES_URL
        r = self._get(
            search,
            params={"short_name": sm.SMAP_SHORT_NAME, "sort_key": "-start_date", "page_size": 1},
        )
        if r is None:
            raise RuntimeError("Soil moisture: the CMR granule search failed")
        try:
            granule = _newest_granule(r.json())
        except ValueError as e:
            raise RuntimeError(f"Soil moisture: {e}") from e

        dest = sm.soil_moisture_cache_path(self.workdir)
        try:
            held = sm.load_soil_moisture(dest)[3]
        except (OSError, KeyError, ValueError):
            held = None
        if held == granule["id"]:
            logger.debug(f"Soil moisture: already holding {granule['id']}.")
            return

        rows, cols = sm.GRID_SHAPE
        logger.info(f"Soil moisture: fetching granule {granule['id']} ({granule['start']}).")
        percentile = self._array(granule["opendap"], _VARIABLE, sm.GRID_SHAPE, token)
        lat = self._array(granule["opendap"], f"/cell_lat%5B0:{rows - 1}%5D%5B0%5D", (rows, 1), token)
        lon = self._array(granule["opendap"], f"/cell_lon%5B0%5D%5B0:{cols - 1}%5D", (1, cols), token)

        percentile = np.where(percentile == sm.FILL_VALUE, np.nan, percentile)
        sm.save_soil_moisture(
            dest, percentile, lat[:, 0], lon[0, :], granule["id"], granule["start"]
        )
        logger.info(f"Soil moisture: stored {granule['id']}.")

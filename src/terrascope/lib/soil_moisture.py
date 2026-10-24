#!/usr/bin/env python3
"""Soil Moisture layer data: NASA SMAP Level 4 (SPL4SMGP, v8), the model-assimilated
global 3-hourly 9 km surface and root-zone soil moisture product, reduced to one field --
`sm_rootzone_pctl`, root-zone (0-100 cm) soil moisture as a percentile 0..100 of the
product's own climatology, so it reads as "drier or wetter than normal for that place".
It is only defined over vegetated, unfrozen land (about 10% of the grid): deserts and
frozen ground carry the fill value.

The grid is the 9 km EASE-Grid 2.0 global cylindrical equal-area grid, 1624 rows by 3856
columns: latitude varies only by row (+84.66 .. -84.66, unevenly spaced) and longitude
only by column (-179.95 .. +179.95, even), so one column and one row stand for the whole
2-D coordinate arrays.

Granules are found through NASA's public CMR search (no key) and read over OPeNDAP with
the Earthdata bearer token, one variable at a time (about 25 MB instead of the 145 MB
granule). OPeNDAP (DAP4) answers in a chunked binary stream; parse_dap4_float32() decodes
it. The cache path lives here so the collector and the updater can never disagree about
where the data is.
"""
import os
import re
import zlib
from datetime import datetime, timezone

import numpy as np

CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
SMAP_PAGE_URL = "https://nsidc.org/data/spl4smgp/versions/8"
SMAP_SHORT_NAME = "SPL4SMGP"
GRID_SHAPE = (1624, 3856)  # rows (latitude) by columns (longitude)
FILL_VALUE = -9999.0

_FLAG_LAST = 0x01
_FLAG_ERROR = 0x02
_FLAG_LITTLE_ENDIAN = 0x04


def soil_moisture_cache_path(workdir: str) -> str:
    """Under {workdir}/data (bind-mounted): written by SoilMoistureCollector in
    data_collector, read by SoilMoistureUpdater in layer_builder."""
    return os.path.join(workdir, "data", "soil_moisture_cache_smap.npz")


def parse_dap4_float32(content: bytes, shape: tuple) -> np.ndarray:
    """Decode a DAP4 response holding one float32 array of `shape`. The stream is a
    series of chunks, each a flags byte plus a 24-bit big-endian length: the first holds
    the XML header, the rest the data (the last four data bytes are a little-endian
    CRC32 of the values), ending in a chunk flagged as last. Raises ValueError for
    anything else: truncation, a server error chunk, a bad checksum or the wrong size."""
    pos, chunks = 0, []
    while True:
        if pos + 4 > len(content):
            raise ValueError("OPeNDAP response ended before its last chunk")
        flags = content[pos]
        length = int.from_bytes(content[pos + 1 : pos + 4], "big")
        payload = content[pos + 4 : pos + 4 + length]
        if len(payload) < length:
            raise ValueError("OPeNDAP response is truncated (or is not a DAP4 stream)")
        pos += 4 + length
        if flags & _FLAG_ERROR:
            text = payload.decode("utf-8", "replace")
            message = re.search(r"<Message>(.*?)</Message>", text, re.S)
            raise ValueError(f"OPeNDAP server error: {(message.group(1) if message else text).strip()}")
        chunks.append((flags, payload))
        if flags & _FLAG_LAST:
            break

    data_chunks = [(f, p) for f, p in chunks[1:] if p]
    if not data_chunks:
        raise ValueError("OPeNDAP response carries no data")
    little_endian = bool(data_chunks[0][0] & _FLAG_LITTLE_ENDIAN)
    body = b"".join(p for _, p in data_chunks)
    values, checksum = body[:-4], body[-4:]
    if zlib.crc32(values).to_bytes(4, "little") != checksum:
        raise ValueError("OPeNDAP data failed its checksum")
    expected = int(np.prod(shape)) * 4
    if len(values) != expected:
        raise ValueError(f"OPeNDAP array has {len(values) // 4} values, expected shape {shape}")
    return np.frombuffer(values, dtype="<f4" if little_endian else ">f4").reshape(shape).astype("float32")


def normalise_time(value) -> str:
    """CMR's '2026-10-20T21:00:00.000Z' as '2026-10-20T21:00:00Z'. ValueError if it is
    not a timestamp."""
    if not isinstance(value, str):
        raise ValueError(f"granule time is not a string: {value!r}")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_soil_moisture(path, percentile, lat, lon, granule_id: str, start: str) -> None:
    """Atomically store the current state: the percentile grid (NaN = no data), the
    latitude of each row and the longitude of each column, and the granule it came from."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.tmp"
    with open(tmp, "wb") as f:
        np.savez_compressed(
            f,
            percentile=np.asarray(percentile, dtype="float32"),
            lat=np.asarray(lat, dtype="float64"),
            lon=np.asarray(lon, dtype="float64"),
            granule_id=np.array(granule_id),
            start=np.array(start),
        )
    os.replace(tmp, path)


def load_soil_moisture(path):
    """(percentile, lat, lon, granule_id, start) as stored by save_soil_moisture."""
    with np.load(path) as z:
        return (
            z["percentile"], z["lat"], z["lon"], str(z["granule_id"]), str(z["start"]),
        )

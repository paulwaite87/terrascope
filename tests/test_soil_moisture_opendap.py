#!/usr/bin/env python3
"""parse_dap4_float32(): the pure decoder for NASA's OPeNDAP (DAP4) responses, against
a recording of the real thing -- a 4 x 6 slice of SMAP L4's sm_rootzone_pctl, requested
from opendap.earthdata.nasa.gov on 2026-10-22 (tests/fixtures/smap_l4_pctl_slice.dap).
The expected values are the ones printed from the full real granule at the same
indices, not recomputed here. A DAP4 response is a length-prefixed XML header chunk,
then data chunks (flags byte + 24-bit length), the data ending in a little-endian CRC32,
then a zero-length last chunk."""

import zlib
from pathlib import Path

import numpy as np
import pytest

from terrascope.lib.soil_moisture import parse_dap4_float32

FIXTURE = Path(__file__).parent / "fixtures" / "smap_l4_pctl_slice.dap"

# Printed to one decimal from the full real granule (the stored values differ in the
# third decimal, e.g. 36.507), hence the tolerance below.
REAL_BLOCK = [
    [36.5, 29.5, 26.5, 23.5, 19.5, 9.5],
    [37.5, 37.5, 33.5, 23.5, 25.5, 17.5],
    [37.5, 39.5, 37.5, 36.5, 31.5, 22.5],
    [37.5, 38.5, 42.5, 39.5, 26.5, 28.5],
]


def chunk(flags: int, payload: bytes) -> bytes:
    return bytes([flags]) + len(payload).to_bytes(3, "big") + payload


def response(values, flags=0x04, dmr=b"<Dataset/>", checksum=None):
    """A well-formed DAP4 response around `values`, split into two data chunks."""
    data = np.asarray(values, dtype="<f4").tobytes()
    crc = zlib.crc32(data).to_bytes(4, "little") if checksum is None else checksum
    half = len(data) // 2
    return (
        chunk(0x04, dmr)
        + chunk(flags, data[:half])
        + chunk(flags, data[half:] + crc)
        + chunk(0x05, b"")
    )


def test_the_real_recorded_slice_decodes_to_the_values_the_granule_holds():
    decoded = parse_dap4_float32(FIXTURE.read_bytes(), (4, 6))

    assert decoded.shape == (4, 6)
    assert decoded.dtype == np.float32
    np.testing.assert_allclose(decoded, REAL_BLOCK, atol=0.05)


def test_a_response_split_into_several_chunks_is_reassembled_in_order():
    values = np.arange(12, dtype="<f4").reshape(3, 4)

    decoded = parse_dap4_float32(response(values), (3, 4))

    np.testing.assert_array_equal(decoded, values)


def test_big_endian_data_is_read_with_its_declared_byte_order():
    values = np.array([[1.5, -9999.0]], dtype=">f4")
    data = values.tobytes()
    body = (
        chunk(0x00, b"<Dataset/>")
        + chunk(0x00, data + zlib.crc32(data).to_bytes(4, "little"))
        + chunk(0x01, b"")
    )

    np.testing.assert_array_equal(parse_dap4_float32(body, (1, 2)), [[1.5, -9999.0]])


def test_a_corrupted_value_fails_the_checksum():
    good = bytearray(response(np.ones((2, 2))))
    # flip a byte inside the data chunk (after the 10-byte header chunk's 14 bytes)
    good[len(chunk(0x04, b"<Dataset/>")) + 6] ^= 0xFF

    with pytest.raises(ValueError, match="checksum"):
        parse_dap4_float32(bytes(good), (2, 2))


def test_a_stream_cut_short_is_rejected():
    full = response(np.ones((2, 2)))

    with pytest.raises(ValueError):
        parse_dap4_float32(full[: len(full) - 12], (2, 2))


def test_an_array_of_the_wrong_size_is_rejected():
    with pytest.raises(ValueError, match="shape"):
        parse_dap4_float32(response(np.ones((2, 3))), (2, 2))


def test_an_error_chunk_from_the_server_is_raised_with_its_message():
    body = chunk(0x04, b"<Dataset/>") + chunk(0x02, b"<Error><Message>no such granule</Message></Error>")

    with pytest.raises(ValueError, match="no such granule"):
        parse_dap4_float32(body, (2, 2))


def test_something_that_is_not_a_dap4_stream_is_rejected():
    with pytest.raises(ValueError):
        parse_dap4_float32(b"<!doctype html><html>Bad Request</html>", (2, 2))

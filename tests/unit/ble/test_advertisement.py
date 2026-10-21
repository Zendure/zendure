"""Tests for reading the serial number out of BLE manufacturer data."""

import pytest

from zendure.ble.advertisement import parse_serial_number


def _manufacturer_data(serial: str, trailer: int = 0x16) -> dict[int, bytes]:
    raw = serial.encode("ascii")
    return {int.from_bytes(raw[:2], "little"): raw[2:] + bytes([trailer])}


def test_parse_round_trip() -> None:
    assert parse_serial_number(_manufacturer_data("TESTDEV00000001")) == (
        "TESTDEV00000001"
    )


def test_parse_matches_captured_layout() -> None:
    # Same byte layout as a real advertisement: company id 0x4554 is "TE".
    data = {0x4554: b"STDEV00000001\x16"}
    assert parse_serial_number(data) == "TESTDEV00000001"


@pytest.mark.parametrize("trailer", [0x0E, 0x16, 0x2E])
def test_parse_ignores_trailer(trailer: int) -> None:
    assert parse_serial_number(_manufacturer_data("TESTDEV00000001", trailer))


def test_parse_skips_unrelated_entries() -> None:
    data = {0x004C: b"\x02\x15apple", **_manufacturer_data("TESTDEV00000001")}
    assert parse_serial_number(data) == "TESTDEV00000001"


@pytest.mark.parametrize(
    "data",
    [
        pytest.param({}, id="empty"),
        pytest.param({0x4554: b"SHORT"}, id="too-short"),
        pytest.param({0x4554: b"STDEV00000001\x16extra"}, id="too-long"),
        pytest.param({0x4554: b"STDEV0000 001\x16"}, id="space"),
        pytest.param({0x4554: b"stdev00000001\x16"}, id="lowercase"),
        pytest.param({0x4554: "STDEV0000000é".encode() + b"\x16"}, id="non-ascii"),
        pytest.param({0x10000: b"STDEV00000001\x16"}, id="bad-company-id"),
    ],
)
def test_parse_rejects_other_devices(data: dict[int, bytes]) -> None:
    assert parse_serial_number(data) is None

"""Decoder tests, validated against the real SolarFlow 2400 AC+ report."""

import pytest

from zendure.exceptions import ValidationError
from zendure.protocols.local_http.codec import (
    decode_centi,
    decode_deci,
    decode_property,
    decode_remain_time,
    decode_signed_deci,
    decode_temperature,
    decode_version,
    encode_property,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(4810, 48.10), (4812, 48.12), (321, 3.21), (0, 0.0)],
)
def test_decode_centi(raw: int, expected: float) -> None:
    assert decode_centi(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(3071, 34.0), (3051, 32.0), (2731, 0.0)],
)
def test_decode_temperature(raw: int, expected: float) -> None:
    assert decode_temperature(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(0, 0.0), (10, 1.0), (0x8000, -3276.8), (0xFFFF, -0.1)],
)
def test_decode_signed_deci(raw: int, expected: float) -> None:
    assert decode_signed_deci(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [(4355, "1.1.3"), (0x0100, "0.1.0"), (0x2305, "2.3.5")],
)
def test_decode_version(raw: int, expected: str) -> None:
    assert decode_version(raw) == expected


def test_remain_time_sentinel_is_none() -> None:
    assert decode_remain_time(59940) is None
    assert decode_remain_time(60000) is None


def test_remain_time_real_value_passes() -> None:
    assert decode_remain_time(120) == 120


def test_decode_property_dispatches() -> None:
    assert decode_property("maxVol", 321) == 3.21
    assert decode_property("softVersion", 4355) == "1.1.3"
    assert decode_property("remainOutTime", 59940) is None


def test_decode_property_passthrough_unknown_key() -> None:
    assert decode_property("electricLevel", 10) == 10


def test_decode_property_passthrough_none() -> None:
    assert decode_property("maxVol", None) is None


@pytest.mark.parametrize(
    ("key", "raw", "expected"),
    [("socSet", 1000, 100.0), ("minSoc", 100, 10.0), ("socSet", 905, 90.5)],
)
def test_decode_deci_keys(key: str, raw: int, expected: float) -> None:
    assert decode_property(key, raw) == expected
    assert decode_deci(raw) == expected


@pytest.mark.parametrize(
    ("key", "value", "expected"),
    [
        ("socSet", 90, 900),
        ("socSet", 100.0, 1000),
        ("outputLimit", 800, 800),
        ("outputLimit", 800.0, 800),
        ("acMode", 2, 2),
    ],
)
def test_encode_property(key: str, value: float, expected: int) -> None:
    result = encode_property(key, value)
    assert result == expected
    assert isinstance(result, int)


def test_encode_round_trips_with_decode() -> None:
    assert decode_property("socSet", encode_property("socSet", 85)) == 85.0


@pytest.mark.parametrize(("key", "value"), [("outputLimit", 800.5), ("socSet", 90.55)])
def test_encode_rejects_non_whole_raw(key: str, value: float) -> None:
    with pytest.raises(ValidationError):
        encode_property(key, value)

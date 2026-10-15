"""Raw-value decoding for the zenSDK protocol.

Converts the device's raw integers into real-world values. These scaling rules
are zenSDK-specific, which is why they live in the protocol layer, not the
catalog. Every rule below was checked against a real SolarFlow 2400 AC+ report
(same property set as Max 5000 Pro); items whose sign/semantics still need a
live Max 5000 Pro are flagged "candidate" in the sensor catalog.
"""

from collections.abc import Callable

from ...exceptions import ValidationError
from ...models import PropertyValue

# remainOutTime uses 59940 (= 999 h) as an "invalid / infinite" sentinel.
_REMAIN_TIME_SENTINEL = 59940

# Keys the device stores in tenths (deci-percent): socSet=1000 means 100 %.
# Confirmed on a real report (socSet=1000, minSoc=100).
_DECI_KEYS = frozenset({"socSet", "minSoc"})
_ENCODE_TOLERANCE = 1e-6


def decode_deci(raw: int) -> float:
    """Scale a value stored in tenths. socSet 1000 -> 100.0 (%)."""
    return round(raw / 10, 1)


def decode_centi(raw: int) -> float:
    """Scale a value stored in hundredths (e.g. volts x100). 4810 -> 48.10."""
    return round(raw / 100, 2)


def decode_temperature(raw: int) -> float:
    """Deci-Kelvin to Celsius: (raw - 2731) / 10. 3071 -> 34.0 degC."""
    return round((raw - 2731) / 10, 1)


def decode_signed_deci(raw: int) -> float:
    """16-bit two's-complement value stored in deci-units. Used by batcur (A)."""
    signed = raw - 0x10000 if raw >= 0x8000 else raw
    return round(signed / 10, 1)


def decode_version(raw: int) -> str:
    """Decode a packed firmware version. 0x1103 (4355) -> '1.1.3'."""
    major = (raw & 0xF000) >> 12
    minor = (raw & 0x0F00) >> 8
    patch = raw & 0x00FF
    return f"{major}.{minor}.{patch}"


def decode_remain_time(raw: int) -> PropertyValue:
    """Minutes of remaining discharge, or None for the invalid sentinel."""
    if raw >= _REMAIN_TIME_SENTINEL:
        return None
    return raw


# Per-key decoders. A key not listed here passes through unchanged.
_DECODERS: dict[str, Callable[[int], PropertyValue]] = {
    "totalVol": decode_centi,
    "maxVol": decode_centi,
    "minVol": decode_centi,
    "maxTemp": decode_temperature,
    "hyperTmp": decode_temperature,
    "batcur": decode_signed_deci,
    "softVersion": decode_version,
    "remainOutTime": decode_remain_time,
    "socSet": decode_deci,
    "minSoc": decode_deci,
}


def decode_property(key: str, raw: PropertyValue) -> PropertyValue:
    """Decode one raw property value by key.

    Keys with no registered decoder (and non-int values) pass through as-is.
    """
    decoder = _DECODERS.get(key)
    if decoder is None or not isinstance(raw, int):
        return raw
    return decoder(raw)


def encode_property(key: str, value: int | float) -> int:
    """Encode a validated user-facing control value to the device's raw int.

    ``socSet`` 90 (%) -> 900. Every zenSDK write value is an integer, so a value
    that does not land on a whole raw unit is rejected rather than rounded.

    Raises:
        ValidationError: the scaled value is not a whole number.
    """
    scaled = value * 10 if key in _DECI_KEYS else value
    rounded = round(scaled)
    if abs(scaled - rounded) > _ENCODE_TOLERANCE:
        raise ValidationError(f"{key}={value} cannot be encoded as a whole raw value")
    return int(rounded)


__all__ = [
    "decode_centi",
    "decode_deci",
    "decode_property",
    "decode_remain_time",
    "decode_signed_deci",
    "decode_temperature",
    "decode_version",
    "encode_property",
]

"""Read-only property descriptions (protocol-agnostic).

Static declaration of every sensor the library exposes for the Max 5000 Pro:
its entity kind, unit, and HA-style classes. Raw-to-value decoding is NOT here
(it is a protocol detail in ``protocols/local_http/codec.py``); this table only
says what each entity *is*.

Keys use the vendor's original casing (``electricLevel``, ``packNum``) on
purpose. A reported key that is absent here is not turned into an entity.
"""

from collections.abc import Mapping

from ..models import EntityKind, SensorDescription


def _power(key: str) -> SensorDescription:
    return SensorDescription(
        key=key, unit="W", device_class="power", state_class="measurement"
    )


def _voltage(key: str) -> SensorDescription:
    return SensorDescription(
        key=key,
        unit="V",
        device_class="voltage",
        state_class="measurement",
        precision=2,
    )


def _temperature(key: str) -> SensorDescription:
    return SensorDescription(
        key=key,
        unit="°C",
        device_class="temperature",
        state_class="measurement",
        precision=1,
    )


def _binary(key: str, device_class: str | None = None) -> SensorDescription:
    return SensorDescription(
        key=key, kind=EntityKind.BINARY_SENSOR, device_class=device_class
    )


def _enum(key: str) -> SensorDescription:
    # Integer state code; the meaning table is validated on real hardware.
    return SensorDescription(key=key)


def _index(
    descriptions: tuple[SensorDescription, ...],
) -> Mapping[str, SensorDescription]:
    return {d.key: d for d in descriptions}


# --- Device-level sensors (from the Max 5000 Pro feature list) ---------------
_DEVICE: tuple[SensorDescription, ...] = (
    SensorDescription(
        key="electricLevel", unit="%", device_class="battery", state_class="measurement"
    ),
    _power("gridInputPower"),  # On-grid input (charge from grid)
    _power("gridOffPower"),  # Off-grid outlet: + output / - input (sign candidate)
    _power("outputHomePower"),  # On-grid output
    _power("outputPackPower"),  # Battery charge power
    _power("packInputPower"),  # Battery discharge power
    _power("solarInputPower"),  # Total PV input
    _power("solarPower1"),
    _power("solarPower2"),
    _power("solarPower3"),
    _power("solarPower4"),
    _temperature("hyperTmp"),  # Enclosure temperature
    SensorDescription(key="packNum", state_class="measurement"),  # pack count
    _enum("packState"),  # 0..2 (candidate)
    SensorDescription(
        key="remainOutTime",
        unit="min",
        device_class="duration",
        state_class="measurement",
    ),
    _binary("heatState", device_class="heat"),
    _binary("pass"),  # bypass state
    _binary("reverseState"),  # reverse-flow state
    _binary("socStatus"),  # SOC calibration state
)

# --- Per-battery sensors -----------------------------------------------------
_BATTERY: tuple[SensorDescription, ...] = (
    SensorDescription(
        key="socLevel", unit="%", device_class="battery", state_class="measurement"
    ),
    _power("power"),  # + charge / - discharge (sign candidate)
    _temperature("maxTemp"),
    _voltage("totalVol"),
    _voltage("maxVol"),
    _voltage("minVol"),
    SensorDescription(
        key="batcur",
        unit="A",
        device_class="current",
        state_class="measurement",
        precision=1,
    ),
    _enum("state"),  # 0 standby / 1 charging / 2 discharging (candidate)
    SensorDescription(key="softVersion"),  # decoded to a version string
)

DEVICE_SENSOR_DESCRIPTIONS: Mapping[str, SensorDescription] = _index(_DEVICE)
BATTERY_SENSOR_DESCRIPTIONS: Mapping[str, SensorDescription] = _index(_BATTERY)


def device_sensor(key: str) -> SensorDescription | None:
    """Return the device-level sensor description for ``key``, or ``None``."""
    return DEVICE_SENSOR_DESCRIPTIONS.get(key)


def battery_sensor(key: str) -> SensorDescription | None:
    """Return the per-battery sensor description for ``key``, or ``None``."""
    return BATTERY_SENSOR_DESCRIPTIONS.get(key)


__all__ = [
    "BATTERY_SENSOR_DESCRIPTIONS",
    "DEVICE_SENSOR_DESCRIPTIONS",
    "battery_sensor",
    "device_sensor",
]

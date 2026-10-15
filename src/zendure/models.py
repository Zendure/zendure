"""Public data contracts: immutable snapshots, static descriptions, and enums.

These are the stable types the library exposes to consumers (including the
future Home Assistant integration). Everything here is protocol-agnostic and
immutable; nothing in this package imports ``homeassistant``.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType

type PropertyValue = int | float | str | None
"""A single normalized property value, or ``None`` when missing/invalid.

Raw protocol integers are decoded to their real-world value (scaled volts,
Celsius, percent, ...) before reaching a snapshot. ``None`` means the value was
absent or failed validation and must never be shown as ``0``.
"""


def _freeze(data: Mapping[str, PropertyValue]) -> Mapping[str, PropertyValue]:
    """Return a read-only shallow copy so a snapshot cannot be mutated through it."""
    return MappingProxyType(dict(data))


class Availability(StrEnum):
    """Whether the device is currently reachable on the local network."""

    INITIALIZING = "initializing"
    ONLINE = "online"
    OFFLINE = "offline"


class EntityKind(StrEnum):
    """Generic entity category.

    Values match Home Assistant platform names for the consumer's convenience,
    but this is only a string classification; the library never imports HA.
    """

    SENSOR = "sensor"
    BINARY_SENSOR = "binary_sensor"
    NUMBER = "number"
    SELECT = "select"
    SWITCH = "switch"


@dataclass(frozen=True, slots=True)
class SensorDescription:
    """Static description of a read-only property.

    ``device_class`` / ``state_class`` follow Home Assistant's vocabulary but
    are plain strings here. Raw-to-value scaling lives in the codec, not here.
    """

    key: str
    kind: EntityKind = EntityKind.SENSOR
    unit: str | None = None
    device_class: str | None = None
    state_class: str | None = None
    precision: int | None = None


@dataclass(frozen=True, slots=True)
class ControlDescription:
    """Static description of a writable property.

    ``max_source_key`` names a reported property that supplies the dynamic upper
    bound (e.g. ``inverseMaxPower``); when set, the device's reported value wins
    over any static ``native_max``. ``options`` maps a raw int to a stable label
    for select-style controls.
    """

    key: str
    kind: EntityKind
    unit: str | None = None
    native_min: float | None = None
    native_max: float | None = None
    step: float | None = None
    max_source_key: str | None = None
    options: Mapping[int, str] | None = None
    writable: bool = True

    def __post_init__(self) -> None:
        if self.options is not None:
            object.__setattr__(self, "options", MappingProxyType(dict(self.options)))


@dataclass(frozen=True, slots=True)
class BatterySnapshot:
    """Immutable view of one battery pack at a point in time."""

    serial_number: str
    properties: Mapping[str, PropertyValue]
    pack_type: int | None = None
    model_key: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", _freeze(self.properties))


@dataclass(frozen=True, slots=True)
class DeviceSnapshot:
    """Immutable view of the whole device at a point in time."""

    serial_number: str
    model_key: str
    product_raw: str
    availability: Availability
    properties: Mapping[str, PropertyValue]
    batteries: tuple[BatterySnapshot, ...] = ()
    protocol_version: int | None = None
    message_id: int | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", _freeze(self.properties))
        object.__setattr__(self, "batteries", tuple(self.batteries))


__all__ = [
    "Availability",
    "BatterySnapshot",
    "ControlDescription",
    "DeviceSnapshot",
    "EntityKind",
    "PropertyValue",
    "SensorDescription",
]

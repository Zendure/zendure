"""Change events emitted as device state is merged.

Events are immutable and carry only what actually changed. A single listener
raising must not interrupt delivery to the others; ``ZendureClient`` isolates
listener failures when dispatching.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from .models import Availability, PropertyValue


def _freeze(data: Mapping[str, PropertyValue]) -> Mapping[str, PropertyValue]:
    return MappingProxyType(dict(data))


@dataclass(frozen=True, slots=True)
class DevicePropertiesChanged:
    """One or more device-level properties changed to new values."""

    serial_number: str
    changed: Mapping[str, PropertyValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed", _freeze(self.changed))


@dataclass(frozen=True, slots=True)
class DeviceAvailabilityChanged:
    """The device moved between online/offline/initializing."""

    serial_number: str
    previous: Availability
    current: Availability


@dataclass(frozen=True, slots=True)
class BatteryAdded:
    """A battery pack was seen for the first time."""

    device_serial_number: str
    battery_serial_number: str


@dataclass(frozen=True, slots=True)
class BatteryRemoved:
    """A battery pack is confirmed gone (only on a full snapshot, never a gap)."""

    device_serial_number: str
    battery_serial_number: str


@dataclass(frozen=True, slots=True)
class BatteryPropertiesChanged:
    """One or more properties of a battery pack changed."""

    device_serial_number: str
    battery_serial_number: str
    changed: Mapping[str, PropertyValue]

    def __post_init__(self) -> None:
        object.__setattr__(self, "changed", _freeze(self.changed))


@dataclass(frozen=True, slots=True)
class ProtocolWarning:
    """A non-fatal protocol anomaly: unknown key, unknown enum, or new version.

    The value is kept as-is and surfaced here rather than dropped or faked.
    """

    serial_number: str
    reason: str
    detail: str | None = None


type ZendureEvent = (
    DevicePropertiesChanged
    | DeviceAvailabilityChanged
    | BatteryAdded
    | BatteryRemoved
    | BatteryPropertiesChanged
    | ProtocolWarning
)

type EventListener = Callable[[ZendureEvent], None]


__all__ = [
    "BatteryAdded",
    "BatteryPropertiesChanged",
    "BatteryRemoved",
    "DeviceAvailabilityChanged",
    "DevicePropertiesChanged",
    "EventListener",
    "ProtocolWarning",
    "ZendureEvent",
]

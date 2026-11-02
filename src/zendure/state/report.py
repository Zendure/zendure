"""The protocol -> state input contract.

A ``DeviceReport`` is what the protocol layer produces after parsing + decoding
a message: already-decoded, protocol-agnostic values the state store merges.
Immutable so it can be passed around and compared safely.
"""

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType

from ..models import PropertyValue


@dataclass(frozen=True, slots=True)
class BatteryReport:
    """One battery pack's decoded values from a single report."""

    serial_number: str
    properties: Mapping[str, PropertyValue]
    pack_type: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", MappingProxyType(dict(self.properties)))


@dataclass(frozen=True, slots=True)
class DeviceReport:
    """A full decoded report for one device.

    ``batteries_present`` says whether the message actually carried a battery
    section. It is ``False`` when the section was absent (so the store must not
    treat missing batteries as removed) and ``True`` when it was present, even
    if empty (an empty present section does mean "no batteries anymore").
    """

    serial_number: str
    model_key: str
    product_raw: str
    properties: Mapping[str, PropertyValue]
    batteries: tuple[BatteryReport, ...] = ()
    batteries_present: bool = True
    protocol_version: int | None = None
    message_id: int | None = None
    timestamp: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "properties", MappingProxyType(dict(self.properties)))
        object.__setattr__(self, "batteries", tuple(self.batteries))


@dataclass(frozen=True, slots=True)
class FaultReport:
    """The fault codes a device reports as active right now (a full snapshot).

    ``codes`` holds each active code once, in the order the device listed them;
    it is empty when the device reports no fault. ``since`` maps a code to the
    Unix time the device stamped it with, when it did.
    """

    codes: tuple[int, ...]
    since: Mapping[int, int] = field(default_factory=dict)
    message_id: int | None = None
    timestamp: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "codes", tuple(self.codes))
        object.__setattr__(self, "since", MappingProxyType(dict(self.since)))


__all__ = ["BatteryReport", "DeviceReport", "FaultReport"]

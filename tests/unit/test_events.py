"""Contract tests for change events."""

import pytest

from zendure.events import (
    BatteryAdded,
    BatteryPropertiesChanged,
    DeviceAvailabilityChanged,
    DevicePropertiesChanged,
    ProtocolWarning,
    ZendureEvent,
)
from zendure.models import Availability


def test_device_properties_changed_is_read_only() -> None:
    event = DevicePropertiesChanged(serial_number="DEVSN", changed={"acMode": 2})
    with pytest.raises(TypeError):
        event.changed["acMode"] = 1  # type: ignore[index]


def test_changed_mapping_copied() -> None:
    source = {"acMode": 2}
    event = DevicePropertiesChanged(serial_number="DEVSN", changed=source)
    source["acMode"] = 1
    assert event.changed["acMode"] == 2


def test_availability_changed_fields() -> None:
    event = DeviceAvailabilityChanged(
        serial_number="DEVSN",
        previous=Availability.INITIALIZING,
        current=Availability.ONLINE,
    )
    assert event.previous is Availability.INITIALIZING
    assert event.current is Availability.ONLINE


def test_event_variants_are_zendure_events() -> None:
    events: list[ZendureEvent] = [
        DevicePropertiesChanged(serial_number="D", changed={}),
        DeviceAvailabilityChanged(
            serial_number="D",
            previous=Availability.ONLINE,
            current=Availability.OFFLINE,
        ),
        BatteryAdded(device_serial_number="D", battery_serial_number="B"),
        BatteryPropertiesChanged(
            device_serial_number="D",
            battery_serial_number="B",
            changed={"socLevel": 10},
        ),
        ProtocolWarning(serial_number="D", reason="unknown_key", detail="foo"),
    ]
    assert len(events) == 5

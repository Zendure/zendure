"""Contract tests for the immutable public models."""

import dataclasses

import pytest

from zendure.models import (
    Availability,
    BatterySnapshot,
    ControlDescription,
    DeviceSnapshot,
    EntityKind,
)


def _device(**overrides: object) -> DeviceSnapshot:
    defaults: dict[str, object] = {
        "serial_number": "DEVSN",
        "model_key": "max_5000_pro",
        "product_raw": "SolarFlowMax5000Pro",
        "availability": Availability.ONLINE,
        "properties": {"electricLevel": 10},
    }
    defaults.update(overrides)
    return DeviceSnapshot(**defaults)  # type: ignore[arg-type]


def test_device_snapshot_is_frozen() -> None:
    device = _device()
    with pytest.raises(dataclasses.FrozenInstanceError):
        device.serial_number = "other"  # type: ignore[misc]


def test_properties_mapping_is_read_only() -> None:
    device = _device(properties={"electricLevel": 10})
    with pytest.raises(TypeError):
        device.properties["electricLevel"] = 99  # type: ignore[index]


def test_properties_are_copied_not_aliased() -> None:
    source = {"electricLevel": 10}
    device = _device(properties=source)
    source["electricLevel"] = 99
    assert device.properties["electricLevel"] == 10


def test_batteries_coerced_to_tuple() -> None:
    battery = BatterySnapshot(serial_number="BATSN", properties={"socLevel": 10})
    device = _device(batteries=[battery])
    assert isinstance(device.batteries, tuple)


def test_none_value_is_preserved() -> None:
    device = _device(properties={"remainOutTime": None})
    assert device.properties["remainOutTime"] is None


def test_battery_snapshot_properties_read_only() -> None:
    battery = BatterySnapshot(serial_number="BATSN", properties={"socLevel": 10})
    with pytest.raises(TypeError):
        battery.properties["socLevel"] = 99  # type: ignore[index]


def test_control_options_frozen() -> None:
    control = ControlDescription(
        key="acMode",
        kind=EntityKind.SELECT,
        options={1: "input", 2: "output"},
    )
    assert control.options is not None
    with pytest.raises(TypeError):
        control.options[3] = "nope"  # type: ignore[index]

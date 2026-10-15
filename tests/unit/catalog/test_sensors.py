"""Tests for the read-only sensor description table."""

from zendure.catalog.sensors import battery_sensor, device_sensor
from zendure.models import EntityKind


def test_device_sensor_lookup() -> None:
    desc = device_sensor("electricLevel")
    assert desc is not None
    assert desc.unit == "%"
    assert desc.device_class == "battery"


def test_power_sensor_shape() -> None:
    desc = device_sensor("solarInputPower")
    assert desc is not None
    assert desc.unit == "W"
    assert desc.state_class == "measurement"


def test_binary_sensor_kind() -> None:
    desc = device_sensor("heatState")
    assert desc is not None
    assert desc.kind is EntityKind.BINARY_SENSOR


def test_four_solar_channels_present() -> None:
    for n in range(1, 5):
        assert device_sensor(f"solarPower{n}") is not None
    assert device_sensor("solarPower5") is None


def test_battery_sensor_lookup() -> None:
    desc = battery_sensor("maxVol")
    assert desc is not None
    assert desc.unit == "V"
    assert desc.precision == 2


def test_battery_current_shape() -> None:
    desc = battery_sensor("batcur")
    assert desc is not None
    assert desc.unit == "A"
    assert desc.precision == 1


def test_unknown_key_returns_none() -> None:
    assert device_sensor("acCouplingState") is None
    assert battery_sensor("mysteryKey") is None

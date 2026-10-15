"""Static capability definitions: protocol-agnostic, no runtime state.

Everything here is declared data (device models, property descriptions, battery
rules) plus the pure functions that look it up. These tables replace the
inheritance tree and runtime entity-building of the old integration.
"""

from .controls import CONTROL_DESCRIPTIONS, control, validate_control
from .devices import DeviceCapability, lookup_device, normalize_product
from .sensors import (
    BATTERY_SENSOR_DESCRIPTIONS,
    DEVICE_SENSOR_DESCRIPTIONS,
    battery_sensor,
    device_sensor,
)

__all__ = [
    "BATTERY_SENSOR_DESCRIPTIONS",
    "CONTROL_DESCRIPTIONS",
    "DEVICE_SENSOR_DESCRIPTIONS",
    "DeviceCapability",
    "battery_sensor",
    "control",
    "device_sensor",
    "lookup_device",
    "normalize_product",
    "validate_control",
]

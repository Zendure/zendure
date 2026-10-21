"""Async local-network client for Zendure energy devices.

Talks to a device on the LAN over the zenSDK HTTP protocol (``GET
/properties/report`` + ``POST /properties/write``). No cloud, no MQTT, no app
token. This package never imports ``homeassistant``: a thin Home Assistant
integration consumes it in a later phase.

Public surface is re-exported here; everything else is an implementation detail.
"""

from .client import ZendureClient
from .events import (
    BatteryAdded,
    BatteryPropertiesChanged,
    BatteryRemoved,
    DeviceAvailabilityChanged,
    DevicePropertiesChanged,
    EventListener,
    ProtocolWarning,
    ZendureEvent,
)
from .exceptions import (
    ClientClosedError,
    DeviceMismatchError,
    MalformedResponseError,
    ProvisioningError,
    ProvisioningFailedError,
    ProvisioningTimeoutError,
    UnsupportedDeviceError,
    UnsupportedPropertyError,
    ValidationError,
    WriteNotConfirmedError,
    WriteRejectedError,
    ZendureConnectionError,
    ZendureError,
    ZendureProtocolError,
)
from .local import create_local_client
from .models import (
    Availability,
    BatterySnapshot,
    ControlDescription,
    DeviceSnapshot,
    EntityKind,
    PropertyValue,
    SensorDescription,
)

__version__ = "0.2.0"

__all__ = [
    "Availability",
    "BatteryAdded",
    "BatteryPropertiesChanged",
    "BatteryRemoved",
    "BatterySnapshot",
    "ClientClosedError",
    "ControlDescription",
    "DeviceAvailabilityChanged",
    "DeviceMismatchError",
    "DevicePropertiesChanged",
    "DeviceSnapshot",
    "EntityKind",
    "EventListener",
    "MalformedResponseError",
    "PropertyValue",
    "ProtocolWarning",
    "ProvisioningError",
    "ProvisioningFailedError",
    "ProvisioningTimeoutError",
    "SensorDescription",
    "UnsupportedDeviceError",
    "UnsupportedPropertyError",
    "ValidationError",
    "WriteNotConfirmedError",
    "WriteRejectedError",
    "ZendureClient",
    "ZendureConnectionError",
    "ZendureError",
    "ZendureEvent",
    "ZendureProtocolError",
    "__version__",
    "create_local_client",
]

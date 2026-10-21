"""Exception hierarchy.

The library only raises ``ZendureError`` subclasses. External errors (aiohttp,
JSON decoding, ...) are caught at the boundary and re-raised as the matching
library exception with the original cause preserved via ``raise ... from err``.
"""

from ._redact import mask_serial


class ZendureError(Exception):
    """Base class for every error raised by this library."""


class ZendureConnectionError(ZendureError):
    """The device could not be reached (network error, timeout, refused)."""


class ZendureProtocolError(ZendureError):
    """A response could not be understood as a valid zenSDK message."""


class MalformedResponseError(ZendureProtocolError):
    """A response arrived but was not valid JSON or lacked required fields."""


class WriteRejectedError(ZendureProtocolError):
    """The device received the write but reported it as failed.

    ``code`` is the device's raw reply ``code`` when it answered with a failure
    body, otherwise the HTTP status. The exception message is Chinese for the
    user; unknown codes keep the number.
    """

    def __init__(self, message: str, *, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


class DeviceMismatchError(ZendureProtocolError):
    """The host answered with a different device than expected.

    Typical cause: DHCP handed the IP to another Zendure device. Writes must not
    reach the wrong device, so this is treated as a failed read. Serial numbers
    in the message are masked.
    """

    def __init__(self, expected: str, actual: str) -> None:
        super().__init__(
            f"expected device {mask_serial(expected)}, got {mask_serial(actual)}"
        )
        self.expected = expected
        self.actual = actual


class WriteNotConfirmedError(ZendureProtocolError):
    """The write was accepted but a fresh report did not confirm its value."""


class ClientClosedError(ZendureError):
    """The client was used after ``close()``."""


class UnsupportedDeviceError(ZendureError):
    """The device's product model is not registered in the capability catalog."""

    def __init__(self, product: str) -> None:
        super().__init__(f"Unsupported device product: {product!r}")
        self.product = product


class UnsupportedPropertyError(ZendureError):
    """A property key is not registered in the catalog."""

    def __init__(self, key: str) -> None:
        super().__init__(f"Unsupported property: {key!r}")
        self.key = key


class ProvisioningError(ZendureError):
    """Wi-Fi provisioning over BLE did not complete."""


class ProvisioningFailedError(ProvisioningError):
    """The device reported that it could not join the Wi-Fi network.

    Typical causes: wrong password, network not found, or no DHCP lease.
    The device does not say which.
    """


class ProvisioningTimeoutError(ProvisioningError):
    """The device did not report a join result in time.

    The credentials may or may not have been applied.
    """


class ValidationError(ZendureError):
    """An input failed validation before any request was sent.

    Covers control values (range, step, enum, read-only), write bodies over the
    device limit, and invalid connection settings such as a malformed host.
    Nothing is sent to the device.
    """


__all__ = [
    "ClientClosedError",
    "DeviceMismatchError",
    "MalformedResponseError",
    "ProvisioningError",
    "ProvisioningFailedError",
    "ProvisioningTimeoutError",
    "UnsupportedDeviceError",
    "UnsupportedPropertyError",
    "ValidationError",
    "WriteNotConfirmedError",
    "WriteRejectedError",
    "ZendureConnectionError",
    "ZendureError",
    "ZendureProtocolError",
]

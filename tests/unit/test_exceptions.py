"""Contract tests for the exception hierarchy."""

import pytest

from zendure.exceptions import (
    MalformedResponseError,
    UnsupportedDeviceError,
    UnsupportedPropertyError,
    WriteRejectedError,
    ZendureConnectionError,
    ZendureError,
    ZendureProtocolError,
)


def test_all_errors_subclass_base() -> None:
    for exc in (
        ZendureConnectionError,
        ZendureProtocolError,
        MalformedResponseError,
        WriteRejectedError,
        UnsupportedDeviceError,
        UnsupportedPropertyError,
    ):
        assert issubclass(exc, ZendureError)


def test_protocol_subtypes() -> None:
    assert issubclass(MalformedResponseError, ZendureProtocolError)
    assert issubclass(WriteRejectedError, ZendureProtocolError)


def test_unsupported_device_carries_product() -> None:
    err = UnsupportedDeviceError("SolarFlow5000MaxPro")
    assert err.product == "SolarFlow5000MaxPro"
    assert "SolarFlow5000MaxPro" in str(err)


def test_unsupported_property_carries_key() -> None:
    err = UnsupportedPropertyError("mysteryKey")
    assert err.key == "mysteryKey"


def _reraise(root: Exception) -> None:
    try:
        raise root
    except ValueError as err:
        raise ZendureConnectionError("unreachable") from err


def test_cause_is_preserved() -> None:
    root = ValueError("boom")
    with pytest.raises(ZendureConnectionError) as excinfo:
        _reraise(root)
    assert excinfo.value.__cause__ is root

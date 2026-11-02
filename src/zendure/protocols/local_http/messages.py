"""Parse zenSDK replies: ``properties/report`` into a ``DeviceReport``, and
validate ``properties/write`` replies.

All validation of untrusted device input happens here: required identity
fields, structure and type checks, and a cap on battery count. Values are
decoded through the codec; unknown keys are kept (raw) but never become
entities, since only the catalog decides that.
"""

from collections.abc import Mapping
from typing import Any, Final

from ...catalog.devices import lookup_device
from ...exceptions import (
    DeviceMismatchError,
    MalformedResponseError,
    WriteRejectedError,
)
from ...models import PropertyValue
from ...state.report import BatteryReport, DeviceReport, FaultReport
from .codec import decode_property
from .write_errors import write_error_message

MAX_BATTERIES: Final = 32
"""Defensive bound on packData length (5000 Max Pro supports far fewer)."""

MAX_FAULT_ENTRIES: Final = 64
"""Defensive bound on the fault report's ``data`` length."""

# Year 2100: rejects garbage that would overflow datetime conversion.
_MAX_TIMESTAMP: Final = 4_102_444_800

_BATTERY_META_KEYS: Final = frozenset({"sn", "packType"})


def parse_report(payload: Mapping[str, Any]) -> DeviceReport:
    """Validate and decode one report.

    Raises:
        MalformedResponseError: missing identity or invalid structure.
        UnsupportedDeviceError: ``product`` is not a registered model.
    """
    serial_number = payload.get("sn")
    if not isinstance(serial_number, str) or not serial_number:
        raise MalformedResponseError("report has no device serial number")
    product = payload.get("product")
    if not isinstance(product, str) or not product:
        raise MalformedResponseError("report has no product identifier")
    capability = lookup_device(product)

    raw_properties = payload.get("properties", {})
    if not isinstance(raw_properties, Mapping):
        raise MalformedResponseError("report properties is not an object")

    batteries_present = "packData" in payload
    batteries = _parse_batteries(payload.get("packData", []))

    return DeviceReport(
        serial_number=serial_number,
        model_key=capability.model_key,
        product_raw=product,
        properties=_decode_values(raw_properties),
        batteries=batteries,
        batteries_present=batteries_present,
        protocol_version=_optional_int(payload.get("version")),
        message_id=_optional_int(payload.get("messageId")),
        timestamp=_optional_int(payload.get("timestamp")),
    )


def parse_fault_report(payload: Mapping[str, Any]) -> FaultReport:
    """Validate and decode one ``properties/error`` reply.

    Shape::

        {"messageId": 30, "timestamp": 1793085345, "deviceId": "...",
         "productKey": "...", "offData": 0, "eventId": 3,
         "data": [{"code": 6, "timestamp": 1793085345}, ...]}

    ``data`` lists every active fault (empty when there is none), so a reply
    is a full snapshot. Each code is kept once, in listed order; code 0 is
    skipped as "no fault". ``deviceId`` is a cloud id, not the serial number,
    so it cannot be checked here; the device report read just before already
    checks identity.

    Raises:
        MalformedResponseError: ``data`` missing or too long, or an entry
            without a non-negative integer ``code``.
    """
    entries = payload.get("data")
    if not isinstance(entries, list):
        raise MalformedResponseError("fault report data is not a list")
    if len(entries) > MAX_FAULT_ENTRIES:
        raise MalformedResponseError(
            f"fault report has {len(entries)} entries (limit {MAX_FAULT_ENTRIES})"
        )
    codes: list[int] = []
    since: dict[int, int] = {}
    for entry in entries:
        code = entry.get("code") if isinstance(entry, Mapping) else None
        if not isinstance(code, int) or isinstance(code, bool) or code < 0:
            raise MalformedResponseError(f"fault report entry {entry!r} is invalid")
        if not code or code in codes:
            continue
        codes.append(code)
        if (timestamp := _timestamp(entry.get("timestamp"))) is not None:
            since[code] = timestamp
    return FaultReport(
        codes=tuple(codes),
        since=since,
        message_id=_optional_int(payload.get("messageId")),
        timestamp=_optional_int(payload.get("timestamp")),
    )


def _timestamp(value: object) -> int | None:
    """A plausible Unix time in seconds, or ``None``."""
    if (seconds := _optional_int(value)) is None or not 0 < seconds < _MAX_TIMESTAMP:
        return None
    return seconds


WRITE_SUCCESS_CODE: Final = 200
"""``code`` value in a successful ``properties/write`` reply (device-confirmed)."""


def parse_write_response(payload: object, expected_serial: str) -> None:
    """Validate a ``properties/write`` reply for the device ``expected_serial``.

    Confirmed success shape::

        {"timestamp": ..., "messageId": ..., "success": true,
         "code": 200, "sn": "<device sn>"}

    Only ``success``, ``code`` and ``sn`` are interpreted. ``messageId`` is not
    correlated with the request id: the device may repeat or reset it.

    Check order: structure first, then identity (a reply from another device
    says nothing about this write), then outcome.

    Raises:
        MalformedResponseError: empty reply, not an object, or ``success`` /
            ``code`` / ``sn`` missing or of the wrong type.
        DeviceMismatchError: ``sn`` names a different device.
        WriteRejectedError: ``success`` is false or ``code`` is not 200.
            The message is Chinese; the raw ``code`` is attached unchanged.
    """
    if not isinstance(payload, Mapping):
        raise MalformedResponseError("write reply is empty or not a JSON object")
    success = payload.get("success")
    # Strict: only real JSON booleans/integers count; 1 / "true" / 200.0 do not.
    if not isinstance(success, bool):
        raise MalformedResponseError("write reply success is missing or not a bool")
    code = payload.get("code")
    if not isinstance(code, int) or isinstance(code, bool):
        raise MalformedResponseError("write reply code is missing or not an int")
    serial_number = payload.get("sn")
    if not isinstance(serial_number, str) or not serial_number:
        raise MalformedResponseError("write reply has no device serial number")

    if serial_number != expected_serial:
        raise DeviceMismatchError(expected_serial, serial_number)
    if not success or code != WRITE_SUCCESS_CODE:
        error_text = payload.get("error")
        message = write_error_message(
            code,
            error_text if isinstance(error_text, str) else None,
            http_status=200,
        )
        raise WriteRejectedError(message, code=code)


def _parse_batteries(raw: object) -> tuple[BatteryReport, ...]:
    if not isinstance(raw, list):
        raise MalformedResponseError("report packData is not a list")
    if len(raw) > MAX_BATTERIES:
        raise MalformedResponseError(
            f"report packData has {len(raw)} entries (limit {MAX_BATTERIES})"
        )
    batteries: list[BatteryReport] = []
    for pack in raw:
        if not isinstance(pack, Mapping):
            continue
        serial_number = pack.get("sn")
        # A pack without a usable serial cannot be tracked; skip it.
        if not isinstance(serial_number, str) or not serial_number:
            continue
        values = {k: v for k, v in pack.items() if k not in _BATTERY_META_KEYS}
        batteries.append(
            BatteryReport(
                serial_number=serial_number,
                properties=_decode_values(values),
                pack_type=_optional_int(pack.get("packType")),
            )
        )
    return tuple(batteries)


def _decode_values(raw: Mapping[str, Any]) -> dict[str, PropertyValue]:
    decoded: dict[str, PropertyValue] = {}
    for key, value in raw.items():
        scalar = _scalar(value)
        if isinstance(scalar, _NotScalar):
            continue
        decoded[str(key)] = decode_property(str(key), scalar)
    return decoded


class _NotScalar:
    pass


_NOT_SCALAR: Final = _NotScalar()


def _scalar(value: object) -> PropertyValue | _NotScalar:
    # JSON booleans become ints so 0/1 flags stay comparable to their raw form.
    if isinstance(value, bool):
        return int(value)
    if value is None or isinstance(value, (int, float, str)):
        return value
    return _NOT_SCALAR


def _optional_int(value: object) -> int | None:
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return None


__all__ = [
    "MAX_BATTERIES",
    "MAX_FAULT_ENTRIES",
    "WRITE_SUCCESS_CODE",
    "parse_fault_report",
    "parse_report",
    "parse_write_response",
]

"""Hand Wi-Fi credentials to a Zendure device over BLE, without the cloud.

The caller owns the BLE connection (Home Assistant connects through its
Bluetooth stack and proxies); this module only exchanges one request and one
reply on an already connected client and never retries the write, because a
timed-out write may already have reached the device.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from ipaddress import IPv4Address
from typing import Any, Final

from bleak import BleakClient
from bleak.backends.characteristic import BleakGATTCharacteristic
from bleak.exc import BleakError

from ..exceptions import (
    MalformedResponseError,
    ProvisioningFailedError,
    ProvisioningTimeoutError,
    ValidationError,
    ZendureConnectionError,
    ZendureProtocolError,
)
from .const import (
    COMMAND_CHAR_UUID,
    DEFAULT_PROVISION_TIMEOUT,
    HANDSHAKE_TIMEOUT,
    MAX_PACKET_BYTES,
    NOTIFY_CHAR_UUID,
    WRITE_TIMEOUT,
)

_LOGGER = logging.getLogger(__name__)

_REQUEST_METHOD: Final = "token"
_REPLY_METHOD: Final = "Token"
# The device greets a new subscriber and expects this answer before requests.
_HANDSHAKE_METHOD: Final = "BLESPP"
_HANDSHAKE_ACK: Final = b'{"method":"BLESPP_OK"}'
# Identifies Home Assistant as the provisioning client.
_SOURCE_HOME_ASSISTANT: Final = 2
# Device reply: 0 = joined the network, anything else = failed.
_RESULT_SUCCESS: Final = 0
_MAX_SSID_BYTES: Final = 32
_MIN_PASSWORD_BYTES: Final = 8
_MAX_PASSWORD_BYTES: Final = 64


@dataclass(frozen=True, slots=True)
class ProvisionResult:
    """Outcome of a successful provisioning.

    ``host`` is the address the device reported after joining the network, or
    ``None`` when it reported none; callers then fall back to discovery.
    """

    serial_number: str
    host: str | None


def build_provision_request(ssid: str, password: str) -> bytes:
    """Serialize the provisioning request.

    UTF-8 is sent verbatim (``ensure_ascii=False``) so non-ASCII network names
    are not turned into ``\\u`` escapes.

    Raises:
        ValidationError: SSID or password length is invalid for Wi-Fi, or the
            request exceeds the device's packet limit.
    """
    ssid_len = len(ssid.encode())
    if not 1 <= ssid_len <= _MAX_SSID_BYTES:
        raise ValidationError(f"SSID must be 1-{_MAX_SSID_BYTES} bytes")
    password_len = len(password.encode())
    if password_len and not _MIN_PASSWORD_BYTES <= password_len <= _MAX_PASSWORD_BYTES:
        raise ValidationError(
            f"password must be empty or {_MIN_PASSWORD_BYTES}-"
            f"{_MAX_PASSWORD_BYTES} bytes"
        )
    payload = {
        "method": _REQUEST_METHOD,
        "source": _SOURCE_HOME_ASSISTANT,
        "ssid": ssid,
        "password": password,
        "AM": 0,
    }
    body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
    if len(body) > MAX_PACKET_BYTES:
        raise ValidationError(
            f"provisioning request is {len(body)} bytes; "
            f"device limit is {MAX_PACKET_BYTES}"
        )
    return body


def parse_provision_reply(message: dict[str, Any]) -> ProvisionResult:
    """Interpret the device's ``Token`` reply.

    Raises:
        ProvisioningFailedError: the device reports it could not join.
        MalformedResponseError: ``result`` or ``deviceId`` is missing or wrong.
    """
    result = message.get("result")
    if not isinstance(result, int) or isinstance(result, bool):
        raise MalformedResponseError("provisioning reply has no integer result")
    if result != _RESULT_SUCCESS:
        raise ProvisioningFailedError(
            f"device could not join the Wi-Fi network (result={result})"
        )
    serial_number = message.get("deviceId")
    if not isinstance(serial_number, str) or not serial_number:
        raise MalformedResponseError("provisioning reply has no deviceId")
    return ProvisionResult(serial_number=serial_number, host=_host(message.get("ip")))


def _host(value: object) -> str | None:
    """Return a usable IPv4 address, or ``None`` if absent or a placeholder."""
    if not isinstance(value, str):
        return None
    try:
        address = IPv4Address(value)
    except ValueError:
        return None
    if address.is_unspecified or address.is_loopback or address.is_multicast:
        return None
    return str(address)


def _loggable_request(body: bytes) -> str:
    """Return the request exactly as sent, except the password value."""
    payload = json.loads(body)
    if payload.get("password"):
        payload["password"] = "***"
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


class _ReplyCollector:
    """Reassemble notifications into the ``BLESPP`` greeting and ``Token`` reply.

    Messages may arrive split across notifications or with a trailing NUL;
    other messages on the same characteristic are logged and ignored.
    """

    def __init__(self) -> None:
        self._buffer = bytearray()
        self.notifications = 0
        loop = asyncio.get_running_loop()
        self.greeting: asyncio.Future[dict[str, Any]] = loop.create_future()
        self.reply: asyncio.Future[dict[str, Any]] = loop.create_future()

    @property
    def buffered(self) -> int:
        """Bytes received that do not yet form a complete message."""
        return len(self._buffer)

    def __call__(self, _char: BleakGATTCharacteristic, data: bytearray) -> None:
        self.notifications += 1
        _LOGGER.debug("BLE RX %d bytes: %r", len(data), bytes(data))
        if self.reply.done():
            _LOGGER.debug("BLE notification after reply (%d bytes), ignored", len(data))
            return
        self._buffer.extend(data)
        try:
            message = json.loads(self._buffer.rstrip(b"\x00"))
        except json.JSONDecodeError, UnicodeDecodeError:
            _LOGGER.debug(
                "BLE notification %d bytes, %d buffered, waiting for the rest",
                len(data),
                len(self._buffer),
            )
            if len(self._buffer) > MAX_PACKET_BYTES:
                _LOGGER.debug("Dropping %d undecodable bytes", len(self._buffer))
                self._buffer.clear()
            return
        self._buffer.clear()
        method = message.get("method") if isinstance(message, dict) else None
        if method == _HANDSHAKE_METHOD and not self.greeting.done():
            _LOGGER.debug("BLE handshake greeting: %s", message)
            self.greeting.set_result(message)
        elif method == _REPLY_METHOD:
            _LOGGER.debug("BLE provisioning reply: %s", message)
            self.reply.set_result(message)
        else:
            _LOGGER.debug("Ignoring unrelated BLE message: %s", message)


async def _async_write(
    client: BleakClient,
    command: BleakGATTCharacteristic,
    data: bytes,
    logged: str,
) -> None:
    """Write ``data`` with response; ``logged`` is what the TX log shows."""
    _LOGGER.debug("BLE TX %d bytes to %s: %s", len(data), COMMAND_CHAR_UUID, logged)
    try:
        async with asyncio.timeout(WRITE_TIMEOUT):
            await client.write_gatt_char(command, data, response=True)
    except TimeoutError as err:
        raise ZendureConnectionError(
            "provisioning write was not acknowledged (outcome unknown)"
        ) from err
    except BleakError as err:
        raise ZendureConnectionError(f"provisioning write failed: {err}") from err
    _LOGGER.debug("BLE TX acknowledged")


def _characteristic(client: BleakClient, uuid: str) -> BleakGATTCharacteristic:
    char = client.services.get_characteristic(uuid)
    if char is None:
        raise ZendureProtocolError(
            f"device does not expose the provisioning characteristic {uuid}"
        )
    return char


async def async_provision_wifi(
    client: BleakClient,
    ssid: str,
    password: str,
    *,
    result_timeout: float = DEFAULT_PROVISION_TIMEOUT,
) -> ProvisionResult:
    """Send Wi-Fi credentials and wait until the device reports the result.

    ``client`` must already be connected; it is left connected on return.

    Raises:
        ValidationError: invalid credentials or request too large for the link.
        ZendureProtocolError: the device lacks the provisioning service.
        ZendureConnectionError: the BLE link failed, the device did not send
            its ``BLESPP`` greeting, or a write timed out (outcome unknown).
        ProvisioningFailedError: the device could not join the network.
        ProvisioningTimeoutError: no result within ``result_timeout`` seconds.
        MalformedResponseError: the reply could not be understood.
    """
    body = build_provision_request(ssid, password)
    command = _characteristic(client, COMMAND_CHAR_UUID)
    notify = _characteristic(client, NOTIFY_CHAR_UUID)
    if len(body) > command.max_write_without_response_size:
        raise ValidationError(
            f"provisioning request is {len(body)} bytes; the BLE link allows "
            f"{command.max_write_without_response_size}"
        )

    collector = _ReplyCollector()
    try:
        await client.start_notify(notify, collector)
    except BleakError as err:
        raise ZendureConnectionError(f"could not subscribe to replies: {err}") from err
    _LOGGER.debug(
        "BLE subscribed to %s (props=%s), write char %s (props=%s, max write %d)",
        NOTIFY_CHAR_UUID,
        notify.properties,
        COMMAND_CHAR_UUID,
        command.properties,
        command.max_write_without_response_size,
    )
    try:
        try:
            async with asyncio.timeout(HANDSHAKE_TIMEOUT):
                await collector.greeting
        except TimeoutError as err:
            _LOGGER.debug(
                "No %s greeting within %g s: %d notifications",
                _HANDSHAKE_METHOD,
                HANDSHAKE_TIMEOUT,
                collector.notifications,
            )
            raise ZendureConnectionError(
                f"device did not send {_HANDSHAKE_METHOD} within "
                f"{HANDSHAKE_TIMEOUT:g} s; BLE link not established"
            ) from err
        await _async_write(client, command, _HANDSHAKE_ACK, _HANDSHAKE_ACK.decode())
        # The password value is never logged, only its length.
        await _async_write(
            client,
            command,
            body,
            f"{_loggable_request(body)} (password_len={len(password.encode())})",
        )
        _LOGGER.debug("Waiting up to %g s for the Token reply", result_timeout)
        try:
            async with asyncio.timeout(result_timeout):
                message = await collector.reply
        except TimeoutError as err:
            _LOGGER.debug(
                "No provisioning reply after %g s: %d notifications, %d bytes buffered",
                result_timeout,
                collector.notifications,
                collector.buffered,
            )
            raise ProvisioningTimeoutError(
                f"no provisioning result within {result_timeout:g} s"
            ) from err
    finally:
        try:
            await client.stop_notify(notify)
        except BleakError:
            # The device may drop the link right after replying.
            _LOGGER.debug("Could not stop notifications", exc_info=True)

    result = parse_provision_reply(message)
    _LOGGER.debug(
        "Provisioned deviceId=%s, reported host=%s",
        result.serial_number,
        result.host,
    )
    return result


__all__ = [
    "ProvisionResult",
    "async_provision_wifi",
    "build_provision_request",
    "parse_provision_reply",
]

"""Tests for BLE Wi-Fi provisioning against a fake BLE client."""

import asyncio
import json
import logging
from collections.abc import Callable
from typing import Any
from unittest.mock import MagicMock

import pytest
from bleak.exc import BleakError

from zendure.ble.const import COMMAND_CHAR_UUID, MAX_PACKET_BYTES, NOTIFY_CHAR_UUID
from zendure.ble.provision import (
    ProvisionResult,
    async_provision_wifi,
    build_provision_request,
    parse_provision_reply,
)
from zendure.exceptions import (
    MalformedResponseError,
    ProvisioningFailedError,
    ProvisioningTimeoutError,
    ValidationError,
    ZendureConnectionError,
    ZendureProtocolError,
)

SERIAL = "TESTDEV00000001"
SUCCESS = {
    "messageId": 1234,
    "deviceId": SERIAL,
    "productKey": "pk",
    "method": "Token",
    "ip": "192.168.1.50",
    "result": 0,
}

GREETING = {"method": "BLESPP", "deviceId": "CLOUDID1", "productKey": "pk"}
HANDSHAKE_ACK = b'{"method":"BLESPP_OK"}'

Notifier = Callable[[Any, bytearray], None]


def _encode(message: dict[str, Any]) -> bytes:
    return json.dumps(message).encode()


class FakeClient:
    """Minimal stand-in for a connected ``BleakClient``."""

    def __init__(
        self,
        replies: list[bytes] | None = None,
        *,
        greeting: list[bytes] | None = None,
        max_write: int = 497,
        chars: tuple[str, ...] = (COMMAND_CHAR_UUID, NOTIFY_CHAR_UUID),
    ) -> None:
        self.replies = replies if replies is not None else [_encode(SUCCESS)]
        self.greeting = greeting if greeting is not None else [_encode(GREETING)]
        self.writes: list[tuple[bytes, bool | None]] = []
        self.notifying = False
        self.stop_calls = 0
        self.callback: Notifier | None = None
        self.start_error: Exception | None = None
        self.write_error: Exception | None = None
        self.stop_error: Exception | None = None
        self.write_delay = 0.0
        self._chars = {}
        for uuid in chars:
            char = MagicMock()
            char.uuid = uuid
            char.max_write_without_response_size = max_write
            self._chars[uuid] = char
        self.services = MagicMock()
        self.services.get_characteristic.side_effect = self._chars.get

    async def start_notify(self, char: Any, callback: Notifier) -> None:
        if self.start_error:
            raise self.start_error
        self.callback = callback
        self.notifying = True
        self._push(self.greeting)

    def _push(self, chunks: list[bytes]) -> None:
        assert self.callback is not None
        for chunk in chunks:
            asyncio.get_running_loop().call_soon(
                self.callback, self._chars[NOTIFY_CHAR_UUID], bytearray(chunk)
            )

    async def stop_notify(self, char: Any) -> None:
        self.stop_calls += 1
        self.notifying = False
        if self.stop_error:
            raise self.stop_error

    async def write_gatt_char(
        self, char: Any, data: bytes, response: bool | None = None
    ) -> None:
        if self.write_delay:
            await asyncio.sleep(self.write_delay)
        if self.write_error:
            raise self.write_error
        self.writes.append((bytes(data), response))
        if bytes(data) != HANDSHAKE_ACK:
            self._push(self.replies)


def test_build_request_matches_firmware_format() -> None:
    assert json.loads(build_provision_request("MyWiFi", "secret123")) == {
        "method": "token",
        "source": 2,
        "ssid": "MyWiFi",
        "password": "secret123",
        "AM": 0,
    }


def test_build_request_keeps_utf8_verbatim() -> None:
    body = build_provision_request("家里", "secret123")
    assert "家里".encode() in body
    assert b"\\u" not in body


def test_build_request_allows_open_network() -> None:
    assert json.loads(build_provision_request("Open", ""))["password"] == ""


@pytest.mark.parametrize(
    ("ssid", "password"),
    [
        pytest.param("", "secret123", id="empty-ssid"),
        pytest.param("x" * 33, "secret123", id="ssid-too-long"),
        pytest.param("MyWiFi", "short", id="password-too-short"),
        pytest.param("MyWiFi", "x" * 65, id="password-too-long"),
    ],
)
def test_build_request_rejects_invalid_credentials(ssid: str, password: str) -> None:
    with pytest.raises(ValidationError):
        build_provision_request(ssid, password)


def test_build_request_never_exceeds_packet_limit() -> None:
    # Longest valid credentials still fit in one packet.
    body = build_provision_request("家" * 10 + "xx", "x" * 64)
    assert len(body) <= MAX_PACKET_BYTES


def test_build_request_rejects_escaped_body_over_limit() -> None:
    # JSON escapes control characters to 6 bytes each, which can overflow.
    with pytest.raises(ValidationError, match="device limit"):
        build_provision_request("\x01" * 32, "\x01" * 64)


@pytest.mark.parametrize(
    ("ip", "host"),
    [
        pytest.param("192.168.1.50", "192.168.1.50", id="valid"),
        pytest.param("0.0.0.0", None, id="unspecified"),
        pytest.param("127.0.0.1", None, id="loopback"),
        pytest.param("not-an-ip", None, id="garbage"),
        pytest.param(None, None, id="missing"),
        pytest.param(42, None, id="wrong-type"),
    ],
)
def test_parse_reply_host(ip: object, host: str | None) -> None:
    message: dict[str, Any] = {**SUCCESS, "ip": ip}
    assert parse_provision_reply(message) == ProvisionResult(SERIAL, host)


def test_parse_reply_success_is_zero() -> None:
    assert parse_provision_reply({**SUCCESS, "result": 0}).serial_number == SERIAL


@pytest.mark.parametrize("result", [1, 2, -1])
def test_parse_reply_failure(result: int) -> None:
    with pytest.raises(ProvisioningFailedError, match=f"result={result}"):
        parse_provision_reply({**SUCCESS, "result": result})


@pytest.mark.parametrize(
    "message",
    [
        pytest.param({**SUCCESS, "result": None}, id="no-result"),
        pytest.param({**SUCCESS, "result": True}, id="bool-result"),
        pytest.param({**SUCCESS, "deviceId": ""}, id="empty-device-id"),
        pytest.param({**SUCCESS, "deviceId": 7}, id="int-device-id"),
    ],
)
def test_parse_reply_malformed(message: dict[str, Any]) -> None:
    with pytest.raises(MalformedResponseError):
        parse_provision_reply(message)


async def test_provision_success() -> None:
    client = FakeClient()

    result = await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]

    assert result == ProvisionResult(SERIAL, "192.168.1.50")
    # Handshake answer first, then the request; both written with response.
    assert client.writes[0][0] == HANDSHAKE_ACK
    assert json.loads(client.writes[1][0])["ssid"] == "MyWiFi"
    assert [response for _, response in client.writes] == [True, True]
    assert client.stop_calls == 1
    assert not client.notifying


@pytest.mark.parametrize(
    "replies",
    [
        pytest.param([_encode(SUCCESS)[:20], _encode(SUCCESS)[20:]], id="split-reply"),
        pytest.param([_encode(SUCCESS) + b"\x00"], id="trailing-nul"),
        pytest.param(
            [_encode({"method": "other", "x": 1}), _encode(SUCCESS)],
            id="unrelated-first",
        ),
        pytest.param([b"[1]", _encode(SUCCESS)], id="non-object-first"),
        pytest.param([_encode(SUCCESS), _encode(SUCCESS)], id="duplicate-reply"),
    ],
)
async def test_provision_reassembles_replies(replies: list[bytes]) -> None:
    client = FakeClient(replies)

    result = await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]

    assert result.serial_number == SERIAL


async def test_provision_drops_oversized_garbage() -> None:
    client = FakeClient([b"\xff" * (MAX_PACKET_BYTES + 1), _encode(SUCCESS)])

    result = await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]

    assert result.serial_number == SERIAL


async def test_provision_device_reports_failure() -> None:
    client = FakeClient([_encode({**SUCCESS, "result": 1, "ip": ""})])

    with pytest.raises(ProvisioningFailedError):
        await async_provision_wifi(client, "MyWiFi", "wrongpass")  # type: ignore[arg-type]
    assert client.stop_calls == 1


async def test_provision_times_out_without_reply() -> None:
    client = FakeClient(replies=[])

    with pytest.raises(ProvisioningTimeoutError):
        await async_provision_wifi(client, "MyWiFi", "secret123", result_timeout=0.05)  # type: ignore[arg-type]
    assert client.stop_calls == 1


@pytest.mark.parametrize(
    "missing", [COMMAND_CHAR_UUID, NOTIFY_CHAR_UUID], ids=["command", "notify"]
)
async def test_provision_requires_characteristics(missing: str) -> None:
    present = tuple(u for u in (COMMAND_CHAR_UUID, NOTIFY_CHAR_UUID) if u != missing)
    client = FakeClient(chars=present)

    with pytest.raises(ZendureProtocolError):
        await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]
    assert client.writes == []


async def test_provision_rejects_request_larger_than_link() -> None:
    client = FakeClient(max_write=20)

    with pytest.raises(ValidationError):
        await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]
    assert client.writes == []
    assert client.callback is None


async def test_provision_subscribe_failure() -> None:
    client = FakeClient()
    client.start_error = BleakError("not connected")

    with pytest.raises(ZendureConnectionError):
        await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]
    assert client.writes == []


async def test_provision_write_failure_stops_notify() -> None:
    client = FakeClient()
    client.write_error = BleakError("GATT error")

    with pytest.raises(ZendureConnectionError):
        await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]
    assert client.stop_calls == 1


async def test_provision_write_timeout_is_outcome_unknown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("zendure.ble.provision.WRITE_TIMEOUT", 0.01)
    client = FakeClient()
    client.write_delay = 1

    with pytest.raises(ZendureConnectionError, match="outcome unknown"):
        await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]
    assert client.stop_calls == 1


async def test_provision_tolerates_link_drop_after_reply() -> None:
    client = FakeClient()
    client.stop_error = BleakError("device disconnected")

    result = await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]

    assert result.serial_number == SERIAL


@pytest.mark.parametrize(
    ("reply", "error"),
    [
        pytest.param(SUCCESS, None, id="success"),
        pytest.param({**SUCCESS, "result": 1}, ProvisioningFailedError, id="failure"),
    ],
)
async def test_provision_logs_exchange_without_password(
    caplog: pytest.LogCaptureFixture,
    reply: dict[str, Any],
    error: type[Exception] | None,
) -> None:
    client = FakeClient([_encode(reply)[:20], _encode(reply)[20:]])

    with caplog.at_level(logging.DEBUG, logger="zendure.ble.provision"):
        if error is None:
            await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]
        else:
            with pytest.raises(error):
                await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]

    size = len(build_provision_request("MyWiFi", "secret123"))
    tx = '{"method":"token","source":2,"ssid":"MyWiFi","password":"***","AM":0}'
    assert f"BLE handshake greeting: {GREETING}" in caplog.text
    assert (
        f"BLE TX 22 bytes to {COMMAND_CHAR_UUID}: " + HANDSHAKE_ACK.decode()
    ) in caplog.text
    assert f"BLE TX {size} bytes to {COMMAND_CHAR_UUID}: {tx} (password_len=9)" in (
        caplog.text
    )
    assert "BLE RX 20 bytes: b'{" in caplog.text
    assert "waiting for the rest" in caplog.text
    assert f"BLE provisioning reply: {reply}" in caplog.text
    assert "secret123" not in caplog.text


async def test_provision_logs_open_network_password_as_empty(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeClient()

    with caplog.at_level(logging.DEBUG, logger="zendure.ble.provision"):
        await async_provision_wifi(client, "OpenWiFi", "")  # type: ignore[arg-type]

    assert '"ssid":"OpenWiFi","password":"","AM":0' in caplog.text
    assert f"Provisioned deviceId={SERIAL}, reported host=192.168.1.50" in (caplog.text)


async def test_provision_logs_unrelated_and_late_messages(
    caplog: pytest.LogCaptureFixture,
) -> None:
    client = FakeClient(
        [_encode({"method": "other", "sn": SERIAL}), _encode(SUCCESS), b"{}"]
    )

    with caplog.at_level(logging.DEBUG, logger="zendure.ble.provision"):
        await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]
        await asyncio.sleep(0)

    assert (
        f"Ignoring unrelated BLE message: {{'method': 'other', 'sn': '{SERIAL}'}}"
        in (caplog.text)
    )
    assert "BLE RX 2 bytes: b'{}'" in caplog.text
    assert "notification after reply (2 bytes)" in caplog.text


async def test_provision_without_greeting_is_link_failure(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setattr("zendure.ble.provision.HANDSHAKE_TIMEOUT", 0.05)
    client = FakeClient(greeting=[])

    with (
        caplog.at_level(logging.DEBUG, logger="zendure.ble.provision"),
        pytest.raises(ZendureConnectionError, match="BLESPP"),
    ):
        await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]

    assert client.writes == []
    assert client.stop_calls == 1
    assert "No BLESPP greeting within 0.05 s: 0 notifications" in caplog.text


async def test_provision_greeting_split_and_late() -> None:
    greeting = _encode(GREETING)
    client = FakeClient(greeting=[greeting[:10], greeting[10:]])

    result = await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]

    assert result.serial_number == SERIAL
    assert client.writes[0][0] == HANDSHAKE_ACK


async def test_provision_ignores_repeated_greeting() -> None:
    client = FakeClient(replies=[_encode(GREETING), _encode(SUCCESS)])

    result = await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]

    assert result.serial_number == SERIAL
    assert len(client.writes) == 2


async def test_provision_handshake_ack_failure() -> None:
    client = FakeClient()
    client.write_error = BleakError("GATT error")

    with pytest.raises(ZendureConnectionError, match="write failed"):
        await async_provision_wifi(client, "MyWiFi", "secret123")  # type: ignore[arg-type]
    assert client.writes == []
    assert client.stop_calls == 1


async def test_provision_logs_timeout_summary(caplog: pytest.LogCaptureFixture) -> None:
    client = FakeClient(replies=[b'{"method":"To'])

    with (
        caplog.at_level(logging.DEBUG, logger="zendure.ble.provision"),
        pytest.raises(ProvisioningTimeoutError),
    ):
        await async_provision_wifi(client, "MyWiFi", "secret123", result_timeout=0.05)  # type: ignore[arg-type]

    # The greeting plus the partial reply.
    assert "2 notifications, 13 bytes buffered" in caplog.text

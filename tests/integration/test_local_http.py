"""End-to-end tests of transport + local-HTTP protocol against a fake device.

The fake device is a real aiohttp server on 127.0.0.1, so requests go through
the actual network stack (timeouts, status codes, body limits). No hardware.
"""

import asyncio
import json
import socket
from typing import Any

import aiohttp
import pytest
from aiohttp.test_utils import TestServer
from fake_device import FakeDevice

from zendure.exceptions import (
    DeviceMismatchError,
    MalformedResponseError,
    WriteRejectedError,
    ZendureConnectionError,
    ZendureProtocolError,
)
from zendure.protocols.local_http import LocalHttpProtocol
from zendure.protocols.local_http.rest import REPORT_PATH, build_url
from zendure.transport.http import HttpStatusError, HttpTransport


def _protocol(
    server: TestServer, session: aiohttp.ClientSession, **kwargs: Any
) -> LocalHttpProtocol:
    return LocalHttpProtocol("127.0.0.1", session, port=server.port, **kwargs)


# --- read --------------------------------------------------------------------
async def test_read_parses_report(
    server: TestServer, session: aiohttp.ClientSession
) -> None:
    report = await _protocol(server, session).async_read()
    assert report.model_key == "solarflow_5000_max_pro"
    assert report.properties["socSet"] == 100.0
    assert report.batteries[0].properties["maxVol"] == 3.21


async def test_read_http_error_is_protocol_error(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.report_status = 500
    with pytest.raises(HttpStatusError) as excinfo:
        await _protocol(server, session).async_read()
    assert excinfo.value.status == 500
    assert isinstance(excinfo.value, ZendureProtocolError)


async def test_read_invalid_json(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.report_raw = b"not json"
    with pytest.raises(MalformedResponseError):
        await _protocol(server, session).async_read()


async def test_read_empty_body(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.report_raw = b""
    with pytest.raises(MalformedResponseError):
        await _protocol(server, session).async_read()


async def test_read_json_array_rejected(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.report_raw = b"[1, 2, 3]"
    with pytest.raises(MalformedResponseError):
        await _protocol(server, session).async_read()


async def test_oversized_response_rejected(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.report_raw = b"{" + b" " * 10_000 + b"}"
    transport = HttpTransport(session, max_response_bytes=1024)
    url = build_url("127.0.0.1", REPORT_PATH, port=server.port)
    with pytest.raises(MalformedResponseError):
        await transport.get_json(url)


async def test_timeout_is_connection_error(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.delay = 0.5
    with pytest.raises(ZendureConnectionError):
        await _protocol(server, session, timeout=0.05).async_read()


async def test_connection_refused(session: aiohttp.ClientSession) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        free_port = probe.getsockname()[1]
    protocol = LocalHttpProtocol("127.0.0.1", session, port=free_port, timeout=1.0)
    with pytest.raises(ZendureConnectionError):
        await protocol.async_read()


async def test_requests_to_one_device_are_serialized(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.delay = 0.05
    protocol = _protocol(server, session)
    await asyncio.gather(*(protocol.async_read() for _ in range(5)))
    assert device.peak_active == 1


async def test_session_not_closed_by_library(
    server: TestServer, session: aiohttp.ClientSession
) -> None:
    await _protocol(server, session).async_read()
    assert not session.closed


# --- write -------------------------------------------------------------------
def _write_reply(sn: str, *, success: bool = True, code: int = 200) -> bytes:
    """Device reply in the confirmed ``POST properties/write`` shape."""
    return json.dumps(
        {
            "timestamp": 1791966822,
            "messageId": 21,
            "success": success,
            "code": code,
            "sn": sn,
        }
    ).encode()


async def test_write_encodes_and_posts(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.write_reply = _write_reply("TESTDEV00000001")
    protocol = _protocol(server, session)
    await protocol.async_write("TESTDEV00000001", {"socSet": 90, "acMode": 2})
    assert device.writes == [
        {
            "sn": "TESTDEV00000001",
            "id": 1,
            "properties": {"socSet": 900, "acMode": 2},
        }
    ]


async def test_write_request_id_increments(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.write_reply = _write_reply("DEVSN")
    protocol = _protocol(server, session)
    await protocol.async_write("DEVSN", {"acMode": 1})
    await protocol.async_write("DEVSN", {"acMode": 2})
    assert [w["id"] for w in device.writes] == [1, 2]


async def test_write_accepts_confirmed_success_reply(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.write_reply = _write_reply("DEVSN")
    await _protocol(server, session).async_write("DEVSN", {"acMode": 2})
    assert len(device.writes) == 1


@pytest.mark.parametrize(
    "reply",
    [b"", b"   ", b'{"code": 0}', b'{"success": true, "code": 200}', b"[]"],
)
async def test_write_malformed_reply(
    server: TestServer,
    session: aiohttp.ClientSession,
    device: FakeDevice,
    reply: bytes,
) -> None:
    device.write_reply = reply
    with pytest.raises(MalformedResponseError):
        await _protocol(server, session).async_write("DEVSN", {"acMode": 2})


async def test_write_failure_reply_carries_code(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.write_reply = _write_reply("DEVSN", success=False, code=500)
    with pytest.raises(WriteRejectedError) as excinfo:
        await _protocol(server, session).async_write("DEVSN", {"acMode": 2})
    assert excinfo.value.code == 500


async def test_write_reply_from_other_device(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.write_reply = _write_reply("OTHERSN")
    with pytest.raises(DeviceMismatchError):
        await _protocol(server, session).async_write("DEVSN", {"acMode": 2})


async def test_write_http_error_is_rejected(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.write_status = 400
    device.write_reply = b'{"code":400}'
    with pytest.raises(WriteRejectedError) as excinfo:
        await _protocol(server, session).async_write("DEVSN", {"acMode": 2})
    assert excinfo.value.code == 400
    assert str(excinfo.value) == "请求参数错误"
    assert isinstance(excinfo.value.__cause__, HttpStatusError)
    assert excinfo.value.__cause__.status == 400


async def test_write_http_error_uses_body_error_text(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.write_status = 400
    device.write_reply = b'{"code":400,"error":"Failed to parse JSON"}'
    with pytest.raises(WriteRejectedError) as excinfo:
        await _protocol(server, session).async_write("DEVSN", {"acMode": 2})
    assert str(excinfo.value) == "JSON解析失败"
    assert excinfo.value.code == 400

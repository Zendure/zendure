"""Fault codes end to end: client -> local HTTP -> fake device."""

import logging
from typing import Any

import aiohttp
import pytest
from aiohttp.test_utils import TestServer
from fake_device import FakeDevice

from zendure import (
    Availability,
    ClientClosedError,
    FaultCleared,
    FaultRaised,
    UnsupportedFeatureError,
    ZendureClient,
    ZendureEvent,
    ZendureProtocolError,
    create_local_client,
)
from zendure.protocols.local_http import LocalHttpProtocol
from zendure.transport.http import HttpStatusError

SERIAL = "TESTDEV00000001"


def _client(
    server: TestServer, session: aiohttp.ClientSession, **kwargs: Any
) -> ZendureClient:
    kwargs.setdefault("timeout", 1.0)
    return create_local_client("127.0.0.1", session, port=server.port, **kwargs)


async def test_protocol_reads_faults(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.error_codes = [6]
    protocol = LocalHttpProtocol("127.0.0.1", session, port=server.port)
    report = await protocol.async_read_faults()
    assert report.codes == (6,)


async def test_protocol_404_is_unsupported(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.error_status = 404
    protocol = LocalHttpProtocol("127.0.0.1", session, port=server.port)
    with pytest.raises(UnsupportedFeatureError) as excinfo:
        await protocol.async_read_faults()
    assert isinstance(excinfo.value.__cause__, HttpStatusError)


async def test_protocol_other_status_stays_protocol_error(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.error_status = 500
    protocol = LocalHttpProtocol("127.0.0.1", session, port=server.port)
    with pytest.raises(HttpStatusError):
        await protocol.async_read_faults()


async def test_refresh_faults_reads_device_first(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.error_codes = [6]
    async with _client(server, session) as client:
        assert client.faults_supported is None
        snapshot = await client.async_refresh_faults()
        assert client.faults_supported is True
    assert device.report_calls == 1
    assert snapshot.active_faults == (6,)
    assert snapshot.properties


async def test_refresh_faults_emits_changes(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    events: list[ZendureEvent] = []
    async with _client(server, session) as client:
        await client.async_refresh()
        client.subscribe(events.append)
        device.error_codes = [6, 202]
        await client.async_refresh_faults()
        device.error_codes = [202]
        await client.async_refresh_faults()
    assert events == [
        FaultRaised(serial_number=SERIAL, code=6),
        FaultRaised(serial_number=SERIAL, code=202),
        FaultCleared(serial_number=SERIAL, code=6),
    ]


async def test_refresh_keeps_last_faults(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.error_codes = [6]
    async with _client(server, session) as client:
        await client.async_refresh_faults()
        snapshot = await client.async_refresh()
    assert snapshot.active_faults == (6,)


async def test_unsupported_is_remembered(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.error_status = 404
    async with _client(server, session) as client:
        await client.async_refresh()
        for _ in range(2):
            with pytest.raises(UnsupportedFeatureError):
                await client.async_refresh_faults()
        assert client.faults_supported is False
        snapshot = await client.async_refresh()
    assert device.error_calls == 1
    assert snapshot.active_faults is None
    assert snapshot.availability is Availability.ONLINE


async def test_failed_fault_read_does_not_count_toward_offline(
    server: TestServer, session: aiohttp.ClientSession, device: FakeDevice
) -> None:
    device.error_codes = [6]
    async with _client(server, session, offline_threshold=1) as client:
        await client.async_refresh_faults()
        device.error_status = 503
        with pytest.raises(ZendureProtocolError):
            await client.async_refresh_faults()
        snapshot = client.snapshot
        assert client.faults_supported is True
    assert snapshot is not None
    assert snapshot.active_faults is None
    assert snapshot.availability is Availability.ONLINE


async def test_refresh_faults_after_close(
    server: TestServer, session: aiohttp.ClientSession
) -> None:
    client = _client(server, session)
    await client.close()
    with pytest.raises(ClientClosedError):
        await client.async_refresh_faults()


async def test_fault_report_logged_in_full(
    server: TestServer,
    session: aiohttp.ClientSession,
    device: FakeDevice,
    caplog: pytest.LogCaptureFixture,
) -> None:
    device.error_codes = [6, 202]
    protocol = LocalHttpProtocol("127.0.0.1", session, port=server.port)
    with caplog.at_level(logging.DEBUG, "zendure.protocols.local_http.protocol"):
        report = await protocol.async_read_faults()
    assert report.codes == (6, 202)
    assert report.since == {6: 1793085345, 202: 1793085345}
    assert (
        'Fault report from 127.0.0.1: {"messageId":30,"timestamp":1793085345,'
        '"deviceId":"VB2nRuA2","productKey":"vCK12r","offData":0,"eventId":3,'
        '"data":[{"code":6,"timestamp":1793085345},{"code":202,"timestamp":1793085345}]}'
    ) in caplog.text

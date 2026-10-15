"""Write validation and read-back confirmation through a fake protocol."""

from collections.abc import Mapping

import pytest

from zendure import ZendureClient
from zendure.exceptions import (
    ClientClosedError,
    ValidationError,
    WriteNotConfirmedError,
    ZendureConnectionError,
)
from zendure.protocols.base import DeviceProtocol
from zendure.state.report import DeviceReport


class MemoryProtocol(DeviceProtocol):
    def __init__(self) -> None:
        self.values = {"outputLimit": 200, "inverseMaxPower": 800, "socSet": 100}
        self.writes: list[dict[str, int | float]] = []
        self.apply = True
        self.fail_write = False

    async def async_read(self) -> DeviceReport:
        return DeviceReport(
            serial_number="TESTDEV",
            model_key="max_5000_pro",
            product_raw="SolarFlowMax5000Pro",
            properties=self.values,
        )

    async def async_write(
        self, serial_number: str, values: Mapping[str, int | float]
    ) -> None:
        self.writes.append(dict(values))
        if self.fail_write:
            raise ZendureConnectionError("timeout")
        if self.apply:
            self.values.update(values)  # type: ignore[arg-type]


class DelayedApplyProtocol(MemoryProtocol):
    def __init__(self) -> None:
        super().__init__()
        self.apply = False
        self._pending: dict[str, int | float] = {}
        self.reads_after_write = 0

    async def async_write(
        self, serial_number: str, values: Mapping[str, int | float]
    ) -> None:
        await super().async_write(serial_number, values)
        self._pending = dict(values)
        self.reads_after_write = 0

    async def async_read(self) -> DeviceReport:
        report = await super().async_read()
        if self._pending:
            self.reads_after_write += 1
            if self.reads_after_write >= 3:
                self.values.update(self._pending)
                self._pending = {}
                return await super().async_read()
        return report


async def test_write_reads_back_actual_state() -> None:
    protocol = MemoryProtocol()
    async with ZendureClient(protocol) as client:
        snapshot = await client.async_set("outputLimit", 500)
        assert snapshot.properties["outputLimit"] == 500
        assert protocol.writes == [{"outputLimit": 500}]


async def test_invalid_write_sends_nothing() -> None:
    protocol = MemoryProtocol()
    async with ZendureClient(protocol) as client:
        with pytest.raises(ValidationError):
            await client.async_set("outputLimit", 900)
        assert protocol.writes == []


async def test_read_only_sends_nothing() -> None:
    protocol = MemoryProtocol()
    async with ZendureClient(protocol) as client:
        with pytest.raises(ValidationError):
            await client.async_set("inverseMaxPower", 1000)
        assert protocol.writes == []


async def test_unconfirmed_write_does_not_optimistically_change_snapshot() -> None:
    protocol = MemoryProtocol()
    protocol.apply = False
    async with ZendureClient(protocol) as client:
        with pytest.raises(WriteNotConfirmedError, match="not confirmed"):
            await client.async_set("outputLimit", 500)
        assert client.snapshot is not None
        assert client.snapshot.properties["outputLimit"] == 200


async def test_write_confirms_after_device_catches_up() -> None:
    protocol = DelayedApplyProtocol()
    async with ZendureClient(protocol) as client:
        snapshot = await client.async_set("outputLimit", 500)
    assert snapshot.properties["outputLimit"] == 500
    assert len(protocol.writes) == 1
    assert protocol.reads_after_write >= 3


async def test_write_timeout_is_not_retried_or_counted_as_read_failure() -> None:
    protocol = MemoryProtocol()
    protocol.fail_write = True
    async with ZendureClient(protocol, offline_threshold=1) as client:
        with pytest.raises(ZendureConnectionError):
            await client.async_set("outputLimit", 500)
        assert len(protocol.writes) == 1
        assert client.availability.value == "online"


async def test_missing_dynamic_bound_sends_nothing() -> None:
    protocol = MemoryProtocol()
    del protocol.values["inverseMaxPower"]
    async with ZendureClient(protocol) as client:
        with pytest.raises(ValidationError, match="upper bound"):
            await client.async_set("outputLimit", 500)
    assert protocol.writes == []


async def test_closed_client_cannot_write() -> None:
    protocol = MemoryProtocol()
    client = ZendureClient(protocol)
    await client.close()
    with pytest.raises(ClientClosedError):
        await client.async_set("outputLimit", 500)
    assert protocol.writes == []

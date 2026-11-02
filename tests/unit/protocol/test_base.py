"""Tests for the protocol interface's optional parts."""

from collections.abc import Mapping

import pytest

from zendure.exceptions import UnsupportedFeatureError
from zendure.protocols.base import DeviceProtocol
from zendure.state.report import DeviceReport


class _ReadOnlyProtocol(DeviceProtocol):
    async def async_read(self) -> DeviceReport:
        raise NotImplementedError

    async def async_write(
        self, serial_number: str, values: Mapping[str, int | float]
    ) -> None:
        raise NotImplementedError


async def test_fault_reading_is_optional() -> None:
    with pytest.raises(UnsupportedFeatureError) as excinfo:
        await _ReadOnlyProtocol().async_read_faults()
    assert excinfo.value.feature == "fault codes"

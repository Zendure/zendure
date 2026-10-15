"""Abstract protocol interface.

The client depends only on this interface, never on a concrete protocol
package. Adding a protocol (Modbus, NB-IoT, ...) means a new subpackage that
implements it; nothing above this layer changes.
"""

from abc import ABC, abstractmethod
from collections.abc import Mapping

from ..state.report import DeviceReport


class DeviceProtocol(ABC):
    """Read and write one device over a specific protocol."""

    @abstractmethod
    async def async_read(self) -> DeviceReport:
        """Fetch and decode the device's full current state."""

    @abstractmethod
    async def async_write(
        self, serial_number: str, values: Mapping[str, int | float]
    ) -> None:
        """Send already-validated, user-facing control values to the device.

        Encoding to raw protocol values is the implementation's job.
        """


__all__ = ["DeviceProtocol"]

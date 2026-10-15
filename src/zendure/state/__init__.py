"""State merging: protocol-agnostic, no network I/O.

Feed decoded ``DeviceReport`` objects into a ``DeviceStore`` and get back
immutable snapshots plus the ordered change events for what actually changed.
Failed reads are counted there too, which drives availability.
"""

from .report import BatteryReport, DeviceReport
from .store import DEFAULT_OFFLINE_THRESHOLD, DeviceStore

__all__ = ["DEFAULT_OFFLINE_THRESHOLD", "BatteryReport", "DeviceReport", "DeviceStore"]

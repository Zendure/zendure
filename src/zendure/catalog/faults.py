"""Per-model fault-code descriptions (English).

Fault codes are what ``GET /properties/error`` reports. The same code can mean
different things on different models (e.g. code 6 is "DSP communication error"
on the SolarFlow line but "Boot and Project Mismatch" on the 5000 Max Pro), so
lookups are always per model.

The data comes from the cloud's fault table via ``scripts/gen_faults.py``; only
English names are kept, since Home Assistant translates from English.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

from ._fault_tables import FAULT_ROWS, FaultRow

# Raw values of the cloud table's ``fault_level`` and ``type`` columns.
_LEVEL_FAULT: Final = 1
_LEVEL_WARNING: Final = 2
_DISPLAY_HIDDEN: Final = 3


class FaultLevel(StrEnum):
    """Severity of a fault code."""

    FAULT = "fault"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class FaultDescription:
    """What one fault code means on one model.

    ``visible`` is ``False`` for codes the Zendure app does not show to users
    (internal protection states); consumers should not raise them as problems.
    ``known`` is ``False`` when the code is not in the model's table.
    """

    code: int
    name: str
    module: str | None = None
    level: FaultLevel | None = None
    visible: bool = True
    known: bool = True


def _level(raw: int | None) -> FaultLevel | None:
    if raw == _LEVEL_FAULT:
        return FaultLevel.FAULT
    if raw == _LEVEL_WARNING:
        return FaultLevel.WARNING
    return None


def _describe(row: FaultRow) -> FaultDescription:
    code, name, module, level, display = row
    return FaultDescription(
        code=code,
        # A few rows have no English name in the source table.
        name=name or f"Fault {code}",
        module=module,
        level=_level(level),
        visible=display != _DISPLAY_HIDDEN,
    )


_TABLES: Final[Mapping[str, Mapping[int, FaultDescription]]] = MappingProxyType(
    {
        model_key: MappingProxyType({row[0]: _describe(row) for row in rows})
        for model_key, rows in FAULT_ROWS.items()
    }
)


def lookup_fault(model_key: str, code: int) -> FaultDescription:
    """Describe ``code`` for ``model_key``; unknown codes get a generic entry.

    An unknown code is still reported as visible: hiding a fault the table does
    not know about could hide a real problem.
    """
    if (description := _TABLES.get(model_key, {}).get(code)) is not None:
        return description
    return FaultDescription(code=code, name=f"Unknown fault {code}", known=False)


def fault_codes(model_key: str) -> tuple[int, ...]:
    """All codes the table defines for ``model_key``, ascending."""
    return tuple(_TABLES.get(model_key, {}))


__all__ = ["FaultDescription", "FaultLevel", "fault_codes", "lookup_fault"]

"""Writable property (control) descriptions and pre-write validation.

Static declaration of the 9 controls shared by the supported models (SolarFlow
2400 AC+ and Max 5000 Pro) plus the pure validation that
guards every write BEFORE anything leaves the library. An out-of-range, bad-enum
or read-only write raises ``ValidationError`` and nothing is sent; the library
never silently clamps (unlike the old integration).

Raw<->user encoding (e.g. ``socSet`` x10) is a protocol detail handled on the
write path, not here. This table holds user-facing ranges and enum options.
"""

from collections.abc import Mapping

from ..exceptions import UnsupportedPropertyError, ValidationError
from ..models import ControlDescription, EntityKind, PropertyValue

_STEP_TOLERANCE = 1e-9

_CONTROLS: tuple[ControlDescription, ...] = (
    ControlDescription(
        key="acMode",
        kind=EntityKind.SELECT,
        options={1: "input", 2: "output"},
    ),
    ControlDescription(
        key="gridOffMode",
        kind=EntityKind.SELECT,
        options={0: "normal", 1: "eco", 2: "off"},
    ),
    ControlDescription(
        key="gridReverse",
        kind=EntityKind.SELECT,
        # 1=allow / 2=forbidden from the old integration; 0's meaning is a
        # candidate pending firmware confirmation.
        options={0: "disabled", 1: "allow", 2: "forbidden"},
    ),
    ControlDescription(
        key="inputLimit",
        kind=EntityKind.NUMBER,
        unit="W",
        native_min=0,
        max_source_key="chargeMaxLimit",
    ),
    ControlDescription(
        key="outputLimit",
        kind=EntityKind.NUMBER,
        unit="W",
        native_min=0,
        max_source_key="inverseMaxPower",
    ),
    # Regulatory output limit: read-only until firmware confirms it is safe and
    # legal to write locally (it tracks gridStandard / regional caps).
    ControlDescription(
        key="inverseMaxPower",
        kind=EntityKind.NUMBER,
        unit="W",
        writable=False,
    ),
    # zenSDK docs mark lampSwitch read-only, but the product's control list
    # exposes Light as a switch; writability is a candidate pending firmware.
    ControlDescription(key="lampSwitch", kind=EntityKind.SWITCH),
    ControlDescription(
        key="socSet",
        kind=EntityKind.NUMBER,
        unit="%",
        native_min=70,
        native_max=100,
        step=1,
    ),
    # NOT a "smart strategy": smartMode=1 means params are not written to flash
    # and revert after a device restart. Exposed verbatim.
    ControlDescription(key="smartMode", kind=EntityKind.SWITCH),
)

CONTROL_DESCRIPTIONS: Mapping[str, ControlDescription] = {c.key: c for c in _CONTROLS}


def control(key: str) -> ControlDescription | None:
    """Return the control description for ``key``, or ``None``."""
    return CONTROL_DESCRIPTIONS.get(key)


def validate_control(
    key: str,
    value: PropertyValue,
    *,
    dynamic_max: float | None = None,
) -> int | float:
    """Validate a user-facing control value and return it normalized.

    ``dynamic_max`` is the device's current reported upper bound (e.g.
    ``inverseMaxPower``); it only applies to controls that declare a
    ``max_source_key``.

    Raises:
        UnsupportedPropertyError: ``key`` is not a known control.
        ValidationError: the control is read-only, or the value is out of
            range / off-step / not a valid option.
    """
    description = CONTROL_DESCRIPTIONS.get(key)
    if description is None:
        raise UnsupportedPropertyError(key)
    if not description.writable:
        raise ValidationError(f"{key} is read-only")
    if value is None:
        raise ValidationError(f"{key} value must not be None")

    if description.kind is EntityKind.SELECT:
        return _validate_select(description, value)
    if description.kind is EntityKind.SWITCH:
        return _validate_switch(key, value)
    if description.kind is EntityKind.NUMBER:
        return _validate_number(description, value, dynamic_max)
    raise ValidationError(f"{key} is not a writable control kind")


def _validate_select(description: ControlDescription, value: PropertyValue) -> int:
    options = description.options
    if options is None:
        raise ValidationError(f"{description.key} has no options")
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValidationError(f"{description.key} expects an integer option")
    if value not in options:
        raise ValidationError(
            f"{description.key}={value} not in options {sorted(options)}"
        )
    return value


def _validate_switch(key: str, value: PropertyValue) -> int:
    if isinstance(value, bool):
        return int(value)
    if value in (0, 1):
        return int(value)
    raise ValidationError(f"{key} expects 0, 1 or a bool")


def _validate_number(
    description: ControlDescription,
    value: PropertyValue,
    dynamic_max: float | None,
) -> int | float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValidationError(f"{description.key} expects a number")

    low = description.native_min
    if description.max_source_key is not None and dynamic_max is not None:
        high: float | None = dynamic_max
    else:
        high = description.native_max

    if low is not None and value < low:
        raise ValidationError(f"{description.key}={value} below minimum {low}")
    if high is not None and value > high:
        raise ValidationError(f"{description.key}={value} above maximum {high}")

    if description.step is not None:
        base = description.native_min if description.native_min is not None else 0
        steps = (value - base) / description.step
        if abs(steps - round(steps)) > _STEP_TOLERANCE:
            raise ValidationError(
                f"{description.key}={value} not aligned to step {description.step}"
            )
    return value


__all__ = [
    "CONTROL_DESCRIPTIONS",
    "control",
    "validate_control",
]

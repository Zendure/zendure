"""Tests for the control registry and pre-write validation."""

import pytest

from zendure.catalog.controls import CONTROL_DESCRIPTIONS, control, validate_control
from zendure.exceptions import UnsupportedPropertyError, ValidationError
from zendure.models import EntityKind


def test_nine_controls_registered() -> None:
    assert len(CONTROL_DESCRIPTIONS) == 9
    assert set(CONTROL_DESCRIPTIONS) == {
        "acMode",
        "gridOffMode",
        "gridReverse",
        "inputLimit",
        "outputLimit",
        "inverseMaxPower",
        "lampSwitch",
        "socSet",
        "smartMode",
    }


def test_control_lookup_unknown_returns_none() -> None:
    assert control("mysteryKey") is None


def test_validate_unknown_key_raises() -> None:
    with pytest.raises(UnsupportedPropertyError):
        validate_control("mysteryKey", 1)


def test_validate_none_value_raises() -> None:
    with pytest.raises(ValidationError):
        validate_control("acMode", None)


# --- select ------------------------------------------------------------------
@pytest.mark.parametrize("value", [1, 2])
def test_acmode_accepts_valid_options(value: int) -> None:
    assert validate_control("acMode", value) == value


@pytest.mark.parametrize("value", [0, 3, -1])
def test_acmode_rejects_bad_options(value: int) -> None:
    with pytest.raises(ValidationError):
        validate_control("acMode", value)


def test_select_rejects_bool() -> None:
    with pytest.raises(ValidationError):
        validate_control("acMode", True)


def test_gridoffmode_is_select() -> None:
    desc = control("gridOffMode")
    assert desc is not None
    assert desc.kind is EntityKind.SELECT


# --- read-only ---------------------------------------------------------------
def test_regulatory_power_is_read_only() -> None:
    desc = control("inverseMaxPower")
    assert desc is not None
    assert desc.writable is False
    with pytest.raises(ValidationError):
        validate_control("inverseMaxPower", 800)


# --- number with dynamic max -------------------------------------------------
def test_outputlimit_within_dynamic_max() -> None:
    assert validate_control("outputLimit", 500, dynamic_max=800) == 500


def test_outputlimit_above_dynamic_max_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_control("outputLimit", 900, dynamic_max=800)


def test_outputlimit_negative_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_control("outputLimit", -1)


def test_outputlimit_no_bound_known_passes() -> None:
    # No dynamic_max and no static native_max: upper bound unverifiable, allowed.
    assert validate_control("outputLimit", 5000) == 5000


# --- socSet range + step -----------------------------------------------------
@pytest.mark.parametrize("value", [70, 85, 100])
def test_socset_in_range(value: int) -> None:
    assert validate_control("socSet", value) == value


@pytest.mark.parametrize("value", [69, 101])
def test_socset_out_of_range(value: int) -> None:
    with pytest.raises(ValidationError):
        validate_control("socSet", value)


def test_socset_off_step_rejected() -> None:
    with pytest.raises(ValidationError):
        validate_control("socSet", 90.5)


# --- switch ------------------------------------------------------------------
@pytest.mark.parametrize("value", [0, 1, True, False])
def test_switch_accepts_binary(value: int | bool) -> None:
    result = validate_control("lampSwitch", value)
    assert result in (0, 1)


def test_switch_rejects_other() -> None:
    with pytest.raises(ValidationError):
        validate_control("smartMode", 2)


def test_number_rejects_non_numeric() -> None:
    with pytest.raises(ValidationError):
        validate_control("socSet", "ninety")

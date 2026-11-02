"""Tests for the per-model fault-code catalog."""

import importlib.util
from pathlib import Path

import pytest

from zendure.catalog import FaultLevel, fault_codes, lookup_fault

MAX_PRO = "solarflow_5000_max_pro"
AC_PLUS = "solarflow_2400ac_plus"
SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "gen_faults.py"


@pytest.mark.parametrize(
    ("model_key", "code", "name"),
    [
        # The 5000 Max Pro's own definitions win over the SolarFlow-wide ones.
        (MAX_PRO, 4, "Wi-Fi/Bluetooth Module Communication Error"),
        (MAX_PRO, 6, "Boot and Project Mismatch"),
        (MAX_PRO, 104, "ARM Relay Closing Timeout"),
        (AC_PLUS, 4, "BMS board communication error"),
        (AC_PLUS, 6, "DSP communication error"),
        (AC_PLUS, 104, "PV3 overvoltage"),
    ],
)
def test_same_code_means_different_faults_per_model(
    model_key: str, code: int, name: str
) -> None:
    assert lookup_fault(model_key, code).name == name


def test_description_fields() -> None:
    fault = lookup_fault(MAX_PRO, 701)
    assert fault.module == "DC"
    assert fault.level is FaultLevel.FAULT
    assert fault.visible
    assert fault.known


def test_model_specific_row_wins_over_generic() -> None:
    # Code 64 has a generic MPPT row and an AC row naming the 2400 AC+.
    fault = lookup_fault(AC_PLUS, 64)
    assert fault.module == "AC"
    assert fault.level is FaultLevel.WARNING


def test_hidden_codes_are_not_visible() -> None:
    assert not lookup_fault(MAX_PRO, 601).visible


def test_missing_level_stays_none() -> None:
    assert lookup_fault(AC_PLUS, 3).level is None


def test_row_without_name_gets_generic_name() -> None:
    fault = lookup_fault(MAX_PRO, 77)
    assert fault.name == "Fault 77"
    assert fault.known


@pytest.mark.parametrize(("model_key", "code"), [(MAX_PRO, 999), ("unknown", 6)])
def test_unknown_code_is_visible_and_marked_unknown(model_key: str, code: int) -> None:
    fault = lookup_fault(model_key, code)
    assert fault.name == f"Unknown fault {code}"
    assert fault.visible
    assert not fault.known
    assert fault.level is None


def test_empty_model_list_row_matches_no_model() -> None:
    # Code 204 has product_model "" in the source table, which the cloud
    # backend matches to nothing; the catalog follows it.
    assert not lookup_fault(MAX_PRO, 204).known
    assert not lookup_fault(AC_PLUS, 204).known


def test_table_sizes() -> None:
    assert len(fault_codes(AC_PLUS)) == 132
    assert len(fault_codes(MAX_PRO)) == 259
    assert fault_codes(MAX_PRO) == tuple(sorted(fault_codes(MAX_PRO)))
    assert fault_codes("unknown") == ()


@pytest.mark.skipif(not SCRIPT.exists(), reason="generator not in this checkout")
def test_generated_table_is_up_to_date() -> None:
    spec = importlib.util.spec_from_file_location("gen_faults", SCRIPT)
    assert spec is not None
    assert spec.loader is not None
    gen = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(gen)
    assert gen.TARGET.read_text(encoding="utf-8") == gen.render(gen.load())

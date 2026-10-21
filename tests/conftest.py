"""Shared test fixtures.

Fixture reports are desensitized copies of a real SolarFlow 2400 AC+ report:
serial numbers are fictional. 5000 Max Pro has the same property set, so the
5000 Max Pro fixture is DERIVED by changing only ``product``; it is not a
captured 5000 Max Pro message.
"""

import copy
import json
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
SOLARFLOW_5000_MAX_PRO_PRODUCT = "SolarFlow5000MaxPro"


def load_fixture(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


@pytest.fixture
def report_2400acplus() -> dict[str, Any]:
    """The desensitized real report, product unchanged."""
    return load_fixture("report_2400acplus_real.json")


@pytest.fixture
def report_5000maxpro() -> dict[str, Any]:
    """Derived 5000 Max Pro report (only ``product`` differs from the real one)."""
    report = copy.deepcopy(load_fixture("report_2400acplus_real.json"))
    report["product"] = SOLARFLOW_5000_MAX_PRO_PRODUCT
    return report

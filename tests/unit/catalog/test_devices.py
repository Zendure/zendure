"""Tests for the device capability table."""

import pytest

from zendure.catalog.devices import lookup_device, normalize_product
from zendure.exceptions import UnsupportedDeviceError


@pytest.mark.parametrize(
    "raw",
    [
        "SolarFlowMax5000Pro",
        "solarflowmax5000pro",
        "SOLARFLOWMAX5000PRO",
        "SolarFlow Max 5000 Pro",
        "  SolarFlowMax5000Pro  ",
    ],
)
def test_lookup_is_case_and_space_insensitive(raw: str) -> None:
    capability = lookup_device(raw)
    assert capability.model_key == "max_5000_pro"


def test_capability_fields() -> None:
    capability = lookup_device("SolarFlowMax5000Pro")
    assert capability.display_name == "SolarFlow Max 5000 Pro"
    assert capability.solar_channels == 4


@pytest.mark.parametrize(
    "raw",
    [
        "solarFlow2400AC+",
        "SolarFlow2400AC+",
        "SolarFlow 2400 AC+",
        "SOLARFLOW2400AC+",
    ],
)
def test_2400acplus_is_registered(raw: str) -> None:
    capability = lookup_device(raw)
    assert capability.model_key == "solarflow_2400ac_plus"
    assert capability.solar_channels == 4


def test_unknown_product_rejected() -> None:
    with pytest.raises(UnsupportedDeviceError) as extra:
        lookup_device("solarFlow800Pro")
    assert extra.value.product == "solarFlow800Pro"


def test_normalize_keeps_plus_sign() -> None:
    assert normalize_product("solarFlow 2400 AC+") == "solarflow2400ac+"

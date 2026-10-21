"""Tests for the device capability table."""

import pytest

from zendure.catalog.devices import lookup_device, normalize_product
from zendure.exceptions import UnsupportedDeviceError


@pytest.mark.parametrize(
    "raw",
    [
        "SolarFlow5000MaxPro",
        "solarflow5000maxpro",
        "SOLARFLOW5000MAXPRO",
        "SolarFlow 5000 Max Pro",
        "  SolarFlow5000MaxPro  ",
    ],
)
def test_lookup_is_case_and_space_insensitive(raw: str) -> None:
    capability = lookup_device(raw)
    assert capability.model_key == "solarflow_5000_max_pro"


def test_capability_fields() -> None:
    capability = lookup_device("SolarFlow5000MaxPro")
    assert capability.display_name == "SolarFlow 5000 Max Pro"
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

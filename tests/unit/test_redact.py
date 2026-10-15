"""Tests for identifier masking."""

from zendure._redact import mask_serial


def test_mask_keeps_prefix() -> None:
    assert mask_serial("HEC4ADP5P210250") == "HEC4***"


def test_mask_short_value_fully_hidden() -> None:
    assert mask_serial("ABCD") == "***"
    assert mask_serial("") == "***"

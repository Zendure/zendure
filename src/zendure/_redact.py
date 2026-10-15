"""Helpers that keep sensitive identifiers out of logs and error messages."""


def mask_serial(serial_number: str) -> str:
    """Keep a 4-character prefix for correlation and hide the rest.

    ``HEC4ADP5P210250`` -> ``HEC4***``.
    """
    if len(serial_number) <= 4:
        return "***"
    return f"{serial_number[:4]}***"


__all__ = ["mask_serial"]

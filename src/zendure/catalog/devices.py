"""Device model capability table.

A device's reported ``product`` string is normalized (lower-cased, whitespace
removed) and looked up here, replacing the old per-model inheritance tree. An
unregistered product raises ``UnsupportedDeviceError`` rather than guessing.

Only ``solarflow_5000_max_pro`` and ``solarflow_2400ac_plus`` are registered. They share
the same property set. Power limits are deliberately NOT stored here: the
device reports its own dynamic limits (``inverseMaxPower``, ``chargeMaxLimit``),
which always win over any static value. Other models are added as they are
verified on real hardware.
"""

from dataclasses import dataclass


def normalize_product(product: str) -> str:
    """Normalize a reported product string for case/whitespace-insensitive match.

    ``"+"`` is significant (e.g. ``solarFlow2400AC+``) and is kept.
    """
    return "".join(product.split()).lower()


@dataclass(frozen=True, slots=True)
class DeviceCapability:
    """What the library knows about one device model, independent of protocol."""

    model_key: str
    display_name: str
    solar_channels: int
    aliases: tuple[str, ...]


# Keyed by model_key. `aliases` hold already-normalized product strings.
_CAPABILITIES: tuple[DeviceCapability, ...] = (
    DeviceCapability(
        model_key="solarflow_5000_max_pro",
        display_name="SolarFlow 5000 Max Pro",
        # 4 PV inputs per the 5000 Max Pro feature list (candidate until a real
        # 5000 Max Pro report is seen; its property set matches 2400 AC+).
        solar_channels=4,
        aliases=("solarflow5000maxpro",),
    ),
    DeviceCapability(
        model_key="solarflow_2400ac_plus",
        display_name="SolarFlow 2400 AC+",
        solar_channels=4,
        aliases=("solarflow2400ac+",),
    ),
)

_BY_ALIAS: dict[str, DeviceCapability] = {
    alias: cap for cap in _CAPABILITIES for alias in cap.aliases
}


def lookup_device(product: str) -> DeviceCapability:
    """Resolve a reported product string to its capability, or reject it.

    Raises:
        UnsupportedDeviceError: the product is not a registered model.
    """
    from ..exceptions import UnsupportedDeviceError

    capability = _BY_ALIAS.get(normalize_product(product))
    if capability is None:
        raise UnsupportedDeviceError(product)
    return capability


__all__ = [
    "DeviceCapability",
    "lookup_device",
    "normalize_product",
]

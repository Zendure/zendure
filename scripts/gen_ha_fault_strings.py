"""Write the Home Assistant ``current_fault_*`` translations from the catalog.

Each model's current-fault sensor has one state per visible fault code, so its
state names are generated from ``zendure.catalog`` rather than typed by hand.
Names are put into sentence case for the HA UI; acronyms and mixed-case words
(``PV1``, ``NTC``, ``eCap``) are kept.

Usage::

    python scripts/gen_ha_fault_strings.py [path/to/core]   # default ../core_zendure
"""

import json
import re
import sys
from pathlib import Path
from typing import Any, Final

ROOT: Final = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from zendure.catalog import fault_codes, lookup_fault  # noqa: E402

# Must match CURRENT_FAULT_TRANSLATION_KEYS in the integration's sensor.py.
TRANSLATION_KEYS: Final = {
    "solarflow_2400ac_plus": "current_fault_2400ac_plus",
    "solarflow_5000_max_pro": "current_fault_5000_max_pro",
}
FIRST_KEY: Final = "current_fault_2400ac_plus"
NAME: Final = "Current fault"
NONE_NAME: Final = "No fault"
OTHER_NAME: Final = "Other fault"
KEEP: Final = frozenset({"Wi", "Fi", "WiFi", "Bluetooth"})
_PARTS: Final = re.compile(r"([-/ ])")


def _word(word: str, first: bool) -> str:
    if (
        word in KEEP
        or any(c.isdigit() for c in word)
        or any(c.isupper() for c in word[1:])
    ):
        return word
    return word.capitalize() if first else word.lower()


def sentence_case(name: str) -> str:
    """``DC Bus Soft-Start Failure`` -> ``DC bus soft-start failure``."""
    parts = _PARTS.split(name.strip())
    return "".join(
        part if _PARTS.fullmatch(part) else _word(part, first=index == 0)
        for index, part in enumerate(parts)
    )


def states(model_key: str) -> dict[str, str]:
    result = {"none": NONE_NAME}
    for code in fault_codes(model_key):
        if (fault := lookup_fault(model_key, code)).visible:
            result[str(code)] = sentence_case(fault.name)
    result["other"] = OTHER_NAME
    return result


def _ref(state: str) -> str:
    return f"[%key:component::zendure::entity::sensor::{FIRST_KEY}::state::{state}%]"


def update(core: Path) -> None:
    component = core / "homeassistant" / "components" / "zendure"
    strings_path = component / "strings.json"
    icons_path = component / "icons.json"
    strings: dict[str, Any] = json.loads(strings_path.read_text(encoding="utf-8"))
    icons: dict[str, Any] = json.loads(icons_path.read_text(encoding="utf-8"))

    sensors = strings["entity"]["sensor"]
    sensor_icons = icons["entity"]["sensor"]
    for model_key, key in TRANSLATION_KEYS.items():
        model_states = states(model_key)
        if key != FIRST_KEY:
            # Shared words point at the first model so they are translated once.
            for state in ("none", "other"):
                model_states[state] = _ref(state)
        sensors[key] = {
            "name": NAME
            if key == FIRST_KEY
            else f"[%key:component::zendure::entity::sensor::{FIRST_KEY}::name%]",
            "state": model_states,
        }
        sensor_icons[key] = {
            "default": "mdi:alert-circle",
            "state": {"none": "mdi:check-circle-outline"},
        }
    strings["entity"]["sensor"] = dict(sorted(sensors.items()))
    icons["entity"]["sensor"] = dict(sorted(sensor_icons.items()))
    for path, data in ((strings_path, strings), (icons_path, icons)):
        text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        path.write_text(text, encoding="utf-8", newline="\n")
        print(f"wrote {path}")


if __name__ == "__main__":
    update(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT.parent / "core_zendure")

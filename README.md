# zendure

Async Python client for Zendure energy devices over the local-network **zenSDK
HTTP** protocol — no cloud, no MQTT, no app token.

The device is reached directly on the LAN: `GET /properties/report` to read all
state, `POST /properties/write` to control it. This library is standalone and
**never imports `homeassistant`**; the Home Assistant `zendure` integration is a
thin layer on top of it.

```bash
pip install zendure
```

## Status

Early development (0.x): the public API may still change between minor
versions. Read and control are supported for:

| Model | Reported `product` | Verified on real hardware |
|---|---|---|
| SolarFlow 2400 AC+ | `solarFlow2400AC+` | Yes |
| SolarFlow 5000 Max Pro | `SolarFlow5000MaxPro` | Not yet (same property set as 2400 AC+) |

Protocol values are derived from a real 2400 AC+ report and the public zenSDK
docs. Items whose meaning is not yet confirmed on hardware are marked
*candidate* in the catalog and locked by tests until verified.

## Requirements

- Python 3.14.2+
- The device must already be added to HEMS (its local HTTP interface is then on)

## Development

```bash
uv pip install -e ".[dev]"
ruff format --check .
ruff check .
mypy
pytest
```

`scripts/live_device_check.py --host <device-ip>` runs a one-shot check against
a real device. It briefly changes `lampSwitch` and `outputLimit`, then restores
them.

## License

Apache-2.0. See [LICENSE](LICENSE).

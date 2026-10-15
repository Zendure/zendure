# zendure

Async Python client for Zendure energy devices over the local-network **zenSDK
HTTP** protocol — no cloud, no MQTT, no app token.

The device is reached directly on the LAN: `GET /properties/report` to read all
state, `POST /properties/write` to control it. This library is standalone and
**never imports `homeassistant`**; a thin Home Assistant integration consumes it
in a later phase.

## Status

Early development. First target model: **Max 5000 Pro** (`product =
SolarFlowMax5000Pro`), read + control. Protocol values are derived from a real
device report and the public zenSDK docs; items not yet checked on a Max 5000
Pro are marked *candidate* in the catalog and locked by tests until verified.

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

## License

Apache-2.0. See [LICENSE](LICENSE).

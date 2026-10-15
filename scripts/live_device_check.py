"""One-shot live check against a LAN device. Not part of the unit suite."""

from __future__ import annotations

import asyncio
import json
import traceback
from dataclasses import dataclass, field
from datetime import UTC, datetime

import aiohttp

from zendure import create_local_client
from zendure.client import ZendureClient
from zendure.models import DeviceSnapshot

HOST = "172.16.211.240"
SAFE_OUTPUT = 250  # W; stay near the current 200, well under inverseMaxPower=800


@dataclass
class Step:
    name: str
    ok: bool
    detail: str
    error: str | None = None


@dataclass
class Report:
    steps: list[Step] = field(default_factory=list)

    def add(self, name: str, ok: bool, detail: str, error: str | None = None) -> None:
        self.steps.append(Step(name, ok, detail, error))


def _brief(snap: DeviceSnapshot) -> str:
    bat = snap.batteries[0] if snap.batteries else None
    bat_s = ""
    if bat is not None:
        bat_s = (
            f" bat_soc={bat.properties.get('socLevel')}"
            f" V={bat.properties.get('totalVol')}"
            f" T={bat.properties.get('maxTemp')}"
        )
    return (
        f"product={snap.product_raw} model={snap.model_key} "
        f"avail={snap.availability} soc={snap.properties.get('electricLevel')} "
        f"acMode={snap.properties.get('acMode')} "
        f"out={snap.properties.get('outputLimit')} "
        f"in={snap.properties.get('inputLimit')} "
        f"maxPwr={snap.properties.get('inverseMaxPower')} "
        f"socSet={snap.properties.get('socSet')} "
        f"lamp={snap.properties.get('lampSwitch')} "
        f"remain={snap.properties.get('remainOutTime')}"
        f"{bat_s}"
    )


async def _set(
    client: ZendureClient, key: str, value: int, report: Report, label: str
) -> None:
    try:
        before = await client.async_refresh()
        after = await client.async_set(key, value)
        ok = after.properties.get(key) == value
        report.add(
            label,
            ok,
            f"before={before.properties.get(key)} after={after.properties.get(key)} "
            f"target={value}",
        )
    except Exception as err:
        report.add(label, False, f"target={value}", f"{type(err).__name__}: {err}")


async def run() -> int:
    report = Report()
    original_lamp: int | None = None
    original_out: int | None = None

    timeout = aiohttp.ClientTimeout(total=10)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        client = create_local_client(HOST, session, timeout=8.0)
        try:
            try:
                snap = await client.async_refresh()
                original_lamp = int(snap.properties.get("lampSwitch") or 0)
                original_out = int(snap.properties.get("outputLimit") or 0)
                report.add("read_status", True, _brief(snap))
                if snap.model_key not in {"solarflow_2400ac_plus", "max_5000_pro"}:
                    report.add(
                        "model_registered",
                        False,
                        f"unexpected model_key={snap.model_key}",
                    )
                else:
                    report.add("model_registered", True, snap.model_key)
                soc = snap.properties.get("electricLevel")
                soc_ok = isinstance(soc, (int, float)) and 0 <= float(soc) <= 100
                report.add("soc_percent", soc_ok, f"electricLevel={soc}")
                remain = snap.properties.get("remainOutTime")
                report.add(
                    "remain_sentinel",
                    remain is None or isinstance(remain, (int, float)),
                    f"remainOutTime={remain}",
                )
            except Exception as err:
                report.add(
                    "read_status",
                    False,
                    HOST,
                    f"{type(err).__name__}: {err}\n{traceback.format_exc()}",
                )
                _print(report)
                return 1

            other_lamp = 0 if original_lamp == 1 else 1
            await _set(client, "lampSwitch", other_lamp, report, "lamp_toggle")
            await _set(client, "lampSwitch", original_lamp, report, "lamp_restore")

            max_pwr = snap.properties.get("inverseMaxPower")
            max_ok = isinstance(max_pwr, (int, float)) and float(max_pwr) >= SAFE_OUTPUT
            if original_out == SAFE_OUTPUT:
                target_out = 200 if SAFE_OUTPUT != 200 else 220
            else:
                target_out = SAFE_OUTPUT
            if max_ok:
                await _set(
                    client, "outputLimit", int(target_out), report, "output_nudge"
                )
                await _set(
                    client,
                    "outputLimit",
                    int(original_out),
                    report,
                    "output_restore",
                )
            else:
                report.add(
                    "output_nudge",
                    False,
                    f"skip: inverseMaxPower={max_pwr} < {SAFE_OUTPUT}",
                )

            try:
                final = await client.async_refresh()
                lamp_ok = final.properties.get("lampSwitch") == original_lamp
                out_ok = final.properties.get("outputLimit") == original_out
                report.add(
                    "restore_check",
                    lamp_ok and out_ok,
                    f"lamp={final.properties.get('lampSwitch')} "
                    f"(want {original_lamp}) out={final.properties.get('outputLimit')} "
                    f"(want {original_out})",
                )
            except Exception as err:
                report.add("restore_check", False, "", f"{type(err).__name__}: {err}")
        finally:
            await client.close()

    _print(report)
    return 0 if all(s.ok for s in report.steps) else 1


def _print(report: Report) -> None:
    payload = {
        "host": HOST,
        "when": datetime.now(tz=UTC).isoformat(),
        "steps": [
            {
                "name": s.name,
                "ok": s.ok,
                "detail": s.detail,
                "error": s.error,
            }
            for s in report.steps
        ],
        "passed": all(s.ok for s in report.steps),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))

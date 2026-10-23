"""Import the after-shot retract measure for past shots from the machine.

The machine keeps every shot with ~10 Hz sensor samples (including motor
current, speed, drive level and piston position). On first setup the
integration reads that history once, summarises each shot the same way as the
live sensor does, and imports the results into Home Assistant's long-term
statistics for the two after-shot sensors. Graphs and cards then show the
trend from the very first shot instead of starting empty.

The machine is read three days at a time, sequentially with a short pause in
between, so neither the machine nor Home Assistant handles more than a few
megabytes at once. Re-running the import is safe: hourly
rows are simply replaced.
"""

from __future__ import annotations

from datetime import datetime, timezone
import logging
from typing import Any

import asyncio

import aiohttp

from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .after_shot import summarise
from .connection import build_base_url
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
CHUNK = 3 * 86400  # seconds of shot history per request
REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=120)

# sensor key -> (index in the summary tuple, unit, unit class)
SERIES = {
    "after_shot_current": (0, "A", "electric_current"),
    "after_shot_speed": (1, "mm/s", "speed"),
}


def _shot_summary(shot: dict[str, Any]) -> tuple[float, float] | None:
    """Summarise one shot from the machine's history format."""
    samples = []
    for row in shot.get("data") or []:
        s = row.get("sensors")
        if not isinstance(s, dict):
            continue
        try:
            samples.append(
                (
                    float(s.get("motor_position") or 0),
                    float(s.get("motor_speed") or 0),
                    float(s.get("motor_power") or 0),
                    float(s.get("motor_current") or 0),
                    float((row.get("shot") or {}).get("pressure") or 0),
                )
            )
        except (TypeError, ValueError):
            continue
    return summarise(samples)


async def _post(session: aiohttp.ClientSession, url: str, body: dict) -> list[dict]:
    async with session.post(url, json=body, timeout=REQUEST_TIMEOUT) as resp:
        resp.raise_for_status()
        data = await resp.json(content_type=None)
    return data.get("history", []) if isinstance(data, dict) else []


async def async_import_after_shot_history(
    hass: HomeAssistant, host: str, port: int, serial: str
) -> int | None:
    """Import past after-shot values into long-term statistics.

    Returns the number of shots used, or None if the sensors don't exist yet.
    """
    from homeassistant.components.recorder.models import StatisticMeanType
    from homeassistant.components.recorder.statistics import async_import_statistics

    registry = er.async_get(hass)
    entity_ids = {
        key: registry.async_get_entity_id("sensor", DOMAIN, f"meticulous_{serial}_{key}")
        for key in SERIES
    }
    if not any(entity_ids.values()):
        _LOGGER.debug("After-shot sensors not registered yet; skipping history import")
        return None

    session = async_get_clientsession(hass)
    url = f"{build_base_url(host, port)}/api/v1/history"

    # 1) the list of all shots (without sample data) to know which weeks to read
    shots = await _post(session, url, {"sort": "asc", "max_results": 100000, "dump_data": False})
    times = sorted(float(s["time"]) for s in shots if s.get("time"))
    if not times:
        return 0

    # 2) a few days at a time, with samples; summarise each shot
    values: list[tuple[float, tuple[float, float]]] = []
    start = times[0] - 1
    while start <= times[-1]:
        end = start + CHUNK
        if any(start <= t < end for t in times):
            await asyncio.sleep(0.5)
            week = await _post(
                session,
                url,
                {"sort": "asc", "max_results": 1000, "dump_data": True, "start_date": start, "end_date": end},
            )
            for shot in week:
                summary = _shot_summary(shot)
                if summary is not None:
                    values.append((float(shot["time"]), summary))
        start = end

    # 3) hourly statistics rows (mean/min/max of the shots in that hour)
    hours: dict[int, list[tuple[float, float]]] = {}
    for ts, summary in values:
        hours.setdefault(int(ts // 3600) * 3600, []).append(summary)

    for key, (idx, unit, unit_class) in SERIES.items():
        entity_id = entity_ids[key]
        if not entity_id or not hours:
            continue
        stats = []
        for hour, items in sorted(hours.items()):
            vals = [item[idx] for item in items]
            stats.append(
                {
                    "start": datetime.fromtimestamp(hour, tz=timezone.utc),
                    "mean": sum(vals) / len(vals),
                    "min": min(vals),
                    "max": max(vals),
                }
            )
        metadata = {
            "has_sum": False,
            "mean_type": StatisticMeanType.ARITHMETIC,
            "name": None,
            "source": "recorder",
            "statistic_id": entity_id,
            "unit_class": unit_class,
            "unit_of_measurement": unit,
        }
        async_import_statistics(hass, metadata, stats)

    _LOGGER.info("Imported the after-shot retract measure for %d past shots", len(values))
    return len(values)


async def async_import_once(hass: HomeAssistant, entry_id: str, host: str, port: int, serial: str) -> None:
    """Run the history import the first time the integration starts with the after-shot sensors."""
    store: Store[dict[str, Any]] = Store(hass, STORE_VERSION, f"{DOMAIN}.{entry_id}.history_import")
    done = await store.async_load() or {}
    if done.get("after_shot"):
        return
    try:
        count = await async_import_after_shot_history(hass, host, port, serial)
    except Exception as err:  # noqa: BLE001 - never block or break setup over the import
        _LOGGER.warning("Could not import shot history from the machine (will retry next start): %s", err)
        return
    if count is None:
        return
    await store.async_save({**done, "after_shot": True, "shots": count, "at": datetime.now(timezone.utc).isoformat()})

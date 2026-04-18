"""Diagnostics support for Meticulous Espresso integration."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinators = hass.data[DOMAIN].get(entry.entry_id, {})
    push = coordinators.get("push")

    data: dict[str, Any] = {
        "config": {
            "host": entry.data.get(CONF_HOST),
        },
        "connection": {
            "connected": push.connected if push else False,
            "serial": push.serial if push else None,
            "model": push.model if push else None,
            "sw_version": push.sw_version if push else None,
            "hw_version": push.hw_version if push else None,
        },
    }

    if push:
        data["sensors"] = dict(push.data)
        data["profiles"] = {
            "count": len(push.available_profiles),
            "names": list(push.available_profiles.values()),
        }

    return data

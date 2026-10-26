"""The Meticulous Espresso integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, CONF_PORT, Platform
from homeassistant.core import HomeAssistant, ServiceCall

from .const import DOMAIN
from .coordinator import MeticulousPollingCoordinator, MeticulousPushCoordinator
from .history_import import async_import_after_shot_history, async_import_once

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.SWITCH,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.IMAGE,
]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Meticulous Espresso from a config entry."""
    host = entry.data[CONF_HOST]
    # Port may be absent for entries created before port auto-detection
    port = entry.data.get(CONF_PORT)

    # Create push coordinator (real-time telemetry via Socket.IO)
    push_coordinator = MeticulousPushCoordinator(
        hass, host, serial=entry.unique_id or "meticulous", port=port
    )

    # Connect to machine (auto-detects the API port)
    if not await push_coordinator.async_setup():
        _LOGGER.error("Failed to connect to Meticulous machine at %s", host)
        return False

    # Persist the detected port so later setups skip probing
    if push_coordinator.port != port:
        hass.config_entries.async_update_entry(
            entry, data={**entry.data, CONF_PORT: push_coordinator.port}
        )

    # Create polling coordinator (profiles, statistics, settings)
    poll_coordinator = MeticulousPollingCoordinator(hass, push_coordinator)

    # Do initial refresh of slow data
    await poll_coordinator.async_config_entry_first_refresh()
    # A DataUpdateCoordinator only keeps polling while something listens to it, and no entity
    # subscribes to this one, so without this it would never refresh after the first run.
    entry.async_on_unload(poll_coordinator.async_add_listener(lambda: None))

    # Store coordinators in runtime data
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = {
        "push": push_coordinator,
        "poll": poll_coordinator,
    }

    # Register cleanup on unload
    entry.async_on_unload(push_coordinator.async_shutdown)

    # Forward to platforms
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    # The first time the after-shot sensors exist, fill their long-term statistics from the
    # machine's own shot history (in the background, once; see history_import.py)
    entry.async_create_background_task(
        hass,
        async_import_once(
            hass, entry.entry_id, push_coordinator.host, push_coordinator.port, push_coordinator.serial
        ),
        f"{DOMAIN} shot history import",
    )

    if not hass.services.has_service(DOMAIN, "import_shot_history"):

        async def _import_history(call: ServiceCall) -> None:
            """Re-import the after-shot measure for all past shots (safe to repeat)."""
            for data in hass.data.get(DOMAIN, {}).values():
                push = data["push"]
                await async_import_after_shot_history(hass, push.host, push.port, push.serial)

        hass.services.async_register(DOMAIN, "import_shot_history", _import_history)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok

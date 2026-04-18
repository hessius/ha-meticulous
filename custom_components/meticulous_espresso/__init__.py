"""The Meticulous Espresso integration."""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import MeticulousPollingCoordinator, MeticulousPushCoordinator

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

    # Create push coordinator (real-time telemetry via Socket.IO)
    push_coordinator = MeticulousPushCoordinator(
        hass, host, serial=entry.unique_id or "meticulous"
    )

    # Connect to machine
    if not await push_coordinator.async_setup():
        _LOGGER.error("Failed to connect to Meticulous machine at %s", host)
        return False

    # Create polling coordinator (profiles, statistics, settings)
    poll_coordinator = MeticulousPollingCoordinator(hass, push_coordinator)

    # Do initial refresh of slow data
    await poll_coordinator.async_config_entry_first_refresh()

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

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)

    return unload_ok

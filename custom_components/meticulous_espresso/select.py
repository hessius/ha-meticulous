"""Select platform for Meticulous Espresso integration."""

from __future__ import annotations

import logging

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import MeticulousPushCoordinator
from .entity import MeticulousEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Meticulous select entities."""
    coordinator: MeticulousPushCoordinator = hass.data[DOMAIN][entry.entry_id]["push"]
    async_add_entities([MeticulousProfileSelect(coordinator)])


class MeticulousProfileSelect(MeticulousEntity, SelectEntity):
    """Select entity for choosing the active profile."""

    def __init__(self, coordinator: MeticulousPushCoordinator) -> None:
        """Initialize the select entity."""
        super().__init__(coordinator, "profile_select")
        self._attr_name = "Active Profile"
        self._attr_icon = "mdi:coffee"

    @property
    def options(self) -> list[str]:
        """Return the list of available profile names."""
        profiles = self.coordinator.available_profiles
        if not profiles:
            current = self.coordinator.data.get("active_profile")
            return [current] if current else []
        return list(profiles.values())

    @property
    def current_option(self) -> str | None:
        """Return the currently active profile name."""
        return self.coordinator.data.get("active_profile")

    async def async_select_option(self, option: str) -> None:
        """Select a profile by name."""
        # Find profile ID from name
        for pid, name in self.coordinator.available_profiles.items():
            if name == option:
                await self.coordinator.async_select_profile(pid)
                return

        _LOGGER.warning("Profile not found: %s", option)

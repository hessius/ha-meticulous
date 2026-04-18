"""Switch platform for Meticulous Espresso integration."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
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
    """Set up Meticulous switches."""
    coordinator: MeticulousPushCoordinator = hass.data[DOMAIN][entry.entry_id]["push"]
    async_add_entities([MeticulousSoundsSwitch(coordinator)])


class MeticulousSoundsSwitch(MeticulousEntity, SwitchEntity):
    """Switch to enable/disable machine sounds."""

    def __init__(self, coordinator: MeticulousPushCoordinator) -> None:
        """Initialize the switch."""
        super().__init__(coordinator, "sounds_enabled")
        self._attr_name = "Sounds"
        self._attr_icon = "mdi:volume-high"
        self._attr_entity_category = EntityCategory.CONFIG

    @property
    def is_on(self) -> bool | None:
        """Return True if sounds are enabled."""
        value = self.coordinator.data.get("sounds_enabled")
        if value is None:
            return None
        return bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable sounds."""
        await self.coordinator.async_set_sounds(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable sounds."""
        await self.coordinator.async_set_sounds(False)

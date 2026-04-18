"""Number platform for Meticulous Espresso integration."""

from __future__ import annotations

import logging

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE
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
    """Set up Meticulous number entities."""
    coordinator: MeticulousPushCoordinator = hass.data[DOMAIN][entry.entry_id]["push"]
    async_add_entities([MeticulousBrightnessNumber(coordinator)])


class MeticulousBrightnessNumber(MeticulousEntity, NumberEntity):
    """Number entity for machine brightness control."""

    def __init__(self, coordinator: MeticulousPushCoordinator) -> None:
        """Initialize the number entity."""
        super().__init__(coordinator, "brightness")
        self._attr_name = "Brightness"
        self._attr_icon = "mdi:brightness-6"
        self._attr_entity_category = EntityCategory.CONFIG
        self._attr_native_min_value = 0
        self._attr_native_max_value = 100
        self._attr_native_step = 1
        self._attr_native_unit_of_measurement = PERCENTAGE
        self._attr_mode = NumberMode.SLIDER

    @property
    def native_value(self) -> float | None:
        """Return the current brightness."""
        return self.coordinator.data.get("brightness")

    async def async_set_native_value(self, value: float) -> None:
        """Set the brightness."""
        await self.coordinator.async_set_brightness(int(value))

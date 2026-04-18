"""Button platform for Meticulous Espresso integration."""

from __future__ import annotations

import logging

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from meticulous.api_types import ActionType

from .const import DOMAIN, BUTTON_DESCRIPTIONS, MeticulousButtonDescription
from .coordinator import MeticulousPushCoordinator
from .entity import MeticulousEntity

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Meticulous buttons."""
    coordinator: MeticulousPushCoordinator = hass.data[DOMAIN][entry.entry_id]["push"]
    async_add_entities(
        MeticulousButton(coordinator, desc) for desc in BUTTON_DESCRIPTIONS
    )


class MeticulousButton(MeticulousEntity, ButtonEntity):
    """Representation of a Meticulous machine button."""

    def __init__(
        self,
        coordinator: MeticulousPushCoordinator,
        description: MeticulousButtonDescription,
    ) -> None:
        """Initialize the button."""
        super().__init__(coordinator, description.key)
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_entity_category = description.entity_category
        self._action = ActionType[description.action]

    async def async_press(self) -> None:
        """Handle the button press."""
        success = await self.coordinator.async_execute_action(self._action)
        if not success:
            _LOGGER.warning("Failed to execute %s", self._description.key)

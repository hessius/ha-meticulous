"""Image platform for Meticulous Espresso integration."""

from __future__ import annotations

import logging
from datetime import datetime

from homeassistant.components.image import ImageEntity
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
    """Set up Meticulous image entities."""
    coordinator: MeticulousPushCoordinator = hass.data[DOMAIN][entry.entry_id]["push"]
    async_add_entities([MeticulousProfileImage(coordinator)])


class MeticulousProfileImage(MeticulousEntity, ImageEntity):
    """Image entity showing the active profile image."""

    def __init__(self, coordinator: MeticulousPushCoordinator) -> None:
        """Initialize the image entity."""
        super().__init__(coordinator, "profile_image")
        ImageEntity.__init__(self, coordinator.hass)
        self._attr_name = "Profile Image"
        self._attr_icon = "mdi:image"
        self._last_profile: str | None = None

    @property
    def image_url(self) -> str | None:
        """Return the URL of the active profile image."""
        profile = self.coordinator.data.get("active_profile")
        if not profile:
            return None

        # Find profile ID from name
        for pid, name in self.coordinator.available_profiles.items():
            if name == profile:
                host = self.coordinator.host
                return f"http://{host}:8080/api/v1/profile/{pid}/image"

        return None

    @property
    def image_last_updated(self) -> datetime | None:
        """Return when the image was last updated."""
        current = self.coordinator.data.get("active_profile")
        if current != self._last_profile:
            self._last_profile = current
            return datetime.now()
        return None

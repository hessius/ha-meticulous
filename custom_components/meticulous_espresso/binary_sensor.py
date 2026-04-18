"""Binary sensor platform for Meticulous Espresso integration."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, BINARY_SENSOR_DESCRIPTIONS, MeticulousBinarySensorDescription
from .coordinator import MeticulousPushCoordinator
from .entity import MeticulousEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Meticulous binary sensors."""
    coordinator: MeticulousPushCoordinator = hass.data[DOMAIN][entry.entry_id]["push"]
    async_add_entities(
        MeticulousBinarySensor(coordinator, desc) for desc in BINARY_SENSOR_DESCRIPTIONS
    )


class MeticulousBinarySensor(MeticulousEntity, BinarySensorEntity):
    """Representation of a Meticulous binary sensor."""

    def __init__(
        self,
        coordinator: MeticulousPushCoordinator,
        description: MeticulousBinarySensorDescription,
    ) -> None:
        """Initialize the binary sensor."""
        super().__init__(coordinator, description.key)
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class
        self._attr_entity_category = description.entity_category

    @property
    def is_on(self) -> bool | None:
        """Return True if brewing."""
        value = self.coordinator.data.get(self._key)
        if value is None:
            return None
        return bool(value)

"""Sensor platform for Meticulous Espresso integration."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SENSOR_DESCRIPTIONS, MeticulousSensorDescription
from .coordinator import MeticulousPushCoordinator
from .entity import MeticulousEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Meticulous sensors."""
    coordinator: MeticulousPushCoordinator = hass.data[DOMAIN][entry.entry_id]["push"]
    async_add_entities(
        MeticulousSensor(coordinator, desc) for desc in SENSOR_DESCRIPTIONS
    )


class MeticulousSensor(MeticulousEntity, SensorEntity):
    """Representation of a Meticulous sensor."""

    def __init__(
        self,
        coordinator: MeticulousPushCoordinator,
        description: MeticulousSensorDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self._description = description
        self._attr_name = description.name
        self._attr_icon = description.icon
        self._attr_device_class = description.device_class
        self._attr_state_class = description.state_class
        self._attr_native_unit_of_measurement = description.native_unit_of_measurement
        self._attr_entity_category = description.entity_category
        self._attr_entity_registry_enabled_default = description.enabled_default
        if description.suggested_display_precision is not None:
            self._attr_suggested_display_precision = description.suggested_display_precision

    @property
    def native_value(self):
        """Return the state of the sensor."""
        return self.coordinator.data.get(self._key)

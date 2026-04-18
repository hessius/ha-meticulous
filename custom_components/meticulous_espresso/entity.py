"""Base entity for Meticulous Espresso integration."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, MANUFACTURER
from .coordinator import MeticulousPushCoordinator


class MeticulousEntity(CoordinatorEntity[MeticulousPushCoordinator]):
    """Base class for Meticulous Espresso entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: MeticulousPushCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        self._key = key
        self._attr_unique_id = f"meticulous_{coordinator.serial}_{key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information."""
        return DeviceInfo(
            identifiers={(DOMAIN, self.coordinator.serial)},
            name="Meticulous Espresso",
            manufacturer=MANUFACTURER,
            model=self.coordinator.model,
            sw_version=self.coordinator.sw_version,
            hw_version=self.coordinator.hw_version,
        )

    @property
    def available(self) -> bool:
        """Return True if the machine is connected."""
        return self.coordinator.connected

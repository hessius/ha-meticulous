"""Constants for the Meticulous Espresso integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    SIGNAL_STRENGTH_DECIBELS,
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfMass,
    UnitOfElectricPotential,
    UnitOfVolumeFlowRate,
)

DOMAIN = "meticulous_espresso"
MANUFACTURER = "Meticulous"
DEFAULT_PORT = 8080

# Reconnection
RECONNECT_INITIAL_DELAY = 5
RECONNECT_MAX_DELAY = 300
RECONNECT_BACKOFF_FACTOR = 2

# Polling interval for slow-changing data (profiles, statistics, settings)
SLOW_POLL_INTERVAL = 60  # seconds


class MachineState(StrEnum):
    """Machine state values."""

    IDLE = "Idle"
    PREHEATING = "Preheating"
    BREWING = "Brewing"
    UNKNOWN = "Unknown"


# Delta-based filtering thresholds to prevent excessive state updates
SENSOR_DELTAS: dict[str, float] = {
    "boiler_temperature": 0.5,
    "brew_head_temperature": 0.5,
    "external_temp_1": 0.5,
    "external_temp_2": 0.5,
    "pressure": 0.2,
    "flow_rate": 0.1,
    "shot_weight": 0.1,
    "shot_timer": 0.1,
    "elapsed_time": 0.1,
    "target_temperature": 0.5,
    "target_weight": 0.1,
    "target_pressure": 0.2,
    "target_flow": 0.1,
    "voltage": 1.0,
}

# Sensors that use exact-match filtering (publish on any change)
EXACT_MATCH_SENSORS: set[str] = {
    "state",
    "active_profile",
    "brewing",
    "last_shot_name",
    "last_shot_rating",
    "profile_author",
    "firmware_version",
    "software_version",
    "last_shot_time",
    "sounds_enabled",
    "total_shots",
    "preheat_countdown",
}


@dataclass(frozen=True)
class MeticulousSensorDescription:
    """Describes a Meticulous sensor entity."""

    key: str
    name: str
    icon: str | None = None
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    native_unit_of_measurement: str | None = None
    entity_category: EntityCategory | None = None
    enabled_default: bool = True
    suggested_display_precision: int | None = None


@dataclass(frozen=True)
class MeticulousBinarySensorDescription:
    """Describes a Meticulous binary sensor entity."""

    key: str
    name: str
    icon: str | None = None
    device_class: BinarySensorDeviceClass | None = None
    entity_category: EntityCategory | None = None


@dataclass(frozen=True)
class MeticulousButtonDescription:
    """Describes a Meticulous button entity."""

    key: str
    name: str
    icon: str
    action: str  # pyMeticulous ActionType name
    entity_category: EntityCategory | None = None


# ─── Sensor definitions ────────────────────────────────────────────────────────

SENSOR_DESCRIPTIONS: list[MeticulousSensorDescription] = [
    # Temperature sensors
    MeticulousSensorDescription(
        key="boiler_temperature",
        name="Boiler Temperature",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="brew_head_temperature",
        name="Brew Head Temperature",
        icon="mdi:thermometer-water",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="external_temp_1",
        name="External Temperature 1",
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="external_temp_2",
        name="External Temperature 2",
        icon="mdi:thermometer-lines",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="target_temperature",
        name="Target Temperature",
        icon="mdi:thermometer-check",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
    ),
    # Brewing sensors
    MeticulousSensorDescription(
        key="pressure",
        name="Pressure",
        icon="mdi:gauge",
        device_class=SensorDeviceClass.PRESSURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfPressure.BAR,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="flow_rate",
        name="Flow Rate",
        icon="mdi:water-outline",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="mL/s",
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="shot_weight",
        name="Shot Weight",
        icon="mdi:scale",
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="shot_timer",
        name="Shot Timer",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="target_weight",
        name="Target Weight",
        icon="mdi:scale-balance",
        device_class=SensorDeviceClass.WEIGHT,
        native_unit_of_measurement=UnitOfMass.GRAMS,
        suggested_display_precision=1,
    ),
    # Profile info
    MeticulousSensorDescription(
        key="active_profile",
        name="Active Profile",
        icon="mdi:coffee",
    ),
    MeticulousSensorDescription(
        key="profile_author",
        name="Profile Author",
        icon="mdi:account",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
    ),
    # Machine state
    MeticulousSensorDescription(
        key="state",
        name="State",
        icon="mdi:state-machine",
    ),
    MeticulousSensorDescription(
        key="preheat_countdown",
        name="Preheat Countdown",
        icon="mdi:timer-sand",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=0,
    ),
    # Statistics
    MeticulousSensorDescription(
        key="total_shots",
        name="Total Shots",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    MeticulousSensorDescription(
        key="last_shot_name",
        name="Last Shot",
        icon="mdi:coffee-outline",
    ),
    MeticulousSensorDescription(
        key="last_shot_rating",
        name="Last Shot Rating",
        icon="mdi:star",
    ),
    MeticulousSensorDescription(
        key="last_shot_time",
        name="Last Shot Time",
        icon="mdi:clock-outline",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    # Device info
    MeticulousSensorDescription(
        key="firmware_version",
        name="Firmware Version",
        icon="mdi:chip",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
    ),
    MeticulousSensorDescription(
        key="software_version",
        name="Software Version",
        icon="mdi:application-cog",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
    ),
    MeticulousSensorDescription(
        key="voltage",
        name="Voltage",
        icon="mdi:flash",
        device_class=SensorDeviceClass.VOLTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricPotential.VOLT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=0,
    ),
]

BINARY_SENSOR_DESCRIPTIONS: list[MeticulousBinarySensorDescription] = [
    MeticulousBinarySensorDescription(
        key="brewing",
        name="Brewing",
        icon="mdi:coffee-maker",
        device_class=BinarySensorDeviceClass.RUNNING,
    ),
]

BUTTON_DESCRIPTIONS: list[MeticulousButtonDescription] = [
    MeticulousButtonDescription(
        key="start_shot",
        name="Start Shot",
        icon="mdi:play",
        action="START",
    ),
    MeticulousButtonDescription(
        key="stop_shot",
        name="Stop Shot",
        icon="mdi:stop",
        action="STOP",
    ),
    MeticulousButtonDescription(
        key="continue_shot",
        name="Continue Shot",
        icon="mdi:play-pause",
        action="CONTINUE",
    ),
    MeticulousButtonDescription(
        key="abort_shot",
        name="Abort Shot",
        icon="mdi:close-circle",
        action="ABORT",
    ),
    MeticulousButtonDescription(
        key="preheat",
        name="Preheat",
        icon="mdi:fire",
        action="PREHEAT",
    ),
    MeticulousButtonDescription(
        key="tare_scale",
        name="Tare Scale",
        icon="mdi:scale-balance",
        action="TARE",
    ),
    MeticulousButtonDescription(
        key="home_plunger",
        name="Home Plunger",
        icon="mdi:arrow-collapse-down",
        action="HOME",
    ),
    MeticulousButtonDescription(
        key="purge",
        name="Purge",
        icon="mdi:water-pump",
        action="PURGE",
    ),
]

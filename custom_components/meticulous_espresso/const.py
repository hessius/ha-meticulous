"""Constants for the Meticulous Espresso integration."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import (
    EntityCategory,
    UnitOfPressure,
    UnitOfTemperature,
    UnitOfTime,
    UnitOfMass,
    UnitOfElectricPotential,
    UnitOfElectricCurrent,
    UnitOfSpeed,
)

DOMAIN = "meticulous_espresso"
MANUFACTURER = "Meticulous"
DEFAULT_PORT = 8080
# Newer firmware binds the backend to localhost and proxies the API on port 80
FALLBACK_PORT = 80
PORT_CANDIDATES: tuple[int, ...] = (DEFAULT_PORT, FALLBACK_PORT)
PORT_PROBE_TIMEOUT = 5  # seconds

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
    # Only changes while the piston moves; ~1 unit filter keeps a full stroke to ~75 updates
    "piston_position": 1.0,
}

# Piston motor effort tracking.
# The Socket.IO "sensors" stream already carries motor position/speed/power/current.
# During three repeatable full-stroke moves the samples are kept in memory and
# summarised once when the move ends, so only one update per sensor per move is
# published. Rising effort over time can indicate seal friction or scale build-up.
#   raise   = "Home" started from Idle (manual raise)
#   retract = "Retracting" started from "Click to Start" (pre-shot retract)
#   lower   = "Purge" started from Idle (manual lower)
PISTON_MOVES: tuple[str, ...] = ("raise", "retract", "lower")
PISTON_SUMMARY_FIELDS: tuple[str, ...] = (
    "avg_power",
    "peak_power",
    "avg_current",
    "duration",
    "travel",
    "motor_temp",
)
PISTON_MOVING_SPEED = 0.5  # |m_spd| above this counts as moving
PISTON_MIN_SAMPLES = 5  # ignore moves with fewer moving samples than this

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
    # ─── Piston position and motor effort (diagnostic) ───
    MeticulousSensorDescription(
        key="piston_position",
        name="Piston Position",
        icon="mdi:arrow-up-down",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="raise_avg_power",
        name="Piston Raise Avg Power",
        icon="mdi:engine",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="raise_peak_power",
        name="Piston Raise Peak Power",
        icon="mdi:engine-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="raise_avg_current",
        name="Piston Raise Avg Current",
        icon="mdi:current-dc",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=3,
    ),
    MeticulousSensorDescription(
        key="raise_duration",
        name="Piston Raise Duration",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="s",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=2,
    ),
    MeticulousSensorDescription(
        key="raise_travel",
        name="Piston Raise Travel",
        icon="mdi:arrow-expand-vertical",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="raise_motor_temp",
        name="Piston Raise Motor Temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="retract_avg_power",
        name="Pre-shot Retract Avg Power",
        icon="mdi:engine",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="retract_peak_power",
        name="Pre-shot Retract Peak Power",
        icon="mdi:engine-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="retract_avg_current",
        name="Pre-shot Retract Avg Current",
        icon="mdi:current-dc",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=3,
    ),
    MeticulousSensorDescription(
        key="retract_duration",
        name="Pre-shot Retract Duration",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="s",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=2,
    ),
    MeticulousSensorDescription(
        key="retract_travel",
        name="Pre-shot Retract Travel",
        icon="mdi:arrow-expand-vertical",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="retract_motor_temp",
        name="Pre-shot Retract Motor Temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="lower_avg_power",
        name="Piston Lower Avg Power",
        icon="mdi:engine",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="lower_peak_power",
        name="Piston Lower Peak Power",
        icon="mdi:engine-outline",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="lower_avg_current",
        name="Piston Lower Avg Current",
        icon="mdi:current-dc",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=3,
    ),
    MeticulousSensorDescription(
        key="lower_duration",
        name="Piston Lower Duration",
        icon="mdi:timer-outline",
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="s",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=2,
    ),
    MeticulousSensorDescription(
        key="lower_travel",
        name="Piston Lower Travel",
        icon="mdi:arrow-expand-vertical",
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="lower_motor_temp",
        name="Piston Lower Motor Temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    MeticulousSensorDescription(
        key="raise_boiler_temp",
        name="Piston Raise Boiler Temp",
        icon="mdi:thermometer",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="°C",
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=False,
        suggested_display_precision=1,
    ),
    # After-shot retract: one value per shot (see after_shot.py). Past shots are
    # imported from the machine's shot history the first time these exist.
    MeticulousSensorDescription(
        key="after_shot_current",
        name="Piston After-Shot Current",
        icon="mdi:current-dc",
        device_class=SensorDeviceClass.CURRENT,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=3,
    ),
    MeticulousSensorDescription(
        key="after_shot_speed",
        name="Piston After-Shot Speed",
        icon="mdi:speedometer",
        device_class=SensorDeviceClass.SPEED,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfSpeed.MILLIMETERS_PER_SECOND,
        entity_category=EntityCategory.DIAGNOSTIC,
        enabled_default=True,
        suggested_display_precision=2,
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

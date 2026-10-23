"""Data update coordinators for Meticulous Espresso integration.

Two coordinators handle different update patterns:
- MeticulousPushCoordinator: Real-time telemetry via Socket.IO push events
- MeticulousPollingCoordinator: Slow-changing data (profiles, statistics) via REST polling
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from meticulous import Api
from meticulous.api import ApiOptions
from meticulous.api_types import ActionType, APIError, BrightnessRequest, PartialSettings

from .after_shot import PRE_SHOT_STATES, summarise
from .connection import build_base_url, discover_api
from .const import (
    DOMAIN,
    EXACT_MATCH_SENSORS,
    PISTON_MIN_SAMPLES,
    PISTON_MOVES,
    PISTON_MOVING_SPEED,
    PISTON_SUMMARY_FIELDS,
    PORT_CANDIDATES,
    RECONNECT_BACKOFF_FACTOR,
    RECONNECT_INITIAL_DELAY,
    RECONNECT_MAX_DELAY,
    SENSOR_DELTAS,
    SLOW_POLL_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)

# Words that should remain lowercase (unless at start of phrase)
_LOWERCASE_WORDS = {"to", "in", "a", "an", "the", "at", "by", "or", "and", "for", "of"}


def _normalize_state_name(state_name: str) -> str:
    """Normalize state names from Socket.IO to human-readable form."""
    state_name = state_name.replace("_", " ").strip()
    if not state_name:
        return state_name

    words = state_name.split()
    normalized = []
    for i, word in enumerate(words):
        if len(word) <= 2 and word.isupper():
            normalized.append(word)
        elif i == 0:
            normalized.append(word.capitalize())
        elif word.lower() in _LOWERCASE_WORDS:
            normalized.append(word.lower())
        else:
            normalized.append(word.capitalize())

    return " ".join(normalized)


class MeticulousPushCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for real-time telemetry via Socket.IO push events.

    Does NOT poll — all updates come from Socket.IO event callbacks
    marshalled from the executor thread to the HA event loop.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        host: str,
        serial: str,
        port: int | None = None,
    ) -> None:
        """Initialize the push coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_push",
            # No update_interval — purely push-based
        )
        self.host = host
        # None until auto-detected (8080 on older firmware, 80 on newer)
        self.port = port
        self.serial = serial
        self.model: str = "Espresso"
        self.sw_version: str | None = None
        self.hw_version: str | None = None

        self._api: Api | None = None
        self._connected = False
        self._reconnect_task: asyncio.Task | None = None
        self._socket_thread_task: asyncio.Task | None = None

        # Delta filtering state
        self._last_values: dict[str, Any] = {}

        # State tracking (ported from addon)
        self._current_state = "Idle"
        self._previous_state_name: str | None = None
        self._current_machine_status = "unknown"
        self._was_in_idle = True
        self._last_shot_timer_value = 0.0
        self._stale_shot_timer_value: float | None = None
        self._preheat_countdown: float = 0.0
        # Piston motor effort tracking (see PISTON_MOVES in const.py)
        self._state_before: str | None = None
        self._motor_episode: dict[str, Any] | None = None
        self._after_shot: list[tuple[float, float, float, float, float]] | None = None
        self._pressure: float = 0.0
        self._last_preheat_time: float = 0.0

        # Current data snapshot
        self.data: dict[str, Any] = {
            "state": "Idle",
            "brewing": False,
            "boiler_temperature": None,
            "brew_head_temperature": None,
            "external_temp_1": None,
            "external_temp_2": None,
            "pressure": 0,
            "flow_rate": 0,
            "shot_weight": 0,
            "shot_timer": 0,
            "target_temperature": None,
            "target_weight": None,
            "active_profile": None,
            "profile_author": None,
            "total_shots": None,
            "last_shot_name": None,
            "last_shot_rating": None,
            "last_shot_time": None,
            "firmware_version": None,
            "software_version": None,
            "voltage": None,
            "preheat_countdown": 0,
            "sounds_enabled": None,
            "brightness": None,
            "piston_position": None,
            "raise_boiler_temp": None,
            "after_shot_current": None,
            "after_shot_speed": None,
            **{
                f"{move}_{field}": None
                for move in PISTON_MOVES
                for field in PISTON_SUMMARY_FIELDS
            },
        }

        # Profile list for select entity
        self.available_profiles: dict[str, str] = {}
        # Profile ID -> image path reported by the machine (may be absent)
        self.profile_images: dict[str, str] = {}

    @property
    def connected(self) -> bool:
        """Return True if connected to the machine."""
        return self._connected

    @property
    def api(self) -> Api | None:
        """Return the API client."""
        return self._api

    async def async_setup(self) -> bool:
        """Set up the coordinator: connect to REST API and start Socket.IO listener."""
        success = await self._connect_api()
        if success:
            await self._start_socket_listener()
        return success

    async def async_shutdown(self) -> None:
        """Clean up on unload."""
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
        if self._socket_thread_task and not self._socket_thread_task.done():
            self._socket_thread_task.cancel()
        if self._api:
            try:
                await self.hass.async_add_executor_job(self._disconnect_socket)
            except Exception:
                pass
        self._connected = False

    def _disconnect_socket(self) -> None:
        """Disconnect Socket.IO (runs in executor)."""
        if self._api and self._api.sio and self._api.sio.connected:
            try:
                self._api.sio.disconnect()
            except Exception:
                pass

    async def _connect_api(self) -> bool:
        """Connect to REST API and fetch device info (runs in executor)."""
        try:

            def _setup_api() -> tuple[Api, Any, int]:
                """Detect the API port, create the client, fetch device info."""
                found = discover_api(self.host, self.port)
                if found is None:
                    raise ConnectionError(
                        f"No Meticulous API found on {self.host} "
                        f"(tried ports {', '.join(str(p) for p in PORT_CANDIDATES)})"
                    )
                port, _ = found
                base_url = build_base_url(self.host, port)
                options = ApiOptions(
                    onStatus=self._handle_status_event,
                    onTemperatureSensors=self._handle_temperature_event,
                    onProfileChange=self._handle_profile_event,
                    onNotification=self._handle_notification_event,
                    onButton=self._handle_button_event,
                    onSettingsChange=self._handle_settings_change_event,
                    onCommunication=lambda *_: None,
                    onActuators=lambda *_: None,
                    onMachineInfo=lambda *_: None,
                    onHeaterStatus=self._handle_heater_status_event,
                )
                api = Api(base_url=base_url, options=options)
                device_info = api.get_device_info()
                return api, device_info, port

            self._api, device_info, port = await self.hass.async_add_executor_job(
                _setup_api
            )

            if port != self.port:
                _LOGGER.info("Using Meticulous API at %s:%s", self.host, port)
            self.port = port

            if isinstance(device_info, APIError):
                _LOGGER.error("Failed to connect: %s", device_info.error)
                return False

            # Extract device information
            self.serial = getattr(device_info, "serial", self.serial)
            self.model = getattr(device_info, "model", "Espresso")
            self.sw_version = getattr(device_info, "software_version", None)
            self.hw_version = getattr(device_info, "model", None)

            # Store firmware/software in data
            self.data["firmware_version"] = getattr(device_info, "firmware", None)
            self.data["software_version"] = self.sw_version

            _LOGGER.info(
                "Connected to %s (Serial: %s, Firmware: %s)",
                getattr(device_info, "name", "Meticulous"),
                self.serial,
                getattr(device_info, "firmware", "unknown"),
            )
            return True

        except Exception as err:
            _LOGGER.error("Error connecting to machine API: %s", err)
            return False

    async def _start_socket_listener(self) -> None:
        """Start Socket.IO connection in executor thread."""

        def _connect_socket() -> None:
            """Connect Socket.IO (blocking)."""
            if not self._api:
                return
            self._api.connect_to_socket()
            # Register profileHover listener (not exposed via ApiOptions)
            self._api.sio.on("profileHover", self._handle_profile_hover_event)

        try:
            await self.hass.async_add_executor_job(_connect_socket)
            self._connected = True
            _LOGGER.info("Socket.IO connected — real-time updates enabled")
        except Exception as err:
            _LOGGER.warning("Socket.IO connection failed: %s", err)
            self._connected = False
            self._schedule_reconnect()

    def _schedule_reconnect(self, attempt: int = 0) -> None:
        """Schedule a reconnection attempt with exponential backoff."""
        if self._reconnect_task and not self._reconnect_task.done():
            return

        async def _reconnect() -> None:
            nonlocal attempt
            while not self._connected:
                attempt += 1
                delay = min(
                    RECONNECT_INITIAL_DELAY * (RECONNECT_BACKOFF_FACTOR ** (attempt - 1)),
                    RECONNECT_MAX_DELAY,
                )
                _LOGGER.info(
                    "Reconnect attempt %d in %.1fs", attempt, delay
                )
                await asyncio.sleep(delay)

                try:

                    def _try_reconnect() -> None:
                        if self._api:
                            self._api.connect_to_socket()

                    await self.hass.async_add_executor_job(_try_reconnect)
                    self._connected = True
                    self.async_set_updated_data(self.data)
                    _LOGGER.info("Socket.IO reconnected successfully")
                    return
                except Exception as err:
                    _LOGGER.warning("Reconnection failed (attempt %d): %s", attempt, err)

                    # The API port may have moved (e.g. firmware update);
                    # rebuild the client against a freshly detected port.
                    previous_port = self.port
                    if await self._connect_api() and self.port != previous_port:
                        _LOGGER.info(
                            "Meticulous API moved to port %s, reconnecting", self.port
                        )
                        continue

        self._reconnect_task = self.hass.async_create_task(_reconnect())

    # ─── Delta filtering ──────────────────────────────────────────────────────

    def _should_publish(self, key: str, value: Any) -> bool:
        """Determine if a value should trigger an entity update."""
        if value is None:
            return True

        if key in EXACT_MATCH_SENSORS:
            last = self._last_values.get(key)
            if last != value:
                self._last_values[key] = value
                return True
            return False

        delta = SENSOR_DELTAS.get(key)
        if delta is not None:
            last = self._last_values.get(key)
            if last is None:
                self._last_values[key] = value
                return True
            try:
                if abs(float(value) - float(last)) >= delta:
                    self._last_values[key] = value
                    return True
            except (ValueError, TypeError):
                self._last_values[key] = value
                return True
            return False

        # Unknown field — always publish
        self._last_values[key] = value
        return True

    def _update_data(self, updates: dict[str, Any]) -> None:
        """Apply filtered updates and push to HA (called from Socket.IO callbacks)."""
        changed = False
        for key, value in updates.items():
            if self._should_publish(key, value):
                self.data[key] = value
                changed = True

        if changed:
            # Marshal from executor thread to HA event loop
            self.hass.loop.call_soon_threadsafe(
                self.async_set_updated_data, dict(self.data)
            )

    # ─── Socket.IO event handlers (run in executor thread) ─────────────────

    def _handle_status_event(self, status: dict) -> None:
        """Handle real-time status updates from Socket.IO."""
        try:
            detailed_state_raw = status.get("name")
            coarse_state = status.get("state", "unknown").lower()
            is_extracting = status.get("extracting", False)

            if detailed_state_raw and detailed_state_raw != self._previous_state_name:
                if detailed_state_raw.lower() == "idle" and self._has_active_preheat():
                    new_state = "Preheating"
                else:
                    new_state = _normalize_state_name(detailed_state_raw)
                if new_state != self._current_state:
                    _LOGGER.info("State transition: %s → %s", self._current_state, new_state)
                    self._state_before = (
                        _normalize_state_name(self._previous_state_name)
                        if self._previous_state_name is not None
                        else None
                    )
                    self._current_state = new_state
                self._previous_state_name = detailed_state_raw
            elif not detailed_state_raw and self._previous_state_name is not None:
                fallback = coarse_state.capitalize()
                if fallback != self._current_state:
                    self._current_state = fallback
                self._previous_state_name = fallback

            # Extract sensor data
            sensors = status.get("sensors", {})
            if isinstance(sensors, dict):
                pressure = sensors.get("p", 0)
                flow = sensors.get("f", 0)
                weight = sensors.get("w", 0)
            else:
                pressure = getattr(sensors, "p", 0)
                flow = getattr(sensors, "f", 0)
                weight = getattr(sensors, "w", 0)

            try:
                self._pressure = float(pressure or 0)
            except (TypeError, ValueError):
                pass

            brewing = coarse_state != "idle" and is_extracting

            # Shot timer with stale value handling
            shot_timer_ms = status.get("profile_time")
            shot_timer = shot_timer_ms / 1000.0 if shot_timer_ms else 0

            is_now_idle = self._current_state == "Idle"
            if is_now_idle:
                if shot_timer > 0:
                    self._stale_shot_timer_value = shot_timer
                shot_timer = 0.0
                self._last_values.pop("shot_timer", None)
            elif self._stale_shot_timer_value is not None:
                if shot_timer == self._stale_shot_timer_value:
                    shot_timer = self._last_shot_timer_value
                else:
                    self._stale_shot_timer_value = None

            # Trigger statistics update when shot finishes
            if self._was_in_idle is False and is_now_idle:
                self.hass.loop.call_soon_threadsafe(
                    self.hass.async_create_task,
                    self._async_refresh_statistics(),
                )

            self._was_in_idle = is_now_idle
            self._last_shot_timer_value = shot_timer

            updates: dict[str, Any] = {
                "state": self._current_state,
                "brewing": brewing,
                "shot_timer": shot_timer,
                "pressure": pressure,
                "flow_rate": flow,
                "shot_weight": weight,
            }

            # Add setpoints if available
            setpoints = status.get("setpoints")
            if setpoints:
                sp = setpoints if isinstance(setpoints, dict) else vars(setpoints)
                if "temperature" in sp:
                    updates["target_temperature"] = sp["temperature"]
                if "pressure" in sp:
                    updates["target_pressure"] = sp["pressure"]
                if "flow" in sp:
                    updates["target_flow"] = sp["flow"]

            self._update_data(updates)

        except Exception as err:
            _LOGGER.error("Error handling status event: %s", err, exc_info=True)

    def _handle_temperature_event(self, temps: dict) -> None:
        """Handle real-time temperature updates from Socket.IO."""
        try:
            self._track_motor(temps)
        except Exception as err:  # never let effort tracking break temperatures
            _LOGGER.debug("Motor tracking error: %s", err)
        try:
            if isinstance(temps, dict):
                temp_data = {
                    "boiler_temperature": temps.get("t_bar_up"),
                    "brew_head_temperature": temps.get("t_bar_down"),
                    "external_temp_1": temps.get("t_ext_1"),
                    "external_temp_2": temps.get("t_ext_2"),
                    "piston_position": temps.get("m_pos"),
                }
            else:
                temp_data = {
                    "boiler_temperature": getattr(temps, "t_bar_up", None),
                    "brew_head_temperature": getattr(temps, "t_bar_down", None),
                    "external_temp_1": getattr(temps, "t_ext_1", None),
                    "external_temp_2": getattr(temps, "t_ext_2", None),
                    "piston_position": getattr(temps, "m_pos", None),
                }

            self._update_data(temp_data)

        except Exception as err:
            _LOGGER.error("Error handling temperature event: %s", err, exc_info=True)

    # ─── Piston motor effort tracking ──────────────────────────────────────
    # Runs on the existing "sensors" Socket.IO stream (same callback as the
    # temperatures). Samples are only buffered during a raise / retract / lower
    # and summarised once when the move ends; nothing is published per sample.

    def _motor_kind(self) -> str | None:
        cur, before = self._current_state, self._state_before
        if cur == "Home" and before == "Idle":
            return "raise"
        if cur == "Retracting" and before == "Click to Start":
            return "retract"
        if cur == "Purge" and before == "Idle":
            return "lower"
        return None

    def _track_motor(self, s: Any) -> None:
        get = s.get if isinstance(s, dict) else (lambda k, d=None: getattr(s, k, d))
        self._track_after_shot(get)
        kind = self._motor_kind()
        ep = self._motor_episode
        if ep is not None and ep["kind"] != kind:
            self._finish_motor_episode(ep)
            ep = self._motor_episode = None
        if kind is None:
            return
        if ep is None:
            ep = self._motor_episode = {
                "kind": kind, "samples": [],
                "boiler": self.data.get("boiler_temperature"),
            }
        try:
            sample = (
                time.monotonic(),
                float(get("m_pos", 0) or 0),
                float(get("m_spd", 0) or 0),
                float(get("m_pwr", 0) or 0),
                float(get("m_cur", 0) or 0),
                float(get("t_motor_temp", 0) or 0),
            )
        except (TypeError, ValueError):
            return
        ep["samples"].append(sample)

    # ─── After-shot retract (one friction value per shot, see after_shot.py) ──

    def _track_after_shot(self, get: Any) -> None:
        after = (
            self._current_state == "Retracting"
            and self._state_before not in PRE_SHOT_STATES
        )
        if not after:
            if self._after_shot is not None:
                samples, self._after_shot = self._after_shot, None
                result = summarise(samples)
                if result is not None:
                    current, speed = result
                    _LOGGER.info("After-shot retract: %.3f A at %.2f mm/s", current, speed)
                    for key, value in (("after_shot_current", current), ("after_shot_speed", speed)):
                        self.data[key] = value
                        self._last_values[key] = value
                    self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, dict(self.data))
            return
        if self._after_shot is None:
            self._after_shot = []
        try:
            self._after_shot.append(
                (
                    float(get("m_pos", 0) or 0),
                    float(get("m_spd", 0) or 0),
                    float(get("m_pwr", 0) or 0),
                    float(get("m_cur", 0) or 0),
                    self._pressure,
                )
            )
        except (TypeError, ValueError):
            return

    def _finish_motor_episode(self, ep: dict[str, Any]) -> None:
        samples = ep["samples"]
        moving = [x for x in samples if abs(x[2]) > PISTON_MOVING_SPEED]
        if len(moving) < PISTON_MIN_SAMPLES:
            return
        kind = ep["kind"]
        pw = [abs(x[3]) for x in moving]
        cu = [abs(x[4]) for x in moving]
        updates = {
            f"{kind}_avg_power": round(sum(pw) / len(pw), 2),
            f"{kind}_peak_power": round(max(pw), 2),
            f"{kind}_avg_current": round(sum(cu) / len(cu), 3),
            f"{kind}_duration": round(moving[-1][0] - moving[0][0], 2),
            f"{kind}_travel": round(abs(moving[-1][1] - moving[0][1]), 1),
            f"{kind}_motor_temp": round(sum(x[5] for x in moving) / len(moving), 1),
        }
        if kind == "raise" and ep.get("boiler") is not None:
            updates["raise_boiler_temp"] = round(float(ep["boiler"]), 1)
        _LOGGER.info("Piston %s summary: %s", kind, updates)
        for k, v in updates.items():
            self.data[k] = v
            self._last_values[k] = v
        self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, dict(self.data))

    def _handle_profile_event(self, profile_event: Any) -> None:
        """Handle profile change events from Socket.IO."""
        self.hass.loop.call_soon_threadsafe(
            self.hass.async_create_task,
            self._async_refresh_profiles(),
        )

    def _handle_profile_hover_event(self, data: Any) -> None:
        """Handle profileHover events — machine UI or client focused a profile."""
        try:
            if isinstance(data, dict):
                profile_id = data.get("id")
            else:
                profile_id = getattr(data, "id", None)

            if profile_id and profile_id in self.available_profiles:
                profile_name = self.available_profiles[profile_id]
                self._update_data({"active_profile": profile_name})
                _LOGGER.debug("Profile hover: %s → %s", profile_id, profile_name)
        except Exception as err:
            _LOGGER.error("Error handling profile hover: %s", err)

    def _handle_notification_event(self, notification: dict) -> None:
        """Handle notification events from Socket.IO."""
        _LOGGER.debug("Notification: %s", notification)

    def _handle_button_event(self, button: Any) -> None:
        """Handle button events from Socket.IO."""
        _LOGGER.debug("Button event: %s", button)

    def _handle_settings_change_event(self, settings: dict) -> None:
        """Handle settings change events from Socket.IO."""
        updates = {k: v for k, v in settings.items() if k != "brightness"}
        if updates:
            self._update_data(updates)

    def _handle_heater_status_event(self, preheat_countdown: float) -> None:
        """Handle heater status events — preheat countdown."""
        try:
            import time

            self._preheat_countdown = preheat_countdown
            self._last_preheat_time = time.monotonic()
            self._update_data({"preheat_countdown": preheat_countdown})
        except Exception as err:
            _LOGGER.error("Error handling heater status: %s", err)

    def _has_active_preheat(self) -> bool:
        """Check if preheat is currently active."""
        import time

        if self._preheat_countdown <= 0:
            return False
        elapsed = time.monotonic() - self._last_preheat_time
        return elapsed < (self._preheat_countdown + 30)

    # ─── Async methods (run in HA event loop) ──────────────────────────────

    async def _async_refresh_statistics(self) -> None:
        """Refresh statistics after a shot completes."""
        if not self._api:
            return

        try:
            api = self._api

            stats = await self.hass.async_add_executor_job(api.get_history_statistics)
            if not isinstance(stats, APIError):
                self.data["total_shots"] = stats.totalSavedShots

            last_shot = await self.hass.async_add_executor_job(api.get_last_shot)
            if last_shot and not isinstance(last_shot, APIError):
                self.data["last_shot_name"] = getattr(last_shot, "name", None)
                self.data["last_shot_rating"] = getattr(last_shot, "rating", None) or "none"
                shot_ts = getattr(last_shot, "time", None)
                if shot_ts is not None:
                    try:
                        self.data["last_shot_time"] = (
                            datetime.fromtimestamp(shot_ts).astimezone().isoformat()
                        )
                    except (ValueError, OSError, TypeError):
                        pass

            self.async_set_updated_data(dict(self.data))

        except Exception as err:
            _LOGGER.error("Error refreshing statistics: %s", err)

    async def _async_refresh_profiles(self) -> None:
        """Refresh profile list and current profile info."""
        if not self._api:
            return

        try:
            api = self._api

            profiles = await self.hass.async_add_executor_job(api.list_profiles)
            if profiles and not isinstance(profiles, APIError):
                self.available_profiles = {}
                self.profile_images = {}
                for p in profiles:
                    pid = getattr(p, "id", None) or getattr(p, "name", "")
                    name = getattr(p, "name", "Unknown")
                    if pid:
                        self.available_profiles[pid] = name
                        image = getattr(getattr(p, "display", None), "image", None)
                        if image:
                            self.profile_images[pid] = image

            # Also update profile info
            last_profile = await self.hass.async_add_executor_job(api.get_last_profile)
            if last_profile and not isinstance(last_profile, APIError):
                profile = getattr(last_profile, "profile", None)
                if profile:
                    updates: dict[str, Any] = {}
                    author = getattr(profile, "author", None)
                    if author:
                        updates["profile_author"] = author
                    target_temp = getattr(profile, "temperature", None)
                    if target_temp:
                        updates["target_temperature"] = target_temp
                    target_weight = getattr(profile, "final_weight", None)
                    if target_weight:
                        updates["target_weight"] = target_weight
                    if updates:
                        self.data.update(updates)

            self.async_set_updated_data(dict(self.data))

        except Exception as err:
            _LOGGER.error("Error refreshing profiles: %s", err)

    # ─── Action execution ──────────────────────────────────────────────────

    async def async_execute_action(self, action: ActionType) -> bool:
        """Execute a machine action (runs in executor)."""
        if not self._api:
            _LOGGER.error("Cannot execute action: API not connected")
            return False

        try:
            api = self._api
            result = await self.hass.async_add_executor_job(api.execute_action, action)
            if isinstance(result, APIError):
                _LOGGER.error("Action %s failed: %s", action.name, result.error)
                return False
            if result.status != "ok":
                _LOGGER.error("Action %s returned status: %s", action.name, result.status)
                return False
            _LOGGER.info("Action %s: Success", action.name)
            return True
        except Exception as err:
            _LOGGER.error("Error executing action %s: %s", action.name, err)
            return False

    async def async_set_brightness(self, brightness: int) -> bool:
        """Set machine brightness (0-100)."""
        if not self._api:
            return False

        try:
            api = self._api

            def _set() -> Any:
                return api.set_brightness(BrightnessRequest(brightness=brightness))

            result = await self.hass.async_add_executor_job(_set)
            if isinstance(result, APIError):
                _LOGGER.error("Set brightness failed: %s", result.error)
                return False
            self.data["brightness"] = brightness
            self.async_set_updated_data(dict(self.data))
            return True
        except Exception as err:
            _LOGGER.error("Error setting brightness: %s", err)
            return False

    async def async_set_sounds(self, enabled: bool) -> bool:
        """Enable or disable machine sounds."""
        if not self._api:
            return False

        try:
            api = self._api

            def _set() -> Any:
                return api.update_setting(
                    PartialSettings(enable_sounds=enabled)
                )

            result = await self.hass.async_add_executor_job(_set)
            if isinstance(result, APIError):
                _LOGGER.error("Set sounds failed: %s", result.error)
                return False
            self.data["sounds_enabled"] = enabled
            self.async_set_updated_data(dict(self.data))
            return True
        except Exception as err:
            _LOGGER.error("Error setting sounds: %s", err)
            return False

    async def async_select_profile(self, profile_id: str) -> bool:
        """Select a profile on the machine."""
        if not self._api:
            return False

        try:
            api = self._api

            def _set() -> Any:
                return api.load_profile_by_id(profile_id)

            result = await self.hass.async_add_executor_job(_set)
            if isinstance(result, APIError):
                _LOGGER.error("Select profile failed: %s", result.error)
                return False

            if profile_id in self.available_profiles:
                self.data["active_profile"] = self.available_profiles[profile_id]
                self.async_set_updated_data(dict(self.data))
            return True
        except Exception as err:
            _LOGGER.error("Error selecting profile: %s", err)
            return False


class MeticulousPollingCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator for slow-changing data via REST API polling.

    Refreshes profiles, statistics, and settings periodically.
    """

    def __init__(
        self, hass: HomeAssistant, push_coordinator: MeticulousPushCoordinator
    ) -> None:
        """Initialize the polling coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_poll",
            update_interval=timedelta(seconds=SLOW_POLL_INTERVAL),
        )
        self._push = push_coordinator

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch slow-changing data from REST API."""
        api = self._push.api
        if not api:
            return {}

        data: dict[str, Any] = {}

        try:
            # Refresh profiles
            await self._push._async_refresh_profiles()

            # Refresh statistics
            stats = await self.hass.async_add_executor_job(api.get_history_statistics)
            if not isinstance(stats, APIError):
                self._push.data["total_shots"] = stats.totalSavedShots
                data["total_shots"] = stats.totalSavedShots

            # Refresh settings
            settings = await self.hass.async_add_executor_job(api.get_settings)
            if settings and not isinstance(settings, APIError):
                if hasattr(settings, "enable_sounds"):
                    self._push.data["sounds_enabled"] = settings.enable_sounds
                if hasattr(settings, "brightness"):
                    self._push.data["brightness"] = settings.brightness

            # Push updates to push coordinator's listeners too
            self._push.async_set_updated_data(dict(self._push.data))

        except Exception as err:
            _LOGGER.warning("Error during periodic refresh: %s", err)

        return data

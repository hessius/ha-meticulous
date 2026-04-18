# Copilot Instructions — ha-meticulous

## Project Overview

Native Home Assistant custom integration for the Meticulous Espresso Machine. Connects directly via Socket.IO (real-time telemetry) and REST API (device info, profiles, settings) — no MQTT broker or Docker addon needed. HACS-compatible.

**Dependency**: `pyMeticulous>=0.3.1` — a **synchronous** Python library. All calls must be wrapped with `hass.async_add_executor_job()` and Socket.IO callbacks marshalled back via `hass.loop.call_soon_threadsafe()`.

## Architecture

### Dual Coordinator Pattern

Two coordinators serve different update patterns — do not merge them:

- **`MeticulousPushCoordinator`** — No `update_interval`. Receives real-time Socket.IO events (status, temperature, profile, settings) in an executor thread. Calls `async_set_updated_data()` to push to HA. Owns the `Api` instance, connection lifecycle, and reconnection logic.
- **`MeticulousPollingCoordinator`** — `update_interval=60s`. Periodically refreshes slow-changing data (profiles, statistics, settings) via REST. Delegates to the push coordinator's API client.

This separation prevents high-frequency Socket.IO events from starving periodic REST refreshes.

### Entity Structure

All entities inherit from `MeticulousEntity` (in `entity.py`), which provides shared `device_info`, `unique_id` (`meticulous_{serial}_{key}`), `has_entity_name=True`, and availability based on coordinator connection state. New entities must extend this base class.

### Key Files

- **`const.py`** — Sensor/button/binary sensor descriptions as frozen dataclasses. Add new entities here first.
- **`coordinator.py`** — Core logic: Socket.IO event handlers, delta filtering, connection lifecycle, API action wrappers.
- **`config_flow.py`** — Zeroconf auto-discovery + manual IP entry. Uses `_abort_if_unique_id_configured(updates={CONF_HOST: host})` to handle DHCP IP changes.

## Conventions

### pyMeticulous API (synchronous — always wrap)

```python
# ✅ Correct — run blocking call in executor
result = await self.hass.async_add_executor_job(api.get_device_info)

# ✅ Correct — marshal Socket.IO callback to HA event loop
self.hass.loop.call_soon_threadsafe(self.async_set_updated_data, dict(self.data))

# ❌ Wrong — blocks the HA event loop
result = api.get_device_info()
```

### Key API method names (not always obvious)

- `api.list_profiles()` — not `get_profiles()`
- `api.load_profile_by_id(id)` — not `select_profile()`
- `api.update_setting(PartialSettings(...))` — not `update_settings()`
- `ApiOptions` is in `meticulous.api`, not `meticulous.api_types`

### Delta Filtering

Numeric sensors use delta thresholds (defined in `SENSOR_DELTAS`) to prevent excessive state updates during brewing. String/boolean sensors use exact-match filtering (`EXACT_MATCH_SENSORS`). When adding a new sensor, register it in the appropriate set in `const.py`.

### Entity Categories

- **Primary**: User-facing data (temps, pressure, flow, weight, profile name, state)
- **Diagnostic** (`EntityCategory.DIAGNOSTIC`): firmware, voltage, total shots — set `enabled_default=False` for noisy ones
- **Config** (`EntityCategory.CONFIG`): sounds, brightness

### Availability

Use HA's built-in entity availability (driven by `coordinator.connected`). Do **not** create binary sensors for connectivity state.

## Adding a New Entity

1. Add a description dataclass to `const.py` (e.g., `MeticulousSensorDescription`)
2. Add it to the corresponding `*_DESCRIPTIONS` list in `const.py`
3. If it needs delta filtering, add to `SENSOR_DELTAS` or `EXACT_MATCH_SENSORS`
4. If it comes from Socket.IO, add handling in the relevant `_handle_*_event` method in `coordinator.py`
5. Initialize its default value in `MeticulousPushCoordinator.data`

# Meticulous Espresso - Home Assistant Integration

[![hacs_badge](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![GitHub Release](https://img.shields.io/github/v/release/hessius/ha-meticulous)](https://github.com/hessius/ha-meticulous/releases)

Native Home Assistant integration for the [Meticulous Espresso Machine](https://www.meticuloushome.com/), adapted from [Nick Wilson's meticulous-addon](https://github.com/nickwilsonr/meticulous-addon). This project rewrites the original MQTT-based addon as a native HA integration — auto-discovery via Zeroconf, direct Socket.IO connection, no MQTT broker or Docker addon required.

> **Based on [meticulous-addon](https://github.com/nickwilsonr/meticulous-addon) by [@nickwilsonr](https://github.com/nickwilsonr)** — the sensor definitions, protocol handling, delta filtering, and command mappings in this integration are derived from Nick's work on the original Home Assistant addon.

## ✨ Features

- **Auto-discovery** via Zeroconf/mDNS — machine appears automatically in HA
- **Real-time push** via Socket.IO — instant temperature, pressure, flow, and weight updates
- **Full machine control** — start/stop shots, preheat, tare, purge, profile selection
- **20+ sensors** — temperatures, brewing data, statistics, device info
- **Zero configuration** — just power on the machine and accept in HA

## 📊 Entities

### Sensors
| Entity | Description | Device Class |
|--------|-------------|-------------|
| Boiler Temperature | Boiler temp (°C) | temperature |
| Brew Head Temperature | Group head temp (°C) | temperature |
| External Temperature 1/2 | External probes (°C) | temperature |
| Target Temperature | Profile target temp (°C) | temperature |
| Pressure | Brewing pressure (bar) | pressure |
| Flow Rate | Water flow (mL/s) | — |
| Shot Weight | Scale reading (g) | weight |
| Shot Timer | Elapsed shot time (s) | duration |
| Target Weight | Profile target weight (g) | weight |
| State | Machine state (Idle, Preheating, Brewing, etc.) | — |
| Preheat Countdown | Preheat time remaining (s) | duration |
| Active Profile | Currently loaded profile name | — |
| Profile Author | Profile creator | — |
| Total Shots | Lifetime shot count | — |
| Last Shot | Name of the last shot | — |
| Last Shot Rating | Rating of the last shot | — |
| Last Shot Time | Timestamp of the last shot | timestamp |
| Firmware Version | Machine firmware | — |
| Software Version | Machine software | — |
| Voltage | Supply voltage (V) | voltage |

### Binary Sensors
| Entity | Description | Device Class |
|--------|-------------|-------------|
| Brewing | Whether a shot is currently being pulled | running |

### Controls
| Entity | Type | Description |
|--------|------|-------------|
| Start Shot | Button | Begin extraction |
| Stop Shot | Button | Stop extraction (normal end) |
| Continue Shot | Button | Resume paused shot |
| Abort Shot | Button | Cancel shot immediately |
| Preheat | Button | Start preheat cycle |
| Tare Scale | Button | Zero the built-in scale |
| Home Plunger | Button | Return plunger to home position |
| Purge | Button | Run water purge cycle |
| Sounds | Switch | Enable/disable machine sounds |
| Brightness | Number | Machine display brightness (0-100%) |
| Active Profile | Select | Choose from available profiles |

### Other
| Entity | Type | Description |
|--------|------|-------------|
| Profile Image | Image | Image of the active profile |

## 🚀 Installation

### HACS (Recommended)

1. Open HACS in Home Assistant
2. Click the three dots menu → **Custom repositories**
3. Add `https://github.com/hessius/ha-meticulous` as an **Integration**
4. Search for "Meticulous Espresso" and install
5. Restart Home Assistant

### Manual

1. Copy the `custom_components/meticulous_espresso` folder to your HA `config/custom_components/` directory
2. Restart Home Assistant

## ⚙️ Setup

### Automatic (Zeroconf)
Your Meticulous machine broadcasts `_meticulous._tcp.local.` on the network. Home Assistant will automatically discover it and prompt you to set it up — just click **Configure**.

### Manual
1. Go to **Settings** → **Devices & Services** → **Add Integration**
2. Search for "Meticulous Espresso"
3. Enter your machine's IP address (e.g., `192.168.1.100` or `meticulous.local`)

## 🏠 Example Automations

### Morning warm-up
```yaml
automation:
  - alias: "Preheat espresso machine"
    trigger:
      - platform: time
        at: "06:30:00"
    action:
      - service: button.press
        target:
          entity_id: button.meticulous_espresso_preheat
```

### Notify when shot is done
```yaml
automation:
  - alias: "Espresso shot notification"
    trigger:
      - platform: state
        entity_id: binary_sensor.meticulous_espresso_brewing
        from: "on"
        to: "off"
    action:
      - service: notify.mobile_app
        data:
          title: "☕ Espresso Ready!"
          message: "Your shot finished — {{ states('sensor.meticulous_espresso_shot_weight') }}g in {{ states('sensor.meticulous_espresso_shot_timer') }}s"
```

### Temperature dashboard card
```yaml
type: sensor
entity: sensor.meticulous_espresso_boiler_temperature
name: Boiler
icon: mdi:thermometer
graph: line
hours_to_show: 4
```

## 🔧 Architecture

This integration connects directly to the Meticulous machine via its local API:

```
Meticulous Machine (port 8080)
    ├── REST API → Device info, profiles, statistics, settings
    └── Socket.IO → Real-time telemetry (temperatures, pressure, flow, weight, state)
         │
    HA Integration
    ├── Push Coordinator → Real-time sensor updates (no polling)
    └── Polling Coordinator → Profiles, statistics (every 60s)
         │
    Home Assistant Entity Registry
    └── 30+ entities across 7 platforms
```

## 🤝 Credits

- **[pyMeticulous](https://pypi.org/project/pyMeticulous/)** — Python API client for Meticulous machines
- **[meticulous-addon](https://github.com/nickwilsonr/meticulous-addon)** — The original HA addon by Nick Wilson, which inspired this native integration's sensor definitions and protocol handling

## 📝 License

MIT License — see [LICENSE](LICENSE) for details.

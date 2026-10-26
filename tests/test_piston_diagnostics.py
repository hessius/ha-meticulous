"""Exercise motor tracking through the real coordinator's event handlers."""

import asyncio
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import IsolatedAsyncioTestCase
from unittest.mock import AsyncMock, Mock, patch

from homeassistant.core import HomeAssistant

from custom_components.meticulous_espresso.coordinator import MeticulousPushCoordinator


class TestPistonDiagnostics(IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.hass = HomeAssistant(self.directory.name)
        self.coordinator = MeticulousPushCoordinator(self.hass, "machine.local", "test")
        self.coordinator._async_refresh_statistics = AsyncMock()

    async def asyncTearDown(self):
        await asyncio.sleep(0)
        await asyncio.sleep(0)

    def status(self, name=None, *, coarse="idle", pressure=0.0):
        sensors = {} if pressure is None else {"p": pressure}
        status = {"state": coarse, "sensors": sensors}
        if name is not None:
            status["name"] = name
        self.coordinator._handle_status_event(status)

    def samples(self, start=0, current=1.0, count=5):
        for offset in range(count):
            clock = SimpleNamespace(monotonic=lambda: start + offset)
            with patch("custom_components.meticulous_espresso.coordinator.time", clock):
                self.coordinator._track_motor({
                    "m_pos": 50.0 - offset,
                    "m_spd": -10.0,
                    "m_pwr": -100.0,
                    "m_cur": current,
                    "t_motor_temp": 30.0,
                })

    async def test_named_transition_finalises_motor_without_sensor_packet(self):
        self.status("Idle")
        self.status("Home")
        self.samples()
        self.status("Idle")
        assert self.coordinator.data["raise_avg_current"] == 1.0
        assert self.coordinator._motor_episode is None

    async def test_fallback_transition_finalises_motor(self):
        self.status("Idle")
        self.status("Purge")
        self.samples()
        self.status(coarse="idle")
        assert self.coordinator.data["lower_avg_current"] == 1.0
        assert self.coordinator._motor_episode is None

    async def test_repeated_moves_do_not_include_idle_gap(self):
        self.status("Idle")
        self.status("Purge")
        self.samples()
        self.status("Idle")
        self.status("Purge")
        self.samples(start=60, current=3.0)
        self.status("Idle")
        self.coordinator._track_motor({})
        assert self.coordinator.data["lower_duration"] == 4.0
        assert self.coordinator.data["lower_avg_current"] == 3.0

    async def test_after_shot_finalises_on_status_transition(self):
        self.status("Extraction")
        self.status("Retracting")
        self.samples()
        self.status("Idle")
        assert self.coordinator.data["after_shot_current"] == 1.0
        assert self.coordinator._after_shot is None

    async def test_after_shot_fallback_transition_finalises(self):
        self.status("Extraction")
        self.status("Retracting")
        self.samples()
        self.status(coarse="idle")
        assert self.coordinator.data["after_shot_current"] == 1.0

    async def test_repeated_after_shot_retractions_stay_separate(self):
        for start, current in [(0, 1.0), (60, 3.0)]:
            self.status("Extraction")
            self.status("Retracting")
            self.samples(start=start, current=current)
            self.status("Idle")
        self.coordinator._track_motor({})
        assert self.coordinator.data["after_shot_current"] == 3.0

    async def test_duplicate_status_does_not_split_move(self):
        self.status("Idle")
        self.status("Home")
        self.samples(count=3)
        self.status("Home")
        self.samples(start=3, count=2)
        self.status("Idle")
        self.coordinator._track_motor({})
        assert self.coordinator.data["raise_duration"] == 4.0

    async def test_pre_shot_retraction_does_not_publish_after_shot_values(self):
        self.status("Click to Start")
        self.status("Retracting")
        self.samples()
        self.status("Extraction")
        assert self.coordinator.data["after_shot_current"] is None

    async def test_connecting_mid_move_does_not_publish_partial_summary(self):
        self.status("Home")
        self.samples()
        self.status("Idle")
        assert self.coordinator.data["raise_avg_current"] is None

    async def test_preheating_uses_observed_idle_as_previous_state(self):
        self.coordinator._preheat_countdown = 60
        with patch.object(self.coordinator, "_has_active_preheat", return_value=True):
            self.status("Idle")
        self.status("Home")
        self.samples()
        self.status("Idle")
        self.coordinator._track_motor({})
        assert self.coordinator.data["raise_avg_current"] == 1.0

    async def test_invalid_boiler_temperature_does_not_block_status_transition(self):
        self.coordinator.data["boiler_temperature"] = "invalid"
        self.status("Idle")
        self.status("Home")
        self.samples()
        self.status("Idle")
        assert self.coordinator.data["state"] == "Idle"
        assert self.coordinator.data["raise_avg_current"] == 1.0
        assert self.coordinator.data["raise_boiler_temp"] is None

    async def test_missing_pressure_does_not_publish_after_shot_values(self):
        self.status("Extraction")
        self.status("Retracting", pressure=None)
        self.samples()
        self.status("Idle")
        self.coordinator._track_motor({})
        assert self.coordinator.data["after_shot_current"] is None

    async def test_invalid_pressure_does_not_reuse_old_pressure(self):
        self.status("Extraction")
        self.status("Retracting")
        self.status("Retracting", pressure="invalid")
        self.samples()
        self.status("Idle")
        self.coordinator._track_motor({})
        assert self.coordinator.data["after_shot_current"] is None

    async def test_shutdown_discards_incomplete_moves(self):
        self.status("Idle")
        self.status("Home")
        self.samples()
        await self.coordinator.async_shutdown()
        self.status("Idle")
        self.coordinator._track_motor({})
        assert self.coordinator.data["raise_avg_current"] is None
        assert self.coordinator._previous_state_name == "Idle"

    async def test_socket_disconnect_discards_incomplete_after_shot(self):
        sio = Mock()
        api = SimpleNamespace(
            sio=sio, connect_to_socket=Mock(),
            get_device_info=Mock(return_value=SimpleNamespace()),
        )
        with (
            patch(
                "custom_components.meticulous_espresso.coordinator.discover_api",
                return_value=(80, {}),
            ),
            patch("custom_components.meticulous_espresso.coordinator.Api", return_value=api),
        ):
            assert await self.coordinator._connect_api()
        await self.coordinator._start_socket_listener()
        self.status("Extraction")
        self.status("Retracting")
        self.samples()
        handlers = dict(call.args for call in sio.on.call_args_list)
        assert "disconnect" in handlers
        handlers["disconnect"]("transport close")
        assert self.coordinator._after_shot is None
        assert self.coordinator._previous_state_name is None
        self.status("Idle")
        self.coordinator._track_motor({})
        assert self.coordinator.data["after_shot_current"] is None

    async def test_rebuilt_api_client_registers_disconnect_cleanup(self):
        sio = Mock()
        api = SimpleNamespace(sio=sio, get_device_info=Mock(return_value=SimpleNamespace()))
        with (
            patch(
                "custom_components.meticulous_espresso.coordinator.discover_api",
                return_value=(80, {}),
            ),
            patch("custom_components.meticulous_espresso.coordinator.Api", return_value=api),
        ):
            assert await self.coordinator._connect_api()
        assert "disconnect" in dict(call.args for call in sio.on.call_args_list)

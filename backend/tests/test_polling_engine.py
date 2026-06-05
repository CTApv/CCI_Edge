import unittest
from unittest.mock import patch

from app.schemas.device_overview_schemas import (
    DeviceOverviewDiagnostics,
    DeviceOverviewMetrics,
    DeviceTelemetryPoint,
)
from app.schemas.device_schemas import DeviceResponse
from app.services.endpoint_runtime_service import EndpointRuntimeService
from app.services.connection_manager import connection_manager
from app.services.live_cache import ConnectionLifecycle, LiveCacheEntry
from app.services.polling_engine import (
    POLLING_ENGINE_BUSY_WAIT_SECONDS,
    POLLING_ENGINE_IDLE_WAIT_SECONDS,
    SERIAL_FAST_HEARTBEAT_INTERVAL_SECONDS,
    SERIAL_INITIAL_FULL_POLL_FALLBACK_SECONDS,
    PollingEngine,
    _NO_DUE_AT,
    _merge_poll_entry,
)


def _build_device(
    *,
    device_id: str,
    name: str,
    protocol: str = "modbus_tcp",
    transport: str = "tcp",
) -> DeviceResponse:
    connection_settings = (
        {
            "port": "COM3",
            "slave_id": 1,
            "baud_rate": 9600,
            "parity": "N",
            "stop_bits": 1,
            "byte_size": 8,
            "timeout_seconds": 3.0,
            "retries": 0,
            "poll_interval_seconds": 15.0,
        }
        if transport == "serial"
        else {
            "host": "192.168.1.10",
            "port": 502,
            "unit_id": 1,
            "timeout_seconds": 3.0,
            "retries": 0,
        }
    )
    return DeviceResponse(
        device_id=device_id,
        name=name,
        brand="Huawei",
        model="SUN2000",
        protocol=protocol,
        transport=transport,
        connection_settings=connection_settings,
        profile_overrides={},
        status="offline",
        created_at="2026-03-24T00:00:00+00:00",
    )


def _build_connect_failure_entry() -> LiveCacheEntry:
    return LiveCacheEntry(
        metrics=DeviceOverviewMetrics(
            power_kw=0.0,
            daily_energy_kwh=0.0,
            total_energy_kwh=0.0,
            temperature_c=25.0,
        ),
        diagnostics=DeviceOverviewDiagnostics(
            last_poll_status="stub_mode=false; stage=connect; protocol=modbus_tcp",
            response_time_ms=20,
            retries=0,
            last_error="Unable to connect to Modbus TCP device.",
            poll_kind="full",
        ),
        telemetry=[],
        timestamp="2026-03-24T10:00:00+00:00",
    )


def _build_success_entry() -> LiveCacheEntry:
    return LiveCacheEntry(
        metrics=DeviceOverviewMetrics(
            power_kw=123.4,
            daily_energy_kwh=10.0,
            total_energy_kwh=100.0,
            temperature_c=33.0,
        ),
        diagnostics=DeviceOverviewDiagnostics(
            last_poll_status="stub_mode=false; stage=read_register; protocol=modbus_tcp",
            response_time_ms=20,
            retries=0,
            last_error=None,
            poll_kind="full",
        ),
        telemetry=[
            DeviceTelemetryPoint(
                key="active_power_kw",
                label="Active power",
                value=123.4,
                raw_value=123.4,
                display_value="123.4",
                unit="kW",
                section="Power",
                visible=True,
                writable=False,
            )
        ],
        timestamp="2026-03-24T09:59:00+00:00",
    )


class PollingEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        connection_manager.close_all_tcp_connections()

    def test_run_keeps_polling_loop_alive_after_cycle_exception(self) -> None:
        engine = PollingEngine()
        calls: list[int] = []

        def fake_poll_devices() -> None:
            calls.append(len(calls) + 1)
            if len(calls) == 1:
                raise RuntimeError("boom")
            engine._stop_event.set()

        with patch.object(engine, "_poll_devices", side_effect=fake_poll_devices), patch.object(
            engine._stop_event,
            "wait",
            return_value=False,
        ):
            engine._run()

        snapshot = engine.get_runtime_snapshot()

        self.assertEqual(calls, [1, 2])
        self.assertEqual(snapshot["consecutive_loop_error_count"], 0)
        self.assertEqual(snapshot["last_loop_error"], "RuntimeError: boom")

    def test_ensure_running_restarts_dead_polling_thread_when_enabled(self) -> None:
        engine = PollingEngine()

        with patch("app.services.polling_engine.Thread") as thread_factory:
            with engine._lock:
                engine._should_run = True

            restarted = engine.ensure_running()

        self.assertTrue(restarted)
        thread_factory.assert_called_once_with(
            target=engine._run,
            name="pv-edge-polling",
            daemon=True,
        )
        thread_factory.return_value.start.assert_called_once()
        self.assertEqual(engine._thread_start_count, 1)

    def test_startup_priority_sweep_schedules_all_devices_immediately(self) -> None:
        engine = PollingEngine()
        first_device = _build_device(device_id="device-1", name="Alpha")
        second_device = _build_device(device_id="device-2", name="Beta")
        now = 123.456

        engine._seed_initial_schedule([first_device, second_device], now)

        self.assertEqual(engine._next_poll_at[first_device.device_id], now)
        self.assertEqual(engine._next_poll_at[second_device.device_id], now)
        self.assertFalse(engine._startup_priority_sweep_pending)

    def test_failed_poll_preserves_last_successful_values_in_cache(self) -> None:
        previous_entry = _build_success_entry()
        failure_entry = _build_connect_failure_entry()

        preserved_entry = _merge_poll_entry(previous_entry, failure_entry)

        self.assertEqual(preserved_entry.metrics.power_kw, 123.4)
        self.assertEqual(len(preserved_entry.telemetry), 1)
        self.assertEqual(preserved_entry.telemetry[0].key, "active_power_kw")
        self.assertEqual(
            preserved_entry.diagnostics.last_error,
            "Unable to connect to Modbus TCP device.",
        )
        self.assertEqual(preserved_entry.timestamp, failure_entry.timestamp)

    def test_serial_devices_start_with_heartbeat_due_and_bounded_full_poll_fallback(
        self,
    ) -> None:
        engine = PollingEngine()
        serial_device = _build_device(
            device_id="device-serial-1",
            name="Seriale",
            protocol="modbus_rtu",
            transport="serial",
        )
        now = 456.789

        engine._seed_initial_schedule([serial_device], now)

        self.assertEqual(engine._next_heartbeat_poll_at[serial_device.device_id], now)
        self.assertEqual(
            engine._next_poll_at[serial_device.device_id],
            now + SERIAL_INITIAL_FULL_POLL_FALLBACK_SECONDS,
        )

    def test_rtu_over_tcp_devices_use_serial_like_startup_schedule(self) -> None:
        engine = PollingEngine()
        gateway_device = _build_device(
            device_id="device-rtu-tcp-1",
            name="RTU over TCP",
            protocol="modbus_rtu",
            transport="tcp",
        )
        now = 789.123

        engine._seed_initial_schedule([gateway_device], now)

        self.assertEqual(engine._next_heartbeat_poll_at[gateway_device.device_id], now)
        self.assertEqual(
            engine._next_poll_at[gateway_device.device_id],
            now + SERIAL_INITIAL_FULL_POLL_FALLBACK_SECONDS,
        )
        self.assertFalse(engine._uses_shared_non_serial_endpoint(gateway_device))

    def test_serial_full_reads_rotate_across_devices_on_shared_endpoint(self) -> None:
        engine = PollingEngine()
        devices = [
            _build_device(
                device_id=f"device-serial-{index}",
                name=f"Seriale {index}",
                protocol="modbus_rtu",
                transport="serial",
            )
            for index in range(1, 5)
        ]
        for device in devices:
            engine._next_poll_at[device.device_id] = 0.0
            engine._next_heartbeat_poll_at[device.device_id] = _NO_DUE_AT

        first_operations = engine._build_serial_endpoint_operations(devices, current_time=0.0)
        second_operations = engine._build_serial_endpoint_operations(devices, current_time=0.0)

        self.assertEqual(
            [operation.device.device_id for operation in first_operations],
            ["device-serial-1", "device-serial-2"],
        )
        self.assertEqual(
            [operation.device.device_id for operation in second_operations],
            ["device-serial-3", "device-serial-4"],
        )
        self.assertTrue(all(operation.poll_kind == "full" for operation in first_operations))
        self.assertTrue(all(operation.poll_kind == "full" for operation in second_operations))

    def test_large_stable_serial_group_prioritizes_full_reads_over_heartbeats(self) -> None:
        engine = PollingEngine()
        devices = [
            _build_device(
                device_id=f"device-serial-{index}",
                name=f"Seriale {index}",
                protocol="modbus_rtu",
                transport="serial",
            )
            for index in range(1, 51)
        ]
        for index, device in enumerate(devices):
            engine._next_poll_at[device.device_id] = 0.0 if index < 10 else _NO_DUE_AT
            engine._next_heartbeat_poll_at[device.device_id] = 0.0

        stable_lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp="2026-04-09T15:40:00+00:00",
            last_attempt_timestamp="2026-04-09T15:40:00+00:00",
            has_seen_full_success=True,
            last_full_success_timestamp="2026-04-09T15:39:00+00:00",
        )

        with patch(
            "app.services.polling_engine.live_cache.get_connection_lifecycle",
            return_value=stable_lifecycle,
        ):
            operations = engine._build_serial_endpoint_operations(devices, current_time=0.0)

        full_operations = [operation for operation in operations if operation.poll_kind == "full"]
        heartbeat_operations = [
            operation for operation in operations if operation.poll_kind == "heartbeat"
        ]
        self.assertGreaterEqual(len(full_operations), 5)
        self.assertLessEqual(len(heartbeat_operations), 2)

    def test_medium_stable_serial_group_reads_more_full_devices_per_pass(self) -> None:
        engine = PollingEngine()
        devices = [
            _build_device(
                device_id=f"device-serial-{index}",
                name=f"Seriale {index}",
                protocol="modbus_rtu",
                transport="serial",
            )
            for index in range(1, 13)
        ]
        for device in devices:
            engine._next_poll_at[device.device_id] = 0.0
            engine._next_heartbeat_poll_at[device.device_id] = _NO_DUE_AT

        stable_lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp="2026-04-10T15:40:00+00:00",
            last_attempt_timestamp="2026-04-10T15:40:00+00:00",
            has_seen_full_success=True,
            last_full_success_timestamp="2026-04-10T15:39:00+00:00",
        )

        with patch(
            "app.services.polling_engine.live_cache.get_connection_lifecycle",
            return_value=stable_lifecycle,
        ):
            operations = engine._build_serial_endpoint_operations(devices, current_time=0.0)

        full_operations = [operation for operation in operations if operation.poll_kind == "full"]
        self.assertGreaterEqual(len(full_operations), 4)

    def test_serial_endpoint_due_group_is_paused_while_command_priority_is_pending(self) -> None:
        engine = PollingEngine()
        serial_device = _build_device(
            device_id="device-serial-1",
            name="Seriale",
            protocol="modbus_rtu",
            transport="serial",
        )
        now = 12.0
        engine._next_heartbeat_poll_at[serial_device.device_id] = now
        engine._next_poll_at[serial_device.device_id] = _NO_DUE_AT

        with patch(
            "app.services.polling_engine.connection_manager.is_modbus_rtu_priority_pending",
            return_value=True,
        ):
            groups = engine._group_due_serial_devices_by_endpoint([serial_device], now)

        self.assertEqual(groups, [])

    def test_rtu_over_tcp_due_group_is_paused_while_command_priority_is_pending(self) -> None:
        engine = PollingEngine()
        gateway_device = _build_device(
            device_id="device-rtu-tcp-1",
            name="RTU over TCP",
            protocol="modbus_rtu",
            transport="tcp",
        )
        gateway_device.connection_settings["host"] = "192.168.100.20"
        gateway_device.connection_settings["port"] = 4002
        now = 12.0
        engine._next_heartbeat_poll_at[gateway_device.device_id] = now
        engine._next_poll_at[gateway_device.device_id] = _NO_DUE_AT

        with patch(
            "app.services.polling_engine.connection_manager.is_modbus_rtu_priority_pending",
            return_value=True,
        ) as priority_mock:
            groups = engine._group_due_serial_devices_by_endpoint([gateway_device], now)

        self.assertEqual(groups, [])
        priority_mock.assert_called_once_with("tcp:192.168.100.20:4002")

    def test_modbus_tcp_due_work_is_paused_while_command_priority_is_pending(self) -> None:
        engine = PollingEngine()
        tcp_device = _build_device(device_id="device-tcp-1", name="TCP")
        now = 12.0
        engine._next_poll_at[tcp_device.device_id] = now

        with patch(
            "app.services.polling_engine.connection_manager.is_modbus_tcp_priority_pending",
            return_value=True,
        ) as priority_mock:
            has_due_work = engine._non_serial_device_has_due_work(tcp_device, now)

        self.assertFalse(has_due_work)
        priority_mock.assert_called_once_with("192.168.1.10", 502)

    def test_serial_heartbeat_interval_is_capped_for_fast_bus_rotation(self) -> None:
        engine = PollingEngine()
        serial_device = _build_device(
            device_id="device-serial-1",
            name="Seriale",
            protocol="modbus_rtu",
            transport="serial",
        )

        next_due_at = engine._resolve_next_heartbeat_due_at(
            device=serial_device,
            completed_at=10.0,
        )

        self.assertEqual(next_due_at, 10.0 + SERIAL_FAST_HEARTBEAT_INTERVAL_SECONDS)

    def test_rtu_over_tcp_light_poll_uses_active_power_slot(self) -> None:
        engine = PollingEngine()
        gateway_device = _build_device(
            device_id="device-rtu-tcp-1",
            name="RTU over TCP",
            protocol="modbus_rtu",
            transport="tcp",
        )
        engine._next_poll_at[gateway_device.device_id] = _NO_DUE_AT
        engine._next_heartbeat_poll_at[gateway_device.device_id] = 0.0

        operations = engine._build_serial_endpoint_operations(
            [gateway_device],
            current_time=0.0,
        )

        self.assertEqual(len(operations), 1)
        self.assertEqual(operations[0].poll_kind, "active_power")

    def test_active_power_poll_updates_live_history_without_persistent_write(self) -> None:
        engine = PollingEngine()
        gateway_device = _build_device(
            device_id="device-rtu-tcp-1",
            name="RTU over TCP",
            protocol="modbus_rtu",
            transport="tcp",
        )
        active_power_entry = LiveCacheEntry(
            metrics=DeviceOverviewMetrics(
                power_kw=42.5,
                daily_energy_kwh=10.0,
                total_energy_kwh=100.0,
                temperature_c=33.0,
            ),
            diagnostics=DeviceOverviewDiagnostics(
                last_poll_status="stub_mode=false; stage=read_register; protocol=modbus_rtu",
                response_time_ms=20,
                retries=0,
                last_error=None,
                poll_kind="active_power",
            ),
            telemetry=[],
            timestamp="2026-04-10T10:00:00+00:00",
        )

        with patch("app.services.polling_engine.live_cache.get", return_value=None), patch(
            "app.services.polling_engine.live_cache.set",
        ), patch(
            "app.services.polling_engine.live_cache.append_power_sample",
        ) as append_live_sample, patch(
            "app.services.polling_engine.power_history_service.append_sample",
        ) as append_persistent_sample:
            result = engine._store_polled_entry(gateway_device, active_power_entry)

        self.assertEqual(result, (1, 0, 0))
        append_live_sample.assert_called_once_with(
            device_id=gateway_device.device_id,
            timestamp="2026-04-10T10:00:00+00:00",
            power_kw=42.5,
        )
        append_persistent_sample.assert_not_called()

    def test_shared_endpoint_connect_failure_skips_remaining_devices(self) -> None:
        engine = PollingEngine()
        endpoint_runtime = EndpointRuntimeService()
        first_device = _build_device(device_id="device-1", name="Alpha")
        second_device = _build_device(device_id="device-2", name="Beta")
        polled_device_ids: list[str] = []

        def fake_poll_device(device: DeviceResponse, *, poll_kind: str = "full") -> LiveCacheEntry:
            polled_device_ids.append(device.device_id)
            return _build_connect_failure_entry()

        with patch("app.services.polling_engine.endpoint_runtime_service", endpoint_runtime), patch(
            "app.services.polling_engine.poll_device",
            side_effect=fake_poll_device,
        ):
            results = engine._poll_endpoint_group([first_device, second_device], current_time=0.0)

        self.assertEqual(polled_device_ids, ["device-1"])
        self.assertEqual(len(results), 2)
        self.assertIn("stage=connect", results[0].entry.diagnostics.last_poll_status)
        self.assertIn("stage=endpoint_backoff", results[1].entry.diagnostics.last_poll_status)
        self.assertIn("192.168.1.10:502", results[1].entry.diagnostics.last_error or "")

    def test_shared_tcp_endpoint_reads_rotate_across_devices_under_cycle_budget(self) -> None:
        engine = PollingEngine()
        devices = [
            _build_device(device_id=f"device-{index}", name=f"TCP {index}")
            for index in range(1, 5)
        ]
        success_entry = _build_success_entry()

        with patch(
            "app.services.polling_engine.poll_device_with_runtime",
            return_value=success_entry,
        ), patch.object(
            engine,
            "_shared_endpoint_cycle_budget_exhausted",
            side_effect=[False, True, False, True],
        ):
            first_results = engine._poll_endpoint_group(devices, current_time=0.0)
            second_results = engine._poll_endpoint_group(devices, current_time=0.0)

        self.assertEqual(
            [result.device.device_id for result in first_results],
            ["device-1", "device-2"],
        )
        self.assertEqual(
            [result.device.device_id for result in second_results],
            ["device-3", "device-4"],
        )

    def test_shared_tcp_gateway_prioritizes_active_power_and_limits_full_reads(self) -> None:
        engine = PollingEngine()
        devices = [
            _build_device(device_id=f"device-{index}", name=f"TCP {index}")
            for index in range(1, 5)
        ]
        for device in devices:
            engine._next_heartbeat_poll_at[device.device_id] = 0.0
            engine._next_poll_at[device.device_id] = 0.0

        operations = engine._build_shared_tcp_gateway_endpoint_operations(
            devices,
            current_time=0.0,
        )

        self.assertEqual(
            [operation.poll_kind for operation in operations],
            ["active_power", "active_power", "active_power", "full"],
        )
        self.assertEqual(
            [operation.device.device_id for operation in operations],
            ["device-2", "device-3", "device-4", "device-1"],
        )

    def test_slow_shared_tcp_gateway_dilutes_full_reads_between_active_power_cycles(self) -> None:
        engine = PollingEngine()
        devices = [
            _build_device(device_id=f"device-{index}", name=f"TCP {index}")
            for index in range(1, 5)
        ]
        for device in devices:
            engine._next_heartbeat_poll_at[device.device_id] = 0.0
            engine._next_poll_at[device.device_id] = 0.0

        with patch.object(engine, "_is_slow_shared_tcp_gateway", return_value=True):
            first_operations = engine._build_shared_tcp_gateway_endpoint_operations(
                devices,
                current_time=0.0,
            )
            second_operations = engine._build_shared_tcp_gateway_endpoint_operations(
                devices,
                current_time=1.0,
            )

        self.assertEqual(
            [operation.poll_kind for operation in first_operations].count("full"),
            1,
        )
        self.assertEqual(
            [operation.poll_kind for operation in second_operations].count("full"),
            0,
        )

    def test_shared_tcp_backlog_keeps_engine_in_busy_wait_mode(self) -> None:
        engine = PollingEngine()
        devices = [
            _build_device(device_id=f"device-{index}", name=f"TCP {index}")
            for index in range(1, 3)
        ]
        success_entry = _build_success_entry()

        with patch("app.services.polling_engine.device_service.list_devices", return_value=devices), patch(
            "app.services.polling_engine.live_cache.prune",
        ), patch(
            "app.services.polling_engine.endpoint_runtime_service.prune",
        ), patch(
            "app.services.polling_engine.poll_device_with_runtime",
            return_value=success_entry,
        ), patch(
            "app.services.polling_engine.live_cache.set",
        ), patch(
            "app.services.polling_engine.live_cache.append_power_sample",
        ), patch(
            "app.services.polling_engine.power_history_service.append_sample",
        ), patch.object(
            engine,
            "_shared_endpoint_cycle_budget_exhausted",
            return_value=True,
        ):
            engine._poll_devices()

        self.assertEqual(engine._next_loop_wait_seconds, POLLING_ENGINE_BUSY_WAIT_SECONDS)

    def test_serial_endpoint_snapshots_expose_scheduler_metrics(self) -> None:
        engine = PollingEngine()
        serial_device = _build_device(
            device_id="device-serial-1",
            name="Seriale",
            protocol="modbus_rtu",
            transport="serial",
        )
        for key in ("_next_poll_at", "_next_heartbeat_poll_at"):
            getattr(engine, key)[serial_device.device_id] = 0.0

        success_entry = LiveCacheEntry(
            metrics=DeviceOverviewMetrics(
                power_kw=50.0,
                daily_energy_kwh=1.0,
                total_energy_kwh=10.0,
                temperature_c=25.0,
            ),
            diagnostics=DeviceOverviewDiagnostics(
                last_poll_status="stub_mode=false; stage=read_register; protocol=modbus_rtu",
                response_time_ms=120,
                retries=0,
                last_error=None,
                poll_kind="full",
            ),
            telemetry=[],
            timestamp="2026-04-10T10:00:00+00:00",
        )

        with patch("app.services.polling_engine.poll_device_with_runtime", return_value=success_entry):
            engine._poll_serial_endpoint_group([serial_device], current_time=0.0)

        snapshots = engine.get_serial_endpoint_snapshots([serial_device])

        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["endpoint_label"], "COM3")
        self.assertGreaterEqual(snapshots[0]["planned_full_count"], 1)
        self.assertGreaterEqual(snapshots[0]["executed_full_count"], 1)
        self.assertIsNotNone(snapshots[0]["last_cycle_duration_ms"])

    def test_serial_backlog_keeps_engine_in_busy_wait_mode(self) -> None:
        engine = PollingEngine()
        serial_devices = [
            _build_device(
                device_id=f"device-serial-{index}",
                name=f"Seriale {index}",
                protocol="modbus_rtu",
                transport="serial",
            )
            for index in range(1, 13)
        ]
        success_entry = LiveCacheEntry(
            metrics=DeviceOverviewMetrics(
                power_kw=50.0,
                daily_energy_kwh=1.0,
                total_energy_kwh=10.0,
                temperature_c=25.0,
            ),
            diagnostics=DeviceOverviewDiagnostics(
                last_poll_status="stub_mode=false; stage=read_register; protocol=modbus_rtu",
                response_time_ms=20,
                retries=0,
                last_error=None,
                poll_kind="full",
            ),
            telemetry=[],
            timestamp="2026-04-10T10:00:00+00:00",
        )
        stable_lifecycle = ConnectionLifecycle(
            has_seen_success=True,
            last_success_timestamp="2026-04-10T15:40:00+00:00",
            last_attempt_timestamp="2026-04-10T15:40:00+00:00",
            has_seen_full_success=True,
            last_full_success_timestamp="2026-04-10T15:39:00+00:00",
        )

        with patch("app.services.polling_engine.device_service.list_devices", return_value=serial_devices), patch(
            "app.services.polling_engine.live_cache.prune",
        ), patch(
            "app.services.polling_engine.endpoint_runtime_service.prune",
        ), patch(
            "app.services.polling_engine.live_cache.get_connection_lifecycle",
            return_value=stable_lifecycle,
        ), patch(
            "app.services.polling_engine.poll_device_with_runtime",
            return_value=success_entry,
        ), patch(
            "app.services.polling_engine.live_cache.set",
        ), patch(
            "app.services.polling_engine.live_cache.append_power_sample",
        ), patch(
            "app.services.polling_engine.power_history_service.append_sample",
        ):
            engine._poll_devices()

        self.assertEqual(engine._next_loop_wait_seconds, POLLING_ENGINE_BUSY_WAIT_SECONDS)

    def test_idle_engine_uses_idle_wait_mode(self) -> None:
        engine = PollingEngine()

        with patch("app.services.polling_engine.device_service.list_devices", return_value=[]), patch(
            "app.services.polling_engine.live_cache.prune",
        ), patch(
            "app.services.polling_engine.endpoint_runtime_service.prune",
        ):
            engine._poll_devices()

        self.assertEqual(engine._next_loop_wait_seconds, POLLING_ENGINE_IDLE_WAIT_SECONDS)


if __name__ == "__main__":
    unittest.main()

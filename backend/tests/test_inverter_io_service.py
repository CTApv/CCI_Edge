import unittest
from unittest.mock import patch

from pymodbus import FramerType

from app.models.inverter_model import InverterModel, InverterPoint
from app.schemas.device_schemas import DeviceResponse
from app.services.inverter_io_service import InverterIoService


class InverterIoServiceTests(unittest.TestCase):
    def test_essential_telemetry_keeps_only_operator_signals(self) -> None:
        service = InverterIoService()
        points = [
            InverterPoint(
                key="active_power_kw",
                label="Potenza attiva",
                kind="telemetry",
                register_type="holding",
                address=1,
                length=1,
                datatype="uint16",
                unit="kW",
                protocol_meta={"summary_metric": "power_kw", "section": "Potenza"},
            ),
            InverterPoint(
                key="dc_link_voltage_v",
                label="DC-link voltage",
                kind="telemetry",
                register_type="holding",
                address=2,
                length=1,
                datatype="uint16",
                unit="V",
                protocol_meta={"section": "DC bus"},
            ),
            InverterPoint(
                key="max_dc_voltage_v",
                label="Max DC voltage",
                kind="telemetry",
                register_type="holding",
                address=3,
                length=1,
                datatype="uint16",
                unit="V",
                protocol_meta={"section": "Targa"},
            ),
            InverterPoint(
                key="total_energy_kwh",
                label="Energia totale",
                kind="telemetry",
                register_type="holding",
                address=4,
                length=2,
                datatype="uint32",
                unit="kWh",
                protocol_meta={"summary_metric": "total_energy_kwh", "section": "Contatori"},
            ),
            InverterPoint(
                key="serial_number",
                label="Seriale",
                kind="telemetry",
                register_type="holding",
                address=6,
                length=8,
                datatype="ascii_string",
                unit="",
                protocol_meta={"section": "Identificazione"},
            ),
        ]

        selected_keys = {
            point.key for point in service._select_essential_readable_points(points)
        }

        self.assertEqual(
            selected_keys,
            {"active_power_kw", "dc_link_voltage_v", "total_energy_kwh"},
        )

    def test_heartbeat_probe_uses_catalog_test_register(self) -> None:
        service = InverterIoService()
        inverter_model = InverterModel(
            brand="Ingeteam",
            model="Ingecon SUN 630HE TL",
            protocol="modbus_rtu",
            transport="serial",
            defaults={
                "test_register": 19,
                "test_function": "input",
                "test_count": 1,
            },
        )

        probe_point = service._select_heartbeat_probe_point(inverter_model)

        self.assertIsNotNone(probe_point)
        assert probe_point is not None
        self.assertEqual(probe_point.address, 19)
        self.assertEqual(probe_point.register_type, "input")
        self.assertEqual(probe_point.length, 1)
        self.assertEqual(probe_point.datatype, "uint16")
        self.assertFalse(probe_point.visible)

    def test_heartbeat_probe_ignores_models_without_test_register(self) -> None:
        service = InverterIoService()
        inverter_model = InverterModel(
            brand="Generic",
            model="No probe",
            protocol="modbus_rtu",
            transport="serial",
        )

        self.assertIsNone(service._select_heartbeat_probe_point(inverter_model))

    def test_fast_power_poll_is_not_claimed_when_model_exposes_only_status(self) -> None:
        service = InverterIoService()
        inverter_model = InverterModel(
            brand="SOLAX POWER",
            model="X3-ULTRA",
            protocol="modbus_tcp",
            transport="tcp",
            telemetry_points=[
                InverterPoint(
                    key="status",
                    label="Stato operativo",
                    kind="telemetry",
                    register_type="input",
                    address=9,
                    length=1,
                    datatype="uint16",
                    protocol_meta={"heartbeat": True, "summary_metric": "status"},
                )
            ],
        )

        self.assertFalse(service.supports_active_power_fast_poll(inverter_model))
        self.assertEqual(service._select_active_power_points(inverter_model.telemetry_points), [])

    def test_rtu_read_prefers_poll_timeout_and_retries(self) -> None:
        service = InverterIoService()
        device = DeviceResponse(
            device_id="device-1",
            name="RTU",
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="serial",
            connection_settings={
                "port": "COM3",
                "slave_id": 1,
                "baud_rate": 9600,
                "parity": "N",
                "stop_bits": 1,
                "byte_size": 8,
                "timeout_seconds": 5.0,
                "retries": 3,
                "poll_interval_seconds": 15.0,
            },
            profile_overrides={},
            status="offline",
            created_at="2026-04-10T00:00:00+00:00",
        )
        inverter_model = InverterModel(
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="serial",
            telemetry_points=[
                InverterPoint(
                    key="active_power_kw",
                    label="Active power",
                    kind="telemetry",
                    register_type="holding",
                    address=1,
                    length=1,
                    datatype="uint16",
                    unit="kW",
                )
            ],
        )

        with patch(
            "app.services.inverter_io_service.connection_manager.execute_modbus_rtu",
            return_value=({}, "device_id"),
        ) as execute_modbus_rtu:
            service.read_telemetry(device, inverter_model)

        self.assertEqual(execute_modbus_rtu.call_args.kwargs["timeout"], 1.0)
        self.assertEqual(execute_modbus_rtu.call_args.kwargs["retries"], 0)

    def test_rtu_over_tcp_read_uses_serial_gateway_poll_caps(self) -> None:
        service = InverterIoService()
        device = DeviceResponse(
            device_id="device-rtu-tcp-1",
            name="RTU over TCP",
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="tcp",
            connection_settings={
                "host": "192.168.1.20",
                "port": 4002,
                "unit_id": 10,
                "timeout_seconds": 5.0,
                "retries": 3,
                "poll_interval_seconds": 15.0,
            },
            profile_overrides={},
            status="offline",
            created_at="2026-04-10T00:00:00+00:00",
        )
        inverter_model = InverterModel(
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="tcp",
            telemetry_points=[
                InverterPoint(
                    key="active_power_kw",
                    label="Active power",
                    kind="telemetry",
                    register_type="holding",
                    address=1,
                    length=1,
                    datatype="uint16",
                    unit="kW",
                )
            ],
        )

        with patch(
            "app.services.inverter_io_service.connection_manager.execute_modbus_tcp",
            return_value=({}, "device_id"),
        ) as execute_modbus_tcp:
            service.read_telemetry(device, inverter_model)

        self.assertEqual(execute_modbus_tcp.call_args.kwargs["framer"], FramerType.RTU)
        self.assertEqual(execute_modbus_tcp.call_args.kwargs["timeout"], 2.0)
        self.assertEqual(execute_modbus_tcp.call_args.kwargs["retries"], 0)
        self.assertTrue(execute_modbus_tcp.call_args.kwargs["reset_after_operation"])

    def test_rtu_write_prefers_write_timeout_and_retries(self) -> None:
        service = InverterIoService()
        device = DeviceResponse(
            device_id="device-1",
            name="RTU",
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="serial",
            connection_settings={
                "port": "COM3",
                "slave_id": 1,
                "baud_rate": 9600,
                "parity": "N",
                "stop_bits": 1,
                "byte_size": 8,
                "timeout_seconds": 5.0,
                "retries": 3,
                "poll_timeout_seconds": 0.8,
                "poll_retries": 0,
                "write_timeout_seconds": 2.5,
                "write_retries": 1,
            },
            profile_overrides={},
            status="offline",
            created_at="2026-04-10T00:00:00+00:00",
        )
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=10,
            length=1,
            datatype="uint16",
            writable=True,
        )

        class _OkResponse:
            def isError(self) -> bool:
                return False

        with patch(
            "app.services.inverter_io_service.connection_manager.execute_modbus_rtu",
            return_value=(_OkResponse(), "device_id"),
        ) as execute_modbus_rtu:
            result = service.write_command(device, command_point, 50.0)

        self.assertTrue(result.success)
        self.assertEqual(execute_modbus_rtu.call_args.kwargs["timeout"], 2.5)
        self.assertEqual(execute_modbus_rtu.call_args.kwargs["retries"], 1)

    def test_rtu_over_tcp_read_uses_tcp_client_with_rtu_framer(self) -> None:
        service = InverterIoService()
        device = DeviceResponse(
            device_id="device-rtu-tcp",
            name="Gateway RTU",
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="tcp",
            connection_settings={
                "host": "192.168.2.15",
                "port": 502,
                "unit_id": 7,
                "timeout_seconds": 1.5,
                "retries": 1,
            },
            profile_overrides={},
            status="offline",
            created_at="2026-04-10T00:00:00+00:00",
        )
        inverter_model = InverterModel(
            brand="Huawei",
            model="SUN2000",
            protocol="modbus_rtu",
            transport="serial",
            telemetry_points=[
                InverterPoint(
                    key="active_power_kw",
                    label="Active power",
                    kind="telemetry",
                    register_type="holding",
                    address=1,
                    length=1,
                    datatype="uint16",
                    unit="kW",
                )
            ],
        )

        with patch(
            "app.services.inverter_io_service.connection_manager.execute_modbus_tcp",
            return_value=({"active_power_kw": 12}, "device_id"),
        ) as execute_modbus_tcp:
            result = service.read_telemetry(device, inverter_model)

        self.assertEqual(result.values["active_power_kw"], 12)
        self.assertEqual(execute_modbus_tcp.call_args.kwargs["framer"], FramerType.RTU)
        self.assertEqual(execute_modbus_tcp.call_args.kwargs["timeout"], 1.5)
        self.assertEqual(execute_modbus_tcp.call_args.kwargs["retries"], 0)
        self.assertTrue(execute_modbus_tcp.call_args.kwargs["reset_after_operation"])

    def test_force_multi_write_uses_write_registers_even_for_single_register(self) -> None:
        service = InverterIoService()

        class _RecordingClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

            def write_register(
                self,
                address: int,
                value: int,
                *,
                device_id: int | None = None,
                no_response_expected: bool = False,
            ) -> object:
                self.calls.append(
                    (
                        "write_register",
                        (address, value),
                        {
                            "device_id": device_id,
                            "no_response_expected": no_response_expected,
                        },
                    )
                )
                return object()

            def write_registers(
                self,
                address: int,
                values: list[int],
                *,
                device_id: int | None = None,
                no_response_expected: bool = False,
            ) -> object:
                self.calls.append(
                    (
                        "write_registers",
                        (address, list(values)),
                        {
                            "device_id": device_id,
                            "no_response_expected": no_response_expected,
                        },
                    )
                )
                return object()

        client = _RecordingClient()

        response, unit_argument_style = service._write_modbus_point_with_retry(
            client=client,
            register_type="holding",
            unit_value=7,
            address=0x1106,
            values=[500],
            settings={},
            force_multiple=True,
        )

        self.assertIsNotNone(response)
        self.assertEqual(unit_argument_style, "device_id")
        self.assertEqual(len(client.calls), 1)
        method_name, args, kwargs = client.calls[0]
        self.assertEqual(method_name, "write_registers")
        self.assertEqual(args, (0x1106, [500]))
        self.assertEqual(kwargs["device_id"], 7)


    def test_rtu_over_tcp_broadcast_uses_unit_zero_and_rtu_framer(self) -> None:
        service = InverterIoService()
        device = DeviceResponse(
            device_id="device-rtu-tcp",
            name="Gateway RTU",
            brand="ZCS",
            model="ZCS",
            protocol="modbus_rtu",
            transport="tcp",
            connection_settings={
                "host": "192.168.2.15",
                "port": 502,
                "unit_id": 7,
                "timeout_seconds": 1.5,
                "retries": 1,
            },
            profile_overrides={},
            status="offline",
            created_at="2026-04-10T00:00:00+00:00",
        )
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=0x1106,
            length=1,
            datatype="uint16",
            scale=0.1,
            unit="%",
            writable=True,
            protocol_meta={"force_multi_write": True},
        )

        class _OkResponse:
            def isError(self) -> bool:
                return False

        class _RecordingClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

            def write_registers(
                self,
                address: int,
                values: list[int],
                *,
                device_id: int | None = None,
                no_response_expected: bool = False,
            ) -> object:
                self.calls.append(
                    (
                        "write_registers",
                        (address, list(values)),
                        {
                            "device_id": device_id,
                            "no_response_expected": no_response_expected,
                        },
                    )
                )
                return _OkResponse()

        client = _RecordingClient()

        def execute_modbus_tcp(**kwargs):  # noqa: ANN003, ANN202
            return kwargs["operation"](client)

        with patch(
            "app.services.inverter_io_service.connection_manager.execute_modbus_tcp",
            side_effect=execute_modbus_tcp,
        ) as execute_modbus_tcp_mock:
            result = service.write_command_broadcast(device, command_point, 50.0)

        self.assertTrue(result.success)
        self.assertEqual(execute_modbus_tcp_mock.call_args.kwargs["framer"], FramerType.RTU)
        self.assertEqual(execute_modbus_tcp_mock.call_args.kwargs["host"], "192.168.2.15")
        self.assertEqual(execute_modbus_tcp_mock.call_args.kwargs["port"], 502)
        self.assertTrue(execute_modbus_tcp_mock.call_args.kwargs["reset_after_operation"])
        self.assertEqual(len(client.calls), 1)
        method_name, args, kwargs = client.calls[0]
        self.assertEqual(method_name, "write_registers")
        self.assertEqual(args, (0x1106, [500]))
        self.assertEqual(kwargs["device_id"], 0)
        self.assertTrue(kwargs["no_response_expected"])
        self.assertEqual(result.diagnostics["unit_id"], 0)
        self.assertEqual(result.diagnostics["gateway_mode"], "rtu_over_tcp")


    def test_modbus_tcp_gateway_broadcast_uses_unit_zero_and_socket_framer(self) -> None:
        service = InverterIoService()
        device = DeviceResponse(
            device_id="device-tcp-gateway",
            name="Gateway TCP",
            brand="Generic",
            model="Generic TCP",
            protocol="modbus_tcp",
            transport="tcp",
            connection_settings={
                "host": "192.168.2.20",
                "port": 5020,
                "unit_id": 7,
                "timeout_seconds": 1.5,
                "retries": 1,
            },
            profile_overrides={},
            status="offline",
            created_at="2026-04-10T00:00:00+00:00",
        )
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=0x1106,
            length=1,
            datatype="uint16",
            scale=0.1,
            unit="%",
            writable=True,
            protocol_meta={"force_multi_write": True},
        )

        class _OkResponse:
            def isError(self) -> bool:
                return False

        class _RecordingClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

            def write_registers(
                self,
                address: int,
                values: list[int],
                *,
                device_id: int | None = None,
                no_response_expected: bool = False,
            ) -> object:
                self.calls.append(
                    (
                        "write_registers",
                        (address, list(values)),
                        {
                            "device_id": device_id,
                            "no_response_expected": no_response_expected,
                        },
                    )
                )
                return _OkResponse()

        client = _RecordingClient()

        def execute_modbus_tcp(**kwargs):  # noqa: ANN003, ANN202
            return kwargs["operation"](client)

        with patch(
            "app.services.inverter_io_service.connection_manager.execute_modbus_tcp",
            side_effect=execute_modbus_tcp,
        ) as execute_modbus_tcp_mock:
            result = service.write_command_broadcast(device, command_point, 50.0)

        self.assertTrue(result.success)
        self.assertEqual(execute_modbus_tcp_mock.call_args.kwargs["framer"], FramerType.SOCKET)
        self.assertEqual(execute_modbus_tcp_mock.call_args.kwargs["host"], "192.168.2.20")
        self.assertEqual(execute_modbus_tcp_mock.call_args.kwargs["port"], 5020)
        self.assertTrue(execute_modbus_tcp_mock.call_args.kwargs["reset_after_operation"])
        self.assertEqual(len(client.calls), 1)
        method_name, args, kwargs = client.calls[0]
        self.assertEqual(method_name, "write_registers")
        self.assertEqual(args, (0x1106, [500]))
        self.assertEqual(kwargs["device_id"], 0)
        self.assertTrue(kwargs["no_response_expected"])
        self.assertEqual(result.diagnostics["unit_id"], 0)
        self.assertEqual(result.diagnostics["gateway_mode"], "modbus_tcp")

    def test_ingeteam_modbus_tcp_gateway_broadcast_uses_unit_zero(self) -> None:
        service = InverterIoService()
        device = DeviceResponse(
            device_id="device-ingeteam-tcp-gateway",
            name="Ingeteam Gateway TCP",
            brand="Ingeteam",
            model="Ingecon SUN 375 TL",
            protocol="modbus_tcp",
            transport="tcp",
            connection_settings={
                "host": "192.168.2.108",
                "port": 5020,
                "unit_id": 7,
                "timeout_seconds": 1.5,
                "retries": 1,
            },
            profile_overrides={},
            status="online",
            created_at="2026-04-10T00:00:00+00:00",
        )
        command_point = InverterPoint(
            key="active_power_limit",
            label="Active power limit",
            kind="command",
            register_type="holding",
            address=1000,
            length=2,
            datatype="uint16",
            unit="%",
            writable=True,
            protocol_meta={
                "driver": "ingeteam_unit_commands",
                "command_start_address": 1000,
                "command_code": 3,
                "command_words": [
                    {"source": "value", "encoding": "percent_to_int16_32767"}
                ],
            },
        )

        class _OkResponse:
            def isError(self) -> bool:
                return False

        class _RecordingClient:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

            def write_registers(
                self,
                address: int,
                values: list[int],
                *,
                device_id: int | None = None,
                no_response_expected: bool = False,
            ) -> object:
                self.calls.append(
                    (
                        "write_registers",
                        (address, list(values)),
                        {
                            "device_id": device_id,
                            "no_response_expected": no_response_expected,
                        },
                    )
                )
                return _OkResponse()

        client = _RecordingClient()

        def execute_modbus_tcp(**kwargs):  # noqa: ANN003, ANN202
            return kwargs["operation"](client)

        signature = service.build_command_broadcast_signature(device, command_point, 50.0)

        with patch(
            "app.services.ingeteam_command_service.connection_manager.execute_modbus_tcp",
            side_effect=execute_modbus_tcp,
        ) as execute_modbus_tcp_mock:
            result = service.write_command_broadcast(device, command_point, 50.0)

        self.assertEqual(signature, ("ingeteam_unit_commands", 1000, (3, 16384)))
        self.assertTrue(result.success)
        self.assertEqual(execute_modbus_tcp_mock.call_args.kwargs["host"], "192.168.2.108")
        self.assertEqual(execute_modbus_tcp_mock.call_args.kwargs["port"], 5020)
        self.assertTrue(execute_modbus_tcp_mock.call_args.kwargs["reset_after_operation"])
        self.assertEqual(len(client.calls), 1)
        method_name, args, kwargs = client.calls[0]
        self.assertEqual(method_name, "write_registers")
        self.assertEqual(args, (1000, [3, 16384]))
        self.assertEqual(kwargs["device_id"], 0)
        self.assertTrue(kwargs["no_response_expected"])
        self.assertEqual(result.diagnostics["unit_id"], 0)
        self.assertTrue(result.diagnostics["broadcast"])
        self.assertEqual(result.diagnostics["gateway_mode"], "modbus_tcp")
        self.assertEqual(result.diagnostics["driver"], "ingeteam_unit_commands")



if __name__ == "__main__":
    unittest.main()

import unittest
from unittest.mock import patch

from pymodbus import FramerType

from app.schemas.protocol_schemas import (
    DeviceDiscoveryRtuRequest,
    DeviceDiscoveryTcpRequest,
    ProtocolTestRequest,
)
from app.services.aurora_service import AuroraProtocolError
from app.services.protocol_test_service import (
    ProtocolOperationBusyError,
    ProtocolTestService,
    _DiscoveryDescriptor,
)


class _FakeResponse:
    def __init__(self, registers: list[int] | None = None, *, error: bool = False) -> None:
        self.registers = registers or []
        self._error = error

    def isError(self) -> bool:
        return self._error


class _FakeClient:
    def __init__(self, responses: dict[tuple[str, int], _FakeResponse]) -> None:
        self._responses = responses

    def read_holding_registers(
        self,
        register_address: int,
        *,
        count: int,
        device_id: int | None = None,
        slave: int | None = None,
    ) -> _FakeResponse:
        return self._responses.get(("holding", register_address), _FakeResponse(error=True))

    def read_input_registers(
        self,
        register_address: int,
        *,
        count: int,
        device_id: int | None = None,
        slave: int | None = None,
    ) -> _FakeResponse:
        return self._responses.get(("input", register_address), _FakeResponse(error=True))


class _TimeoutClient:
    def read_holding_registers(
        self,
        register_address: int,
        *,
        count: int,
        device_id: int | None = None,
        slave: int | None = None,
    ) -> _FakeResponse:
        raise TimeoutError("No response received")


class _TrackedClient:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True

    def read_input_registers(
        self,
        register_address: int,
        *,
        count: int,
        device_id: int | None = None,
        slave: int | None = None,
    ) -> _FakeResponse:
        raise TimeoutError("No response received")


class ProtocolTestServiceDiscoveryTests(unittest.TestCase):
    def test_discover_tcp_gateway_rtu_over_tcp_uses_serial_descriptors_and_rtu_framer(self) -> None:
        service = ProtocolTestService()
        payload = DeviceDiscoveryTcpRequest(
            host_start="192.168.2.10",
            host_end="192.168.2.10",
            port_start=502,
            port_end=502,
            timeout_seconds=0.35,
            retries=0,
            unit_ids=[1],
            gateway_protocol_mode="rtu_over_tcp",
        )
        descriptor = _DiscoveryDescriptor(
            register=23,
            function="holding",
            candidate_brands=("Huawei",),
            candidate_profiles=(("Huawei", "SUN2000", "modbus_rtu", "serial"),),
        )

        with (
            patch.object(service, "_get_discovery_descriptors", return_value=(descriptor,)) as get_descriptors,
            patch.object(service, "_discover_tcp_endpoint", return_value=([], 1)) as discover_endpoint,
        ):
            response = service.discover_tcp(payload)

        self.assertEqual(response.request_count, 1)
        get_descriptors.assert_called_once_with("serial", ("modbus_rtu",))
        self.assertEqual(discover_endpoint.call_args.kwargs["framer"], FramerType.RTU)

    def test_discover_tcp_prefers_selected_catalog_descriptor(self) -> None:
        service = ProtocolTestService()
        payload = DeviceDiscoveryTcpRequest(
            host_start="192.168.2.10",
            host_end="192.168.2.10",
            port_start=502,
            port_end=502,
            timeout_seconds=0.35,
            retries=0,
            unit_ids=[1],
            preferred_brand="GoodWe",
            preferred_model="Grid-tied MT/SMT/MTG2",
        )
        generic_descriptor = _DiscoveryDescriptor(
            register=30070,
            function="holding",
            candidate_brands=("Huawei",),
            candidate_profiles=(("Huawei", "SUN2000", "modbus_tcp", "tcp"),),
        )
        goodwe_descriptor = _DiscoveryDescriptor(
            register=35137,
            function="holding",
            candidate_brands=("GoodWe",),
            candidate_profiles=(
                ("GoodWe", "Grid-tied MS/DNS/XS/SDTG2", "modbus_tcp", "tcp"),
                ("GoodWe", "Grid-tied MT/SMT/MTG2", "modbus_tcp", "tcp"),
            ),
        )

        with (
            patch.object(
                service,
                "_get_discovery_descriptors",
                return_value=(generic_descriptor, goodwe_descriptor),
            ),
            patch.object(service, "_discover_tcp_endpoint", return_value=([], 1)) as discover_endpoint,
        ):
            response = service.discover_tcp(payload)

        self.assertEqual(response.request_count, 1)
        selected_descriptors = discover_endpoint.call_args.kwargs["descriptors"]
        self.assertEqual(len(selected_descriptors), 1)
        self.assertEqual(selected_descriptors[0].register, goodwe_descriptor.register)
        self.assertEqual(
            selected_descriptors[0].candidate_profiles,
            (("GoodWe", "Grid-tied MT/SMT/MTG2", "modbus_tcp", "tcp"),),
        )

    def test_protocol_operation_blocks_other_operations_until_finished(self) -> None:
        service = ProtocolTestService()
        payload = DeviceDiscoveryTcpRequest(
            host_start="192.168.2.10",
            host_end="192.168.2.10",
            port_start=502,
            port_end=502,
            timeout_seconds=0.35,
            retries=0,
            unit_ids=[1],
            operation_id="op-2",
        )

        with service._protocol_operation_scope(
            operation_id="op-1",
            kind="discover_tcp",
            label="Browsing TCP",
        ):
            with self.assertRaises(ProtocolOperationBusyError):
                service.discover_tcp(payload)

        state = service.protocol_operation_state()
        self.assertTrue(state.active)
        self.assertEqual(state.operation_id, "op-1")
        service.finish_protocol_operation("op-1")
        self.assertFalse(service.protocol_operation_state().active)

    def test_protocol_operation_cancel_closes_tracked_clients(self) -> None:
        service = ProtocolTestService()
        client = _TrackedClient()

        with service._protocol_operation_scope(
            operation_id="op-1",
            kind="discover_tcp",
            label="Browsing TCP",
        ):
            service._track_protocol_client(client)
            state = service.cancel_protocol_operation("op-1")
            self.assertTrue(client.closed)
            self.assertTrue(state.active)
            self.assertTrue(state.cancel_requested)
            service._untrack_protocol_client(client)

        self.assertFalse(service.protocol_operation_state().active)

    def test_discover_modbus_rtu_requests_serial_priority_window(self) -> None:
        service = ProtocolTestService()
        payload = DeviceDiscoveryRtuRequest(
            port="COM7",
            baud_rate=9600,
            parity="N",
            stop_bits=1,
            byte_size=8,
            timeout_seconds=0.35,
            retries=0,
            scan_protocol="modbus_rtu",
            slave_ids=[1],
        )
        descriptor = _DiscoveryDescriptor(
            register=23,
            function="holding",
            candidate_brands=("Huawei",),
            candidate_profiles=(("Huawei", "SUN2000", "modbus_rtu", "serial"),),
        )

        with (
            patch.object(service, "_get_discovery_descriptors", return_value=(descriptor,)),
            patch(
                "app.services.protocol_test_service.connection_manager.request_modbus_rtu_priority",
            ) as request_priority,
            patch(
                "app.services.protocol_test_service.connection_manager.execute_modbus_rtu",
                side_effect=lambda **kwargs: kwargs["operation"](_FakeClient({})),
            ),
            patch.object(
                service,
                "_probe_modbus_discovery_unit",
                return_value=(None, 1),
            ),
        ):
            results, request_count = service._discover_modbus_rtu(payload=payload)

        self.assertEqual(results, [])
        self.assertEqual(request_count, 1)
        request_priority.assert_called_once()
        self.assertEqual(request_priority.call_args.args[0], "COM7")

    def test_discover_modbus_rtu_prefers_selected_catalog_descriptor(self) -> None:
        service = ProtocolTestService()
        payload = DeviceDiscoveryRtuRequest(
            port="COM7",
            preferred_brand="Ingeteam",
            preferred_model="Ingecon SUN 630HE TL",
            baud_rate=9600,
            parity="N",
            stop_bits=1,
            byte_size=8,
            timeout_seconds=0.35,
            retries=0,
            scan_protocol="modbus_rtu",
            slave_ids=[7],
        )
        generic_descriptor = _DiscoveryDescriptor(
            register=207,
            function="holding",
            candidate_brands=("Huawei",),
            candidate_profiles=(("Huawei", "SUN2000", "modbus_rtu", "serial"),),
        )
        ingeteam_descriptor = _DiscoveryDescriptor(
            register=19,
            function="input",
            candidate_brands=("Ingeteam",),
            candidate_profiles=(
                ("Ingeteam", "Ingecon SUN 315HE TL", "modbus_rtu", "serial"),
                ("Ingeteam", "Ingecon SUN 630HE TL", "modbus_rtu", "serial"),
            ),
        )

        with (
            patch.object(
                service,
                "_get_discovery_descriptors",
                return_value=(generic_descriptor, ingeteam_descriptor),
            ),
            patch(
                "app.services.protocol_test_service.connection_manager.request_modbus_rtu_priority",
            ),
            patch(
                "app.services.protocol_test_service.connection_manager.execute_modbus_rtu",
                side_effect=lambda **kwargs: kwargs["operation"](
                    _FakeClient({("input", 19): _FakeResponse([123])})
                ),
            ) as execute_rtu,
        ):
            results, request_count = service._discover_modbus_rtu(payload=payload)

        self.assertEqual(request_count, 1)
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].unit_id, 7)
        self.assertEqual(results[0].register_address, 19)
        self.assertEqual(results[0].function, "input")
        self.assertEqual(results[0].candidate_profile_count, 1)
        self.assertEqual(results[0].candidate_profiles[0].model, "Ingecon SUN 630HE TL")
        self.assertEqual(execute_rtu.call_args.kwargs["timeout"], 1.0)

    def test_rtu_priority_window_scales_with_scan_request_count(self) -> None:
        service = ProtocolTestService()

        with patch(
            "app.services.protocol_test_service.connection_manager.request_modbus_rtu_priority",
        ) as request_priority:
            service._request_rtu_priority_window(
                port="COM7",
                timeout_seconds=1.0,
                retries=0,
                request_count=30,
            )

        request_priority.assert_called_once()
        self.assertEqual(request_priority.call_args.args[0], "COM7")
        self.assertAlmostEqual(request_priority.call_args.kwargs["hold_seconds"], 33.0)

    def test_probe_prefers_more_specific_successful_descriptor(self) -> None:
        service = ProtocolTestService()
        generic_descriptor = _DiscoveryDescriptor(
            register=30070,
            function="holding",
            candidate_brands=("Huawei",),
            candidate_profiles=(
                ("Huawei", "A", "modbus_tcp", "tcp"),
                ("Huawei", "B", "modbus_tcp", "tcp"),
                ("Huawei", "C", "modbus_tcp", "tcp"),
            ),
        )
        specific_descriptor = _DiscoveryDescriptor(
            register=23,
            function="input",
            candidate_brands=("Ingeteam",),
            candidate_profiles=(
                ("Ingeteam", "X", "modbus_tcp", "tcp"),
            ),
        )
        client = _FakeClient(
            {
                ("holding", 30070): _FakeResponse([101]),
                ("input", 23): _FakeResponse([202]),
            }
        )

        result, attempts = service._probe_modbus_discovery_unit(
            client=client,
            unit_id=1,
            descriptors=(generic_descriptor, specific_descriptor),
            builder=lambda descriptor, raw_values, candidate_profiles: {
                "register": descriptor.register,
                "raw_values": raw_values,
                "candidate_profiles": candidate_profiles,
            },
        )

        self.assertEqual(attempts, 2)
        self.assertEqual(result["register"], 23)
        self.assertEqual(result["raw_values"], [202])
        self.assertEqual(
            result["candidate_profiles"],
            (("Ingeteam", "X", "modbus_tcp", "tcp"),),
        )

    def test_probe_keeps_intersection_when_multiple_hits_agree(self) -> None:
        service = ProtocolTestService()
        descriptor_a = _DiscoveryDescriptor(
            register=100,
            function="holding",
            candidate_brands=("BrandA", "BrandB"),
            candidate_profiles=(
                ("BrandA", "Alpha", "modbus_tcp", "tcp"),
                ("BrandB", "Beta", "modbus_tcp", "tcp"),
            ),
        )
        descriptor_b = _DiscoveryDescriptor(
            register=101,
            function="holding",
            candidate_brands=("BrandB", "BrandC"),
            candidate_profiles=(
                ("BrandB", "Beta", "modbus_tcp", "tcp"),
                ("BrandC", "Gamma", "modbus_tcp", "tcp"),
            ),
        )
        client = _FakeClient(
            {
                ("holding", 100): _FakeResponse([1]),
                ("holding", 101): _FakeResponse([2]),
            }
        )

        result, _ = service._probe_modbus_discovery_unit(
            client=client,
            unit_id=1,
            descriptors=(descriptor_a, descriptor_b),
            builder=lambda descriptor, raw_values, candidate_profiles: {
                "register": descriptor.register,
                "candidate_profiles": candidate_profiles,
            },
        )

        self.assertEqual(
            result["candidate_profiles"],
            (("BrandB", "Beta", "modbus_tcp", "tcp"),),
        )

    def test_probe_stops_after_consecutive_no_response_exceptions(self) -> None:
        service = ProtocolTestService()
        descriptors = tuple(
            _DiscoveryDescriptor(
                register=register,
                function="holding",
                candidate_brands=("BrandA",),
                candidate_profiles=(("BrandA", "ModelA", "modbus_tcp", "tcp"),),
            )
            for register in (100, 101, 102)
        )

        result, attempts = service._probe_modbus_discovery_unit(
            client=_TimeoutClient(),
            unit_id=1,
            descriptors=descriptors,
            builder=lambda descriptor, raw_values, candidate_profiles: {
                "register": descriptor.register,
                "candidate_profiles": candidate_profiles,
            },
        )

        self.assertIsNone(result)
        self.assertEqual(attempts, 2)

    def test_generic_aurora_connection_uses_probe_service(self) -> None:
        service = ProtocolTestService()
        payload = ProtocolTestRequest(
            protocol="aurora",
            transport="serial",
            connection_settings={
                "port": "COM7",
                "address": 2,
                "baud_rate": 19200,
                "parity": "N",
                "stop_bits": 1,
                "byte_size": 8,
                "timeout_seconds": 0.5,
                "retries": 1,
            },
        )

        with patch(
            "app.services.protocol_test_service.aurora_service.probe_connection",
            return_value={
                "global_state": 1,
                "inverter_state": 2,
                "part_number": "3M22",
                "part_number_source": "op_52",
                "version_signature": "OENN",
            },
        ):
            result = service.test_connection(payload)

        self.assertTrue(result.success)
        self.assertEqual(result.message, "Aurora connection test passed.")
        self.assertEqual(result.diagnostics["stage"], "aurora_probe")
        self.assertEqual(result.diagnostics["global_state"], 1)
        self.assertEqual(result.diagnostics["resolved_brand"], "PowerOne")
        self.assertEqual(
            result.diagnostics["resolved_model"],
            "ABB/Aurora PVI-TRIO-27.6-TL-OUTD-S2X-400",
        )

    def test_generic_aurora_connection_failure_keeps_trace_diagnostics(self) -> None:
        service = ProtocolTestService()
        payload = ProtocolTestRequest(
            protocol="aurora",
            transport="serial",
            connection_settings={
                "port": "COM7",
                "address": 2,
                "baud_rate": 19200,
                "parity": "N",
                "stop_bits": 1,
                "byte_size": 8,
                "timeout_seconds": 0.5,
                "retries": 1,
            },
        )

        with patch(
            "app.services.protocol_test_service.aurora_service.probe_connection",
            side_effect=AuroraProtocolError(
                "Aurora TxState=51",
                diagnostics={
                    "aurora_op": 151,
                    "aurora_tx_frame": "02 97 01 01 40 00 00 03 AA BB",
                    "aurora_reply_frame": "33 00 00 00 00 00 CC DD",
                    "aurora_reply_tx_state": 51,
                    "aurora_reply_tx_state_label": "Command is not implemented",
                },
            ),
        ):
            result = service.test_connection(payload)

        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics["stage"], "aurora_probe")
        self.assertEqual(result.diagnostics["aurora_op"], 151)
        self.assertEqual(result.diagnostics["aurora_reply_tx_state"], 51)
        self.assertEqual(
            result.diagnostics["aurora_reply_tx_state_label"],
            "Command is not implemented",
        )
        self.assertIn("aurora_tx_frame", result.diagnostics)

    def test_generic_modbus_rtu_over_tcp_connection_uses_rtu_framer(self) -> None:
        service = ProtocolTestService()
        payload = ProtocolTestRequest(
            protocol="modbus_rtu",
            transport="tcp",
            connection_settings={
                "host": "192.168.2.15",
                "port": 502,
                "unit_id": 7,
                "timeout_seconds": 0.5,
                "retries": 0,
            },
        )

        with patch(
            "app.services.protocol_test_service.connection_manager.execute_modbus_tcp",
            return_value=(_FakeResponse([123]), "device_id"),
        ) as execute_tcp:
            result = service.test_connection(payload)

        self.assertTrue(result.success)
        self.assertEqual(result.diagnostics["stage"], "generic")
        self.assertEqual(execute_tcp.call_args.kwargs["framer"], FramerType.RTU)
        self.assertTrue(execute_tcp.call_args.kwargs["reset_after_operation"])

    def test_discover_rtu_aurora_mode_uses_dedicated_probe(self) -> None:
        service = ProtocolTestService()
        payload = DeviceDiscoveryRtuRequest(
            port="COM7",
            baud_rate=19200,
            parity="N",
            stop_bits=1,
            byte_size=8,
            timeout_seconds=0.5,
            retries=1,
            scan_protocol="aurora",
            slave_ids=[2],
        )

        with (
            patch(
                "app.services.protocol_test_service.connection_manager.execute_modbus_rtu",
                side_effect=RuntimeError("no modbus reply"),
            ) as execute_modbus,
            patch.object(service, "_discover_delta_rtu", return_value=([], 0)) as discover_delta,
            patch(
                "app.services.protocol_test_service.aurora_service.probe_connection",
                return_value={
                    "global_state": 1,
                    "inverter_state": 2,
                    "dcdc1_state": 3,
                    "dcdc2_state": 4,
                    "alarm_code": 5,
                    "part_number": "3M22",
                    "part_number_source": "op_52",
                    "version_signature": "OENN",
                },
            ),
        ):
            result = service.discover_rtu(payload)

        execute_modbus.assert_not_called()
        discover_delta.assert_not_called()
        self.assertEqual(result.request_count, 1)
        self.assertEqual(len(result.results), 1)
        self.assertEqual(result.results[0].register_address, 52)
        self.assertEqual(result.results[0].raw_values, [1, 2, 3, 4, 5])
        self.assertEqual(result.results[0].signature_label, "Part number Aurora 3M22")
        self.assertEqual(len(result.results[0].candidate_profiles), 1)
        self.assertEqual(result.results[0].candidate_profiles[0].brand, "PowerOne")
        self.assertEqual(
            result.results[0].candidate_profiles[0].model,
            "ABB/Aurora PVI-TRIO-27.6-TL-OUTD-S2X-400",
        )

    def test_discover_rtu_modbus_mode_skips_aurora_probe(self) -> None:
        service = ProtocolTestService()
        payload = DeviceDiscoveryRtuRequest(
            port="COM7",
            baud_rate=9600,
            parity="N",
            stop_bits=1,
            byte_size=8,
            timeout_seconds=0.35,
            retries=0,
            scan_protocol="modbus_rtu",
            slave_ids=[1, 2],
        )

        with (
            patch.object(
                service,
                "_discover_modbus_rtu",
                return_value=([], 3),
            ) as discover_modbus,
            patch.object(service, "_discover_delta_rtu") as discover_delta,
            patch.object(service, "_discover_aurora_rtu") as discover_aurora,
        ):
            result = service.discover_rtu(payload)

        self.assertEqual(result.request_count, 3)
        self.assertEqual(result.results, [])
        discover_modbus.assert_called_once_with(payload=payload)
        discover_delta.assert_not_called()
        discover_aurora.assert_not_called()


if __name__ == "__main__":
    unittest.main()

from dataclasses import replace
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from app.api.routes_catalog import list_catalog_models
from app.catalog.xantrex_gt500_catalog import GT500_E_MODELS, GT500_NATIVE_MODELS, build_xantrex_gt500_models
from app.catalog.xantrex_catalog import build_xantrex_gt_models
from app.schemas.protocol_schemas import ProtocolTestRequest
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.device_service import device_service
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver
from app.services.protocol_test_service import ProtocolTestService
from app.services.xantrex_gt500_service import xantrex_gt500_service


class XantrexGt500Tests(unittest.TestCase):
    def setUp(self):
        self.models = build_xantrex_gt500_models('modbus_tcp', 'tcp')
        self.gateway = self.models[0]
        self.device = SimpleNamespace(brand='Xantrex', model=self.gateway.model, protocol='modbus_tcp', transport='tcp',
            connection_settings={'host': '127.0.0.1', 'port': 502, 'unit_id': 1}, profile_overrides={})
        self.client = Mock()
        self.client.read_holding_registers.return_value = SimpleNamespace(
            registers=[0, 4, 4, 0, 4, 3, 123, 456], isError=lambda: False)

    def read(self):
        with patch('app.services.xantrex_gt500_service.connection_manager.execute_modbus_tcp',
                   side_effect=lambda *a, **kw: kw['operation'](self.client)):
            return inverter_io_service.read_telemetry(self.device, self.gateway)

    def test_all_eight_families_are_separate_from_legacy(self):
        models = build_xantrex_gt_models('modbus_tcp', 'tcp')
        self.assertEqual({m.model for m in models}, {'GT Series', *GT500_E_MODELS, *GT500_NATIVE_MODELS})
        self.assertEqual(len(build_xantrex_gt500_models('modbus_rtu', 'serial')), 6)
        for model in self.models:
            self.assertFalse(model.command_points)
            self.assertIsNone(active_power_limit_resolver.resolve_for_write(model, 50))
            self.assertFalse(model.catalog_meta['field_tested'])

    def test_diagnostics_are_passive_and_bounded(self):
        result = self.read()
        self.assertEqual(result.values['system_state'], 4)
        self.assertNotIn('active_power_kw', result.values)
        self.client.read_holding_registers.assert_called_once_with(0, count=8, device_id=1)
        self.client.write_registers.assert_not_called()
        self.assertFalse(inverter_io_service.supports_active_power_fast_poll(self.gateway))

    def test_gateway_error_does_not_publish_stale_states(self):
        for status in [4, 1, 0xFFFF]:
            self.client.read_holding_registers.return_value.registers[0] = status
            with self.subTest(status=status), self.assertRaisesRegex(RuntimeError, 'non validi'):
                self.read()
        self.client.write_registers.assert_not_called()

    def test_short_response_is_rejected(self):
        self.client.read_holding_registers.return_value.registers = [0]
        with self.assertRaisesRegex(RuntimeError, 'incompleta'):
            self.read()

    def test_heartbeat_and_fast_poll_still_validate_gateway_health(self):
        for method in [inverter_io_service.read_heartbeat, inverter_io_service.read_active_power_only]:
            with patch('app.services.xantrex_gt500_service.connection_manager.execute_modbus_tcp',
                       side_effect=lambda *a, **kw: kw['operation'](self.client)):
                self.assertEqual(method(self.device, self.gateway).values['gateway_communication_status'], 0)
                self.client.read_holding_registers.return_value.registers[0] = 4
                with self.assertRaisesRegex(RuntimeError, 'non validi'):
                    method(self.device, self.gateway)
                self.client.read_holding_registers.return_value.registers[0] = 0
        self.client.write_registers.assert_not_called()

    def test_native_families_cannot_be_provisioned(self):
        for model in GT500_NATIVE_MODELS:
            for protocol, transport in [('modbus_tcp', 'tcp'), ('modbus_rtu', 'serial'), ('modbus_rtu', 'tcp')]:
                with self.subTest(model=model, protocol=protocol, transport=transport):
                    with self.assertRaisesRegex(ValueError, 'non operativa'):
                        device_service._ensure_catalog_profile_exists(brand='Xantrex', model=model, protocol=protocol, transport=transport)

    def test_pending_connection_test_does_not_open_network(self):
        service = ProtocolTestService()
        with patch.object(service, '_test_profile_connection') as probe:
            result = service.test_connection(ProtocolTestRequest(brand='Xantrex', model=GT500_NATIVE_MODELS[0],
                protocol='modbus_tcp', transport='tcp', connection_settings={'host': '127.0.0.1'}))
        self.assertFalse(result.success)
        self.assertFalse(result.diagnostics['request_attempted'])
        probe.assert_not_called()

    def test_overrides_cannot_route_a_native_family_to_legacy_driver(self):
        self.device.model = GT500_NATIVE_MODELS[0]
        legacy = build_xantrex_gt_models('modbus_tcp', 'tcp')[0]
        with patch('app.services.inverter_io_service.xantrex_modbus_service.read_points') as legacy_read:
            with self.assertRaisesRegex(ValueError, 'non operativa'):
                inverter_io_service.read_telemetry(self.device, legacy)
        legacy_read.assert_not_called()

    def test_every_family_blocks_generic_commands_and_broadcast(self):
        command = build_xantrex_gt_models('modbus_tcp', 'tcp')[0].command_points[0]
        for name in (*GT500_E_MODELS, *GT500_NATIVE_MODELS):
            self.device.model = name
            self.assertFalse(inverter_io_service.write_command(self.device, command, 0).success)
            self.assertIsNone(inverter_io_service.build_command_broadcast_signature(self.device, command, 0))
            self.assertFalse(inverter_io_service.write_command_broadcast(self.device, command, 0).success)

    def test_gateway_canonical_map_is_enforced(self):
        for kwargs in [{'address': 99}, {'scale': .1}, {'datatype': 'uint32'}, {'unit': 'kW'}, {'register_type': 'input'}]:
            point = replace(self.gateway.telemetry_points[0], **kwargs)
            with self.subTest(kwargs=kwargs), self.assertRaisesRegex(ValueError, 'Mappa diagnostica'):
                xantrex_gt500_service.read_points(self.device, [point])
        self.client.read_holding_registers.assert_not_called()

    def test_gateway_is_not_accepted_on_serial_or_broadcast(self):
        self.device.transport = 'serial'
        with self.assertRaisesRegex(ValueError, 'Modbus TCP'):
            self.read()
        self.device.transport = 'tcp'
        self.device.connection_settings['unit_id'] = 0
        with self.assertRaisesRegex(ValueError, 'Unit ID'):
            self.read()

    def test_catalog_describes_real_capabilities(self):
        entries = [m for m in list_catalog_models() if m['brand'] == 'Xantrex' and m['model'] != 'GT Series']
        self.assertEqual(len(entries), 14)
        for entry in entries:
            self.assertFalse(entry['capabilities']['has_active_power_limit'])
            self.assertFalse(entry['capabilities']['supports_power_history'])
            self.assertEqual(entry['command_count'], 0)
            if entry['model'] in GT500_NATIVE_MODELS:
                self.assertFalse(entry['capabilities']['supports_live_telemetry'])

    def test_discovery_never_identifies_gt500_from_a_zero_word(self):
        service = ProtocolTestService()
        for descriptor in service._get_discovery_descriptors('tcp'):
            for profile in descriptor.candidate_profiles:
                self.assertNotIn(profile[1], (*GT500_E_MODELS, *GT500_NATIVE_MODELS))

    def test_metadata_survives_profile_overrides(self):
        self.device.profile_overrides = {'defaults': {'timeout_seconds': 3}}
        model = inverter_profile_resolver.resolve_for_device(self.device)
        self.assertEqual(model.catalog_meta['scope'], 'diagnostics_only')

    def test_connection_success_only_claims_diagnostics(self):
        with patch('app.services.xantrex_gt500_service.connection_manager.execute_modbus_tcp',
                   side_effect=lambda *a, **kw: kw['operation'](self.client)):
            result = ProtocolTestService().test_connection(ProtocolTestRequest(brand='Xantrex', model=self.gateway.model,
                protocol='modbus_tcp', transport='tcp', connection_settings={'host': '127.0.0.1'}))
        self.assertTrue(result.success)
        self.assertIn('identita inverter e potenza non confermate', result.message)

from dataclasses import replace
from types import SimpleNamespace
import unittest
import socketserver
import struct
import threading
from unittest.mock import Mock, patch
from pymodbus import FramerType

from app.catalog.sungrow_catalog import build_sungrow_models, SG110CX_PREMIUM_MODEL
from app.services.inverter_io_service import inverter_io_service
from app.services.sungrow_sg110cx_service import sungrow_sg110cx_service
from app.services.active_power_limit_readback_resolver import active_power_limit_readback_resolver
from app.services.connection_manager import ConnectionManager


def response(registers=None, address=5006, count=2):
    return SimpleNamespace(registers=registers, address=address, count=count, isError=lambda: False)


class SungrowSg110cxTests(unittest.TestCase):
    def setUp(self):
        self.model = next(m for m in build_sungrow_models('modbus_tcp', 'tcp') if m.model == SG110CX_PREMIUM_MODEL)
        self.points = {p.key: p for p in self.model.telemetry_points}
        self.commands = {p.key: p for p in self.model.command_points}
        self.device = SimpleNamespace(brand='SUNGROW', model=SG110CX_PREMIUM_MODEL,
            protocol='modbus_tcp', transport='tcp', connection_settings={'host': '127.0.0.1', 'unit_id': 1})
        self.client = Mock()
        self.client.read_input_registers.return_value = response([0x2C06])
        self.client.write_registers.return_value = response()
        self.client.read_holding_registers.return_value = response([0xAA, 555])

    def write(self, value=55.5, key='active_power_limit'):
        with patch('app.services.sungrow_sg110cx_service.connection_manager.execute_modbus_tcp',
                   side_effect=lambda *a, **kw: kw['operation'](self.client)) as manager:
            result = sungrow_sg110cx_service.write(self.device, self.commands[key], value)
            if manager.called:
                self.assertEqual(manager.call_args.kwargs['retries'], 0)
            return result

    def test_coordinated_write_and_readback(self):
        result = self.write()
        self.assertTrue(result.success)
        self.client.read_input_registers.assert_called_once_with(4999, count=1, device_id=1)
        self.client.write_registers.assert_called_once_with(5006, [0xAA, 555], device_id=1)
        self.assertTrue(result.diagnostics['readback_confirmed'])
        self.assertFalse(result.diagnostics['physical_execution_confirmed'])

    def test_wrong_identity_blocks_every_command(self):
        self.client.read_input_registers.return_value = response([0x2C07])
        for key, value in [('active_power_limit', 50), ('start_stop', 0xCF),
                           ('active_power_limit_enable', 0x55), ('power_factor_setting', .95)]:
            with self.subTest(key=key):
                self.assertFalse(self.write(value, key).success)
        self.client.write_registers.assert_not_called()

    def test_lost_ack_is_uncertain_without_resending(self):
        self.client.write_registers.side_effect = ConnectionError('lost response')
        result = self.write()
        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics['stage'], 'uncertain')
        self.client.write_registers.assert_called_once()

    def test_mismatch_only_retries_reads(self):
        self.client.read_holding_registers.return_value = response([0x55, 555])
        result = self.write()
        self.assertFalse(result.success)
        self.assertTrue(result.diagnostics['write_accepted'])
        self.assertFalse(result.diagnostics['readback_confirmed'])
        self.assertEqual(self.client.read_holding_registers.call_count, 3)
        self.client.write_registers.assert_called_once()

    def test_invalid_values_never_write(self):
        for value in [-.1, 110.1, float('nan'), float('inf'), True]:
            with self.subTest(value=value):
                self.assertFalse(self.write(value).success)
        self.client.write_registers.assert_not_called()

    def test_custom_register_map_is_blocked(self):
        self.commands['active_power_limit'] = replace(self.commands['active_power_limit'], address=99)
        self.assertFalse(self.write().success)
        self.client.write_registers.assert_not_called()

    def test_broadcast_address_is_blocked(self):
        self.device.connection_settings['unit_id'] = 0
        self.assertFalse(self.write().success)
        self.client.write_registers.assert_not_called()

    def test_start_ack_does_not_confirm_physical_start(self):
        self.client.write_registers.return_value = response(address=5005, count=1)
        result = self.write(0xCF, 'start_stop')
        self.assertTrue(result.success)
        self.assertFalse(result.diagnostics['physical_execution_confirmed'])
        self.assertFalse(result.diagnostics['readback_confirmed'])
        self.client.read_holding_registers.assert_not_called()

    def test_nine_mppt_and_eighteen_strings(self):
        self.assertEqual(self.points['pv9_voltage_v'].address, 5129)
        self.assertEqual(self.points['pv9_current_a'].address, 5130)
        self.assertEqual(self.points['pv8_voltage_v'].address, 5122)
        self.assertEqual(len([k for k in self.points if k.startswith('string_')]), 18)
        self.assertFalse(self.model.catalog_meta['field_tested'])
        self.assertNotIn('broadcast write', self.model.features)

    def test_low_word_first_and_invalid_raw_values(self):
        for key, words, expected in [('active_power_kw', [0, 1], 65.536),
                                     ('reactive_power_kvar', [0xFC18, 0xFFFF], -1.0),
                                     ('active_power_kw', [0xFFFF, 0xFFFF], None)]:
            with self.subTest(key=key, words=words):
                point = self.points[key]
                raw = inverter_io_service._decode_register_value(registers=words, start_address=point.address, point=point)
                self.assertEqual(inverter_io_service._apply_point_scaling([point], {key: raw})[key], expected)

    def test_readback_requires_enabled_aa(self):
        for enabled, confirmed in [(0xAA, True), (0x55, False), (1, False)]:
            telemetry = [SimpleNamespace(key='active_power_limit_pct', value=55.5, unit='%', quality='valid'),
                         SimpleNamespace(key='active_power_limit_switch', value=enabled, unit='', quality='valid')]
            result = active_power_limit_readback_resolver.evaluate(inverter_model=self.model, telemetry=telemetry,
                desired_percent=55.5, resolved_value=55.5, resolved_unit='%', resolved_max_value=110)
            self.assertEqual(result.confirmed, confirmed)

    def test_real_pymodbus_tcp_loopback(self):
        requests = []

        class Handler(socketserver.BaseRequestHandler):
            def receive(self, count):
                data = b''
                while len(data) < count:
                    chunk = self.request.recv(count-len(data))
                    if not chunk:
                        raise ConnectionError('closed')
                    data += chunk
                return data

            def handle(self):
                for _ in range(3):
                    header = self.receive(7)
                    tx, proto, length, unit = struct.unpack('>HHHB', header)
                    pdu = self.receive(length-1)
                    requests.append((unit, pdu))
                    if pdu[0] == 4:
                        reply = bytes([4, 2]) + struct.pack('>H', 0x2C06)
                    elif pdu[0] == 16:
                        reply = pdu[:5]
                    else:
                        reply = bytes([3, 4]) + struct.pack('>HH', 0xAA, 555)
                    self.request.sendall(struct.pack('>HHHB', tx, proto, len(reply)+1, unit) + reply)

        with socketserver.TCPServer(('127.0.0.1', 0), Handler) as server:
            thread = threading.Thread(target=server.handle_request, daemon=True)
            thread.start()
            self.device.connection_settings['port'] = server.server_address[1]
            manager = ConnectionManager()
            try:
                with patch('app.services.sungrow_sg110cx_service.connection_manager', manager):
                    result = sungrow_sg110cx_service.write(self.device, self.commands['active_power_limit'], 55.5)
            finally:
                manager.close_all_tcp_connections()
            thread.join(timeout=3)
        self.assertTrue(result.success, result.error)
        self.assertEqual([pdu[0] for _, pdu in requests], [4, 16, 3])
        self.assertEqual(requests[1], (1, bytes([16]) + struct.pack('>HHBHH', 5006, 2, 4, 0xAA, 555)))

    def test_power_factor_requires_documented_range_and_mode(self):
        for value in [0, -.7, .7, 1.1]:
            self.assertFalse(self.write(value, 'power_factor_setting').success)
        self.client.read_holding_registers.return_value = response([0x55])
        self.assertFalse(self.write(.95, 'power_factor_setting').success)
        self.client.write_registers.assert_not_called()
        self.client.read_holding_registers.side_effect = [response([0xA1]), response([950])]
        self.client.write_registers.return_value = response(address=5018, count=1)
        self.assertTrue(self.write(.95, 'power_factor_setting').success)

    def test_rtu_gateway_uses_rtu_framer(self):
        self.device.protocol = 'modbus_rtu'
        with patch('app.services.sungrow_sg110cx_service.connection_manager.execute_modbus_tcp',
                   side_effect=lambda *a, **kw: kw['operation'](self.client)) as manager:
            self.assertTrue(sungrow_sg110cx_service.write(self.device, self.commands['active_power_limit'], 55.5).success)
        self.assertEqual(manager.call_args.kwargs['framer'], FramerType.RTU)

    def test_serial_uses_addressed_command_without_retries(self):
        self.device.protocol, self.device.transport = 'modbus_rtu', 'serial'
        self.device.connection_settings = {'port': 'COM_TEST', 'slave_id': 7}
        with patch('app.services.sungrow_sg110cx_service.connection_manager.execute_modbus_rtu',
                   side_effect=lambda *a, **kw: kw['operation'](self.client)) as manager:
            self.assertTrue(sungrow_sg110cx_service.write(self.device, self.commands['active_power_limit'], 55.5).success)
        self.assertEqual(manager.call_args.kwargs['retries'], 0)
        self.client.write_registers.assert_called_once_with(5006, [0xAA, 555], device_id=7)

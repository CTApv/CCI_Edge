import struct
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app.catalog.sinvert_s7_catalog import COMMISSIONING_MODEL, build_sinvert_s7_models
from app.services.sinvert_native_service import NativeBusyError, NativeChannel, SinvertNativeService
from app.services.sinvert_s7_command_service import SinvertS7CommandService


REFERENCE = {'cpu_module': 'CPU 315-2 DP', 'blocks': {'FB64': {'CheckSum': 123}}}


class Plc:
    def __init__(self):
        self.dbs = {n: bytearray(1800) for n in (3, 64, 100, 120, 402, 511, 944, 570, 600)}
        self.mk = bytearray(200)
        self.dbs[100][3] = 16
        self.dbs[100][6:8] = b'\0\x08'
        self.dbs[3][0] = 128
        self.dbs[570][140:144] = struct.pack('>f', 2500)
        self.writes = []
        self.checksum = 123
    def connect(self, *args, **kwargs): pass
    def disconnect(self): pass
    def get_cpu_state(self): return 'S7CpuStatusRun'
    def get_cpu_info(self): return SimpleNamespace(ModuleTypeName=b'CPU 315-2 DP')
    def get_block_info(self, kind, n): return SimpleNamespace(CheckSum=self.checksum)
    def db_read(self, db, offset, size): return self.dbs[db][offset:offset+size]
    def read_area(self, area, db, offset, size): return self.mk[offset:offset+size]
    def write_area(self, area, db, bit, data, wordlen):
        self.writes.append((db, bit, bytes(data)))
        byte, shift = divmod(bit, 8)
        target = self.dbs[db] if db else self.mk
        target[byte] = (target[byte] | 1 << shift) if data[0] else (target[byte] & ~(1 << shift))
    def db_write(self, *args): raise AssertionError('Native reference must never use S7 DB writes')


class Channel:
    def __init__(self, plc):
        self.plc = plc
        self.frames = []
        self.closed = False
        self.fail = False
        self.copy = True
    def send(self, payload):
        if self.fail: raise ConnectionError('native disconnected')
        self.frames.append(payload)
        self.plc.dbs[511][:64] = payload
        if self.copy:
            self.plc.dbs[944][:64] = payload
            self.plc.dbs[570][2:6] = payload[32:36]
    def close(self): self.closed = True


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.plc = Plc()
        self.channel = Channel(self.plc)
        self.device = SimpleNamespace(device_id='native-test', model=COMMISSIONING_MODEL, connection_settings={
            'host':'192.0.2.77', 'port':102, 'rack':0, 'slot':2,
            'sinvert_write_mode':'commissioning', 'sinvert_reference_max_raw':1000})
        self.bench = patch('app.services.sinvert_bench_service.sinvert_bench_service.status', return_value={'active':True})
        self.bench_mock = self.bench.start()
        self.addCleanup(self.bench.stop)
        self.audit = Mock()
        self.service = SinvertNativeService(client_factory=lambda:self.plc, channel_factory=lambda *a:self.channel,
            device_getter=lambda _:self.device, audit=self.audit, reference=REFERENCE)
        self.addCleanup(self.service.stop_all)
        self.service.interval = .03

    def wait_stopped(self):
        deadline = time.monotonic() + 3
        while self.service.status(self.device)['active'] and time.monotonic() < deadline:
            time.sleep(.01)
        session = self.service._get(self.device)
        if session.thread: session.thread.join(3)
        return self.service.status(self.device)

    def test_native_reference_cycle_readback_and_stop_preserve_other_bits(self):
        self.plc.dbs[100][135] = 0xa0
        status = self.service.start(self.device, 450.25, bench=True)
        self.assertTrue(status['active'])
        self.assertTrue(status['feedback']['regulator_input_confirmed'])
        time.sleep(.09)
        self.assertGreaterEqual(len(self.channel.frames), 2)
        self.service.update(self.device, self.plc, 451.5)
        self.assertEqual(struct.unpack('>f', self.channel.frames[-1][32:36])[0], 451.5)
        for frame in self.channel.frames:
            self.assertEqual(frame[:32], bytes(32))
            self.assertEqual(frame[36:], bytes(28))
        stopped = self.service.stop(self.device)
        self.assertFalse(stopped['active'])
        self.assertTrue(self.channel.closed)
        self.assertEqual(self.plc.dbs[100][135], 0xa0)
        self.assertEqual(self.plc.dbs[511][32:36], struct.pack('>f', 451.5))
        self.assertFalse(stopped['physical_execution_confirmed'])

    def test_changed_program_and_pending_hmi_prevent_any_write(self):
        self.plc.checksum = 999
        with self.assertRaisesRegex(ValueError, 'Programma'): self.service.start(self.device, 450, bench=True)
        self.assertEqual(self.plc.writes, [])
        self.plc.checksum = 123
        self.plc.dbs[402][842] = 2
        with self.assertRaisesRegex(ValueError, 'HMI'): self.service.start(self.device, 450, bench=True)
        self.assertEqual(self.plc.writes, [])

    def test_command_telegram_and_non_reference_changes_are_not_replayed(self):
        self.plc.dbs[511][14] = 1
        self.plc.dbs[944][14] = 1
        with self.assertRaisesRegex(ValueError, 'Telegramma'): self.service.start(self.device, 450, bench=True)
        self.assertEqual(self.channel.frames, [])
        self.assertEqual(self.plc.writes, [])

    def test_failure_after_gate_enable_restores_owned_bits(self):
        self.channel.fail = True
        self.plc.dbs[100][135] = 0x80
        with self.assertRaises(ConnectionError): self.service.start(self.device, 450, bench=True)
        self.assertEqual(self.plc.dbs[100][135], 0x80)
        self.assertEqual(self.service.status(self.device)['state'], 'fault')

    def test_external_writer_stops_without_overwriting_its_reference(self):
        self.service.start(self.device, 450, bench=True)
        self.plc.dbs[511][32:36] = struct.pack('>f', 700)
        result = self.wait_stopped()
        self.assertEqual(result['state'], 'fault')
        self.assertIn('produttore', result['error'])
        self.assertEqual(len(self.channel.frames), 1)
        self.assertEqual(self.plc.dbs[511][32:36], struct.pack('>f', 700))

    def test_bench_expiry_stops_instead_of_switching_to_field(self):
        self.service.start(self.device, 450, bench=True)
        self.bench_mock.return_value = {'active':False}
        result = self.wait_stopped()
        self.assertEqual(result['state'], 'fault')
        self.assertTrue(self.channel.closed)

    def test_lease_expires_without_reconnect(self):
        self.service.lease_seconds = .12
        self.service.start(self.device, 450, bench=True)
        result = self.wait_stopped()
        self.assertEqual(result['state'], 'fault')
        self.assertIn('scaduta', result['error'])
        count = len(self.channel.frames)
        time.sleep(.08)
        self.assertEqual(len(self.channel.frames), count)

    def test_stale_sender_is_not_revived_by_a_new_reference(self):
        self.service.start(self.device, 450, bench=True)
        session=self.service._get(self.device)
        from app.services.sinvert_s7_service import sinvert_s7_service
        with sinvert_s7_service.endpoint_lock(*session.identity):
            session.last_sent=time.monotonic()-4
            with self.assertRaisesRegex(TimeoutError, 'Cadenza'):
                self.service.update(self.device,self.plc,451)
        self.assertEqual(self.wait_stopped()['state'],'fault')
        self.assertEqual(len(self.channel.frames),1)

    def test_field_requires_consents_and_never_modifies_them(self):
        self.bench_mock.return_value = {'active':False}
        with self.assertRaisesRegex(ValueError, 'Consensi'): self.service.start(self.device, 450, bench=False)
        self.assertEqual(self.plc.writes, [])
        self.plc.mk[55] = 1
        self.assertTrue(self.service.start(self.device, 450, bench=False)['active'])
        self.plc.mk[55] = 0
        self.assertEqual(self.wait_stopped()['state'], 'fault')

    def test_field_sequence_and_pending_stop_prevent_native_start(self):
        self.bench_mock.return_value={'active':False}
        self.plc.mk[55]=1
        self.plc.mk[34]=8
        with self.assertRaisesRegex(ValueError,'Sequenza'):self.service.start(self.device,450,bench=False)
        self.plc.mk[34]=0
        self.plc.dbs[64][26]=4
        with self.assertRaisesRegex(ValueError,'Sequenza'):self.service.start(self.device,450,bench=False)
        self.assertEqual(self.plc.writes,[])
        self.assertEqual(self.channel.frames,[])

    def test_read_only_profile_and_invalid_values_fail_before_connection(self):
        for value in (float('nan'), float('inf'), -1, 1001, True):
            with self.assertRaises(ValueError): self.service.start(self.device, value, bench=True)
        self.device.connection_settings['sinvert_write_mode'] = 'read_only'
        with self.assertRaises(ValueError): self.service.start(self.device, 450, bench=True)
        self.assertEqual(self.plc.writes, [])

    def test_profile_disable_and_endpoint_change_stop_session(self):
        self.service.start(self.device, 450, bench=True)
        self.device.connection_settings['sinvert_write_mode'] = 'read_only'
        self.assertEqual(self.wait_stopped()['state'], 'fault')

    def test_app_reference_uses_native_and_fault_never_falls_back_to_s7(self):
        self.service.start(self.device, 450, bench=True)
        point = next(p for p in build_sinvert_s7_models()[1].command_points if p.key=='sinvert_power_reference_raw')
        with tempfile.TemporaryDirectory() as directory:
            commands = SinvertS7CommandService(client_factory=lambda:self.plc, reference=REFERENCE, audit_path=Path(directory)/'audit.jsonl')
            with patch('app.services.sinvert_native_service.sinvert_native_service', self.service):
                result = commands.write(self.device, point, 451.5)
                self.assertTrue(result.success, result.error)
                self.assertEqual(result.diagnostics['reference_transport'], 'iso_on_tcp')
                self.service.stop(self.device)
                result = commands.write(self.device, point, 452)
                self.assertFalse(result.success)
                self.assertFalse(result.diagnostics['write_attempted'])

    def test_native_command_waits_for_poll_and_reports_busy_as_no_write(self):
        from threading import Thread,Event
        from app.services.sinvert_s7_service import sinvert_s7_service
        self.service.start(self.device,450,bench=True)
        endpoint=sinvert_s7_service.endpoint_lock(*self.service.identity(self.device))
        ready=Event()
        def polling():
            with endpoint:
                ready.set();time.sleep(.7)
        thread=Thread(target=polling);thread.start();ready.wait(1)
        status=self.service.submit_reference(self.device,451)
        thread.join(1)
        self.assertTrue(status['active'])
        self.assertEqual(self.plc.dbs[511][32:36],struct.pack('>f',451))
        point=next(p for p in build_sinvert_s7_models()[1].command_points if p.key=='sinvert_power_reference_raw')
        with patch('app.services.sinvert_native_service.sinvert_native_service',self.service),patch.object(self.service,'submit_reference',side_effect=NativeBusyError('busy')):
            result=SinvertS7CommandService().write(self.device,point,452)
        self.assertFalse(result.success)
        self.assertFalse(result.diagnostics['write_attempted'])
        self.assertEqual(result.diagnostics['stage'],'blocked')

    def test_hmi_on_are_blocked_but_off_stops_native_then_uses_independent_s7(self):
        self.service.start(self.device, 450, bench=True)
        with tempfile.TemporaryDirectory() as directory:
            commands = SinvertS7CommandService(client_factory=lambda:self.plc, reference=REFERENCE, audit_path=Path(directory)/'audit.jsonl')
            with patch('app.services.sinvert_native_service.sinvert_native_service', self.service):
                for key in ('sinvert_on_request', 'sinvert_unit_1_test_mode', 'sinvert_alarm_ack'):
                    point=next(p for p in build_sinvert_s7_models()[1].command_points if p.key==key)
                    self.assertFalse(commands.write(self.device,point,1).success)
                point=next(p for p in build_sinvert_s7_models()[1].command_points if p.key=='sinvert_off_request')
                self.assertTrue(commands.write(self.device,point,1).success)
                self.assertTrue(self.channel.closed)
                self.assertFalse(self.service.status(self.device)['active'])
                self.assertIn((0,275,b'\1'),self.plc.writes)


class NativeWireTests(unittest.TestCase):
    def test_wire_handshake_and_64_byte_tpkt(self):
        cc = bytearray(b'\x03\0\0\x0b\x06\xd0\0\x01\0\x02\0')
        sock=Mock()
        def receive(n):
            value=bytes(cc[:n]); del cc[:n]; return value
        sock.recv.side_effect=receive
        channel=NativeChannel('192.0.2.1',102,socket_factory=lambda *a:sock)
        with patch('app.services.sinvert_native_service.select.select',return_value=([],[],[])):
            channel.send(bytes(64))
        self.assertIn(b'PVGUARDIAN',sock.sendall.call_args_list[0].args[0])
        self.assertIn(b'SINVERT',sock.sendall.call_args_list[0].args[0])
        self.assertEqual(sock.sendall.call_args_list[1].args[0],b'\x03\0\0\x47\x02\xf0\x80'+bytes(64))
        with self.assertRaises(ValueError):channel.send(bytes(63))

    def test_rejected_handshake_closes_socket(self):
        sock=Mock()
        sock.recv.side_effect=[b'\x03\0\0\x0b',b'\x06\x80\0\x01\0\x02\0']
        with self.assertRaises(ConnectionError):NativeChannel('192.0.2.1',102,socket_factory=lambda *a:sock)
        sock.close.assert_called_once()

    def test_segmented_cp_response_is_drained_without_interpreting_commands(self):
        incoming=bytearray(b'\x03\0\0\x0b\x06\xd0\0\x01\0\x02\0')
        sock=Mock()
        def receive(n):
            value=bytes(incoming[:n]);del incoming[:n];return value
        sock.recv.side_effect=receive
        channel=NativeChannel('192.0.2.1',102,socket_factory=lambda *a:sock)
        incoming.extend(b'\x03\0\0\x08\x02\xf0\0x')
        with patch('app.services.sinvert_native_service.select.select',side_effect=[([sock],[],[]),([],[],[])]):
            channel.send(bytes(64))
        self.assertEqual(incoming,bytearray())


class NativeRouteTests(unittest.TestCase):
    def test_start_requires_strict_confirmation_and_finite_value(self):
        from pydantic import ValidationError
        from fastapi import HTTPException
        from app.api.routes_sinvert_lab import NativeRequest,native_start
        for fields in ({'cpu_only':'yes'},{'exclusive_control_confirmed':'yes'},{'value':float('nan')}):
            payload={'value':450,'cpu_only':True,'exclusive_control_confirmed':True,**fields}
            with self.assertRaises(ValidationError):NativeRequest(**payload)
        with patch('app.api.routes_sinvert_lab.device_for',return_value=Mock()),patch('app.services.sinvert_native_service.sinvert_native_service.start') as start:
            with self.assertRaises(HTTPException):
                native_start('device',NativeRequest(value=450,cpu_only=True,exclusive_control_confirmed=False))
            start.assert_not_called()

    def test_status_is_read_only_and_stop_available_without_writable_profile(self):
        from app.api.routes_sinvert_lab import native_status,native_stop
        device=Mock()
        with patch('app.api.routes_sinvert_lab.device_for',return_value=device) as get,patch('app.services.sinvert_native_service.sinvert_native_service') as service:
            native_status('device')
            service.start.assert_not_called()
            service.submit_reference.assert_not_called()
            native_stop('device')
            service.stop.assert_called_once_with(device)
            get.assert_called_with('device')

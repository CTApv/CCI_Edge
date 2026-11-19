import struct
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from test_sinvert_ra1 import Ra1ReadOnlyPlc
from app.catalog.sinvert_ra1_catalog import RA1_BRAND, RA1_MODEL
from app.services.sinvert_ra1_lab_service import SinvertRa1LabService, Ra1Channel


class LabPlc(Ra1ReadOnlyPlc):
    def get_block_info(self, kind, number):
        from snap7.type import Block
        if kind == Block.FC and number == 500:
            return SimpleNamespace(MC7Size=732, CheckSum=40259+(1 if self.bad_block == 'FC500' else 0))
        return super().get_block_info(kind, number)

    def __init__(self):
        super().__init__()
        self.mk[55] = 0
        self.writes = []
        self.no_copy = False
        self.ack_lost = False
        self.stopped = False

    def read_szl(self, *args):
        raw = b'\0\4\0\1\0\0\0' + (b'\4' if self.stopped else b'\x08')
        return SimpleNamespace(Header=SimpleNamespace(LengthDR=8), Data=raw)

    def db_write(self, db, offset, data):
        self.writes.append((db, offset, bytes(data)))
        assert db == 944 and offset == 32 and len(data) == 4, 'No gate or unrelated writes'
        self.dbs[db][offset:offset+len(data)] = data
        if not self.no_copy:
            self.dbs[570][2:6] = data
        if self.ack_lost and len(self.writes) == 1:
            raise TimeoutError('write acknowledgement lost')


class Channel:
    def __init__(self, plc):
        self.plc = plc
        self.frames = []
        self.closed = False
        self.fail = False

    def send(self, frame):
        self.frames.append(frame)
        if self.fail:
            raise TimeoutError('send uncertain')
        self.plc.dbs[944][:64] = frame
        self.plc.dbs[570][2:6] = frame[32:36]
        self.plc.dbs[600][24] = 0

    def close(self):
        self.closed = True


class Ra1LabTests(unittest.TestCase):
    def setUp(self):
        self.plc = LabPlc()
        self.channel = Channel(self.plc)
        self.events = []
        self.device = SimpleNamespace(device_id='ra1', brand=RA1_BRAND, model=RA1_MODEL,
            protocol='s7_tcp', transport='tcp', profile_overrides={},
            connection_settings={'host':'192.0.2.44'})
        self.factory_calls = []
        def factory(*args):
            self.factory_calls.append(args)
            return self.channel
        self.service = SinvertRa1LabService(lambda:self.plc, factory, self.events.append, lambda _:self.device)
        self.addCleanup(self.service.stop_all)

    def native_ready(self):
        self.plc.dbs[400][16] = 128
        self.plc.dbs[100][135] = 2
        self.plc.dbs[3][0] = 128
        self.plc.mk[55] = 1

    def start(self):
        return self.service.start(self.device, 400, 1000, '0101', '0202',
                                  connection_confirmed=True, exclusive_confirmed=True)

    def wait_state(self, expected):
        deadline = time.monotonic()+3
        while time.monotonic() < deadline:
            status = self.service.status(self.device)
            if status['state'] == expected:
                return status
            time.sleep(.01)
        self.fail(str(self.service.status(self.device)))

    def test_preflight_reads_without_any_writes_or_native_connection(self):
        result = self.service.preflight(self.device, bench=True)
        self.assertTrue(result['success'])
        self.assertFalse(result['write_attempted'])
        self.assertEqual(self.plc.writes, [])
        self.assertEqual(self.factory_calls, [])

    def test_probe_confirms_real_change_and_restores_original(self):
        before = bytes(self.plc.dbs[944])
        result = self.service.probe(self.device, 500, 1000, cpu_only_confirmed=True)
        self.assertTrue(result['success'], result)
        self.assertTrue(result['restored'])
        self.assertTrue(result['feedback']['regulator_input_confirmed'])
        self.assertFalse(result['watchdog_tested'])
        self.assertEqual(bytes(self.plc.dbs[944]), before)
        self.assertEqual(len(self.plc.writes), 2)

    def test_probe_rejects_unconfirmed_field_or_live_outputs(self):
        with self.assertRaises(ValueError):
            self.service.probe(self.device, 500, 1000, cpu_only_confirmed=False)
        for condition in ('cp', 'consent', 'outputs'):
            self.plc.dbs[400][16] = 128 if condition == 'cp' else 0
            self.plc.mk[55] = 1 if condition == 'consent' else 0
            self.plc.mk[102] = 1 if condition == 'outputs' else 0
            result = self.service.probe(self.device, 500, 1000, cpu_only_confirmed=True)
            self.assertFalse(result['success'])
            self.assertFalse(result['write_attempted'])
        self.assertEqual(self.plc.writes, [])

    def test_changed_program_or_stopped_cpu_blocks_probe(self):
        for change in ('signature', 'stop'):
            self.plc.bad_block = 'OB1' if change == 'signature' else None
            self.plc.stopped = change == 'stop'
            result = self.service.probe(self.device, 500, 1000, cpu_only_confirmed=True)
            self.assertFalse(result['write_attempted'])
        self.assertEqual(self.plc.writes, [])

    def test_lost_write_ack_restores_without_retrying_requested_value(self):
        self.plc.ack_lost = True
        result = self.service.probe(self.device, 500, 1000, cpu_only_confirmed=True)
        self.assertFalse(result['success'])
        self.assertTrue(result['write_attempted'])
        self.assertTrue(result['restored'])
        self.assertEqual(result['stage'], 'uncertain')
        self.assertEqual(len(self.plc.writes), 2)

    def test_probe_cannot_claim_success_from_source_only(self):
        self.plc.no_copy = True
        result = self.service.probe(self.device, 500, 1000, cpu_only_confirmed=True)
        self.assertFalse(result['success'])
        self.assertTrue(result['restored'])
        self.assertTrue(result['feedback']['received_matches'])
        self.assertFalse(result['feedback']['regulator_input_confirmed'])

    def test_probe_does_not_overwrite_another_producer_during_cleanup(self):
        original = self.service.feedback
        def feedback(*args):
            result = original(*args)
            self.plc.dbs[944][32:36] = struct.pack('>f', 123)
            return result
        self.service.feedback = feedback
        result = self.service.probe(self.device, 500, 1000, cpu_only_confirmed=True)
        self.assertFalse(result['success'])
        self.assertFalse(result['restored'])
        self.assertEqual(len(self.plc.writes), 1)

    def test_bad_limits_confirmation_and_legacy_profile_never_connect(self):
        with patch.object(self.plc, 'connect') as connect:
            for value, maximum in [(False, 1000), (float('nan'), 1000), (-1, 1000), (500, 0), (1001, 1000)]:
                with self.assertRaises(ValueError):
                    self.service.probe(self.device, value, maximum, cpu_only_confirmed=True)
            with self.assertRaises(ValueError):
                self.service.start(self.device, 400, 1000, '01', '02', connection_confirmed=False, exclusive_confirmed=True)
            self.device.brand = 'SINVERT'
            with self.assertRaises(ValueError):
                self.service.preflight(self.device, bench=True)
            connect.assert_not_called()

    def test_native_uses_confirmed_tsaps_and_only_A_without_s7_writes(self):
        self.native_ready()
        self.start()
        status = self.wait_state('active')
        self.assertTrue(status['feedback']['regulator_input_confirmed'])
        self.assertEqual(self.factory_calls[0], ('192.0.2.44', 102, '0101', '0202'))
        frame = self.channel.frames[0]
        self.assertEqual(frame[:32]+frame[36:], bytes(60))
        self.assertEqual(struct.unpack('>f', frame[32:36])[0], 400)
        self.assertEqual(self.plc.writes, [])
        self.service.stop(self.device)
        self.assertTrue(self.channel.closed)
        self.assertFalse(self.service.status(self.device)['active'])

    def test_native_missing_conditions_block_before_channel_open(self):
        self.start()
        self.wait_state('fault')
        self.assertEqual(self.factory_calls, [])
        self.assertEqual(self.plc.writes, [])

    def test_native_hmi_conflict_and_changed_cp_mapping_are_blocked(self):
        self.native_ready()
        self.plc.dbs[511][10] = 1
        self.start()
        self.wait_state('fault')
        self.assertEqual(self.factory_calls, [])
        self.plc.dbs[511][10] = 0
        struct.pack_into('>H', self.plc.dbs[600], 20, 511)
        self.start()
        self.wait_state('fault')
        self.assertEqual(self.factory_calls, [])

    def test_native_expires_without_restart_or_extra_sends(self):
        self.native_ready()
        self.service.lease_seconds = .12
        self.start()
        self.wait_state('fault')
        self.assertEqual(len(self.channel.frames), 1)
        self.assertTrue(self.channel.closed)
        self.assertIn('scaduta', self.service.status(self.device)['error'])

    def test_uncertain_send_is_not_retried(self):
        self.native_ready()
        self.channel.fail = True
        self.start()
        status = self.wait_state('fault')
        self.assertTrue(status['write_attempted'])
        self.assertEqual(len(self.channel.frames), 1)
        self.assertTrue(self.channel.closed)

    def test_consent_loss_stops_and_closes_session(self):
        self.native_ready()
        self.service.interval = .05
        self.start()
        self.wait_state('active')
        self.plc.mk[55] = 0
        self.wait_state('fault')
        self.assertEqual(len(self.channel.frames), 1)
        self.assertTrue(self.channel.closed)

    def test_changes_are_limited_and_no_implicit_lease_renewal(self):
        self.native_ready()
        self.start()
        self.wait_state('active')
        session = next(iter(self.service._sessions.values()))
        deadline = session.deadline
        self.service.change(self.device, 500)
        self.assertEqual(session.deadline, deadline)
        self.assertFalse(self.service.status(self.device)['feedback']['regulator_input_confirmed'])
        with self.assertRaises(ValueError):
            self.service.change(self.device, 1001)
        with self.assertRaises(ValueError):
            self.start()
        self.service.change(self.device, 500, renew=True)
        self.assertGreater(session.deadline, deadline)

    def test_transport_rejects_non_neutral_payload(self):
        channel = object.__new__(Ra1Channel)
        channel.sock = SimpleNamespace(sendall=lambda _:self.fail('must not send'))
        frame = bytearray(64)
        frame[36] = 1
        with self.assertRaises(ValueError):
            channel.send(frame)

    def test_watchdog_program_mismatch_blocks_before_writes(self):
        self.plc.bad_block = 'FC500'
        result = self.service.probe(self.device, 500, 1000, cpu_only_confirmed=True)
        self.assertFalse(result['write_attempted'])
        self.assertIn('FC500', result['error'])

    def test_foreign_reference_stops_instead_of_overwriting_it(self):
        self.native_ready()
        self.service.interval = .05
        self.start()
        self.wait_state('active')
        self.plc.dbs[944][32:36] = struct.pack('>f', 777)
        self.wait_state('fault')
        self.assertEqual(len(self.channel.frames), 1)
        self.assertEqual(struct.unpack('>f', self.plc.dbs[944][32:36])[0], 777)

    def test_api_validation_is_strict_and_separate_from_legacy(self):
        from pydantic import ValidationError
        from app.api.routes_sinvert_ra1_lab import Probe, Start, device_for
        from fastapi import HTTPException
        with self.assertRaises(ValidationError):
            Probe(value=True, maximum=1000, cpu_only_confirmed=True)
        with self.assertRaises(ValidationError):
            Start(value=1, maximum=1000, local_tsap='wrong', remote_tsap='02', connection_confirmed=True, exclusive_confirmed=True)
        old = SimpleNamespace(brand='SINVERT', model='legacy')
        with patch('app.api.routes_sinvert_ra1_lab.device_service.get_device', return_value=old):
            with self.assertRaises(HTTPException):
                device_for('legacy')

    def test_watchdog_gap_stops_without_another_frame(self):
        self.native_ready()
        self.start()
        self.wait_state('active')
        next(iter(self.service._sessions.values())).last_sent = time.monotonic()-10
        self.wait_state('fault')
        self.assertEqual(len(self.channel.frames), 1)

    def test_native_requires_regulator_and_watchdog_feedback(self):
        for failure in ('regulator', 'watchdog'):
            with self.subTest(failure=failure):
                self.setUp()
                self.native_ready()
                send = self.channel.send
                def broken(frame):
                    send(frame)
                    if failure == 'regulator':
                        self.plc.dbs[570][2:6] = bytes(4)
                    else:
                        self.plc.dbs[600][24] = 16
                self.channel.send = broken
                self.start()
                status = self.wait_state('fault')
                self.assertTrue(status['write_attempted'])
                self.assertEqual(len(self.channel.frames), 1)
                self.assertTrue(self.channel.closed)

    def test_audit_failure_before_probe_prevents_writes(self):
        def fail(_):
            raise OSError('disk full')
        self.service.audit_callback = fail
        result = self.service.probe(self.device, 500, 1000, cpu_only_confirmed=True)
        self.assertFalse(result['write_attempted'])
        self.assertEqual(self.plc.writes, [])

    def test_close_failure_does_not_release_an_unowned_endpoint_lock(self):
        self.native_ready()
        def fail():
            raise OSError('close failure')
        self.channel.close = fail
        self.service.lease_seconds = .1
        self.start()
        self.wait_state('fault')
        from app.services.sinvert_s7_service import sinvert_s7_service
        lock = sinvert_s7_service.endpoint_lock(*self.service.endpoint(self.device))
        self.assertTrue(lock.acquire(timeout=.2))
        lock.release()

    def test_transport_uses_explicit_tsaps_and_exact_64_byte_frame(self):
        sent = []
        cc = bytearray(b'\x03\0\0\x0b\x06\xd0\0\x01\0\x02\0')
        def recv(count):
            fragment = bytes(cc[:count])
            del cc[:count]
            return fragment
        sock = SimpleNamespace(settimeout=lambda _:None, sendall=sent.append, recv=recv, close=lambda:None)
        with patch('app.services.sinvert_ra1_lab_service.socket.create_connection', return_value=sock), \
             patch('app.services.sinvert_ra1_lab_service.select.select', return_value=([], [], [])):
            channel = Ra1Channel('192.0.2.44', 102, '0102', '0304')
            channel.send(bytes(64))
        self.assertIn(b'\xc1\2\1\2\xc2\2\3\4', sent[0])
        self.assertEqual(sent[1], b'\x03\0\0\x47\x02\xf0\x80'+bytes(64))


if __name__ == '__main__':
    unittest.main()

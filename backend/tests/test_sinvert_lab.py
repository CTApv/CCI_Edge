import io
import struct
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from dataclasses import replace
from unittest.mock import patch
from snap7.type import Areas

import test_sinvert_commissioning as commissioning
from app.services.sinvert_bench_service import SinvertBenchService, sinvert_bench_service
from app.services.sinvert_trace_service import SinvertTraceService
from app.services.telemetry_quality_service import telemetry_quality_service
from app.catalog.sinvert_s7_catalog import build_sinvert_s7_models
from app.schemas.device_overview_schemas import DeviceOverviewDiagnostics, DeviceTelemetryPoint


class LabWriteTests(unittest.TestCase):
    send = commissioning.SinvertCommissioningTests.send

    def setUp(self):
        commissioning.SinvertCommissioningTests.setUp(self)
        self.addCleanup(lambda: sinvert_bench_service.set_enabled(self.device, False))
        original = self.client.write_area
        def bit_write(area, db, start, data, word_len):
            if area != Areas.DB: return original(area, db, start, data, word_len)
            self.client.writes.append(('DB_BIT', db, start, bytes(data)))
            byte, bit = divmod(start, 8)
            if data[0]: self.client.dbs[db][byte] |= 1 << bit
            else: self.client.dbs[db][byte] &= ~(1 << bit)
        self.client.write_area = bit_write

    def test_hmi_selector_targets_requested_group_and_preserves_other_bits(self):
        self.client.dbs[402][1036] = 128
        self.client.mk[55] = 0
        self.assertTrue(self.send('sinvert_unit_2_test_mode', 1).success)
        self.assertEqual(self.client.dbs[402][1036], 130)
        self.assertEqual(self.client.writes, [('DB_BIT', 402, 1036*8+1, b'\1')])
        self.assertTrue(self.send('sinvert_unit_2_test_mode', 0).success)
        self.assertEqual(self.client.dbs[402][1036], 128)

    def test_unconfigured_group_and_invalid_value_never_write(self):
        self.assertFalse(self.send('sinvert_unit_3_test_mode', 1).success)
        self.assertFalse(self.send('sinvert_unit_1_test_mode', .5).success)
        self.assertEqual(self.client.writes, [])

    def test_operator_pulse_cleanup_after_lost_write_ack(self):
        original = self.client.write_area
        def timeout(area, db, start, data, word_len):
            original(area, db, start, data, word_len)
            if data[0]: raise TimeoutError('ack lost')
        self.client.write_area = timeout
        result = self.send('sinvert_unit_1_operator_pulse')
        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics['stage'], 'uncertain')
        self.assertEqual(self.client.dbs[402][842] & 1, 0)
        self.assertEqual(len(self.client.writes), 2)

    def test_reset_sets_test_bit_reads_true_and_clears_same_bit(self):
        self.client.dbs[402][842] = 128
        result = self.send('sinvert_unit_1_reset')
        self.assertTrue(result.success)
        self.assertTrue(result.diagnostics['reset_true_observed'])
        self.assertTrue(result.diagnostics['reset_false_observed'])
        self.assertEqual(self.client.writes, [('DB_BIT',402,842*8+1,b'\1'),('DB_BIT',402,842*8+1,b'\0')])
        self.assertEqual(self.client.dbs[402][842],128)

    def test_reset_cleanup_when_true_cannot_be_read(self):
        original = self.client.db_read
        def hide_true(db, offset, count):
            value = original(db,offset,count)
            if db==402 and offset==842: return bytes([value[0] & ~2])
            return value
        self.client.db_read = hide_true
        result = self.send('sinvert_unit_1_reset')
        self.assertFalse(result.success)
        self.assertFalse(result.diagnostics['reset_true_observed'])
        self.assertEqual(self.client.dbs[402][842]&2,0)
        self.assertEqual(len(self.client.writes),2)

    def test_alarm_ack_is_collective_and_does_not_require_start_consents(self):
        self.client.mk[55] = 0
        self.client.dbs[100][3] = 0
        self.client.dbs[100][6:8] = bytes(2)
        self.client.dbs[402][0] = 128
        original = self.client.write_area
        def plc_ack(area, db, start, data, word_len):
            original(area,db,start,data,word_len)
            if area==Areas.DB and db==402 and start==1 and data[0]:
                self.client.dbs[402][0] &= ~2
        self.client.write_area = plc_ack
        result = self.send('sinvert_alarm_ack')
        self.assertTrue(result.success)
        self.assertTrue(result.diagnostics['ack_consumed'])
        self.assertFalse(result.diagnostics['alarms_clear_confirmed'])
        self.assertEqual(self.client.writes,[('DB_BIT',402,1,b'\1')])
        self.assertEqual(self.client.dbs[402][0],128)

    def test_alarm_ack_timeout_withdraws_only_ack_bit_and_reports_uncertainty(self):
        self.client.dbs[402][0] = 128
        result = self.send('sinvert_alarm_ack')
        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics['stage'],'uncertain')
        self.assertFalse(result.diagnostics['ack_consumed'])
        self.assertTrue(result.diagnostics['ack_pulse_withdrawn'])
        self.assertEqual(self.client.writes,[('DB_BIT',402,1,b'\1'),('DB_BIT',402,1,b'\0')])
        self.assertEqual(self.client.dbs[402][0],128)

    def test_alarm_ack_does_not_overwrite_a_pending_request(self):
        self.client.dbs[402][0] = 2
        self.assertFalse(self.send('sinvert_alarm_ack').success)
        self.assertEqual(self.client.writes,[])

    def test_alarm_ack_lost_write_response_is_not_retried_and_cleans_up(self):
        original=self.client.write_area
        def lost_ack(area,db,start,data,word_len):
            original(area,db,start,data,word_len)
            if data[0]:raise TimeoutError('write response lost')
        self.client.write_area=lost_ack
        result=self.send('sinvert_alarm_ack')
        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics['stage'],'uncertain')
        self.assertEqual(self.client.writes,[('DB_BIT',402,1,b'\1'),('DB_BIT',402,1,b'\0')])
        self.assertEqual(self.client.dbs[402][0]&2,0)

    def test_bench_power_write_persists_without_enabling_consents(self):
        self.client.copy = False
        self.client.mk[55] = 0
        self.client.dbs[100][135] = 0
        self.client.dbs[3][0] = 0
        sinvert_bench_service.set_enabled(self.device, True)
        result = self.send('sinvert_power_reference_raw', 80)
        self.assertTrue(result.success)
        self.assertFalse(result.diagnostics['copied'])
        self.assertTrue(result.diagnostics['reference_persistent'])
        self.assertEqual(self.client.dbs[511][32:36], struct.pack('>f',80))
        self.assertTrue(all(w[:3] == ('DB', 511, 32) for w in self.client.writes))
        self.assertEqual(len(self.client.writes), 1)
        sinvert_bench_service.set_enabled(self.device, False)
        self.client.writes.clear()
        self.assertFalse(self.send('sinvert_power_reference_raw', 80).success)
        self.assertEqual(self.client.writes, [])

    def test_bench_does_not_clear_existing_on_request(self):
        sinvert_bench_service.set_enabled(self.device, True)
        self.client.mk[34] |= 4
        self.assertFalse(self.send('sinvert_on_request').success)
        self.assertEqual(self.client.writes, [])

    def test_bench_does_not_overwrite_or_retry_when_write_ack_is_lost(self):
        sinvert_bench_service.set_enabled(self.device, True)
        original = self.client.db_write
        def timeout(db, offset, data):
            original(db, offset, data)
            if bytes(data) != bytes(4): raise TimeoutError('write ack lost')
        self.client.db_write = timeout
        result = self.send('sinvert_power_reference_raw', 80)
        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics['stage'],'uncertain')
        self.assertEqual(self.client.dbs[511][32:36], struct.pack('>f',80))
        self.assertEqual(len(self.client.writes), 1)

    def test_bench_program_mismatch_still_blocks(self):
        sinvert_bench_service.set_enabled(self.device, True)
        self.client.checksum = 0
        self.assertFalse(self.send('sinvert_unit_1_test_mode', 1).success)
        self.assertEqual(self.client.writes, [])


class LabStateTests(unittest.TestCase):
    def test_bench_api_requires_explicit_boolean_declaration(self):
        from fastapi import HTTPException
        from pydantic import ValidationError
        from app.api.routes_sinvert_lab import BenchRequest, bench_mode
        from app.catalog.sinvert_s7_catalog import COMMISSIONING_MODEL
        device = SimpleNamespace(device_id='api-test', brand='SINVERT', model=COMMISSIONING_MODEL,
            protocol='s7_tcp', connection_settings={'host':'192.0.2.1'})
        try:
            with patch('app.api.routes_sinvert_lab.device_service.get_device', return_value=device):
                with self.assertRaises(HTTPException):
                    bench_mode('api-test', BenchRequest(enabled=True,cpu_only_confirmed=False))
                with self.assertRaises(ValidationError):
                    BenchRequest(enabled=True,cpu_only_confirmed='yes')
                self.assertTrue(bench_mode('api-test', BenchRequest(enabled=True,cpu_only_confirmed=True))['active'])
                self.assertFalse(bench_mode('api-test', BenchRequest(enabled=False,cpu_only_confirmed=False))['active'])
        finally: sinvert_bench_service.set_enabled(device, False)

    def test_bench_expires_and_is_bound_to_endpoint(self):
        device = SimpleNamespace(device_id='x', connection_settings={'host':'192.0.2.1'})
        service = SinvertBenchService()
        with patch('app.services.sinvert_bench_service.monotonic', return_value=100):
            self.assertTrue(service.set_enabled(device, True)['active'])
        with patch('app.services.sinvert_bench_service.monotonic', return_value=701):
            self.assertFalse(service.status(device)['active'])
        device.connection_settings['host'] = '192.0.2.2'
        with patch('app.services.sinvert_bench_service.monotonic', return_value=101):
            self.assertFalse(service.status(device)['active'])

    def test_boolean_quality_does_not_accept_strings_or_integers(self):
        point = next(p for p in build_sinvert_s7_models()[0].telemetry_points if p.datatype=='bool')
        for value in (True, False): self.assertEqual(telemetry_quality_service.evaluate(point, value).state, 'valid')
        for value in ('true', 1): self.assertEqual(telemetry_quality_service.evaluate(point, value).state, 'invalid')

    def test_export_filters_devices_and_contains_csv_raw_and_audit(self):
        with tempfile.TemporaryDirectory() as root:
            service = SinvertTraceService(Path(root))
            device = SimpleNamespace(device_id='one', brand='SINVERT', protocol='s7_tcp', connection_settings={'host':'192.0.2.1'})
            entry = SimpleNamespace(timestamp='2026-11-08T00:00:00Z',
                diagnostics=DeviceOverviewDiagnostics(last_poll_status='ok',response_time_ms=1,retries=0,last_error=None),
                telemetry=[DeviceTelemetryPoint(key='flag', label='Flag', value=True, raw_value=True, display_value='true')])
            try:
                service.append(device, entry)
                (Path(root)/'sinvert_command_audit.jsonl').write_text(json.dumps({'device_id':'other','secret':'not-exported'})+'\n')
                with zipfile.ZipFile(io.BytesIO(service.export('one'))) as z:
                    self.assertIn('telemetry.csv', z.namelist())
                    self.assertIn(b'flag', z.read('telemetry.csv'))
                    self.assertNotIn(b'not-exported', z.read('sinvert_command_audit.jsonl'))
                    self.assertIn(b'one', z.read('sinvert_samples.jsonl'))
            finally: service.close()

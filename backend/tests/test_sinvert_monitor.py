import struct
import json
import unittest
from dataclasses import replace

from app.catalog.sinvert_s7_catalog import build_sinvert_s7_models
from app.services.sinvert_monitor import build_sinvert_monitor
from app.services.sinvert_s7_service import SinvertS7Service, DB_LIMITS
from app.services.polling_engine import _build_telemetry_points
import test_sinvert_commissioning as commissioning


class MonitorTests(unittest.TestCase):
    def sample(self):
        values={'configured_groups_raw':3,'mtl_mode_raw':True,'plc_reset_raw':False,
            'plc_reinitialize_raw':False,'plc_requests_raw':0,'plc_sequence_raw':0,
            'external_copy_enabled_a':True,'external_copy_enabled_b':True,
            'external_consent_raw':True,'external_watchdog_fault':False,'external_channel_fault':False}
        for index in range(1,5):
            values.update({f'unit_{index}_flag_raw':index<=2,f'unit_{index}_consent_status_raw':32,
                f'unit_{index}_hmi_flags_raw':12,f'unit_{index}_hmi_status_raw':2,
                f'unit_{index}_comm_flag_a':False,f'unit_{index}_comm_flag_b':False,
                f'unit_{index}_active_power':1234,f'unit_{index}_frequency':5000})
            for kind in ['alarm','warning']:
                for word in range(4):values[f'unit_{index}_{kind}_word_{word}']=0
        return values

    def test_variant_states_and_scaled_measurements(self):
        values=self.sample();values['unit_1_hmi_status_raw']=4
        monitor=build_sinvert_monitor(values,{'sinvert_reference_max_raw':100})
        self.assertEqual(monitor['groups'][0]['state_label'],'Allarmi presenti')
        self.assertEqual(monitor['groups'][0]['measurements']['active_power'],123.4)
        self.assertEqual(monitor['groups'][0]['measurements']['frequency'],50)
        self.assertEqual(monitor['on_blockers'],[]);self.assertEqual(monitor['power_blockers'],[])
        self.assertFalse(monitor['groups'][0]['feedback_independent'])

    def test_unknown_missing_or_unconfigured_never_become_valid_zero_measurements(self):
        for code in [None,0,99]:
            values=self.sample();values['unit_1_hmi_status_raw']=code
            monitor=build_sinvert_monitor(values)
            self.assertIsNone(monitor['groups'][0]['measurements']['active_power'])
            self.assertIsNone(monitor['groups'][2]['measurements']['active_power'])

    def test_each_consent_operand_has_a_specific_reason(self):
        for status,reason in [(0,'59.5=0'),(48,'59.4=1'),(96,'59.6=1')]:
            values=self.sample();values['unit_1_consent_status_raw']=status;values['unit_1_flag_raw']=False
            group=build_sinvert_monitor(values)['groups'][0]
            self.assertFalse(group['expected_consent'])
            self.assertTrue(any(reason in text for text in group['consent_reasons']))

    def test_missing_or_inconsistent_sources_are_explicit(self):
        values=self.sample();values['unit_1_flag_raw']=False
        group=build_sinvert_monitor(values)['groups'][0]
        self.assertTrue(any('non coincide' in text for text in group['consent_reasons']))
        del values['configured_groups_raw']
        self.assertIsNone(build_sinvert_monitor(values)['groups'][0]['expected_consent'])

    def test_watchdog_and_comm_failure_do_not_fabricate_healthy_data(self):
        values=self.sample();values['external_watchdog_fault']=True;values['unit_1_comm_flag_a']=True
        monitor=build_sinvert_monitor(values)
        self.assertIsNone(monitor['groups'][0]['measurements']['active_power'])
        self.assertTrue(any('Watchdog' in text for text in monitor['power_blockers']))
        self.assertFalse(monitor['power_scale_confirmed'])

    def test_alarm_byte_order_and_manual_attribution(self):
        values=self.sample();values['unit_1_alarm_word_0']=1 # byte147 bit0, not144 bit0
        values['unit_1_alarm_word_1']=0x08000000 # byte148 bit3
        group=build_sinvert_monitor(values)['groups'][0]
        self.assertEqual([m['address'] for m in group['active_messages']],['DB401.DBX147.0','DB401.DBX148.3'])
        self.assertIn('Fast OFF',group['active_messages'][0]['label'])
        self.assertFalse(group['active_messages'][0]['label_verified_in_variant'])
        del values['unit_1_alarm_word_2']
        self.assertFalse(build_sinvert_monitor(values)['groups'][0]['messages_complete'])

    def test_all_zero_or_missing_consents_block_start(self):
        for value in [False,None]:
            values=self.sample()
            for index in range(1,5):values[f'unit_{index}_flag_raw']=value
            self.assertTrue(build_sinvert_monitor(values)['on_blockers'])

    def test_hmi_scaling_preserves_raw_values_and_rejects_modified_map(self):
        model=build_sinvert_s7_models()[0]
        point=next(p for p in model.telemetry_points if p.key=='unit_1_active_power')
        values=self.sample()
        row=next(row for row in _build_telemetry_points(model,values) if row.key==point.key)
        self.assertEqual(row.raw_value,1234);self.assertEqual(row.value,123.4)
        self.assertEqual(row.unit,'kW')
        values['unit_1_comm_flag_a']=True
        unavailable=next(row for row in _build_telemetry_points(model,values) if row.key==point.key)
        self.assertIsNone(unavailable.value);self.assertEqual(unavailable.raw_value,1234)
        self.assertEqual(unavailable.display_value,'--')
        with self.assertRaises(ValueError):SinvertS7Service._spec(replace(point,scale=1))
        with self.assertRaises(ValueError):SinvertS7Service._spec(replace(point,address=0))

    def test_full_profile_is_batched_and_keeps_partial_errors(self):
        model=build_sinvert_s7_models()[0]
        class MemoryClient:
            def __init__(self):self.reads=[];self.closed=False
            def connect(self,*a,**k):pass
            def disconnect(self):self.closed=True
            def db_read(self,db,offset,n):
                self.reads.append((db,offset,n))
                if db==511:raise RuntimeError('Source DB unavailable')
                return bytes(n)
            def read_area(self,area,db,offset,n):return self.db_read(0,offset,n)
        client=MemoryClient()
        result=SinvertS7Service(lambda:client).read_points({'host':'192.0.2.1'},model.telemetry_points)
        self.assertLess(len(client.reads),len(model.telemetry_points)//2)
        self.assertIsNone(result.values['controller_a_external_raw'])
        self.assertEqual(result.values['controller_a_input_raw'],0)
        self.assertIn('controller_a_external_raw',result.errors)
        self.assertTrue(client.closed)


class PreflightTests(unittest.TestCase):
    setUp = commissioning.SinvertCommissioningTests.setUp
    send = commissioning.SinvertCommissioningTests.send

    def test_reset_during_preparation_reconnects_and_rechecks_without_writes(self):
        failed=commissioning.ControlClient()
        from unittest.mock import Mock, patch
        failed.connect=Mock(side_effect=ConnectionResetError(10054,'connection reset'))
        self.factory.side_effect=[failed,self.client]
        point=next(p for p in self.model.command_points if p.key=='sinvert_off_request')
        with patch('app.services.sinvert_s7_command_service.time.sleep'):
            result=self.service.write(self.device,point,1,dry_run=True)
        self.assertTrue(result.success)
        self.assertEqual(result.diagnostics['preparation_attempts'],2)
        self.assertTrue(result.diagnostics['program_verified'])
        self.assertEqual(failed.writes+self.client.writes,[])
        self.assertTrue(failed.closed);self.assertTrue(self.client.closed)
        self.assertTrue(all(json.loads(line)["phase"]=="preflight_failed" for line in self.audit.read_text().splitlines()))

    def test_persistent_reset_has_phase_and_stops_after_two_read_attempts(self):
        from unittest.mock import Mock, patch
        self.client.connect=Mock(side_effect=ConnectionResetError(10054,'connection reset'))
        point=next(p for p in self.model.command_points if p.key=='sinvert_off_request')
        with patch('app.services.sinvert_s7_command_service.time.sleep'):
            result=self.service.write(self.device,point,1,dry_run=True)
        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics['preparation_attempts'],2)
        self.assertEqual(result.diagnostics['operation_phase'],'connect')
        self.assertEqual(self.client.writes,[])

    def test_reset_after_write_is_not_retried(self):
        from unittest.mock import Mock
        def write_then_reset(*args):
            self.client.writes.append(('BIT_ATTEMPT',))
            raise ConnectionResetError(10054,'reply lost')
        self.client.write_area=Mock(side_effect=write_then_reset)
        result=self.send('sinvert_off_request')
        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics['stage'],'uncertain')
        self.assertEqual(result.diagnostics['preparation_attempts'],1)
        self.assertEqual(len(self.client.writes),1)
        self.factory.assert_called_once()
    def test_preflight_pass_and_block_never_write_or_create_command_audit(self):
        for key in ['sinvert_on_request','sinvert_off_request','sinvert_power_reference_raw']:
            point=next(p for p in self.model.command_points if p.key==key)
            self.assertTrue(self.service.write(self.device,point,1,dry_run=True).success)
            self.assertEqual(self.client.writes,[])
        self.assertFalse(self.audit.exists())
        self.client.mk[55]=0
        point=next(p for p in self.model.command_points if p.key=='sinvert_on_request')
        result=self.service.write(self.device,point,1,dry_run=True)
        self.assertFalse(result.success);self.assertFalse(result.diagnostics['write_attempted'])

    def test_power_copy_without_regulator_input_is_uncertain_without_repeat(self):
        self.client.dbs[570][2:6]=struct.pack('>f',9)
        def copy_only(db,offset,data):
            self.client.writes.append(('DB',db,offset,bytes(data)))
            self.client.dbs[511][32:36]=data;self.client.dbs[944][32:36]=data
        self.client.db_write=copy_only
        result=self.send('sinvert_power_reference_raw',1)
        self.assertFalse(result.success);self.assertEqual(result.diagnostics['stage'],'uncertain')
        self.assertFalse(result.diagnostics['regulator_input_confirmed'])
        self.assertEqual(len(self.client.writes),1)

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from test_sinvert_ra1_lab import LabPlc
from app.catalog.sinvert_ra1_catalog import RA1_BRAND, RA1_MODEL
from app.services.sinvert_ra1_lab_service import SinvertRa1LabService, Ra1Session
from app.services.sinvert_ra1_command_service import SinvertRa1CommandService, MANUAL_BLOCKS, COMMANDS
from snap7.type import Areas, Block


class ManualPlc(LabPlc):
    def __init__(self):
        super().__init__()
        self.consume_on=True
        self.lose_ack=False
        self.break_copy=False

    def connect(self,*args,**kwargs):
        self.closed=False

    def get_block_info(self,kind,n):
        name=('FB' if kind==Block.FB else 'FC')+str(n)
        if kind!=Block.DB and name in MANUAL_BLOCKS:
            size,checksum=MANUAL_BLOCKS[name]
            return SimpleNamespace(MC7Size=size, CheckSum=checksum+(1 if self.bad_block==name else 0))
        return super().get_block_info(kind,n)

    def write_area(self,area,db,start,data,word_len):
        if self.closed:raise AssertionError('Cleanup after disconnect is forbidden')
        offset,bit=divmod(start,8)
        self.writes.append((area,db,start,bytes(data)))
        target=self.mk if area==Areas.MK else self.dbs[db]
        if data[0]:target[offset]|=1<<bit
        else:target[offset]&=~(1<<bit)
        if area==Areas.MK and offset==34 and bit==2 and self.consume_on:
            self.mk[34]&=~4
        if db==511 and not self.break_copy and self.dbs[400][16]&128:
            group=(offset-14)//2
            dest=842+194*group
            self.dbs[402][dest:dest+2]=self.dbs[511][14+2*group:16+2*group]
        if self.lose_ack and data[0]:raise TimeoutError('ack lost')


class Ra1CommandsTests(unittest.TestCase):
    def setUp(self):
        self.plc=ManualPlc();self.events=[]
        self.device=SimpleNamespace(device_id='manual-ra1',brand=RA1_BRAND,model=RA1_MODEL,protocol='s7_tcp',transport='tcp',
            profile_overrides={},connection_settings={'host':'192.0.2.46','ra1_write_mode':'commissioning','ra1_reference_max_raw':1000})
        self.lab=SinvertRa1LabService(lambda:self.plc,audit=self.events.append)
        self.service=SinvertRa1CommandService(self.lab)
        self.addCleanup(self.lab.stop_all)

    def send(self,key,value=1,**kwargs):
        return self.service.execute(self.device,key,value,dry_run=False,enabled=True,scope_confirmed=True,**kwargs)

    def test_capabilities_include_all_142_manual_actions_and_group_reset(self):
        self.assertEqual(len(COMMANDS),15)
        for i in range(1,5):
            for action in ('test','operator','reset'):self.assertIn(f'group_{i}_{action}',COMMANDS)

    def test_preflight_never_writes_or_requires_enable(self):
        self.device.connection_settings['ra1_write_mode']='read_only'
        result=self.service.execute(self.device,'group_1_reset')
        self.assertTrue(result['success'],result)
        self.assertFalse(result['write_attempted'])
        self.assertEqual(self.plc.writes,[])

    def test_readonly_or_missing_confirmation_blocks_before_connection(self):
        with patch.object(self.plc,'connect') as connect:
            for enabled,scope,mode in ((False,True,'commissioning'),(True,False,'commissioning'),(True,True,'read_only')):
                self.device.connection_settings['ra1_write_mode']=mode
                result=self.service.execute(self.device,'off',dry_run=False,enabled=enabled,scope_confirmed=scope)
                self.assertFalse(result['write_attempted'])
            connect.assert_not_called()

    def test_on_requires_consents_but_off_remains_available(self):
        self.assertFalse(self.send('on')['write_attempted'])
        result=self.send('off')
        self.assertTrue(result['success'],result)
        self.assertTrue(result['off_remains_pending'])
        self.assertEqual(self.plc.mk[34]&8,8)
        self.assertEqual(len(self.plc.writes),1)

    def test_off_already_pending_is_idempotent_and_never_cleared(self):
        self.plc.mk[34]=8
        result=self.send('off')
        self.assertTrue(result['success'])
        self.assertFalse(result['write_attempted'])
        self.assertEqual(self.plc.writes,[])
        self.assertEqual(self.plc.mk[34],8)

    def test_on_in_bench_is_withdrawn_and_retains_unrelated_bits(self):
        self.plc.mk[34]=128
        result=self.send('on',bench=True)
        self.assertTrue(result['success'],result)
        self.assertTrue(result['plc_processed'])
        self.assertFalse(result['physical_execution_confirmed'])
        self.assertEqual(self.plc.mk[34],128)
        self.assertEqual([w[2] for w in self.plc.writes],[274,274])

    def test_unconsumed_on_is_removed_and_reported_unconfirmed(self):
        self.plc.consume_on=False
        result=self.send('on',bench=True)
        self.assertFalse(result['success'])
        self.assertTrue(result['write_attempted'])
        self.assertEqual(self.plc.mk[34]&4,0)

    def test_lost_ack_cleanup_runs_before_disconnect_without_retry(self):
        self.plc.lose_ack=True
        result=self.send('group_2_reset')
        self.assertFalse(result['success'])
        self.assertEqual(result['stage'],'uncertain')
        self.assertNotIn('cleanup_error',result)
        self.assertEqual(self.plc.dbs[402][1036]&2,0)
        self.assertEqual(len(self.plc.writes),2)

    def test_hmi_uses_db402_when_cp_disabled(self):
        self.plc.dbs[402][842]=128
        result=self.send('group_1_test')
        self.assertTrue(result['success'],result)
        self.assertEqual(self.plc.writes[0][1:3],(402,842*8+1))
        self.assertEqual(self.plc.dbs[402][842],130)
        result=self.send('group_1_test',0)
        self.assertTrue(result['success'])
        self.assertEqual(self.plc.dbs[402][842],128)

    def test_hmi_uses_db511_and_confirms_copy_when_cp_enabled(self):
        self.plc.dbs[400][16]=128
        result=self.send('group_3_reset')
        self.assertTrue(result['success'],result)
        self.assertTrue(result['group_results'][0]['hmi_echo'])
        self.assertEqual([w[1] for w in self.plc.writes],[511,511])
        self.assertEqual(self.plc.writes[0][2],18*8+1)
        self.assertEqual(self.plc.dbs[402][1230]&2,0)

    def test_missing_copy_cannot_claim_success(self):
        self.plc.dbs[400][16]=128;self.plc.break_copy=True
        result=self.send('group_1_test')
        self.assertFalse(result['success'])
        self.assertTrue(result['write_attempted'])
        self.assertEqual(len(self.plc.writes),1)

    def test_group_reset_and_operator_pulses_return_to_false(self):
        for action,bit in [('reset',1),('operator',0)]:
            result=self.send('group_4_'+action)
            self.assertTrue(result['success'],result)
            self.assertTrue(result['group_results'][0]['pulse_withdrawn'])
            self.assertEqual(self.plc.dbs[402][1424]&(1<<bit),0)
            self.assertFalse(result['plc_processed'])

    def test_general_reset_targets_configured_groups_without_old_ack_bit(self):
        self.plc.mk[51]=5
        result=self.send('reset_all')
        self.assertTrue(result['success'],result)
        self.assertEqual([g['group'] for g in result['group_results']],[1,3])
        self.assertEqual([w[2] for w in self.plc.writes],[842*8+1,842*8+1,1230*8+1,1230*8+1])

    def test_general_reset_prechecks_all_groups_before_first_write(self):
        self.plc.dbs[402][1424]=2
        result=self.send('reset_all')
        self.assertFalse(result['write_attempted'])
        self.assertEqual(self.plc.writes,[])

    def test_changed_program_in_new_command_blocks_is_rejected(self):
        for name in MANUAL_BLOCKS:
            self.plc.bad_block=name
            result=self.send('off')
            self.assertFalse(result['write_attempted'],name)
        self.assertEqual(self.plc.writes,[])

    def test_unknown_command_and_invalid_value_never_connect(self):
        with patch.object(self.plc,'connect') as connect:
            for key,value in [('cpu_restart',1),('off',0),('on',True),('group_1_test',2),('group_1_test',float('nan'))]:
                self.assertFalse(self.send(key,value)['write_attempted'])
            connect.assert_not_called()

    def test_unconfigured_group_and_existing_selector_are_not_overwritten(self):
        self.plc.mk[51]=1
        self.assertFalse(self.send('group_2_reset')['write_attempted'])
        self.plc.dbs[402][842]=2
        self.assertFalse(self.send('group_1_reset')['write_attempted'])
        self.assertEqual(self.plc.dbs[402][842],2)

    def test_off_preflight_does_not_stop_active_native_session(self):
        endpoint=self.lab.endpoint(self.device)
        session=Ra1Session(self.device,endpoint,{},0,state='active')
        self.lab._sessions[endpoint]=session
        with patch.object(self.lab,'stop') as stop:
            result=self.service.execute(self.device,'off')
            self.assertTrue(result['success'],result)
            stop.assert_not_called()
        self.assertIs(self.lab._sessions[endpoint],session)

    def test_off_stops_native_before_s7_request(self):
        endpoint=self.lab.endpoint(self.device)
        session=Ra1Session(self.device,endpoint,{},0,state='active')
        self.lab._sessions[endpoint]=session
        def stop(_):
            self.assertEqual(self.plc.writes,[])
            session.state='stopped'
        with patch.object(self.lab,'stop',side_effect=stop) as stop_method:
            self.assertTrue(self.send('off')['success'])
            stop_method.assert_called_once()

    def test_reference_limit_and_mode_are_enforced_server_side(self):
        with patch.object(self.plc,'connect') as connect:
            for mode,maximum in [('read_only',1000),('commissioning',1001)]:
                self.device.connection_settings['ra1_write_mode']=mode
                with self.assertRaises(ValueError):
                    self.lab.probe(self.device,500,maximum,cpu_only_confirmed=True)
            connect.assert_not_called()

    def test_trace_is_separate_and_filters_other_devices(self):
        import json,io,zipfile
        from app.services.sinvert_ra1_trace_service import SinvertRa1TraceService
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'sinvert_ra1_audit.jsonl').write_text('\n'.join(json.dumps({'device_id':d}) for d in ['manual-ra1','other']))
            service=SinvertRa1TraceService(root)
            with zipfile.ZipFile(io.BytesIO(service.export('manual-ra1'))) as z:
                self.assertIn('telemetry.csv',z.namelist())
                self.assertNotIn(b'other',z.read('sinvert_ra1_audit.jsonl'))

    def test_settings_are_persisted_locally_without_polling_or_plc_writes(self):
        from app.schemas.device_schemas import DeviceResponse
        from app.api.routes_sinvert_ra1_lab import settings, LabSettings
        device=DeviceResponse(**vars(self.device),name='RA1',status='online',created_at='2026-11-19T00:00:00Z')
        with patch('app.api.routes_sinvert_ra1_lab.device_service.get_device',return_value=device), \
             patch('app.api.routes_sinvert_ra1_lab.device_service.update_device',return_value=device) as update, \
             patch('app.api.routes_sinvert_ra1_lab.lab.status',return_value={'state':'stopped'}):
            settings(device.device_id,LabSettings(enabled=True,maximum=500))
            payload=update.call_args.args[1]
            self.assertEqual(payload.connection_settings['host'],'192.0.2.46')
            self.assertEqual(payload.connection_settings['ra1_write_mode'],'commissioning')
            self.assertEqual(payload.connection_settings['ra1_reference_max_raw'],500)
            self.assertEqual(self.plc.writes,[])

    def test_settings_cannot_change_during_an_active_session(self):
        from app.api.routes_sinvert_ra1_lab import settings, LabSettings
        from fastapi import HTTPException
        with patch('app.api.routes_sinvert_ra1_lab.device_service.get_device',return_value=self.device), \
             patch('app.api.routes_sinvert_ra1_lab.lab.status',return_value={'state':'active'}), \
             patch('app.api.routes_sinvert_ra1_lab.device_service.update_device') as update:
            with self.assertRaises(HTTPException):settings(self.device.device_id,LabSettings(enabled=True,maximum=500))
            update.assert_not_called()

    def test_saved_reference_limit_cannot_be_bypassed_by_request_maximum(self):
        self.device.connection_settings['ra1_reference_max_raw']=100
        with patch.object(self.plc,'connect') as connect:
            with self.assertRaises(ValueError):self.lab.probe(self.device,200,1000,cpu_only_confirmed=True)
            connect.assert_not_called()

    def test_unsupported_group_mask_blocks_start_but_not_stop(self):
        self.plc.mk[51]=31
        self.assertFalse(self.send('on')['write_attempted'])
        self.assertFalse(self.send('reset_all')['write_attempted'])
        self.assertTrue(self.send('off')['success'])

    def test_lost_ack_reports_a_pulse_that_cannot_be_withdrawn_from_echo(self):
        self.plc.dbs[400][16]=128;self.plc.lose_ack=True
        original=self.plc.write_area
        def write(*args):
            try:original(*args)
            finally:
                if args[3][0]:self.plc.break_copy=True
        self.plc.write_area=write
        result=self.send('group_1_reset')
        self.assertFalse(result['success'])
        self.assertIn('cleanup_error',result)
        self.assertIn('Ripristino',result['error'])
        self.assertEqual(self.plc.dbs[511][14]&2,0)
        self.assertEqual(self.plc.dbs[402][842]&2,2)
        self.assertEqual([w[1] for w in self.plc.writes],[511,511])


if __name__=='__main__':unittest.main()

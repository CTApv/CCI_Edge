import tempfile,unittest,json,struct
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch,Mock
from dataclasses import replace

from app.catalog.sinvert_s7_catalog import build_sinvert_s7_models
from app.services.sinvert_s7_command_service import SinvertS7CommandService
from app.services.sinvert_s7_discovery import probe_sinvert,DISCOVERY_LAYOUT
from app.services.active_power_limit_resolver import active_power_limit_resolver
from app.services.protocol_test_service import ProtocolTestService
from app.schemas.protocol_schemas import DeviceDiscoveryTcpRequest
from snap7.type import WordLen


REFERENCE={'cpu_module':'CPU 315-2 DP','blocks':{'FB64':{'MC7Size':1292,'CheckSum':123}}}


class ControlClient:
    def __init__(self):
        self.dbs={100:bytearray(158),3:bytearray(254),600:bytearray(64),64:bytearray(164),511:bytearray(64),944:bytearray(64),570:bytearray(246)}
        self.dbs[100][3]=16;self.dbs[100][6:8]=b'\0\x08';self.dbs[100][135]=3;self.dbs[3][0]=128
        self.mk=bytearray(200);self.mk[55]=1;self.mk[34]=128
        self.writes=[];self.copy=True;self.checksum=123;self.closed=False
    def connect(self,*args,**kwargs):pass
    def disconnect(self):self.closed=True
    def get_cpu_state(self):return 'S7CpuStatusRun'
    def get_cpu_info(self):return SimpleNamespace(ModuleTypeName=b'CPU 315-2 DP',SerialNumber=b'test')
    def get_block_info(self,kind,number):return SimpleNamespace(MC7Size=1292,CheckSum=self.checksum)
    def db_read(self,db,offset,n):return self.dbs[db][offset:offset+n]
    def read_area(self,area,db,offset,n):return self.mk[offset:offset+n]
    def db_write(self,db,offset,data):
        self.writes.append(('DB',db,offset,bytes(data)))
        self.dbs[db][offset:offset+len(data)]=data
        if self.copy:
            self.dbs[944][32:36]=data
            self.dbs[570][2:6]=data
    def write_area(self,area,db,start,data,word_len):
        assert word_len==WordLen.Bit
        self.writes.append(('BIT',start,bytes(data)))
        byte,bit=divmod(start,8)
        if data[0]:
            if bit==2:self.mk[102]=1;self.dbs[64][26]=4
            else:self.mk[102]=0
            # PLC consumes the request; unrelated marker bits remain unchanged.
        else:self.mk[byte]&=~(1<<bit)


class SinvertCommissioningTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.client=ControlClient();self.factory=Mock(return_value=self.client)
        self.model=build_sinvert_s7_models()[1]
        self.device=SimpleNamespace(device_id='bench',model=self.model.model,connection_settings={
            'host':'192.0.2.1','port':102,'rack':0,'slot':2,'timeout_seconds':1,
            'sinvert_write_mode':'commissioning','sinvert_reference_max_raw':100})
        self.audit=Path(self.temp.name)/'audit.jsonl'
        self.service=SinvertS7CommandService(client_factory=self.factory,reference=REFERENCE,audit_path=self.audit)
    def send(self,key,value=1,point=None):
        point=point or next(p for p in self.model.command_points if p.key==key)
        with patch('app.services.sinvert_s7_command_service.time.sleep'):
            return self.service.write(self.device,point,value)
    def test_default_read_only_and_diagnostic_profile_cannot_write(self):
        self.device.connection_settings['sinvert_write_mode']='read_only'
        self.assertFalse(self.send('sinvert_on_request').success);self.factory.assert_not_called()
        self.device.connection_settings['sinvert_write_mode']='commissioning'
        self.device.model=build_sinvert_s7_models()[0].model
        self.assertFalse(self.send('sinvert_off_request').success);self.factory.assert_not_called()
    def test_changed_program_and_missing_consents_block_without_writes(self):
        self.client.checksum=999
        r=self.send('sinvert_on_request');self.assertFalse(r.success);self.assertIn('Programma',r.error)
        self.client.checksum=123;self.client.mk[55]=0
        r=self.send('sinvert_on_request');self.assertFalse(r.success);self.assertIn('consensi',r.error)
        self.assertEqual(self.client.writes,[])
    def test_on_uses_only_native_bit_and_withdraws_pulse_without_clearing_other_bits(self):
        r=self.send('sinvert_on_request')
        self.assertTrue(r.success);self.assertFalse(r.diagnostics['physical_execution_confirmed'])
        self.assertEqual(self.client.writes,[('BIT',274,b'\1'),('BIT',274,b'\0')])
        self.assertEqual(self.client.mk[34],128)
        rows=[json.loads(s) for s in self.audit.read_text().splitlines()]
        self.assertEqual(rows[0]['phase'],'before_write');self.assertEqual(rows[-1]['phase'],'session_closed')
        self.assertTrue(any(row['phase']=='completed' for row in rows))
    def test_off_does_not_automatically_clear_the_plc_owned_stop(self):
        self.client.mk[55]=0
        self.assertTrue(self.send('sinvert_off_request').success)
        self.assertEqual(self.client.writes,[('BIT',275,b'\1')])
    def test_power_preserves_fraction_and_targets_only_canonical_reference(self):
        point=next(p for p in self.model.command_points if p.key=='sinvert_power_reference_raw')
        r=self.send(point.key,1.25,replace(point,address=999,protocol_meta={**point.protocol_meta,'db':999}))
        self.assertTrue(r.success);self.assertTrue(r.diagnostics['copied'])
        self.assertEqual(self.client.writes,[('DB',511,32,struct.pack('>f',1.25))])
    def test_power_requires_explicit_limit_external_consents_and_finite_value(self):
        self.device.connection_settings['sinvert_reference_max_raw']=0
        self.assertFalse(self.send('sinvert_power_reference_raw',1).success);self.factory.assert_not_called()
        self.device.connection_settings['sinvert_reference_max_raw']=100
        self.assertFalse(self.send('sinvert_power_reference_raw',float('nan')).success)
        self.assertFalse(self.send('sinvert_power_reference_raw',101).success)
        self.client.dbs[100][135]=1
        self.assertFalse(self.send('sinvert_power_reference_raw',1).success)
        self.client.dbs[100][135]=3;self.client.dbs[3][0]=0
        self.assertFalse(self.send('sinvert_power_reference_raw',1).success)
        self.assertEqual(self.client.writes,[])
    def test_copy_failure_is_uncertain_and_never_retries_a_write(self):
        self.client.copy=False
        r=self.send('sinvert_power_reference_raw',1)
        self.assertFalse(r.success);self.assertTrue(r.diagnostics['write_accepted'])
        self.assertEqual(r.diagnostics['stage'],'uncertain');self.assertEqual(len(self.client.writes),1)
    def test_raw_commissioning_reference_is_not_a_fleet_percent_command(self):
        self.assertIsNone(active_power_limit_resolver.resolve_for_write(self.model,50))
        self.assertIsNone(active_power_limit_resolver.build_overview_command_alias(self.model)[0])

    def test_timeout_after_power_write_is_uncertain_and_not_retried(self):
        def write_then_timeout(db,offset,data):
            self.client.writes.append(('DB',db,offset,bytes(data)))
            raise TimeoutError('reply lost after transmission')
        self.client.db_write=write_then_timeout
        r=self.send('sinvert_power_reference_raw',1)
        self.assertFalse(r.success);self.assertTrue(r.diagnostics['write_attempted'])
        self.assertFalse(r.diagnostics['write_accepted']);self.assertEqual(r.diagnostics['stage'],'uncertain')
        self.assertEqual(len(self.client.writes),1)

    def test_another_writer_overriding_reference_is_reported_as_uncertain(self):
        original=self.client.db_write
        def overwrite(db,offset,data):
            original(db,offset,data);self.client.dbs[511][32:36]=bytes(4)
        self.client.db_write=overwrite
        r=self.send('sinvert_power_reference_raw',1)
        self.assertFalse(r.success);self.assertFalse(r.diagnostics['source_matches'])
        self.assertTrue(r.diagnostics['copied']);self.assertEqual(len(self.client.writes),1)

    def test_invalid_position_count_prevents_even_off_writes(self):
        self.client.dbs[100][6:8]=bytes(2)
        self.assertFalse(self.send('sinvert_off_request').success)
        self.assertEqual(self.client.writes,[])


class SinvertDiscoveryTests(unittest.TestCase):
    def request(self,**kwargs):
        return DeviceDiscoveryTcpRequest(host_start='192.0.2.1',host_end='192.0.2.1',
          port_start=102,port_end=102,timeout_seconds=1,retries=0,unit_ids=[1,2,3],**kwargs)
    def test_native_probe_requires_cpu_layout_and_readable_db_not_only_open_port(self):
        client=ControlClient()
        client.get_block_info=lambda kind,n:SimpleNamespace(MC7Size=DISCOVERY_LAYOUT[n])
        result=probe_sinvert('192.0.2.1',102,1,client_factory=lambda:client)
        self.assertEqual(result['rack'],0);self.assertTrue(client.closed);self.assertEqual(client.writes,[])
        client.get_block_info=lambda kind,n:SimpleNamespace(MC7Size=1)
        with self.assertRaises(ValueError):probe_sinvert('192.0.2.1',102,1,client_factory=lambda:client)
    def test_sinvert_discovery_does_not_send_modbus_or_repeat_unit_ids(self):
        identity={'cpu':'CPU 315-2 DP','serial':'test','rack':0,'slot':2,'raw':[0]}
        with patch('app.services.sinvert_s7_discovery.probe_sinvert',return_value=identity) as probe,patch('app.services.protocol_test_service.ModbusTcpClient') as modbus:
            response=ProtocolTestService()._discover_tcp(self.request(preferred_brand='SINVERT'))
        probe.assert_called_once();modbus.assert_not_called()
        self.assertEqual(response.request_count,1);self.assertEqual(response.results[0].function,'s7')
        self.assertEqual(response.results[0].candidate_profiles[0].protocol,'s7_tcp')
    def test_old_sinvert_modbus_profile_is_not_rerouted_to_s7(self):
        payload=self.request(preferred_brand='SINVERT',preferred_model='Modbus TCP Inverter')
        payload=payload.model_copy(update={'port_start':502,'port_end':502})
        service=ProtocolTestService()
        with patch.object(service,'_discover_tcp_endpoint',return_value=([],1)) as modbus,patch('app.services.sinvert_s7_discovery.probe_sinvert') as s7:
            service._discover_tcp(payload)
        modbus.assert_called_once();s7.assert_not_called()

    def test_s7_scan_retries_reads_and_returns_precise_probe_errors(self):
        payload=self.request(preferred_brand='SINVERT').model_copy(update={'retries':1})
        with patch('app.services.sinvert_s7_discovery.probe_sinvert',side_effect=ValueError('DB120 incompatible')) as probe:
            response=ProtocolTestService()._discover_tcp(payload)
        self.assertEqual(probe.call_count,2);self.assertEqual(response.request_count,2)
        self.assertEqual(response.results,[]);self.assertIn('DB120 incompatible',response.errors[0])

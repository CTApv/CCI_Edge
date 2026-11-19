from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch
import struct
import unittest

from app.catalog.sinvert_ra1_catalog import (
    RA1_BRAND, RA1_MODEL, RA1_DRIVER, RA1_BLOCKS, RA1_DB_SIZES, build_sinvert_ra1_models,
)
from app.catalog.sinvert_s7_catalog import build_sinvert_s7_models
from app.services.sinvert_ra1_service import SinvertRa1Service, build_ra1_monitor
from app.services.inverter_io_service import inverter_io_service
from snap7.type import Block


class Ra1ReadOnlyPlc:
    def __init__(self):
        self.dbs={db:bytearray(size) for db,size in {**RA1_DB_SIZES,3:254,400:222}.items()}
        self.mk=bytearray(200);self.mk[51]=15;self.mk[55]=8
        self.metadata_reads=0;self.reads=[];self.bad_block=None;self.bad_db=None
        self.bad_cpu=False;self.unreadable_db=None;self.closed=False
        values={0:1,2:440,4:504,6:0,8:1864,16:1,18:440,20:944,22:0,28:64}
        for offset,value in values.items():struct.pack_into('>H',self.dbs[600],offset,value)
        struct.pack_into('>f',self.dbs[944],32,450.0)
        struct.pack_into('>f',self.dbs[570],2,450.0)
        struct.pack_into('>H',self.dbs[100],6,16)

    def connect(self,*args,**kwargs):pass
    def disconnect(self):self.closed=True
    def destroy(self):pass
    def get_cpu_info(self):return SimpleNamespace(ModuleTypeName=b'OTHER' if self.bad_cpu else b'CPU 315-2 DP')
    def get_block_info(self,kind,number):
        self.metadata_reads+=1
        if kind==Block.DB:
            return SimpleNamespace(MC7Size=RA1_DB_SIZES[number]+(1 if number==self.bad_db else 0))
        prefix='OB' if kind==Block.OB else 'FC' if kind==Block.FC else 'FB'
        name=prefix+str(number);size,checksum=RA1_BLOCKS[name]
        return SimpleNamespace(MC7Size=size,CheckSum=checksum+(1 if name==self.bad_block else 0))
    def db_read(self,db,start,size):
        self.reads.append((db,start,size))
        if db==self.unreadable_db:raise ConnectionError('read failed')
        return self.dbs[db][start:start+size]
    def read_area(self,area,db,start,size):return self.mk[start:start+size]
    def db_write(self,*args,**kwargs):raise AssertionError('RA1 must never write')
    def write_area(self,*args,**kwargs):raise AssertionError('RA1 must never write')


class SinvertRa1Tests(unittest.TestCase):
    def setUp(self):
        self.plc=Ra1ReadOnlyPlc();self.service=SinvertRa1Service(lambda:self.plc)
        self.model=build_sinvert_ra1_models()[0]
        self.device=SimpleNamespace(brand=RA1_BRAND,model=RA1_MODEL,protocol='s7_tcp',transport='tcp',
                                    connection_settings={'host':'192.0.2.42','timeout_seconds':5})

    def read(self):return self.service.read_points(self.device,self.model.telemetry_points)

    def test_ra1_reads_correct_direct_buffer_and_own_diagnostics(self):
        result=self.read();monitor=build_ra1_monitor(result.values)
        self.assertTrue(monitor['program_verified'])
        self.assertTrue(monitor['cp_parameters_match'])
        self.assertEqual(monitor['reference_a'],450)
        self.assertEqual(monitor['regulator_a'],450)
        self.assertEqual(monitor['position_count'],16)
        self.assertFalse(monitor['writes_enabled'])
        self.assertTrue(any('disabilitato' in r for r in monitor['blockers']))
        self.assertTrue(self.plc.closed)
        self.assertEqual(result.errors,{})

    def test_program_checks_all_reference_blocks_and_caches_only_reads(self):
        self.read();initial=self.plc.metadata_reads
        self.assertEqual(initial,len(RA1_BLOCKS)+len(RA1_DB_SIZES))
        self.read();self.assertEqual(self.plc.metadata_reads,initial)
        self.service._verified.clear();self.plc.bad_block='FC30'
        with self.assertRaisesRegex(ValueError,'FC30'):self.read()
        self.assertFalse(self.service._verified)

    def test_cpu_code_or_layout_mismatch_blocks_values(self):
        for change in ('cpu','code','layout'):
            with self.subTest(change=change):
                plc=Ra1ReadOnlyPlc()
                if change=='cpu':plc.bad_cpu=True
                elif change=='code':plc.bad_block='OB1'
                else:plc.bad_db=944
                service=SinvertRa1Service(lambda:plc)
                with self.assertRaises(ValueError):service.read_points(self.device,self.model.telemetry_points)
                self.assertFalse(plc.reads)
                self.assertTrue(plc.closed)

    def test_mutated_point_rejected_before_network(self):
        with patch.object(self.plc,'connect') as connect:
            for point in [replace(self.model.telemetry_points[0],address=0),
                          replace(self.model.telemetry_points[0],writable=True)]:
                with self.assertRaises(ValueError):self.service.read_points(self.device,[point])
            connect.assert_not_called()

    def test_failed_span_returns_missing_values_not_zero(self):
        self.plc.unreadable_db=944;result=self.read();monitor=build_ra1_monitor(result.values)
        self.assertIsNone(monitor['reference_a'])
        self.assertIn('ra1_received_reference_a',result.errors)
        self.assertEqual(monitor['regulator_a'],450)

    def test_changed_cp_parameters_are_visible_as_blocker(self):
        struct.pack_into('>H',self.plc.dbs[600],20,511)
        monitor=build_ra1_monitor(self.read().values)
        self.assertFalse(monitor['cp_parameters_match'])
        self.assertTrue(any('Parametri CP' in r for r in monitor['blockers']))

    def test_reference_nan_is_unavailable(self):
        struct.pack_into('>f',self.plc.dbs[944],32,float('nan'))
        result=self.read();self.assertIsNone(result.values['ra1_received_reference_a'])
        self.assertIn('ra1_received_reference_a',result.errors)

    def test_bulk_reads_yield_endpoint_without_sharing_a_client(self):
        from threading import Thread, Event
        from app.services.sinvert_s7_service import sinvert_s7_service
        waiting=Event();acquired=Event();threads=[]
        original=self.plc.db_read
        lock=sinvert_s7_service.endpoint_lock('192.0.2.42',102,0,2)
        def other_owner():
            waiting.set()
            if lock.acquire(timeout=2):
                acquired.set();lock.release()
        def read(db,start,size):
            if not threads:
                t=Thread(target=other_owner);threads.append(t);t.start();waiting.wait(.5)
            else:self.assertTrue(acquired.is_set(),'A complete telemetry batch must not starve the CP owner')
            return original(db,start,size)
        self.plc.db_read=read
        self.read()
        for thread in threads:thread.join(timeout=2)
        self.assertTrue(acquired.is_set())

    def test_manual_commands_are_catalogued_but_never_use_generic_or_legacy_fallback(self):
        self.assertEqual(len(self.model.command_points),16)
        self.assertTrue(all(p.protocol_meta['manual_only'] for p in self.model.command_points))
        for point in self.model.command_points:
            result=inverter_io_service.write_command(self.device,point,1)
            self.assertFalse(result.success)
            self.assertFalse(result.diagnostics['write_attempted'])
        old=build_sinvert_s7_models()[1].command_points[0]
        with patch('app.services.sinvert_s7_command_service.sinvert_s7_command_service.write') as legacy:
            result=inverter_io_service.write_command(self.device,old,1)
            self.assertFalse(result.success)
            self.assertFalse(result.diagnostics['write_attempted'])
            legacy.assert_not_called()

    def test_catalog_is_separate_and_old_profiles_remain_present(self):
        from app.catalog.inverter_catalog import get_inverter_catalog
        models=get_inverter_catalog()
        self.assertTrue(any(m.brand==RA1_BRAND and m.model==RA1_MODEL for m in models))
        for old in build_sinvert_s7_models():
            self.assertIn(old,models)
        self.assertEqual(self.model.catalog_meta['source_version'],'KOMM 3.0 / REGEL 3.9')

    def test_io_and_heartbeat_use_ra1_instead_of_legacy_adapter(self):
        result=self.read()
        with patch('app.services.inverter_io_service.sinvert_ra1_service.read_points',return_value=result) as own, \
             patch('app.services.inverter_io_service.sinvert_s7_service.read_points') as legacy:
            read=inverter_io_service.read_telemetry(self.device,self.model)
            heartbeat=inverter_io_service.read_heartbeat(self.device,self.model)
            self.assertEqual(read.unit_argument_style,RA1_DRIVER)
            self.assertEqual(heartbeat.values['ra1_rx_db'],944)
            self.assertEqual(own.call_count,2)
            legacy.assert_not_called()

    def test_ra1_telemetry_presentation_does_not_apply_legacy_semantics(self):
        from app.services.polling_engine import _build_telemetry_points
        values=self.read().values
        with patch('app.services.polling_engine.build_sinvert_monitor',side_effect=AssertionError('legacy monitor')):
            items=_build_telemetry_points(self.model,values)
        received=next(p for p in items if p.key=='ra1_received_reference_a')
        self.assertEqual(received.value,450)
        self.assertEqual(received.unit,'')


if __name__=='__main__':unittest.main()

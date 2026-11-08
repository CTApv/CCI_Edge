import json
import struct
import unittest
from dataclasses import replace
from unittest.mock import patch

from app.catalog.sinvert_s7_catalog import build_sinvert_s7_models
from app.schemas.device_schemas import DeviceCreate, DeviceResponse
from app.services.inverter_io_service import InverterIoService
from app.services.sinvert_s7_service import SinvertS7Service


class FakeClient:
    def __init__(self, buffers):
        self.buffers=buffers;self.reads=[];self.closed=False
    def connect(self,*args,**kwargs):self.endpoint=(args,kwargs)
    def db_read(self,db,offset,size):
        self.reads.append((db,offset,size))
        result=self.buffers.get((db,offset,size),RuntimeError('DB unavailable'))
        if isinstance(result,list):result=result.pop(0)
        if isinstance(result,Exception):raise result
        return result
    def read_area(self,area,db,offset,size):
        return self.db_read(0,offset,size)
    def disconnect(self):self.closed=True


class SinvertS7ServiceTests(unittest.TestCase):
    def setUp(self):
        self.model=build_sinvert_s7_models()[0]
        self.settings={'host':'192.0.2.1','port':102,'rack':0,'slot':2,'timeout_seconds':5}

    def test_big_endian_reference_and_shared_boolean_byte(self):
        points=self.model.telemetry_points[:3]
        client=FakeClient({(100,135,1):b'\x01',(511,10,4):struct.pack('>f',1.25)})
        result=SinvertS7Service(lambda:client).read_points(self.settings,points)
        self.assertEqual(result.values['external_reference_raw'],1.25)
        self.assertTrue(result.values['external_copy_enabled_a'])
        self.assertFalse(result.values['external_copy_enabled_b'])
        self.assertEqual(client.reads.count((100,135,1)),1)
        self.assertEqual(result.errors,{})
        self.assertTrue(client.closed)

    def test_missing_point_stays_none_with_explicit_quality(self):
        points=[self.model.telemetry_points[0],self.model.telemetry_points[2]]
        client=FakeClient({(100,135,1):b'\0'})
        result=SinvertS7Service(lambda:client).read_points(self.settings,points)
        self.assertIsNone(result.values['external_reference_raw'])
        self.assertEqual(result.values['s7_failed_points'],1)
        self.assertIn('external_reference_raw',json.loads(result.values['s7_read_errors']))

    def test_configured_read_retry_remains_inside_one_sample(self):
        client=FakeClient({(511,10,4):[RuntimeError('temporary'),struct.pack('>f',1.0)]})
        result=SinvertS7Service(lambda:client).read_points({**self.settings,'retries':1},[self.model.telemetry_points[2]])
        self.assertEqual(result.values['external_reference_raw'],1.0)
        self.assertEqual(len(client.reads),2)

    def test_short_response_is_not_decoded_or_padded(self):
        client=FakeClient({(511,10,4):b'\0\0'})
        with self.assertRaisesRegex(RuntimeError,'incompleta'):
            SinvertS7Service(lambda:client).read_points(self.settings,[self.model.telemetry_points[2]])
        self.assertTrue(client.closed)

    def test_nan_cannot_enter_json_telemetry(self):
        points=[self.model.telemetry_points[0],self.model.telemetry_points[2]]
        client=FakeClient({(100,135,1):b'\0',(511,10,4):struct.pack('>f',float('nan'))})
        result=SinvertS7Service(lambda:client).read_points(self.settings,points)
        self.assertIsNone(result.values['external_reference_raw'])
        json.dumps(result.values,allow_nan=False)

    def test_invalid_profile_is_rejected_before_connection(self):
        for point in [replace(self.model.telemetry_points[2],address=63),
                      replace(self.model.telemetry_points[2],scale=100),
                      replace(self.model.telemetry_points[2],unit='kW')]:
            with self.subTest(point=point),patch.object(FakeClient,'connect') as connect:
                with self.assertRaises(ValueError):
                    SinvertS7Service(lambda:FakeClient({})).read_points(self.settings,[point])
                connect.assert_not_called()

    def test_catalog_and_override_cannot_enable_writes(self):
        self.assertEqual(self.model.command_points,[])
        device=DeviceResponse(name='Bench',brand=self.model.brand,model=self.model.model,protocol='s7_tcp',transport='tcp',
                              connection_settings=self.settings,status='pending',device_id='bench',created_at='2026-11-04T00:00:00Z')
        point=replace(self.model.telemetry_points[2],writable=True,kind='command')
        with patch('app.services.inverter_io_service.sinvert_s7_service.read_points') as read:
            result=InverterIoService().write_command(device,point,1)
        self.assertFalse(result.success)
        self.assertTrue(result.diagnostics['read_only'])
        read.assert_not_called()

    def test_device_validation_rejects_invalid_rack(self):
        payload=dict(name='Bench',brand=self.model.brand,model=self.model.model,protocol='s7_tcp',transport='tcp',
                     connection_settings={**self.settings,'rack':8})
        with self.assertRaises(ValueError):DeviceCreate(**payload)
        payload['connection_settings']['rack']=0
        result=DeviceCreate(**payload)
        self.assertEqual(result.connection_settings['slot'],2)

    def test_runtime_polls_all_points_without_fabricating_measurements_or_history(self):
        from app.services.polling_engine import PollingEngine, poll_device
        buffers={}
        for point in self.model.telemetry_points:
            area,db,offset,size,_=SinvertS7Service._spec(point)
            buffers[(db if area=='DB' else 0,offset,size)]=b'\0'*size
        device=DeviceResponse(name='Bench',brand=self.model.brand,model=self.model.model,protocol='s7_tcp',transport='tcp',
                              connection_settings=self.settings,status='pending',device_id='bench',created_at='2026-11-04T00:00:00Z')
        with patch('app.services.inverter_io_service.sinvert_s7_service',SinvertS7Service(lambda:FakeClient(buffers))):
            entry=poll_device(device)
        self.assertIsNotNone(entry)
        self.assertEqual(len(entry.telemetry),len(self.model.telemetry_points))
        self.assertFalse(entry.metrics.physical_measurements_available)
        self.assertIsNone(entry.diagnostics.last_error)
        with patch('app.services.polling_engine.live_cache') as cache,patch('app.services.polling_engine.power_history_service') as history:
            cache.get.return_value=None
            PollingEngine()._store_polled_entry(device,entry)
            cache.append_power_sample.assert_not_called()
            history.append_sample.assert_not_called()

    def test_partial_read_errors_are_exposed_by_the_app_polling_api(self):
        from app.services.polling_engine import poll_device
        buffers={}
        for point in self.model.telemetry_points:
            area,db,offset,size,_=SinvertS7Service._spec(point)
            buffers[(db if area=='DB' else 0,offset,size)]=b'\0'*size
        del buffers[(511,10,4)]
        device=DeviceResponse(name='Bench',brand=self.model.brand,model=self.model.model,protocol='s7_tcp',transport='tcp',
                              connection_settings=self.settings,status='pending',device_id='bench',created_at='2026-11-04T00:00:00Z')
        with patch('app.services.inverter_io_service.sinvert_s7_service',SinvertS7Service(lambda:FakeClient(buffers))):
            entry=poll_device(device)
        self.assertEqual(entry.diagnostics.failed_points,1)
        self.assertIn('external_reference_raw',entry.diagnostics.read_errors)
        self.assertIsNone(next(p.value for p in entry.telemetry if p.key=='external_reference_raw'))


if __name__=='__main__':unittest.main()

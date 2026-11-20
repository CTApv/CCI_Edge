import struct
import socketserver
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.catalog.sma_stp60_catalog import build_sma_stp60_models, MANAGER_MODEL, SMA_DRIVER
from app.catalog.inverter_catalog import get_inverter_catalog
from app.services.sma_stp60_service import SmaStp60Service
from app.services.inverter_io_service import inverter_io_service
from app.services.fleet_dispatch_service import FleetDispatchService
from app.services.active_power_limit_readback_resolver import active_power_limit_readback_resolver
from app.schemas.device_overview_schemas import DeviceTelemetryPoint


class Response:
    def __init__(self, registers=(), error=False):
        self.registers = list(registers)
        self.error = error
    def isError(self):
        return self.error


class Fixture:
    """Independent fixed address fixture taken from SMA TI en-15 pp.18–33."""
    def __init__(self, unit=125, manager=True):
        self.unit, self.writes = unit, []
        self.words = {i: 0xffff for i in range(40000, 40369)}
        self.words.update({40000:0x5375,40001:0x6e53,40002:1,40003:66,40068:unit,
            40185:103,40186:50,40199:1234,40200:2,40209:0,40210:12345,40211:3,
            40218:250,40222:0xffff,40224:60,40237:120,40238:26,40240:600,40241:3,40265:121,40266:30,
            40267:600,40287:3,40343:123,40344:24,40347:1,40348:10000,
            40352:1,40366:0xfffe})
        self.text(40004, 'SMA',16)
        self.text(40020, 'SMA Inverter Manager' if manager else 'STP60',16)
        self.text(40044, '1.50',8)
        self.text(40052, 'TEST0001',16)
        self.reject_write = False
        self.mismatch = False
    def text(self, address, value, length):
        self.words.update({address+i:w for i,w in enumerate(struct.unpack('>'+'H'*length,value.encode().ljust(length*2,b'\0')))})
    def read_holding_registers(self, address, *, count, device_id):
        if device_id != self.unit:
            return Response(error=True)
        return Response(self.words.get(address+i,0xffff) for i in range(count))
    def write_registers(self, address, values, *, device_id):
        self.writes.append((address,list(values),device_id))
        if not self.reject_write and not self.mismatch:
            self.words.update({address+i:w for i,w in enumerate(values)})
        return Response(error=self.reject_write)


class SmaTests(unittest.TestCase):
    def setUp(self):
        self.service = SmaStp60Service()
        self.models = build_sma_stp60_models()
        self.device = SimpleNamespace(protocol='modbus_tcp',transport='tcp',brand='SMA',model=MANAGER_MODEL,
            profile_overrides={},connection_settings={'host':'127.0.0.1','port':502,'unit_id':125})
        self.clock = 0.
        def sleep(seconds):
            self.clock += seconds
        self.time_patch = patch('app.services.sma_stp60_service.monotonic',side_effect=lambda:self.clock)
        self.sleep_patch = patch('app.services.sma_stp60_service.sleep',side_effect=sleep)
        self.time_patch.start();self.sleep_patch.start()
        self.addCleanup(self.time_patch.stop);self.addCleanup(self.sleep_patch.stop)
    def write(self, fake, key, value):
        point=next(p for p in self.models[0].command_points if p.key==key)
        return self.service.write_point(self.device,point,value)
    def connect(self, fake):
        return patch('app.services.sma_stp60_service.connection_manager.execute_modbus_tcp',
            side_effect=lambda **kwargs:kwargs['operation'](fake))
    def test_catalog_and_individual_read_only(self):
        self.assertEqual(len([m for m in get_inverter_catalog() if m.brand=='SMA']),2)
        self.assertEqual(len(self.models[0].command_points),3)
        self.assertEqual(self.models[1].command_points,[])
        self.assertTrue(all(not m.catalog_meta['field_tested'] for m in self.models))
    def test_telemetry_scaling_identity_and_nan(self):
        with self.connect(Fixture()):
            values=self.service.read_points(self.device,self.models[0].telemetry_points)
        result=inverter_io_service._apply_point_scaling(self.models[0].telemetry_points,values)
        self.assertAlmostEqual(result['active_power_kw'],123.4)
        self.assertAlmostEqual(result['temperature_c'],25)
        self.assertEqual(result['power_limit_pct'],100)
        self.assertNotIn('vendor_events_1',result)
        self.assertEqual(result['maximum_power_kw'],600)
        self.assertEqual(result['rated_power_kw'],600)
    def test_single_register_writes_and_ro_fields_untouched(self):
        for key,value,address,raw in [('active_power_limit',90,40348,9000),('start_inverter',1,40347,1),('stop_inverter',0,40347,0)]:
            fake=Fixture()
            with self.connect(fake):r=self.write(fake,key,value)
            self.assertEqual(fake.writes,[(address,[raw],125)])
            self.assertTrue(r['readback_confirmed']);self.assertFalse(r['physical_execution_confirmed'])
            self.assertEqual(fake.words[40352],1)
    def test_wrong_identity_common_header_unit_and_controls_block_writes(self):
        for mutation in [lambda f:f.text(40004,'Other',16),lambda f:f.text(40020,'STP60',16),
                lambda f:f.words.update({40068:126}),lambda f:f.words.update({40003:65}),
                lambda f:f.words.update({40343:124}),lambda f:f.words.update({40366:0xffff})]:
            fake=Fixture();mutation(fake)
            with self.connect(fake),self.assertRaises(RuntimeError):self.write(fake,'active_power_limit',50)
            self.assertEqual(fake.writes,[])
    def test_write_rejection_and_readback_mismatch(self):
        for field in ['reject_write','mismatch']:
            fake=Fixture();setattr(fake,field,True)
            with self.connect(fake),self.assertRaises(RuntimeError):self.write(fake,'active_power_limit',50)
            self.assertEqual(len(fake.writes),1)
    def test_invalid_values_units_and_individual_commands(self):
        fake=Fixture()
        for value in [-1,101,float('nan'),float('inf')]:
            with self.connect(fake),self.assertRaises(ValueError):self.write(fake,'active_power_limit',value)
        for unit in [0,126,200,201,255]:
            self.device.connection_settings['unit_id']=unit
            with self.connect(fake),self.assertRaises(ValueError):self.write(fake,'active_power_limit',50)
        self.device.model=self.models[1].model;self.device.connection_settings['unit_id']=126
        with self.connect(fake),self.assertRaises(ValueError):self.write(fake,'active_power_limit',50)
        self.assertEqual(fake.writes,[])
    def test_legacy_and_individual_telemetry(self):
        for unit,manager,index in [(1,True,0),(2,False,1),(126,False,1),(167,False,1)]:
            self.device.connection_settings['unit_id']=unit;self.device.model=self.models[index].model
            with self.connect(Fixture(unit,manager)):
                result=self.service.read_points(self.device,self.models[index].telemetry_points)
            self.assertEqual(result['operating_state'],60)
    def test_pacing_shared_across_unit_ids_even_after_errors(self):
        starts=[]
        for unit in [125,126,127]:
            self.device.connection_settings['unit_id']=unit
            self.service._call(self.device,lambda:starts.append(self.clock))
        self.assertEqual(starts,[0,1,2])
        self.assertGreaterEqual(self.clock,2)
    def test_uncertain_oserror_not_replayed_by_connection_manager(self):
        fake=Fixture()
        def uncertain(*args,**kwargs):
            fake.writes.append(args)
            raise OSError('response lost')
        fake.write_registers=uncertain
        with self.connect(fake),self.assertRaises(RuntimeError):self.write(fake,'active_power_limit',50)
        self.assertEqual(len(fake.writes),1)
    def test_fleet_readback_and_broadcast_guards(self):
        target=FleetDispatchService()._resolve_target(self.device,90)
        self.assertEqual(target.eligibility,'eligible')
        telemetry=[DeviceTelemetryPoint(key='power_limit_pct',label='Limite',value=90,display_value='90',unit='%'),
            DeviceTelemetryPoint(key='power_limit_enabled',label='Stato',value=1,display_value='1')]
        result=active_power_limit_readback_resolver.evaluate(inverter_model=self.models[0],telemetry=telemetry,
            desired_percent=90,resolved_value=90,resolved_unit='%',resolved_max_value=100)
        self.assertTrue(result.confirmed)
        point=self.models[0].command_points[0]
        self.assertIsNone(inverter_io_service.build_command_broadcast_signature(self.device,point,90))
        self.assertFalse(inverter_io_service.write_command_broadcast(self.device,point,90).success)

    def test_group_and_individual_cannot_double_count_the_same_manager(self):
        from app.services.device_service import DeviceService
        service=object.__new__(DeviceService)
        self.device.device_id='manager'
        service._devices=[self.device]
        candidate=SimpleNamespace(brand='SMA',model=self.models[1].model,protocol='modbus_tcp',transport='tcp',
            connection_settings={'host':'127.0.0.1','port':502,'unit_id':126})
        with self.assertRaisesRegex(ValueError,'duplica'):
            service._ensure_unique_endpoint_unit(candidate)

    def test_real_modbus_tcp_framing_read_write_and_readback(self):
        fake=Fixture()
        class Handler(socketserver.BaseRequestHandler):
            def exact(self,n):
                data=b''
                while len(data)<n:
                    chunk=self.request.recv(n-len(data))
                    if not chunk:return None
                    data+=chunk
                return data
            def handle(self):
                while True:
                    header=self.exact(7)
                    if header is None:return
                    tid,proto,length,unit=struct.unpack('>HHHB',header)
                    pdu=self.exact(length-1)
                    if not pdu:return
                    if pdu[0]==3:
                        address,count=struct.unpack('>HH',pdu[1:5])
                        response=fake.read_holding_registers(address,count=count,device_id=unit)
                        body=bytes([3,count*2])+struct.pack('>'+'H'*count,*response.registers)
                    elif pdu[0]==16:
                        address,count=struct.unpack('>HH',pdu[1:5])
                        words=struct.unpack('>'+'H'*count,pdu[6:])
                        fake.write_registers(address,words,device_id=unit)
                        body=pdu[:5]
                    else:body=bytes([pdu[0]|128,1])
                    self.request.sendall(struct.pack('>HHHB',tid,proto,len(body)+1,unit)+body)
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads=True
            allow_reuse_address=True
        server=Server(('127.0.0.1',0),Handler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        self.device.connection_settings['port']=server.server_address[1]
        try:
            values=self.service.read_points(self.device,self.models[0].telemetry_points)
            self.assertEqual(values['power_limit_pct'],100)
            result=self.write(fake,'active_power_limit',95)
            self.assertTrue(result['readback_confirmed'])
            self.assertEqual(fake.writes,[(40348,[9500],125)])
        finally:
            server.shutdown();server.server_close();thread.join(timeout=2)


if __name__=='__main__':unittest.main()

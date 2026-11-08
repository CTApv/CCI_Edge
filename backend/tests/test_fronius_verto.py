import math
import struct
import socketserver
import threading
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from app.catalog.fronius_verto_catalog import MAP_SOURCE, build_fronius_verto_models
from app.catalog.inverter_catalog import get_inverter_catalog
from app.services.fronius_sunspec_service import FroniusSunSpecService
from app.services.inverter_io_service import inverter_io_service
from app.services.active_power_limit_readback_resolver import active_power_limit_readback_resolver
from app.services.fleet_dispatch_service import FleetDispatchService
from app.schemas.device_overview_schemas import DeviceTelemetryPoint


class Response:
    def __init__(self, words=(), error=False):
        self.registers, self.error = list(words), error

    def isError(self):
        return self.error


class RegisterDevice:
    """SunSpec register fixture; no hardware or private data."""
    def __init__(self, variant='3mppt', fmt='float', *, relocated=False):
        self.words = {40000: 0x5375, 40001: 0x6e53}
        self.writes = []
        self.bases = {}
        self.map = MAP_SOURCE['maps'][f'{variant}_{fmt}']['models']
        addr = 40002
        for did, definition in self.map.items():
            did, length = int(did), definition['length']
            if relocated and did == 123:
                self.words.update({addr: 65000, addr+1: 2, addr+2: 0, addr+3: 0})
                addr += 4
            self.bases[did] = addr
            self.words.update({i: 0 for i in range(addr, addr+length+2)})
            self.words[addr], self.words[addr+1] = did, length
            addr += length+2
        self.words.update({addr: 0xffff, addr+1: 0})
        self.text('Mn', 'Fronius')
        self.text('Md', 'Verto 30.0 Plus' if variant == 'plus' else 'Verto 25.0' if variant == '4mppt' else 'Verto 15.0')
        self.set(123, 'WMaxLimPct_SF', [0xfffe])
        self.set(123, 'WMaxLimPct', [10000])
        self.set(123, 'WMaxLimPct_RvrtTms', [60])
        self.set(123, 'WMaxLimPct_RmpTms', [5])
        self.set(123, 'Conn_RvrtTms', [90])
        did = 113 if fmt == 'float' else 103
        if fmt == 'float':
            self.set(did, 'W', struct.unpack('>HH', struct.pack('>f', 12345.0)))
        else:
            self.set(did, 'W', [12345])
            self.set(did, 'W_SF', [0])

    def set(self, did, name, words):
        field = self.map[str(did)]['fields'][name]
        self.words.update({self.bases[did]+field['offset']+i: v for i, v in enumerate(words)})

    def text(self, name, value):
        length = self.map['1']['fields'][name]['length']
        self.set(1, name, struct.unpack('>'+str(length)+'H', value.encode().ljust(length*2, b'\0')))

    def read_holding_registers(self, address, *, count, device_id):
        if device_id != 1:
            return Response(error=True)
        return Response(self.words.get(address+i, 0xffff) for i in range(count))

    def write_registers(self, address, values, *, device_id):
        self.writes.append((address, list(values), device_id))
        self.words.update({address+i: v for i, v in enumerate(values)})
        return Response()


class FroniusTests(unittest.TestCase):
    def setUp(self):
        self.service = FroniusSunSpecService()
        self.model = build_fronius_verto_models('modbus_tcp', 'tcp')[0]
        self.device = SimpleNamespace(protocol='modbus_tcp', transport='tcp',
            connection_settings={'host': '127.0.0.1', 'port': 1502, 'unit_id': 1})

    def command(self, fake, key, value, model=None):
        point = next(p for p in (model or self.model).command_points if p.key == key)
        return self.service._write_point_with_client(client=fake, device=self.device,
            unit_value=1, point=point, value=value)

    def test_catalog_series_protocol_and_no_meter_alias(self):
        models = [m for m in get_inverter_catalog() if m.brand == 'Fronius' and m.model.startswith('Verto ')]
        self.assertEqual(len(models), 28)
        self.assertEqual(len({(m.model,m.protocol,m.transport) for m in models}), 28)
        for model in models:
            self.assertEqual(model.defaults['test_register'], 40000)
            self.assertEqual(len(model.command_points), 4)
            self.assertFalse(model.catalog_meta['field_tested'])
            self.assertEqual(any(p.key == 'battery_soc_pct' for p in model.telemetry_points), ' Plus' in model.model)
        self.assertEqual(next(m for m in models if m.model == 'Verto 25.0').catalog_meta['mppt_count'], 4)

    def test_standard_external_fleet_target_and_enable_readback(self):
        self.device.brand='Fronius';self.device.model='Verto 15.0';self.device.profile_overrides={}
        target=FleetDispatchService()._resolve_target(self.device,60)
        self.assertEqual(target.eligibility,'eligible')
        self.assertEqual(target.command_key,'active_power_limit')
        self.assertEqual(target.resolved_value,60)
        for enabled in (0,1):
            telemetry=[DeviceTelemetryPoint(key='power_limit_pct',label='Limite potenza',value=60,display_value='60',unit='%'),
                DeviceTelemetryPoint(key='power_limit_enabled',label='Abilitato',value=enabled,display_value=str(enabled))]
            result=active_power_limit_readback_resolver.evaluate(inverter_model=self.model,telemetry=telemetry,
                desired_percent=60,resolved_value=60,resolved_unit='%',resolved_max_value=100)
            self.assertTrue(result.supported)
            self.assertEqual(result.confirmed, bool(enabled))

    def test_float_and_integer_formats_and_relocated_controls(self):
        for fmt in ('float', 'int_sf'):
            with self.subTest(fmt=fmt):
                fake = RegisterDevice(fmt=fmt, relocated=True)
                self.service = FroniusSunSpecService()
                point = next(p for p in self.model.telemetry_points if p.key == 'active_power_kw')
                raw = self.service._read_points_with_client(client=fake, device=self.device, unit_value=1, points=[point])
                self.assertAlmostEqual(inverter_io_service._apply_point_scaling([point], raw)['active_power_kw'], 12.345)
                result = self.command(fake, 'active_power_limit', 60)
                self.assertEqual(fake.writes, [(fake.bases[123]+5, [6000,0,60,5,1],1)])
                self.assertTrue(result['readback_confirmed'])
                self.assertFalse(result['physical_execution_confirmed'])

    def test_on_off_and_disable_are_separate_commands(self):
        fake = RegisterDevice()
        self.command(fake, 'start_inverter', 1)
        self.command(fake, 'stop_inverter', 0)
        self.command(fake, 'disable_power_limit', 0)
        self.assertEqual([r[1] for r in fake.writes], [[0,90,1],[0,90,0],[0]])

    def test_limits_nan_and_invalid_fixed_commands_do_not_write(self):
        for key, value in [('active_power_limit', -1), ('active_power_limit',101),
                           ('active_power_limit', math.nan), ('active_power_limit', math.inf),
                           ('start_inverter',0), ('stop_inverter',1)]:
            fake=RegisterDevice()
            with self.subTest(key=key,value=value), self.assertRaises(ValueError):
                self.command(fake,key,value)
            self.assertEqual(fake.writes,[])

    def test_missing_or_wrong_scale_factor_does_not_write(self):
        for value in (0x8000, 0xfff6, 1):
            fake=RegisterDevice();fake.set(123,'WMaxLimPct_SF',[value])
            with self.assertRaises(ValueError):self.command(fake,'active_power_limit',60)
            self.assertFalse(fake.writes)

    def test_wrong_brand_or_series_does_not_write(self):
        fake=RegisterDevice();fake.text('Mn','Other')
        with self.assertRaises(ValueError):self.command(fake,'active_power_limit',60)
        self.assertFalse(fake.writes)
        fake=RegisterDevice();fake.text('Md','Verto 20.0')
        with self.assertRaises(ValueError):self.command(fake,'active_power_limit',60)
        self.assertFalse(fake.writes)
        fake=RegisterDevice(variant='plus')
        with self.assertRaises(ValueError):self.command(fake,'active_power_limit',60)
        self.assertFalse(fake.writes)

    def test_plus_storage_map_and_controls(self):
        fake=RegisterDevice(variant='plus')
        model=next(m for m in build_fronius_verto_models('modbus_tcp','tcp') if m.model=='Verto 30.0 Plus')
        result=self.command(fake,'active_power_limit',25,model)
        self.assertTrue(result['write_accepted'])
        self.assertTrue(any(p.key=='battery_soc_pct' for p in model.telemetry_points))

    def test_unavailable_values_not_reported_as_real_measurements(self):
        for words,kind in [([0x8000],'int16'),([0xffff],'uint16'),([0x7fc0,0],'float32'),
                           ([0xffff,0xffff],'bitfield32'),([0,0,0,0],'acc64')]:
            self.assertIsNone(self.service._decode(words,kind))
        self.assertEqual(self.service._decode([0],'bitfield16'),0)

    def test_write_rejected_and_readback_mismatch(self):
        fake=RegisterDevice()
        with patch.object(fake,'write_registers',return_value=Response(error=True)):
            with self.assertRaises(RuntimeError):self.command(fake,'active_power_limit',60)
        with patch.object(fake,'write_registers',return_value=Response()):
            with self.assertRaises(RuntimeError):self.command(fake,'active_power_limit',60)

    def test_malformed_and_short_discovery_do_not_write(self):
        for mutation in ('magic','length','short'):
            fake=RegisterDevice()
            if mutation=='magic':fake.words[40000]=0
            elif mutation=='length':fake.words[40003]=0
            else:fake.read_holding_registers=lambda *a,**k:Response([1])
            with self.assertRaises((ValueError,RuntimeError)):self.command(fake,'active_power_limit',60)
            self.assertFalse(fake.writes)

    def test_no_unit_zero_or_broadcast(self):
        fake=RegisterDevice()
        with self.assertRaises(ValueError):self.service._discover_model_map(client=fake,unit_value=0)
        point=self.model.command_points[0]
        self.assertIsNone(inverter_io_service.build_command_broadcast_signature(self.device,point,60))
        self.assertFalse(inverter_io_service.write_command_broadcast(self.device,point,60).success)

    def test_io_dispatch_tcp_and_rtu(self):
        point=self.model.command_points[0]
        for protocol in ('modbus_tcp','modbus_rtu'):
            self.device.protocol=protocol
            with patch('app.services.inverter_io_service.fronius_sunspec_service.write_point',
                       return_value={'driver':'fronius_verto_sunspec'}) as write:
                self.assertTrue(inverter_io_service.write_command(self.device,point,60).success)
                write.assert_called_once()

    def test_transport_configuration_tcp_serial_and_rtu_gateway(self):
        for protocol, transport, method in [
            ('modbus_tcp','tcp','execute_modbus_tcp'),
            ('modbus_rtu','serial','execute_modbus_rtu'),
            ('modbus_rtu','tcp','execute_modbus_tcp')]:
            self.device.protocol, self.device.transport = protocol, transport
            self.device.connection_settings.update({'slave_id':7,'unit_id':3,'port':1502 if transport=='tcp' else 'COM1'})
            with patch('app.services.fronius_sunspec_service.connection_manager.'+method, return_value='sent') as execute:
                result=self.service._execute_with_client(self.device,operation_kind='command',operation=lambda *a:None)
                self.assertEqual(result,'sent')
                self.assertEqual(execute.call_args.kwargs['retries'],0)
                self.assertEqual(execute.call_args.kwargs['operation_kind'],'command')
                # Gateway uses unit_id, serial uses slave_id.
                with patch('app.services.fronius_sunspec_service.connection_manager.'+method,
                           side_effect=lambda **kw:kw['operation'](None)):
                    unit=self.service._execute_with_client(self.device,operation_kind='command',operation=lambda c,u:u)
                    self.assertEqual(unit,3 if transport=='tcp' else 7)

    def test_live_modbus_tcp_framing_end_to_end(self):
        fake=RegisterDevice(fmt='int_sf',relocated=True)
        class Handler(socketserver.StreamRequestHandler):
            def handle(self):
                while True:
                    header=self.rfile.read(7)
                    if len(header)!=7:return
                    tid,pid,length,unit=struct.unpack('>HHHB',header)
                    pdu=self.rfile.read(length-1)
                    if pdu[0]==3:
                        address,count=struct.unpack('>HH',pdu[1:5])
                        words=fake.read_holding_registers(address,count=count,device_id=unit).registers
                        result=bytes([3,2*count])+struct.pack('>'+str(count)+'H',*words)
                    elif pdu[0]==16:
                        address,count,size=struct.unpack('>HHB',pdu[1:6])
                        words=struct.unpack('>'+str(count)+'H',pdu[6:6+size])
                        fake.write_registers(address,words,device_id=unit)
                        result=bytes([16])+struct.pack('>HH',address,count)
                    else:return
                    self.wfile.write(struct.pack('>HHHB',tid,pid,len(result)+1,unit)+result)
                    self.wfile.flush()
        class Server(socketserver.ThreadingTCPServer):
            daemon_threads=True
        server=Server(('127.0.0.1',0),Handler)
        worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
        try:
            self.device.connection_settings['port']=server.server_address[1]
            point=next(p for p in self.model.telemetry_points if p.key=='active_power_kw')
            data=self.service.read_points(self.device,[point])
            self.assertEqual(data['active_power_kw'],12345)
            result=self.service.write_point(self.device,self.model.command_points[0],60)
            self.assertTrue(result['readback_confirmed'])
            self.assertEqual(fake.writes[-1][1],[6000,0,60,5,1])
        finally:
            server.shutdown();server.server_close();worker.join(timeout=2)


if __name__ == '__main__':
    unittest.main()

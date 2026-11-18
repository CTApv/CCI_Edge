from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
import socketserver
import struct
import threading
import unittest
from unittest.mock import patch
from pymodbus import FramerType
from app.catalog.fimer_pvs_catalog import PVS_MAP, PVS_MODELS, build_fimer_pvs_models
from app.services.connection_manager import ConnectionManager
from app.services.fimer_pvs_service import FimerPvsService, decode
from app.services.inverter_io_service import inverter_io_service
from app.services.inverter_profile_resolver import inverter_profile_resolver
from app.services.active_power_limit_readback_resolver import active_power_limit_readback_resolver
from app.services.fleet_dispatch_service import FleetDispatchService


class PvsSimulator:
    """Independent in-memory device with shifted blocks and real FC03/FC16 PDUs."""
    def __init__(self, code='3P80', power=100, channels=6):
        self.words, self.bases, self.writes = {40000: 0x5375, 40001: 0x6E53}, {}, []
        self.reject = self.lost_ack = self.mismatch = False
        address = 40002
        for did, length in [(1, 66), (65000, 7), (103, 50), (120, 26), (121, 30), (122, 44), (123, 24), (160, 8+channels*20)]:
            self.bases[did] = address
            self.words.update({address+i: 0 for i in range(length+2)})
            self.words[address], self.words[address+1] = did, length
            address += length+2
        self.end = address
        self.words.update({address: 0xFFFF, address+1: 0})
        self.set(1, 'Mn', 'ABB')
        self.set(1, 'Md', '-'+code+'-')
        self.set(1, 'Vr', 'test-fw')
        self.set(1, 'Number', 'SN123')
        self.set(103, 'W', 10000)
        self.set(103, 'W_SF', 1)
        self.set(103, 'St', 4)
        self.set(103, 'TmpCab', 250)
        self.set(103, 'Tmp_SF', -1)
        self.set(120, 'WRtg', power*100)
        self.set(120, 'WRtg_SF', 1)
        self.set(121, 'WMax', power*100)
        self.set(121, 'WMax_SF', 1)
        self.set(122, 'ActWh', 2**32+123)
        self.set(123, 'WMaxLimPct_SF', -1)
        self.set(123, 'WMaxLimPct', 1000)
        self.set(123, 'WMaxLimPct_RvrtTms', 120)
        self.set(160, 'N', channels)
        self.set(160, 'DCA_SF', -1)
        self.set(160, 'DCV_SF', -1)
        self.set(160, 'DCW_SF', 0)
        for channel in range(1, channels+1):
            self.set(160, f'module/{channel}/DCV', 7500)
            self.set(160, f'module/{channel}/DCA', 105)

    def set(self, did, field, value):
        d=PVS_MAP['models'][str(did)]['fields'][field]
        address=self.bases[did]+d['offset']
        if isinstance(value,str):
            payload=value.encode().ljust(d['length']*2,b'\0')
            words=struct.unpack('>'+'H'*d['length'],payload)
        else:
            value=int(value)&((1<<(16*d['length']))-1)
            words=[(value>>(16*i))&0xFFFF for i in reversed(range(d['length']))]
        self.words.update({address+i:v for i,v in enumerate(words)})

    def read_holding_registers(self, address, *, count, device_id):
        values=[self.words.get(address+i,0xFFFF) for i in range(count)]
        if self.mismatch and self.writes and address==self.writes[-1][0]:values[0]^=1
        return SimpleNamespace(registers=values,isError=lambda:False)

    def write_registers(self,address,values,*,device_id):
        self.writes.append((address,list(values),device_id))
        if not self.reject:self.words.update({address+i:v for i,v in enumerate(values)})
        if self.lost_ack:raise ConnectionError('ACK lost after device accepted command')
        return SimpleNamespace(address=address,count=len(values),isError=lambda:self.reject)


class FimerPvsTests(unittest.TestCase):
    def setUp(self):
        self.service=FimerPvsService()
        self.model=build_fimer_pvs_models('modbus_tcp','tcp')[0]
        self.device=SimpleNamespace(brand='ABB/FIMER',model=self.model.model,protocol='modbus_tcp',transport='tcp',
            connection_settings={'host':'127.0.0.1','unit_id':1},profile_overrides={},device_id='pvs-1',name='PVS test',status='online')
        self.sim=PvsSimulator()

    def call(self,operation):
        with patch('app.services.fimer_pvs_service.connection_manager.execute_modbus_tcp',
            side_effect=lambda *a,**kw:kw['operation'](self.sim)) as manager:
            result=operation()
        if manager.called:self.assertEqual(manager.call_args.kwargs['retries'],0)
        return result

    def write(self,value=55.5,point=None):
        return self.call(lambda:self.service.write(self.device,point or self.model.command_points[0],value))

    def read(self):
        return self.call(lambda:self.service.read_points(self.device,self.model.telemetry_points))

    def test_catalog_variants_and_gateway_resolution(self):
        for protocol,transport in [('modbus_tcp','tcp'),('modbus_rtu','serial')]:
            models=build_fimer_pvs_models(protocol,transport)
            self.assertEqual({m.model for m in models},set(PVS_MODELS))
            self.assertTrue(all(not m.catalog_meta['field_tested'] for m in models))
        for name in PVS_MODELS:
            self.assertIsNotNone(inverter_profile_resolver.find_catalog_model(brand='ABB/FIMER',model=name,protocol='modbus_rtu',transport='tcp'))

    def test_dynamic_offsets_and_64_bit_energy(self):
        values=self.read()
        self.assertEqual(values['active_power_kw'],100000)
        self.assertEqual(values['temperature_c'],25)
        self.assertEqual(values['total_energy_kwh'],2**32+123)
        self.assertEqual(values['mppt_6_voltage_v'],750)
        self.assertFalse(self.sim.writes)
        self.assertNotEqual(self.sim.bases[123],40228)

    def test_two_mppt_do_not_fabricate_other_channels(self):
        self.sim=PvsSimulator(channels=2)
        values=self.read()
        self.assertEqual(values['mppt_count'],2)
        self.assertEqual(values['mppt_2_current_a'],10.5)
        self.assertIsNone(values['mppt_3_voltage_v'])
        self.assertIsNone(values['mppt_6_power_kw'])

    def test_each_profile_matches_its_own_part_number(self):
        for name,(code,power) in PVS_MODELS.items():
            with self.subTest(name=name):
                self.device.model=name
                self.sim=PvsSimulator(code,power)
                result=self.write()
                self.assertTrue(result.success,result.error)

    def test_wrong_brand_size_or_revision_blocks_every_write(self):
        for code in ['3P20','3Q15','3Q42','3P800','OTHER']:
            self.sim=PvsSimulator(code)
            self.assertFalse(self.write().success)
            self.assertFalse(self.sim.writes)
        self.sim=PvsSimulator();self.sim.set(1,'Mn','OTHER')
        self.assertFalse(self.write().success)
        self.assertFalse(self.sim.writes)

    def test_observed_b2_full_identity_reads_without_any_write(self):
        self.device.model='PVS-100-TL B2'
        for name in ['3Q4200', '-3Q4200-', '3Q42', '-3Q42-']:
            with self.subTest(name=name):
                self.sim=PvsSimulator('3Q42',100)
                self.sim.set(1,'Md',name)
                values=self.read()
                self.assertEqual(values['model_code'],name)
                self.assertEqual(values['active_power_kw'],100000)
                self.assertFalse(self.sim.writes)

    def test_b2_alias_does_not_relax_other_identity_guards(self):
        for profile,name in [
            ('PVS-100-TL','3Q4200'), ('PVS-100-TL B','3Q4200'), ('PVS-120-TL B2','3Q4200'),
            ('PVS-100-TL B2','3Q420'), ('PVS-100-TL B2','3Q4201'),
            ('PVS-100-TL B2','3Q42000'), ('PVS-100-TL B2','X3Q4200'),
            ('PVS-100-TL B2','3Q4200X'), ('PVS-100-TL B2','3Q4100'),
        ]:
            with self.subTest(profile=profile,name=name):
                self.device.model=profile
                self.sim=PvsSimulator('3Q42',100)
                self.sim.set(1,'Md',name)
                with self.assertRaisesRegex(ValueError,'diversa'):self.read()
                self.assertFalse(self.write().success)
                self.assertFalse(self.sim.writes)

    def test_fresh_identity_even_after_successful_poll(self):
        self.read();self.sim.set(1,'Md','-3Q15-')
        with self.assertRaisesRegex(ValueError,'diversa'):self.read()
        self.assertFalse(self.write().success)
        self.assertFalse(self.sim.writes)

    def test_expiring_write_includes_enable_and_readback(self):
        result=self.write()
        self.assertTrue(result.success,result.error)
        self.assertEqual(self.sim.writes,[(self.sim.bases[123]+5,[555,0,120,0,1],1)])
        self.assertTrue(result.diagnostics['readback_confirmed'])
        self.assertFalse(result.diagnostics['physical_execution_confirmed'])

    def test_zero_and_full_scale(self):
        for value,raw in [(0,0),(100,1000)]:
            self.assertTrue(self.write(value).success)
            self.assertEqual(self.sim.writes[-1][1][0],raw)

    def test_invalid_numeric_commands_never_write(self):
        for value in [-1,100.1,float('nan'),float('inf'),True]:
            self.assertFalse(self.write(value).success)
        self.assertFalse(self.sim.writes)

    def test_lost_ack_is_uncertain_and_never_retransmitted(self):
        self.sim.lost_ack=True
        result=self.write()
        self.assertFalse(result.success)
        self.assertEqual(result.diagnostics['stage'],'uncertain')
        self.assertEqual(len(self.sim.writes),1)

    def test_device_refusal_and_readback_mismatch(self):
        self.sim.reject=True
        result=self.write();self.assertFalse(result.success);self.assertFalse(result.diagnostics['write_accepted'])
        self.sim.reject=False;self.sim.mismatch=True
        result=self.write();self.assertFalse(result.success);self.assertTrue(result.diagnostics['write_accepted'])
        self.assertFalse(result.diagnostics['readback_confirmed'])

    def test_ratings_and_scale_sentinels_block_commands(self):
        for did,field,value in [(120,'WRtg',9000),(121,'WMax',0),(121,'WMax',11000),(123,'WMaxLimPct_SF',-32768)]:
            self.sim=PvsSimulator();self.sim.set(did,field,value)
            self.assertFalse(self.write().success)
            self.assertFalse(self.sim.writes)

    def test_read_sentinels_and_missing_optional_models(self):
        self.sim.set(103,'W',-32768)
        self.assertIsNone(self.read()['active_power_kw'])
        self.service._maps.clear()
        address=self.sim.bases[160];self.sim.words[address]=0xFFFF;self.sim.words[address+1]=0
        self.assertIsNone(self.read()['mppt_count'])

    def test_bad_magic_duplicate_and_bad_terminator(self):
        for mutate in [lambda s:s.words.update({40000:0}),
                lambda s:s.words.update({s.bases[103]:1}), lambda s:s.words.update({s.end+1:1})]:
            self.sim=PvsSimulator();mutate(self.sim)
            self.assertFalse(self.write().success)
            self.assertFalse(self.sim.writes)

    def test_changed_header_invalidates_cached_map(self):
        self.read();self.sim.words[self.sim.bases[103]+1]=49
        with self.assertRaisesRegex(ValueError,'non compatibile|cambiata'):self.read()
        self.assertFalse(self.service._maps)

    def test_unsafe_overrides_cannot_change_command_policy(self):
        point=self.model.command_points[0]
        for changes in [{'address':0},{'scale':.1},{'protocol_meta':{**point.protocol_meta,'revert_seconds':0}}]:
            self.assertFalse(self.write(point=replace(point,**changes)).success)
        self.assertFalse(self.sim.writes)

    def test_disable_limit_is_only_single_enable_register(self):
        self.assertTrue(self.write(0,self.model.command_points[1]).success)
        self.assertEqual(self.sim.writes[-1][1],[0])

    def test_unit_zero_and_transport_validation(self):
        self.device.connection_settings['unit_id']=0
        self.assertFalse(self.write().success)
        self.assertFalse(self.sim.writes)

    def test_gateway_rtu_framer_and_serial(self):
        self.device.protocol='modbus_rtu'
        with patch('app.services.fimer_pvs_service.connection_manager.execute_modbus_tcp',side_effect=lambda *a,**kw:kw['operation'](self.sim)) as manager:
            self.assertTrue(self.service.write(self.device,self.model.command_points[0],50).success)
        self.assertEqual(manager.call_args.kwargs['framer'],FramerType.RTU)
        self.device.transport='serial';self.device.connection_settings={'port':'COM_TEST','slave_id':7}
        with patch('app.services.fimer_pvs_service.connection_manager.execute_modbus_rtu',side_effect=lambda *a,**kw:kw['operation'](self.sim)):
            self.assertTrue(self.service.write(self.device,self.model.command_points[0],50).success)
        self.assertEqual(self.sim.writes[-1][2],7)

    def test_io_scaling_heartbeat_and_broadcast_guards(self):
        with patch('app.services.inverter_io_service.fimer_pvs_service',self.service):
            result=self.call(lambda:inverter_io_service.read_telemetry(self.device,self.model))
            self.assertEqual(result.values['active_power_kw'],100)
            self.assertAlmostEqual(result.values['total_energy_kwh'],(2**32+123)/1000)
            self.call(lambda:inverter_io_service.read_heartbeat(self.device,self.model))
            self.assertTrue(self.call(lambda:inverter_io_service.write_command(self.device,self.model.command_points[0],50)).success)
        self.assertIsNone(inverter_io_service.build_command_broadcast_signature(self.device,self.model.command_points[0],50))
        self.assertFalse(inverter_io_service.write_command_broadcast(self.device,self.model.command_points[0],50).success)

    def test_readback_requires_timeout_enable_and_ramp(self):
        points=[SimpleNamespace(key=k,value=v,unit='%' if k=='active_power_limit_pct' else '',quality='valid') for k,v in
            [('active_power_limit_pct',50),('active_power_limit_enabled',1),('power_limit_revert_s',120),('power_limit_ramp_s',0),('power_limit_window_s',0)]]
        def evaluate():return active_power_limit_readback_resolver.evaluate(inverter_model=self.model,telemetry=points,desired_percent=50,resolved_value=50,resolved_unit='%',resolved_max_value=100)
        self.assertTrue(evaluate().confirmed)
        points[0].quality="invalid"
        self.assertFalse(evaluate().confirmed)
        points[0].quality="valid"
        for index,bad in [(1,0),(2,0),(3,10),(4,10)]:
            old=points[index].value;points[index].value=bad
            self.assertFalse(evaluate().confirmed);points[index].value=old

    def test_refresh_is_scoped_and_due_before_reversion(self):
        service=FleetDispatchService()
        for age,expected in [(20,False),(44,False),(46,True),(121,True)]:
            previous=SimpleNamespace(last_dispatch_at=(datetime.now(UTC)-timedelta(seconds=age)).isoformat())
            self.assertEqual(service._pvs_refresh_due(self.device,previous),expected)
        self.assertFalse(service._pvs_refresh_due(SimpleNamespace(brand='SUNGROW'),previous))

    def test_aligned_fleet_really_renews_an_expiring_setpoint(self):
        service=FleetDispatchService()
        now=datetime.now(UTC)
        desired=(now-timedelta(minutes=5)).isoformat()
        previous=SimpleNamespace(desired_updated_at=desired,desired_percent=50,last_sent_percent=50,
            last_applied_percent=50,last_dispatch_at=(now-timedelta(seconds=20)).isoformat(),control_state='aligned')
        resolved=SimpleNamespace(eligibility='eligible',eligibility_reason=None,inverter_model=self.model,
            command_point=self.model.command_points[0],command_key='active_power_limit',resolved_value=50,resolved_unit='%',resolved_max_value=100)
        readback=SimpleNamespace(supported=True,fresh=True,confirmed=True,observed_percent=50,
            observed_value=50,observed_unit='%',telemetry_label='Limite PVS')
        def send(*a,**kw):
            r=self.write(50)
            return SimpleNamespace(success=r.success,diagnostics=r.diagnostics,command='active_power_limit',message=r.error or 'OK')
        with patch.object(service,'_evaluate_readback',return_value=readback),\
                patch.object(service,'_endpoint_backoff_note',return_value=None),\
                patch('app.services.fleet_dispatch_service.command_service.send_active_power_limit_value',side_effect=send) as sender:
            args=dict(device=self.device,previous_state=previous,resolved_target=resolved,desired_percent=50,
                desired_updated_at=desired,desired_source='api',desired_source_priority=300)
            service._reconcile_device(**args)
            sender.assert_not_called()
            previous.last_dispatch_at=(now-timedelta(seconds=60)).isoformat()
            service._reconcile_device(**args)
            sender.assert_called_once()
        self.assertEqual(self.sim.writes[-1][1],[500,0,120,0,1])

    def test_source_offsets_match_manufacturer_pics(self):
        fields=PVS_MAP['models']
        self.assertEqual(fields['103']['fields']['W']['offset'],14)
        self.assertEqual(fields['122']['fields']['ActWh']['offset'],5)
        self.assertEqual(fields['122']['fields']['ActWh']['length'],4)
        self.assertEqual(fields['123']['fields']['WMaxLimPct']['offset'],5)
        self.assertEqual(fields['123']['fields']['WMaxLim_Ena']['offset'],9)
        self.assertEqual(fields['123']['fields']['WMaxLimPct_SF']['offset'],23)

    def test_sunspec_integer_and_accumulator_rules(self):
        self.assertIsNone(decode([],'sunssf'))
        self.assertIsNone(decode([0x8000],'int16'))
        self.assertEqual(decode([0xFFFF],'int16'),-1)
        self.assertIsNone(decode([0xFFFF],'uint16'))
        self.assertIsNone(decode([0,0,0,0],'acc64'))
        self.assertEqual(decode([0,1,0,1],'acc64'),2**32+1)

    def test_real_pymodbus_loopback(self):
        sim=self.sim
        class Handler(socketserver.BaseRequestHandler):
            def receive(self,n):
                data=b''
                while len(data)<n:
                    chunk=self.request.recv(n-len(data))
                    if not chunk:raise EOFError
                    data+=chunk
                return data
            def handle(self):
                try:
                    while True:
                        tx,proto,n,unit=struct.unpack('>HHHB',self.receive(7));pdu=self.receive(n-1)
                        address,count=struct.unpack('>HH',pdu[1:5])
                        if pdu[0]==3:
                            response=sim.read_holding_registers(address,count=count,device_id=unit)
                            reply=bytes([3,count*2])+struct.pack('>'+'H'*count,*response.registers)
                        elif pdu[0]==16:
                            sim.write_registers(address,list(struct.unpack('>'+'H'*count,pdu[6:])),device_id=unit)
                            reply=pdu[:5]
                        else:raise AssertionError('unexpected function')
                        self.request.sendall(struct.pack('>HHHB',tx,proto,len(reply)+1,unit)+reply)
                except EOFError:return
        manager=ConnectionManager()
        with socketserver.TCPServer(('127.0.0.1',0),Handler) as server:
            thread=threading.Thread(target=server.handle_request,daemon=True);thread.start()
            self.device.connection_settings['port']=server.server_address[1]
            try:
                with patch('app.services.fimer_pvs_service.connection_manager',manager):
                    self.assertEqual(self.service.read_points(self.device,self.model.telemetry_points)['mppt_count'],6)
                    result=self.service.write(self.device,self.model.command_points[0],55.5)
                    self.assertTrue(result.success,result.error)
            finally:manager.close_all_tcp_connections()
            thread.join(3)

"""Addressed SG110CX power limiting, with fresh identity and register readback.

No broadcast and no repeat of a write whose outcome may be uncertain. Register
readback confirms configuration, not the physical power delivered by the inverter.
"""
from dataclasses import dataclass
import math
import time

from pymodbus import FramerType

from app.catalog.sungrow_catalog import SG110CX_POWER_DRIVER, SG110CX_PREMIUM_MODEL, SG110CX_TYPE_CODE
from app.core.connection_settings import get_write_timeout_seconds
from app.services.connection_manager import connection_manager


@dataclass(frozen=True)
class SungrowPowerResult:
    success: bool
    diagnostics: dict
    error: str | None = None


class SungrowSg110cxService:
    def write(self, device, point, value):
        diag = {'stub_mode': False, 'driver': SG110CX_POWER_DRIVER, 'write_attempted': False,
                'write_accepted': False, 'readback_confirmed': False, 'physical_execution_confirmed': False}
        def failed(exc):
            diag['stage'] = 'uncertain' if diag['write_attempted'] else 'blocked'
            return SungrowPowerResult(False, diag, str(exc))
        try:
            if device.brand != 'SUNGROW' or device.model != SG110CX_PREMIUM_MODEL:
                raise ValueError('Il comando richiede il profilo SG110CX Premium.')
            specs = {'active_power_limit': (5007, 'uint16', .1, '%'),
                     'active_power_limit_enable': (5006, 'uint16', 1., ''),
                     'start_stop': (5005, 'uint16', 1., ''),
                     'power_factor_setting': (5018, 'int16', .001, '')}
            if (point.key not in specs or point.protocol_meta.get('driver') != SG110CX_POWER_DRIVER
                    or (point.address, point.datatype, point.scale, point.unit) != specs[point.key]
                    or point.register_type != 'holding' or point.length != 1):
                raise ValueError('Mappa del comando SG110CX diversa dal profilo verificato.')
            if isinstance(value, bool) or not math.isfinite(value):
                raise ValueError('Il comando SG110CX richiede un valore numerico finito.')
            power = point.key == 'active_power_limit'
            if power and not 0 <= value <= 110:
                raise ValueError('Riferimento SG110CX fuori intervallo 0..110%.')
            if point.key == 'active_power_limit_enable' and value not in {0xAA, 0x55}:
                raise ValueError('Abilitazione SG110CX: usare 0xAA o 0x55.')
            if point.key == 'start_stop' and value not in {0xCF, 0xCE}:
                raise ValueError('Start/Stop SG110CX: usare 0xCF o 0xCE.')
            if point.key == 'power_factor_setting' and not .8 <= abs(value) <= 1:
                raise ValueError('Fattore di potenza SG110CX: intervalli -1..-0.8 oppure 0.8..1.')
            raw = round(value / point.scale) & 0xFFFF
            address, payload = (5006, [0xAA, raw]) if power else (point.address, [raw])
            s = device.connection_settings
            timeout = get_write_timeout_seconds(s)
            unit = int(s.get('unit_id', s.get('slave_id', 1)))
            if not 1 <= unit <= 247:
                raise ValueError('Serve un indirizzo inverter 1..247; broadcast non supportato.')
            diag.update(requested_value=value, encoded_values=','.join(str(v) for v in payload),
                        register_start=address, register_count=len(payload), write_function='0x10')
            if power:
                diag.update(encoded_reference=raw, reference_pct=raw/10)

            def operation(client):
                # Catch inside the manager callback: reconnect logic must never
                # resubmit an already attempted write after a lost response.
                try:
                    identity = client.read_input_registers(4999, count=1, device_id=unit)
                    if identity.isError() or len(identity.registers) != 1:
                        raise ValueError('Identita SG110CX non leggibile.')
                    diag['device_type_code'] = identity.registers[0]
                    if identity.registers[0] != SG110CX_TYPE_CODE:
                        raise ValueError('Codice inverter diverso da SG110CX (0x2C06): nessuna scrittura.')
                    if point.key == 'power_factor_setting':
                        mode = client.read_holding_registers(5035, count=1, device_id=unit)
                        if mode.isError() or list(mode.registers) != [0xA1]:
                            raise ValueError('Il fattore di potenza richiede modalita reattiva 0xA1 gia attiva (holding 5036).')
                        diag['reactive_mode'] = 0xA1
                    diag['write_attempted'] = True
                    response = client.write_registers(address, payload, device_id=unit)
                    if response.isError() or response.address != address or response.count != len(payload):
                        raise RuntimeError('Risposta alla scrittura SG110CX non confermata: verificare prima di ripetere.')
                    diag['write_accepted'] = True
                    if point.key == 'start_stop':
                        # A pulse/register echo is not evidence of a real start/stop.
                        diag['stage'] = 'request_submitted'
                        return SungrowPowerResult(True, diag)
                    for attempt in range(3):
                        readback = client.read_holding_registers(address, count=len(payload), device_id=unit)
                        if not readback.isError() and len(readback.registers) == len(payload):
                            if power:
                                enabled, observed = readback.registers
                                diag.update(limit_enabled=enabled == 0xAA, observed_reference_pct=observed/10)
                            if list(readback.registers) == payload:
                                diag.update(readback_confirmed=True, stage='reference_confirmed' if power else 'setting_confirmed')
                                return SungrowPowerResult(True, diag)
                        if attempt < 2:
                            time.sleep(.05)
                    raise RuntimeError('Scrittura accettata, ma abilitazione e riferimento non confermati dalla rilettura.')
                except Exception as exc:
                    return failed(exc)

            # Pymodbus retries are explicitly off for this addressed write.
            if device.transport == 'tcp' and device.protocol in {'modbus_tcp', 'modbus_rtu'}:
                host, port = str(s.get('host', '')), int(s.get('port', 502))
                if not host or not 1 <= port <= 65535:
                    raise ValueError('Endpoint Modbus TCP/gateway non valido.')
                return connection_manager.execute_modbus_tcp(host, port, timeout=timeout, retries=0,
                    framer=FramerType.RTU if device.protocol == 'modbus_rtu' else FramerType.SOCKET,
                    operation_kind='command', operation=operation)
            if device.protocol == 'modbus_rtu' and device.transport == 'serial':
                port = str(s.get('port', ''))
                if not port:
                    raise ValueError('Porta seriale SG110CX non configurata.')
                return connection_manager.execute_modbus_rtu(port, int(s.get('baud_rate', 9600)),
                    int(s.get('byte_size', 8)), str(s.get('parity', 'N')), int(s.get('stop_bits', 1)),
                    timeout=timeout, retries=0, advanced_options=s, operation_kind='command', operation=operation)
            raise ValueError('Trasporto SG110CX non supportato.')
        except Exception as exc:
            return failed(exc)


sungrow_sg110cx_service = SungrowSg110cxService()

"""RA1 read-only driver. Does not inherit the legacy SINVERT command path."""
import math
import struct
import time
from threading import Lock
from time import monotonic
from app.catalog.sinvert_ra1_catalog import (
    RA1_BLOCKS, RA1_DB_SIZES, is_ra1_device, ra1_points,
)
from app.services.sinvert_s7_service import sinvert_s7_service, S7ReadResult

FORMATS={"uint8":">B", "uint16":">H", "int16":">h", "float32":">f", "uint32":">I"}
CANONICAL={p.key:p for p in ra1_points()}


class SinvertRa1Service:
    def __init__(self, client_factory=None):
        self.client_factory=client_factory
        self._verified={}
        self._cache_lock=Lock()

    @staticmethod
    def _verify(client, cooperate=None):
        from snap7.type import Block
        cpu=client.get_cpu_info().ModuleTypeName.decode('latin1').strip('\0 ')
        if cpu!='CPU 315-2 DP':raise ValueError('RA1: tipo CPU diverso dal progetto verificato.')
        for name,(size,checksum) in RA1_BLOCKS.items():
            kind=Block.OB if name.startswith('OB') else Block.FC if name.startswith('FC') else Block.FB
            info=client.get_block_info(kind,int(name[2:]))
            if (int(info.MC7Size),int(info.CheckSum))!=(size,checksum):
                raise ValueError(f'RA1: firma programma diversa in {name}; lettura del profilo bloccata.')
            if cooperate:cooperate()
        for db,size in RA1_DB_SIZES.items():
            if int(client.get_block_info(Block.DB,db).MC7Size)!=size:
                raise ValueError(f'RA1: dimensione DB{db} diversa dal progetto.')
            if cooperate:cooperate()

    def read_points(self,device,points):
        if not is_ra1_device(device) or device.protocol!='s7_tcp' or device.transport!='tcp':
            raise ValueError('Profilo SINVERT RA1 non valido.')
        if not points or any(CANONICAL.get(p.key)!=p for p in points):
            raise ValueError('Mappa RA1 modificata rispetto al progetto verificato.')
        s=device.connection_settings
        host=str(s.get('host','')).strip();port=int(s.get('port',102))
        rack=int(s.get('rack',0));slot=int(s.get('slot',2));timeout=float(s.get('timeout_seconds',10))
        if not host or not 1<=port<=65535 or not 0<=rack<=7 or not 0<=slot<=31 or not math.isfinite(timeout) or not .05<=timeout<=60:
            raise ValueError('Parametri collegamento RA1 non validi.')
        endpoint=(host,port,rack,slot);lock=sinvert_s7_service.endpoint_lock(*endpoint)
        if not lock.acquire(timeout=timeout):raise TimeoutError('Endpoint RA1 occupato.')
        client=None
        lock_held=True
        try:
            from snap7.client import Client
            from snap7.type import Areas
            client=(self.client_factory or (lambda:Client(auto_reconnect=False)))()
            client.connect(host,rack,slot,tcp_port=port)
            connection=getattr(client,'connection',None)
            deadline=monotonic()+timeout
            def cooperate():
                nonlocal lock_held
                if lock_held:
                    lock.release()
                    lock_held=False
                time.sleep(.005)
                remaining=deadline-monotonic()
                if remaining<=0 or not lock.acquire(timeout=remaining):
                    raise TimeoutError('Tempo RA1 esaurito in attesa dell’endpoint.')
                lock_held=True
            if connection is not None:
                connection.timeout=timeout
                if getattr(connection,'socket',None) is not None:connection.socket.settimeout(timeout)
            with self._cache_lock:verified=self._verified.get(endpoint)
            if verified is None or monotonic()-verified>=60:
                try:self._verify(client,cooperate)
                except Exception:
                    with self._cache_lock:self._verified.pop(endpoint,None)
                    raise
                verified=monotonic()
                with self._cache_lock:self._verified[endpoint]=verified
            spans=[]
            for p in sorted(points,key=lambda x:(x.protocol_meta['area'],x.protocol_meta['db'],x.address)):
                area=p.protocol_meta['area'];db=p.protocol_meta['db'];end=p.address+p.length
                if spans and spans[-1][:2]==[area,db] and p.address<=spans[-1][3]+12 and end-spans[-1][2]<=200:
                    spans[-1][3]=max(spans[-1][3],end);spans[-1][4].append(p)
                else:spans.append([area,db,p.address,end,[p]])
            values={};errors={}
            for area,db,start,end,items in spans:
                try:
                    # Read snapshots are already non-atomic. Yield between requests so
                    # the CP owner's fresh checks/send cannot be starved by bulk polls.
                    cooperate()
                    remaining=deadline-monotonic()
                    if remaining<=0:raise TimeoutError('Tempo di lettura RA1 esaurito.')
                    if connection is not None:
                        connection.timeout=remaining
                        if getattr(connection,'socket',None) is not None:connection.socket.settimeout(remaining)
                    raw=bytes(client.db_read(db,start,end-start) if area=='DB' else client.read_area(Areas.MK,0,start,end-start))
                    if len(raw)!=end-start:raise ValueError('Risposta RA1 incompleta.')
                    for p in items:
                        fragment=raw[p.address-start:p.address-start+p.length]
                        value=bool(fragment[0] & (1<<p.protocol_meta['bit'])) if p.datatype=='bool' else struct.unpack(FORMATS[p.datatype],fragment)[0]
                        if isinstance(value,float) and not math.isfinite(value):
                            errors[p.key]='REAL RA1 non finito.';value=None
                        values[p.key]=value
                except Exception as exc:
                    for p in items:values[p.key]=None;errors[p.key]=str(exc)
            if all(values.get(p.key) is None for p in points):raise RuntimeError('Nessun dato RA1 leggibile.')
            values.update(ra1_program_verified=True,ra1_program_check_age_seconds=round(monotonic()-verified,2))
            return S7ReadResult(values,errors)
        finally:
            try:
                if client is not None:
                    try:client.disconnect()
                    finally:client.destroy()
            finally:
                if lock_held:lock.release()


def build_ra1_monitor(values):
    reasons=['Controllo di flotta disabilitato. Usare il collaudo RA1 dedicato con riferimenti grezzi.']
    if values.get('ra1_cp_enabled') is False:reasons.append('Ramo di comunicazione CP disabilitato nel PLC.')
    if values.get('ra1_external_b') is False:reasons.append('Abilitazione del riferimento esterno non attiva.')
    if values.get('ra1_watchdog_fault') is True:reasons.append('Watchdog del canale esterno scaduto.')
    if values.get('ra1_receive_error') is True:reasons.append('Il PLC segnala un errore di ricezione CP.')
    if values.get('ra1_external_consent') is False:reasons.append('Consenso esterno PLC assente.')
    if values.get('ra1_ready_groups')==0:reasons.append('Nessun gruppo con consenso M55.')
    expected={'rx_id':1,'rx_laddr':440,'rx_db':944,'rx_offset':0,'rx_length':64,
              'tx_id':1,'tx_laddr':440,'tx_db':504,'tx_offset':0,'tx_length':1864}
    match=all(values.get('ra1_'+key)==value for key,value in expected.items())
    if not match:reasons.append('Parametri CP diversi o dati non disponibili.')
    return {'program_verified':values.get('ra1_program_verified') is True,
            'program_check_age_seconds':values.get('ra1_program_check_age_seconds'),
            'writes_enabled':False,'physical_execution_confirmed':False,'cp_parameters_match':match,
            'cp_enabled':values.get('ra1_cp_enabled'),'blockers':reasons,
            'reference_a':values.get('ra1_received_reference_a'),
            'reference_b':values.get('ra1_received_reference_b'),
            'regulator_a':values.get('ra1_regulator_input_a'),
            'regulator_b':values.get('ra1_regulator_input_b'),
            'processed_a':values.get('ra1_processed_reference_a'),
            'position_count':values.get('ra1_position_count')}


sinvert_ra1_service=SinvertRa1Service()

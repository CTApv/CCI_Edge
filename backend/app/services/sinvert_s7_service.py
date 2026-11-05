"""Read-only SINVERT PLC adapter; lab write routines are deliberately separate."""
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import math
import struct
import time
from threading import Lock
from typing import Callable

from app.models.inverter_model import InverterPoint

# Verified DB extents in the examined project. Read errors remain errors if another
# installation uses different extents; missing data must never become zero.
DB_LIMITS = {3:254,4:52,64:164,97:36,100:158,103:272,104:272,120:298,121:56,
             126:600,310:30,401:640,402:1618,511:64,570:246,579:98,600:64,944:64}
FORMATS = {"uint8":">B", "uint16":">H", "int16":">h", "uint32":">I", "int32":">i", "float32":">f"}


@dataclass(frozen=True)
class S7ReadResult:
    values: dict[str, str | int | float | bool | None]
    errors: dict[str, str]


class SinvertS7Service:
    def __init__(self, client_factory: Callable | None = None):
        self._client_factory = client_factory
        self._locks: dict[tuple, Lock] = {}
        self._lock = Lock()

    def endpoint_lock(self, host, port, rack, slot):
        with self._lock:
            return self._locks.setdefault((host,port,rack,slot),Lock())

    @staticmethod
    def _spec(point: InverterPoint) -> tuple[str,int,int,int,int | None]:
        meta=point.protocol_meta
        area=str(meta.get("area", "DB")); db=meta.get("db",0); offset=point.address
        if meta.get("driver")!="sinvert_s7" or point.register_type!="s7":
            raise ValueError("Profilo diagnostico SINVERT S7 non valido.")
        if type(db) is not int or type(offset) is not int or offset<0:
            raise ValueError("Indirizzo S7 non valido.")
        if point.datatype=="bool":
            size=1;bit=meta.get("bit")
            if type(bit) is not int or not 0<=bit<=7:raise ValueError("Bit S7 non valido.")
        elif point.datatype in FORMATS:
            size=struct.calcsize(FORMATS[point.datatype]);bit=None
        else:raise ValueError("Tipo diagnostico S7 non supportato.")
        documented=meta.get("semantics")=="documented_hmi"
        if documented:
            from app.catalog.sinvert_s7_catalog import build_sinvert_s7_models
            canonical=next((p for p in build_sinvert_s7_models()[0].telemetry_points if p.key==point.key),None)
            if canonical!=point:raise ValueError("Mappa HMI S7 modificata rispetto al profilo verificato.")
        if point.length!=size or (not documented and (point.scale!=1 or point.unit)) or point.writable:
            raise ValueError("Il profilo S7 espone soltanto dati grezzi in lettura.")
        limit=DB_LIMITS.get(db,0) if area=="DB" else (200 if area=="MK" and db==0 else 0)
        if offset+size>limit:raise ValueError("Intervallo S7 fuori dal profilo verificato.")
        return area,db,offset,size,bit

    def read_points(self, settings: dict, points: list[InverterPoint]) -> S7ReadResult:
        # Validate all overrides before any network access.
        specs=[self._spec(p) for p in points]
        if not specs or len(specs)>192:raise ValueError("Il profilo S7 deve richiedere da 1 a 192 punti.")
        host=str(settings.get("host","")).strip()
        port=int(settings.get("port",102));rack=int(settings.get("rack",0));slot=int(settings.get("slot",2))
        if not host or not 1<=port<=65535 or not 0<=rack<=7 or not 0<=slot<=31:
            raise ValueError("Endpoint S7 non valido.")
        timeout=float(settings.get("timeout_seconds",5))
        retries=int(settings.get("retries",0))
        if not math.isfinite(timeout) or not .05<=timeout<=60:raise ValueError("Timeout S7 non valido.")
        if not 0<=retries<=10:raise ValueError("Numero retry S7 non valido.")
        key=(host,port,rack,slot)
        with self._lock:lock=self._locks.setdefault(key,Lock())
        # Limit lock wait too: a broken endpoint must not stall another polling job.
        if not lock.acquire(timeout=timeout):raise TimeoutError("Endpoint S7 occupato.")
        client=None
        try:
            if self._client_factory is None:
                try:
                    from snap7.client import Client
                except ImportError as exc:
                    raise RuntimeError("Installare la dipendenza python-snap7 per il protocollo S7.") from exc
                client=Client(auto_reconnect=False)
            else:client=self._client_factory()
            started=datetime.now(timezone.utc).isoformat()
            deadline=time.monotonic()+timeout
            client.connect(host,rack,slot,tcp_port=port)
            # 3.3.1 negotiates with a fixed5s handshake; apply the configured
            # timeout to subsequent reads without changing global socket defaults.
            connection=getattr(client,"connection",None)
            if connection is not None:
                connection.timeout=timeout
                sock=getattr(connection,"socket",None)
                if sock is not None:sock.settimeout(timeout)
            values={};errors={};cache={}
            # Coalesce nearby spans into bounded reads. This reduces a full HMI
            # sample to a few requests per DB; samples still are not scan-atomic.
            if len(specs)>32:
                groups=[]
                for area,db,offset,size,_ in sorted(set(specs),key=lambda s:(s[0],s[1],s[2],s[3],str(s[4]))):
                    end=offset+size
                    if groups and groups[-1][0:2]==[area,db] and offset<=groups[-1][3]+16 and end-groups[-1][2]<=200:
                        groups[-1][3]=max(groups[-1][3],end)
                    else:groups.append([area,db,offset,end])
                for area,db,start,end in groups:
                    try:
                        remaining=deadline-time.monotonic()
                        if remaining<=0:break
                        if connection is not None:
                            connection.timeout=remaining
                            sock=getattr(connection,"socket",None)
                            if sock is not None:sock.settimeout(remaining)
                        if area=="DB":block=bytes(client.db_read(db,start,end-start))
                        else:
                            from snap7.type import Areas
                            block=bytes(client.read_area(Areas.MK,0,start,end-start))
                        if len(block)!=end-start:raise ValueError("Risposta S7 incompleta.")
                        for a,d,off,size,_ in specs:
                            if a==area and d==db and start<=off and off+size<=end:
                                cache[(a,d,off,size)]=block[off-start:off-start+size]
                    except Exception:
                        # A failed aggregate read is retried as individual spans
                        # below, retaining per-point quality instead of zeros.
                        pass
            for point,(area,db,offset,size,bit) in zip(points,specs):
                span=(area,db,offset,size)
                if span not in cache:
                    for _ in range(retries+1):
                        try:
                            remaining=deadline-time.monotonic()
                            if remaining<=0:raise TimeoutError("Tempo massimo di acquisizione S7 superato.")
                            if connection is not None:
                                connection.timeout=remaining
                                sock=getattr(connection,"socket",None)
                                if sock is not None:sock.settimeout(remaining)
                            if area=="DB":data=bytes(client.db_read(db,offset,size))
                            else:
                                from snap7.type import Areas
                                data=bytes(client.read_area(Areas.MK,0,offset,size))
                            if len(data)!=size:raise ValueError("Risposta S7 incompleta.")
                            cache[span]=data
                            break
                        except Exception as exc:
                            cache[span]=exc
                            if time.monotonic()>=deadline:break
                try:
                    data=cache[span]
                    if isinstance(data,Exception):raise data
                    value=bool(data[0]&(1<<bit)) if bit is not None else struct.unpack(FORMATS[point.datatype],data)[0]
                    if isinstance(value,float) and not math.isfinite(value):raise ValueError("REAL PLC non finito.")
                    values[point.key]=value
                except Exception as exc:
                    values[point.key]=None;errors[point.key]=str(exc)
            if len(errors)==len(points):raise RuntimeError("Nessun punto S7 leggibile: "+next(iter(errors.values())))
            values.update(s7_sample_started_utc=started,s7_sample_finished_utc=datetime.now(timezone.utc).isoformat(),
                          s7_failed_points=len(errors),s7_read_errors=json.dumps(errors,ensure_ascii=False))
            return S7ReadResult(values,errors)
        finally:
            try:
                if client is not None:client.disconnect()
            finally:lock.release()


sinvert_s7_service=SinvertS7Service()

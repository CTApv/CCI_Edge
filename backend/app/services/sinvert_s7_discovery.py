"""Read-only S7 identity and DB-layout probe; never identifies an open port alone."""
from app.services.sinvert_s7_service import sinvert_s7_service

DISCOVERY_LAYOUT = {100:158,120:298,126:600,511:64,944:64}


def probe_sinvert(host: str, port: int, timeout: float, *, client_factory=None) -> dict:
    import snap7
    from snap7.type import Block
    reader=sinvert_s7_service
    lock=reader.endpoint_lock(host,port,0,2)
    if not lock.acquire(timeout=timeout):raise TimeoutError('Endpoint S7 occupato')
    client=None
    try:
        client=(client_factory or snap7.client.Client)()
        client.connect(host,0,2,tcp_port=port)
        connection=getattr(client,'connection',None)
        if connection is not None:
            connection.timeout=timeout
            sock=getattr(connection,'socket',None)
            if sock is not None:sock.settimeout(timeout)
        info=client.get_cpu_info()
        for db,size in DISCOVERY_LAYOUT.items():
            if client.get_block_info(Block.DB,db).MC7Size!=size:
                raise ValueError('Layout DB non compatibile con il profilo SINVERT')
        data=bytes(client.db_read(100,135,1))
        if len(data)!=1:raise ValueError('DB100 non leggibile')
        decode=lambda v:v.decode('latin1').strip('\0 ') if isinstance(v,bytes) else str(v)
        return {'cpu':decode(info.ModuleTypeName),'serial':decode(info.SerialNumber),
                'rack':0,'slot':2,'raw':list(data)}
    finally:
        try:
            if client is not None:client.disconnect()
        finally:lock.release()

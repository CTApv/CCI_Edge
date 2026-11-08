from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, StrictBool
from app.services.device_service import device_service
from app.services.sinvert_bench_service import sinvert_bench_service
from app.services.sinvert_trace_service import sinvert_trace_service
from app.catalog.sinvert_s7_catalog import COMMISSIONING_MODEL

router = APIRouter(prefix='/api/devices', tags=['sinvert-lab'])


def device_for(device_id, *, writable=False):
    device = device_service.get_device(device_id)
    if device is None: raise HTTPException(404, 'Device not found')
    if device.protocol != 's7_tcp' or device.brand != 'SINVERT' or (writable and device.model != COMMISSIONING_MODEL):
        raise HTTPException(400, 'Selezionare il profilo SINVERT Collaudo comandi')
    return device


class BenchRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: StrictBool
    cpu_only_confirmed: StrictBool


@router.get('/{device_id}/sinvert/bench')
def bench_status(device_id: str):
    return sinvert_bench_service.status(device_for(device_id))


@router.post('/{device_id}/sinvert/bench')
def bench_mode(device_id: str, payload: BenchRequest):
    device = device_for(device_id, writable=True)
    if payload.enabled and not payload.cpu_only_confirmed:
        raise HTTPException(400, 'Confermare banco con sola CPU, senza inverter o periferiche collegate')
    return sinvert_bench_service.set_enabled(device, payload.enabled)


@router.get('/{device_id}/sinvert/trace.zip')
def trace_export(device_id: str):
    device_for(device_id)
    return Response(sinvert_trace_service.export(device_id), media_type='application/zip',
        headers={'Content-Disposition': 'attachment; filename="sinvert-trace.zip"'})

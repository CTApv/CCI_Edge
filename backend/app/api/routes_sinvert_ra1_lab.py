from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, ConfigDict, FiniteFloat, StrictBool, Field

from app.catalog.sinvert_ra1_catalog import is_ra1_device
from app.services.device_service import device_service
from app.services.sinvert_ra1_lab_service import sinvert_ra1_lab_service as lab

router = APIRouter(prefix='/api/devices', tags=['sinvert-ra1-lab'])


class Request(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Preflight(Request):
    bench: StrictBool


class Reference(Request):
    value: FiniteFloat = Field(strict=True)
    maximum: FiniteFloat = Field(strict=True)


class Probe(Reference):
    cpu_only_confirmed: StrictBool


class Start(Reference):
    local_tsap: str = Field(min_length=2, max_length=64, pattern=r'^(?:[0-9a-fA-F]{2})+$')
    remote_tsap: str = Field(min_length=2, max_length=64, pattern=r'^(?:[0-9a-fA-F]{2})+$')
    connection_confirmed: StrictBool
    exclusive_confirmed: StrictBool


class Change(Request):
    value: FiniteFloat = Field(strict=True)
    renew: StrictBool = False


class Manual(Request):
    command: str
    value: FiniteFloat = Field(default=1, strict=True)
    dry_run: StrictBool = True
    enabled: StrictBool = False
    bench: StrictBool = False
    scope_confirmed: StrictBool = False


class LabSettings(Request):
    enabled: StrictBool
    maximum: FiniteFloat = Field(strict=True, ge=0, le=1000000)


@router.post('/{device_id}/sinvert-ra1/lab/settings')
def settings(device_id: str, payload: LabSettings):
    from app.schemas.device_schemas import DeviceUpdate
    device = device_for(device_id)
    state=lab.status(device)
    if state.get('state') in ('starting','active','stopping','bench_probe','command'):
        if payload.enabled:
            raise HTTPException(409, 'Arrestare il collaudo prima di cambiare le impostazioni.')
        lab.stop(device)
        if lab.status(device).get('state') in ('starting','active','stopping','bench_probe','command'):
            raise HTTPException(409,'Arresto ancora in corso: attendere prima di cambiare impostazioni.')
    current=device.model_dump(exclude={'device_id','created_at'})
    current['connection_settings']={**device.connection_settings,
        'ra1_write_mode':'commissioning' if payload.enabled else 'read_only',
        'ra1_reference_max_raw':payload.maximum}
    return device_service.update_device(device_id,DeviceUpdate(**current))


@router.get('/{device_id}/sinvert-ra1/lab/trace.zip')
def trace(device_id: str):
    from app.services.sinvert_ra1_trace_service import sinvert_ra1_trace_service
    device_for(device_id)
    return Response(sinvert_ra1_trace_service.export(device_id),media_type='application/zip',
                    headers={'Content-Disposition':'attachment; filename="sinvert-ra1-trace.zip"'})


@router.post('/{device_id}/sinvert-ra1/lab/command')
def manual(device_id: str, payload: Manual):
    from app.services.sinvert_ra1_command_service import sinvert_ra1_command_service
    return invoke(device_id, lambda d: sinvert_ra1_command_service.execute(d, **payload.model_dump()))


def device_for(device_id):
    device = device_service.get_device(device_id)
    if device is None:
        raise HTTPException(404, 'Dispositivo non trovato.')
    if not is_ra1_device(device):
        raise HTTPException(400, 'Collaudo riservato al profilo SINVERT RA1.')
    return device


def invoke(device_id, operation):
    device = device_for(device_id)
    try:
        return operation(device)
    except Exception as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get('/{device_id}/sinvert-ra1/lab')
def status(device_id: str):
    return invoke(device_id, lab.status)


@router.post('/{device_id}/sinvert-ra1/lab/preflight')
def preflight(device_id: str, payload: Preflight):
    return invoke(device_id, lambda d: lab.preflight(d, bench=payload.bench))


@router.post('/{device_id}/sinvert-ra1/lab/probe')
def probe(device_id: str, payload: Probe):
    return invoke(device_id, lambda d: lab.probe(d, payload.value, payload.maximum,
                                               cpu_only_confirmed=payload.cpu_only_confirmed))


@router.post('/{device_id}/sinvert-ra1/lab/start')
def start(device_id: str, payload: Start):
    return invoke(device_id, lambda d: lab.start(d, payload.value, payload.maximum,
        payload.local_tsap, payload.remote_tsap, connection_confirmed=payload.connection_confirmed,
        exclusive_confirmed=payload.exclusive_confirmed))


@router.post('/{device_id}/sinvert-ra1/lab/reference')
def reference(device_id: str, payload: Change):
    return invoke(device_id, lambda d: lab.change(d, payload.value, renew=payload.renew))


@router.post('/{device_id}/sinvert-ra1/lab/stop')
def stop(device_id: str):
    return invoke(device_id, lab.stop)

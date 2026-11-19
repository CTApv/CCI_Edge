from fastapi import APIRouter, HTTPException
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

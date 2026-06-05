from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_catalog import router as catalog_router
from app.api.routes_commands import router as commands_router
from app.api.routes_fleet_control import router as fleet_control_router
from app.api.routes_device_detail import router as device_detail_router
from app.api.routes_device_overview import router as device_overview_router
from app.api.routes_dashboard import router as dashboard_router
from app.api.routes_devices import router as devices_router
from app.api.routes_protocols import router as protocols_router
from app.api.routes_serial import router as serial_router
from app.api.routes_system import router as system_router
from app.config import settings
from app.logger import get_logger
from app.services.connection_manager import connection_manager
from app.services.fleet_dispatch_service import fleet_dispatch_service
from app.services.hsm_bridge_service import hsm_bridge_service
from app.services.modbus_tcp_slave_service import modbus_tcp_slave_service
from app.services.polling_engine import polling_engine

logger = get_logger("pv_edge_manager.api")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    logger.info("Starting %s", settings.app_title)
    modbus_tcp_slave_service.start()
    hsm_bridge_service.start()
    fleet_dispatch_service.start()
    polling_engine.start()
    try:
        yield
    finally:
        polling_engine.stop()
        fleet_dispatch_service.stop()
        hsm_bridge_service.stop()
        modbus_tcp_slave_service.stop()
        connection_manager.close_all_rtu_connections()
        logger.info("Stopping %s", settings.app_title)


app = FastAPI(title=settings.app_title, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(catalog_router)
app.include_router(commands_router)
app.include_router(fleet_control_router)
app.include_router(devices_router)
app.include_router(device_detail_router)
app.include_router(device_overview_router)
app.include_router(dashboard_router)
app.include_router(protocols_router)
app.include_router(serial_router)
app.include_router(system_router)

@app.get(f"{settings.api_prefix}/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}

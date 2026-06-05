import os
from pathlib import Path


def _env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}


class Settings:
    def __init__(self) -> None:
        self.app_title = "PV Edge Manager"
        self.api_prefix = "/api"
        self.cors_allow_origins = ["*"]
        self.database_path = Path(
            os.getenv(
                "PV_EDGE_MANAGER_DATABASE_PATH",
                Path(__file__).resolve().parent / "pv_edge_manager.db",
            )
        ).expanduser()
        self.power_history_database_path = Path(
            os.getenv(
                "PV_EDGE_MANAGER_HISTORY_DATABASE_PATH",
                self.database_path.with_name(f"{self.database_path.stem}_history.db"),
            )
        ).expanduser()
        self.modbus_tcp_slave_enabled = _env_bool("PV_EDGE_MANAGER_MODBUS_TCP_SLAVE_ENABLED", True)
        self.modbus_tcp_slave_host = os.getenv("PV_EDGE_MANAGER_MODBUS_TCP_SLAVE_HOST", "0.0.0.0")
        self.modbus_tcp_slave_port = int(os.getenv("PV_EDGE_MANAGER_MODBUS_TCP_SLAVE_PORT", "15020"))
        self.modbus_tcp_slave_unit_id = int(os.getenv("PV_EDGE_MANAGER_MODBUS_TCP_SLAVE_UNIT_ID", "1"))
        self.fleet_dispatch_interval_seconds = float(
            os.getenv("PV_EDGE_MANAGER_FLEET_DISPATCH_INTERVAL_SECONDS", "5"),
        )
        self.power_history_limit = int(
            os.getenv("PV_EDGE_MANAGER_POWER_HISTORY_LIMIT", "2880"),
        )
        self.power_history_max_bytes = int(
            os.getenv("PV_EDGE_MANAGER_POWER_HISTORY_MAX_BYTES", str(2 * 1024 * 1024 * 1024)),
        )
        self.power_history_query_max_points = int(
            os.getenv("PV_EDGE_MANAGER_POWER_HISTORY_QUERY_MAX_POINTS", "720"),
        )


settings = Settings()

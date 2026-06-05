from dataclasses import dataclass

from app.config import settings
from app.database import get_connection

MODBUS_TCP_SLAVE_CONFIG_SINGLETON_KEY = "default"
DEFAULT_CCI_READBACK_ENABLED = True
DEFAULT_CCI_READBACK_RANGE_PERCENT = 1.0
DEFAULT_CCI_READBACK_STABLE_SECONDS = 3.0
DEFAULT_CCI_READBACK_ACTIVE_POWER_ONLY = False


@dataclass(slots=True, frozen=True)
class ModbusTcpSlaveConfig:
    enabled: bool
    cci_enabled: bool
    host: str
    port: int
    unit_id: int
    cci_readback_enabled: bool
    cci_readback_range_percent: float
    cci_readback_stable_seconds: float
    cci_readback_active_power_only: bool


class ModbusTcpSlaveConfigService:
    def __init__(self) -> None:
        self._initialize_storage()

    def get_config(self) -> ModbusTcpSlaveConfig:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    enabled,
                    cci_enabled,
                    host,
                    port,
                    unit_id,
                    cci_readback_enabled,
                    cci_readback_range_percent,
                    cci_readback_stable_seconds,
                    cci_readback_active_power_only
                FROM modbus_tcp_slave_config
                WHERE singleton_key = ?
                """,
                (MODBUS_TCP_SLAVE_CONFIG_SINGLETON_KEY,),
            ).fetchone()

        if row is None:
            raise RuntimeError("Missing Modbus TCP slave config row.")

        return ModbusTcpSlaveConfig(
            enabled=bool(row["enabled"]),
            cci_enabled=bool(row["cci_enabled"]),
            host=row["host"],
            port=int(row["port"]),
            unit_id=int(row["unit_id"]),
            cci_readback_enabled=bool(row["cci_readback_enabled"]),
            cci_readback_range_percent=float(row["cci_readback_range_percent"]),
            cci_readback_stable_seconds=float(row["cci_readback_stable_seconds"]),
            cci_readback_active_power_only=bool(row["cci_readback_active_power_only"]),
        )

    def update_config(
        self,
        *,
        enabled: bool,
        cci_enabled: bool,
        host: str,
        port: int,
        unit_id: int,
        cci_readback_enabled: bool,
        cci_readback_range_percent: float,
        cci_readback_stable_seconds: float,
        cci_readback_active_power_only: bool,
    ) -> ModbusTcpSlaveConfig:
        normalized_host = host.strip() or "0.0.0.0"
        normalized_port = min(max(int(port), 1), 65535)
        normalized_unit_id = min(max(int(unit_id), 1), 247)
        normalized_cci_readback_range_percent = round(
            min(max(float(cci_readback_range_percent), 0.0), 100.0),
            2,
        )
        normalized_cci_readback_stable_seconds = round(
            min(max(float(cci_readback_stable_seconds), 0.1), 3600.0),
            2,
        )

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE modbus_tcp_slave_config
                SET
                    enabled = ?,
                    cci_enabled = ?,
                    host = ?,
                    port = ?,
                    unit_id = ?,
                    cci_readback_enabled = ?,
                    cci_readback_range_percent = ?,
                    cci_readback_stable_seconds = ?,
                    cci_readback_active_power_only = ?
                WHERE singleton_key = ?
                """,
                (
                    1 if enabled else 0,
                    1 if cci_enabled else 0,
                    normalized_host,
                    normalized_port,
                    normalized_unit_id,
                    1 if cci_readback_enabled else 0,
                    normalized_cci_readback_range_percent,
                    normalized_cci_readback_stable_seconds,
                    1 if cci_readback_active_power_only else 0,
                    MODBUS_TCP_SLAVE_CONFIG_SINGLETON_KEY,
                ),
            )

        return self.get_config()

    def _initialize_storage(self) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS modbus_tcp_slave_config (
                    singleton_key TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL,
                    cci_enabled INTEGER NOT NULL DEFAULT 1,
                    host TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    unit_id INTEGER NOT NULL,
                    cci_readback_enabled INTEGER NOT NULL DEFAULT 1,
                    cci_readback_range_percent REAL NOT NULL DEFAULT 1.0,
                    cci_readback_stable_seconds REAL NOT NULL DEFAULT 3.0,
                    cci_readback_active_power_only INTEGER NOT NULL DEFAULT 0
                )
                """,
            )
            self._ensure_column(
                connection,
                "modbus_tcp_slave_config",
                "cci_enabled",
                "INTEGER NOT NULL DEFAULT 1",
            )
            self._ensure_column(
                connection,
                "modbus_tcp_slave_config",
                "cci_readback_enabled",
                f"INTEGER NOT NULL DEFAULT {1 if DEFAULT_CCI_READBACK_ENABLED else 0}",
            )
            self._ensure_column(
                connection,
                "modbus_tcp_slave_config",
                "cci_readback_range_percent",
                f"REAL NOT NULL DEFAULT {DEFAULT_CCI_READBACK_RANGE_PERCENT}",
            )
            self._ensure_column(
                connection,
                "modbus_tcp_slave_config",
                "cci_readback_stable_seconds",
                f"REAL NOT NULL DEFAULT {DEFAULT_CCI_READBACK_STABLE_SECONDS}",
            )
            self._ensure_column(
                connection,
                "modbus_tcp_slave_config",
                "cci_readback_active_power_only",
                f"INTEGER NOT NULL DEFAULT {1 if DEFAULT_CCI_READBACK_ACTIVE_POWER_ONLY else 0}",
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO modbus_tcp_slave_config (
                    singleton_key,
                    enabled,
                    cci_enabled,
                    host,
                    port,
                    unit_id,
                    cci_readback_enabled,
                    cci_readback_range_percent,
                    cci_readback_stable_seconds,
                    cci_readback_active_power_only
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    MODBUS_TCP_SLAVE_CONFIG_SINGLETON_KEY,
                    1 if settings.modbus_tcp_slave_enabled else 0,
                    1,
                    settings.modbus_tcp_slave_host,
                    settings.modbus_tcp_slave_port,
                    settings.modbus_tcp_slave_unit_id,
                    1 if DEFAULT_CCI_READBACK_ENABLED else 0,
                    DEFAULT_CCI_READBACK_RANGE_PERCENT,
                    DEFAULT_CCI_READBACK_STABLE_SECONDS,
                    1 if DEFAULT_CCI_READBACK_ACTIVE_POWER_ONLY else 0,
                ),
            )

    def _ensure_column(
        self,
        connection: object,
        table_name: str,
        column_name: str,
        column_definition: str,
    ) -> None:
        existing_columns = {
            row["name"]
            for row in connection.execute(f"PRAGMA table_info({table_name})").fetchall()
        }
        if column_name in existing_columns:
            return
        connection.execute(
            f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}"
        )


modbus_tcp_slave_config_service = ModbusTcpSlaveConfigService()

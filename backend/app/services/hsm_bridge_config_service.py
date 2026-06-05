from dataclasses import dataclass

from app.database import get_connection

HSM_BRIDGE_CONFIG_SINGLETON_KEY = "default"


@dataclass(slots=True, frozen=True)
class HsmBridgeConfig:
    enabled: bool
    hsm_port: str
    inverter_port: str
    hsm_baud_rate: int
    hsm_parity: str
    hsm_stop_bits: int
    hsm_byte_size: int
    frame_gap_ms: int
    forward_delay_ms: int
    ack_timeout_ms: int


class HsmBridgeConfigService:
    def __init__(self) -> None:
        self._initialize_storage()

    def get_config(self) -> HsmBridgeConfig:
        with get_connection() as connection:
            row = connection.execute(
                """
                SELECT
                    enabled,
                    hsm_port,
                    inverter_port,
                    hsm_baud_rate,
                    hsm_parity,
                    hsm_stop_bits,
                    hsm_byte_size,
                    frame_gap_ms,
                    forward_delay_ms,
                    ack_timeout_ms
                FROM hsm_bridge_config
                WHERE singleton_key = ?
                """,
                (HSM_BRIDGE_CONFIG_SINGLETON_KEY,),
            ).fetchone()

        if row is None:
            raise RuntimeError("Missing HSM bridge config row.")

        return HsmBridgeConfig(
            enabled=bool(row["enabled"]),
            hsm_port=str(row["hsm_port"] or "").strip(),
            inverter_port=str(row["inverter_port"] or "").strip(),
            hsm_baud_rate=int(row["hsm_baud_rate"]),
            hsm_parity=self._normalize_parity(row["hsm_parity"]),
            hsm_stop_bits=int(row["hsm_stop_bits"]),
            hsm_byte_size=int(row["hsm_byte_size"]),
            frame_gap_ms=int(row["frame_gap_ms"]),
            forward_delay_ms=int(row["forward_delay_ms"]),
            ack_timeout_ms=int(row["ack_timeout_ms"]),
        )

    def update_config(
        self,
        *,
        enabled: bool,
        hsm_port: str,
        inverter_port: str,
        hsm_baud_rate: int,
        hsm_parity: str,
        hsm_stop_bits: int,
        hsm_byte_size: int,
        frame_gap_ms: int,
        forward_delay_ms: int,
        ack_timeout_ms: int,
    ) -> HsmBridgeConfig:
        normalized_hsm_port = hsm_port.strip()
        normalized_inverter_port = inverter_port.strip()
        normalized_hsm_baud_rate = min(max(int(hsm_baud_rate), 1), 921600)
        normalized_hsm_parity = self._normalize_parity(hsm_parity)
        normalized_hsm_stop_bits = min(max(int(hsm_stop_bits), 1), 2)
        normalized_hsm_byte_size = min(max(int(hsm_byte_size), 5), 8)
        normalized_frame_gap_ms = min(max(int(frame_gap_ms), 5), 500)
        normalized_forward_delay_ms = min(max(int(forward_delay_ms), 0), 5000)
        normalized_ack_timeout_ms = min(max(int(ack_timeout_ms), 50), 10000)

        with get_connection() as connection:
            connection.execute(
                """
                UPDATE hsm_bridge_config
                SET
                    enabled = ?,
                    hsm_port = ?,
                    inverter_port = ?,
                    hsm_baud_rate = ?,
                    hsm_parity = ?,
                    hsm_stop_bits = ?,
                    hsm_byte_size = ?,
                    frame_gap_ms = ?,
                    forward_delay_ms = ?,
                    ack_timeout_ms = ?
                WHERE singleton_key = ?
                """,
                (
                    1 if enabled else 0,
                    normalized_hsm_port,
                    normalized_inverter_port,
                    normalized_hsm_baud_rate,
                    normalized_hsm_parity,
                    normalized_hsm_stop_bits,
                    normalized_hsm_byte_size,
                    normalized_frame_gap_ms,
                    normalized_forward_delay_ms,
                    normalized_ack_timeout_ms,
                    HSM_BRIDGE_CONFIG_SINGLETON_KEY,
                ),
            )

        return self.get_config()

    def _initialize_storage(self) -> None:
        with get_connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS hsm_bridge_config (
                    singleton_key TEXT PRIMARY KEY,
                    enabled INTEGER NOT NULL DEFAULT 0,
                    hsm_port TEXT NOT NULL DEFAULT '',
                    inverter_port TEXT NOT NULL DEFAULT '',
                    hsm_baud_rate INTEGER NOT NULL DEFAULT 9600,
                    hsm_parity TEXT NOT NULL DEFAULT 'N',
                    hsm_stop_bits INTEGER NOT NULL DEFAULT 1,
                    hsm_byte_size INTEGER NOT NULL DEFAULT 8,
                    frame_gap_ms INTEGER NOT NULL DEFAULT 30,
                    forward_delay_ms INTEGER NOT NULL DEFAULT 300,
                    ack_timeout_ms INTEGER NOT NULL DEFAULT 500
                )
                """,
            )
            connection.execute(
                """
                INSERT OR IGNORE INTO hsm_bridge_config (
                    singleton_key,
                    enabled,
                    hsm_port,
                    inverter_port,
                    hsm_baud_rate,
                    hsm_parity,
                    hsm_stop_bits,
                    hsm_byte_size,
                    frame_gap_ms,
                    forward_delay_ms,
                    ack_timeout_ms
                ) VALUES (?, 0, '', '', 9600, 'N', 1, 8, 30, 300, 500)
                """,
                (HSM_BRIDGE_CONFIG_SINGLETON_KEY,),
            )

    def _normalize_parity(self, value: object) -> str:
        normalized = str(value or "N").strip().upper()
        if normalized not in {"N", "E", "O"}:
            return "N"
        return normalized


hsm_bridge_config_service = HsmBridgeConfigService()

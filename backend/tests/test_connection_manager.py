import unittest
from unittest.mock import patch

from pymodbus.exceptions import ConnectionException as ModbusConnectionException

from app.services.connection_manager import ConnectionManager


class FakeModbusTcpClient:
    def __init__(
        self,
        host: str,
        port: int,
        timeout: float,
        retries: int,
        framer: object | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self.timeout = timeout
        self.retries = retries
        self.framer = framer
        self._open = False
        self.closed = False
        self.connect_calls = 0
        self.connect_result = True

    def is_socket_open(self) -> bool:
        return self._open

    def connect(self) -> bool:
        self.connect_calls += 1
        self._open = self.connect_result
        return self.connect_result

    def close(self) -> None:
        self.closed = True
        self._open = False


class FakeSerialSocket:
    def __init__(self) -> None:
        self.is_open = False
        self.rs485_mode = None
        self.in_waiting = 0
        self.timeout = None
        self.write_timeout = None
        self.read_buffer = bytearray()
        self.written_payloads: list[bytes] = []
        self.auto_response_payload = b""

    def read(self, size: int) -> bytes:
        chunk = bytes(self.read_buffer[:size])
        del self.read_buffer[:size]
        self.in_waiting = len(self.read_buffer)
        return chunk

    def write(self, payload: bytes) -> int:
        self.written_payloads.append(bytes(payload))
        if self.auto_response_payload:
            self.read_buffer.extend(self.auto_response_payload)
            self.in_waiting = len(self.read_buffer)
        return len(payload)

    def reset_input_buffer(self) -> None:
        self.read_buffer.clear()
        self.in_waiting = 0

    def reset_output_buffer(self) -> None:
        self.written_payloads.clear()


class FakeModbusSerialClient:
    def __init__(
        self,
        port: str,
        baudrate: int,
        bytesize: int,
        parity: str,
        stopbits: int,
        handle_local_echo: bool,
        timeout: float,
        retries: int,
        trace_packet: object | None = None,
    ) -> None:
        self.port = port
        self.baudrate = baudrate
        self.bytesize = bytesize
        self.parity = parity
        self.stopbits = stopbits
        self.handle_local_echo = handle_local_echo
        self.timeout = timeout
        self.retries = retries
        self.trace_packet = trace_packet
        self.socket = FakeSerialSocket()
        self.closed = False
        self.connect_calls = 0
        self.connect_result = True

    def connect(self) -> bool:
        self.connect_calls += 1
        self.socket.is_open = self.connect_result
        return self.connect_result

    def close(self) -> None:
        self.closed = True
        self.socket.is_open = False

    def send(self, request: bytes, addr: object | None = None) -> int:
        _ = addr
        return self.socket.write(request)


class ConnectionManagerTests(unittest.TestCase):
    def test_retries_with_fresh_client_after_broken_socket(self) -> None:
        created_clients: list[FakeModbusTcpClient] = []

        def build_client(
            host: str,
            port: int,
            timeout: float,
            retries: int,
            framer: object | None = None,
        ) -> FakeModbusTcpClient:
            client = FakeModbusTcpClient(host, port, timeout, retries, framer)
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusTcpClient", side_effect=build_client):
            result = manager.execute_modbus_tcp(
                "127.0.0.1",
                502,
                timeout=1.0,
                retries=0,
                operation=lambda client: self._operation_with_first_client_failure(
                    client,
                    created_clients[0],
                ),
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(created_clients), 2)
        self.assertTrue(created_clients[0].closed)
        self.assertEqual(created_clients[0].connect_calls, 1)
        self.assertEqual(created_clients[1].connect_calls, 1)

    def test_recreates_cached_client_when_timeout_changes(self) -> None:
        created_clients: list[FakeModbusTcpClient] = []

        def build_client(
            host: str,
            port: int,
            timeout: float,
            retries: int,
            framer: object | None = None,
        ) -> FakeModbusTcpClient:
            client = FakeModbusTcpClient(host, port, timeout, retries, framer)
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusTcpClient", side_effect=build_client):
            first_timeout = manager.execute_modbus_tcp(
                "127.0.0.1",
                502,
                timeout=1.0,
                retries=0,
                operation=lambda client: client.timeout,
            )
            second_timeout = manager.execute_modbus_tcp(
                "127.0.0.1",
                502,
                timeout=5.0,
                retries=2,
                operation=lambda client: client.timeout,
            )

        self.assertEqual(first_timeout, 1.0)
        self.assertEqual(second_timeout, 5.0)
        self.assertEqual(len(created_clients), 2)
        self.assertTrue(created_clients[0].closed)
        self.assertEqual(created_clients[1].retries, 2)

    def test_reset_after_operation_recreates_tcp_client_after_success(self) -> None:
        created_clients: list[FakeModbusTcpClient] = []

        def build_client(
            host: str,
            port: int,
            timeout: float,
            retries: int,
            framer: object | None = None,
        ) -> FakeModbusTcpClient:
            client = FakeModbusTcpClient(host, port, timeout, retries, framer)
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusTcpClient", side_effect=build_client):
            result = manager.execute_modbus_tcp(
                "127.0.0.1",
                502,
                timeout=1.0,
                retries=0,
                reset_after_operation=True,
                operation=lambda client: "ok",
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(created_clients), 2)
        self.assertTrue(created_clients[0].closed)
        self.assertFalse(created_clients[1].is_socket_open())

    def test_retries_connect_once_with_recreated_client(self) -> None:
        created_clients: list[FakeModbusTcpClient] = []

        def build_client(
            host: str,
            port: int,
            timeout: float,
            retries: int,
            framer: object | None = None,
        ) -> FakeModbusTcpClient:
            client = FakeModbusTcpClient(host, port, timeout, retries, framer)
            if not created_clients:
                client.connect_result = False
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusTcpClient", side_effect=build_client):
            result = manager.execute_modbus_tcp(
                "127.0.0.1",
                502,
                timeout=1.0,
                retries=0,
                operation=lambda client: "ok",
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(created_clients), 2)
        self.assertTrue(created_clients[0].closed)
        self.assertEqual(created_clients[0].connect_calls, 1)
        self.assertEqual(created_clients[1].connect_calls, 1)

    def test_modbus_tcp_runtime_snapshot_records_lock_and_operation_metrics(self) -> None:
        manager = ConnectionManager()
        with patch(
            "app.services.connection_manager.ModbusTcpClient",
            side_effect=lambda host, port, timeout, retries, framer=None: FakeModbusTcpClient(
                host,
                port,
                timeout,
                retries,
                framer,
            ),
        ):
            result = manager.execute_modbus_tcp(
                "127.0.0.1",
                502,
                timeout=1.0,
                retries=0,
                operation=lambda client: "ok",
            )

        snapshots = manager.get_modbus_tcp_runtime_snapshots()
        self.assertEqual(result, "ok")
        self.assertEqual(len(snapshots), 1)
        self.assertEqual(snapshots[0]["endpoint_label"], "127.0.0.1:502")
        self.assertEqual(snapshots[0]["tcp_sample_count"], 1)
        self.assertIsNotNone(snapshots[0]["last_lock_wait_ms"])
        self.assertIsNotNone(snapshots[0]["last_operation_duration_ms"])
        self.assertIsNotNone(snapshots[0]["last_round_trip_duration_ms"])

    def test_modbus_tcp_command_operation_reserves_priority_window(self) -> None:
        manager = ConnectionManager()
        with patch(
            "app.services.connection_manager.ModbusTcpClient",
            side_effect=lambda host, port, timeout, retries, framer=None: FakeModbusTcpClient(
                host,
                port,
                timeout,
                retries,
                framer,
            ),
        ):
            result = manager.execute_modbus_tcp(
                "127.0.0.1",
                502,
                timeout=1.0,
                retries=0,
                operation_kind="command",
                operation=lambda client: "ok",
            )

        snapshots = manager.get_modbus_tcp_runtime_snapshots()
        self.assertEqual(result, "ok")
        self.assertTrue(manager.is_modbus_tcp_priority_pending("127.0.0.1", 502))
        self.assertTrue(snapshots[0]["priority_pending"])
        self.assertIsNotNone(snapshots[0]["last_command_age_ms"])

    def test_reuses_persistent_rtu_client_for_same_signature(self) -> None:
        created_clients: list[FakeModbusSerialClient] = []

        def build_client(**kwargs: object) -> FakeModbusSerialClient:
            client = FakeModbusSerialClient(**kwargs)
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusSerialClient", side_effect=build_client):
            first_client_id = manager.execute_modbus_rtu(
                "COM1",
                19200,
                8,
                "N",
                1,
                timeout=1.0,
                retries=0,
                operation=lambda client: id(client),
            )
            second_client_id = manager.execute_modbus_rtu(
                "COM1",
                19200,
                8,
                "N",
                1,
                timeout=1.0,
                retries=0,
                operation=lambda client: id(client),
            )

        self.assertEqual(first_client_id, second_client_id)
        self.assertEqual(len(created_clients), 1)
        self.assertEqual(created_clients[0].connect_calls, 1)
        self.assertFalse(created_clients[0].closed)

    def test_recreates_persistent_rtu_client_when_serial_signature_changes(self) -> None:
        created_clients: list[FakeModbusSerialClient] = []

        def build_client(**kwargs: object) -> FakeModbusSerialClient:
            client = FakeModbusSerialClient(**kwargs)
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusSerialClient", side_effect=build_client):
            first_timeout = manager.execute_modbus_rtu(
                "COM1",
                19200,
                8,
                "N",
                1,
                timeout=1.0,
                retries=0,
                operation=lambda client: client.timeout,
            )
            second_timeout = manager.execute_modbus_rtu(
                "COM1",
                19200,
                8,
                "E",
                1,
                timeout=5.0,
                retries=0,
                operation=lambda client: client.timeout,
            )

        self.assertEqual(first_timeout, 1.0)
        self.assertEqual(second_timeout, 5.0)
        self.assertEqual(len(created_clients), 2)
        self.assertTrue(created_clients[0].closed)
        self.assertEqual(created_clients[1].connect_calls, 1)

    def test_execute_modbus_rtu_raw_reuses_client_and_returns_raw_response(self) -> None:
        created_clients: list[FakeModbusSerialClient] = []

        def build_client(**kwargs: object) -> FakeModbusSerialClient:
            client = FakeModbusSerialClient(**kwargs)
            client.socket.auto_response_payload = b"\x01\x06\x00\x02\x00\x37"
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusSerialClient", side_effect=build_client):
            response = manager.execute_modbus_rtu_raw(
                "COM1",
                19200,
                8,
                "N",
                1,
                timeout=1.0,
                retries=0,
                raw_request=b"\x01\x06\x00\x02\x00\x37",
                response_timeout=0.1,
            )

        self.assertEqual(response, b"\x01\x06\x00\x02\x00\x37")
        self.assertEqual(len(created_clients), 1)
        self.assertEqual(created_clients[0].socket.written_payloads, [b"\x01\x06\x00\x02\x00\x37"])

    def test_resets_persistent_rtu_client_after_connection_failure(self) -> None:
        created_clients: list[FakeModbusSerialClient] = []

        def build_client(**kwargs: object) -> FakeModbusSerialClient:
            client = FakeModbusSerialClient(**kwargs)
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusSerialClient", side_effect=build_client):
            result = manager.execute_modbus_rtu(
                "COM1",
                19200,
                8,
                "N",
                1,
                timeout=1.0,
                retries=0,
                operation=lambda client: self._rtu_operation_with_first_client_failure(
                    client,
                    created_clients[0],
                ),
            )

        self.assertEqual(result, "ok")
        self.assertEqual(len(created_clients), 2)
        self.assertTrue(created_clients[0].closed)
        self.assertEqual(created_clients[0].connect_calls, 1)
        self.assertEqual(created_clients[1].connect_calls, 1)

    def test_close_all_rtu_connections_closes_cached_clients(self) -> None:
        created_clients: list[FakeModbusSerialClient] = []

        def build_client(**kwargs: object) -> FakeModbusSerialClient:
            client = FakeModbusSerialClient(**kwargs)
            created_clients.append(client)
            return client

        manager = ConnectionManager()
        with patch("app.services.connection_manager.ModbusSerialClient", side_effect=build_client):
            manager.execute_modbus_rtu(
                "COM1",
                19200,
                8,
                "N",
                1,
                timeout=1.0,
                retries=0,
                operation=lambda client: "ok",
            )
            manager.close_all_rtu_connections()

        self.assertEqual(len(created_clients), 1)
        self.assertTrue(created_clients[0].closed)

    def _operation_with_first_client_failure(
        self,
        client: FakeModbusTcpClient,
        first_client: FakeModbusTcpClient,
    ) -> str:
        if client is first_client:
            raise ModbusConnectionException("stale socket")
        return "ok"

    def _rtu_operation_with_first_client_failure(
        self,
        client: FakeModbusSerialClient,
        first_client: FakeModbusSerialClient,
    ) -> str:
        if client is first_client:
            raise ModbusConnectionException("stale serial client")
        return "ok"


if __name__ == "__main__":
    unittest.main()

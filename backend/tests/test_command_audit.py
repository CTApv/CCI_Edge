import unittest
from unittest.mock import patch

from app.services.command_service import CommandService


class CommandAuditTests(unittest.TestCase):
    def test_every_command_response_records_an_audit_event(self) -> None:
        service = CommandService()
        with patch(
            "app.services.command_service.runtime_event_service.record_event"
        ) as record_event, patch(
            "app.services.command_service.device_service.get_device",
            return_value=None,
        ):
            response = service._build_response(
                success=False,
                message="Modbus TCP command failed.",
                device_id="device-1",
                command_key="active_power_limit",
                diagnostics={"stage": "connect", "requested_percent": 50.0},
            )

        self.assertFalse(response.success)
        record_event.assert_called_once()
        event = record_event.call_args.kwargs
        self.assertEqual(event["category"], "command")
        self.assertEqual(event["level"], "error")
        self.assertEqual(event["details"]["device_id"], "device-1")
        self.assertEqual(event["details"]["requested_percent"], 50.0)


if __name__ == "__main__":
    unittest.main()

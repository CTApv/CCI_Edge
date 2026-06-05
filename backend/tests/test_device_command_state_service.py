import tempfile
import unittest
from pathlib import Path

from app.config import settings
from app.services.device_command_state_service import DeviceCommandStateService


class DeviceCommandStateServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self._original_database_path = settings.database_path
        settings.database_path = Path(self._temp_dir.name) / "device-command-state-test.db"

    def tearDown(self) -> None:
        settings.database_path = self._original_database_path
        self._temp_dir.cleanup()

    def test_records_and_reads_last_successful_command(self) -> None:
        service = DeviceCommandStateService()

        service.record_successful_command(
            device_id="device-1",
            command_key="active_power_limit",
            value=40.0,
            display_value="40 %",
        )

        states = service.list_command_states("device-1")
        state = states.get("active_power_limit")

        self.assertIsNotNone(state)
        self.assertEqual(state.last_set_value, 40.0)
        self.assertEqual(state.last_set_display, "40 %")
        self.assertIsNotNone(state.last_set_at)

    def test_delete_device_states_removes_rows(self) -> None:
        service = DeviceCommandStateService()

        service.record_successful_command(
            device_id="device-1",
            command_key="active_power_limit",
            value=55.0,
            display_value="55 %",
        )
        service.delete_device_states("device-1")

        states = service.list_command_states("device-1")

        self.assertEqual(states, {})


if __name__ == "__main__":
    unittest.main()

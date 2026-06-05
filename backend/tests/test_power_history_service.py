import tempfile
import unittest
from pathlib import Path

from app.config import settings
from app.services.power_history_service import PowerHistoryService


class PowerHistoryServiceTests(unittest.TestCase):
    def test_row_count_estimate_quarantines_malformed_database(self) -> None:
        original_database_path = settings.power_history_database_path
        original_limit = settings.power_history_limit
        original_max_bytes = settings.power_history_max_bytes
        original_query_max_points = settings.power_history_query_max_points

        with tempfile.TemporaryDirectory() as temp_dir:
            database_path = Path(temp_dir) / "history.db"
            settings.power_history_database_path = database_path
            settings.power_history_limit = 120
            settings.power_history_max_bytes = 1024 * 1024
            settings.power_history_query_max_points = 120

            try:
                service = PowerHistoryService()
                database_path.write_bytes(b"this is not a sqlite database")

                row_count = service._read_fast_row_count_estimate()

                self.assertEqual(row_count, 0)
                self.assertTrue(database_path.exists())
                self.assertEqual(
                    len(list(database_path.parent.glob("history.db.corrupt-*"))),
                    1,
                )

                service.append_sample("device-1", "2026-04-29T12:00:00+00:00", 12.5)
                samples = service.get_device_history("device-1")
                self.assertEqual(len(samples), 1)
                self.assertEqual(samples[0].power_kw, 12.5)
            finally:
                settings.power_history_database_path = original_database_path
                settings.power_history_limit = original_limit
                settings.power_history_max_bytes = original_max_bytes
                settings.power_history_query_max_points = original_query_max_points


if __name__ == "__main__":
    unittest.main()

import os
import unittest
from unittest.mock import patch

from app.services.system_identity_service import DEFAULT_APP_VERSION, SystemIdentityService


class _SystemIdentityServiceForTest(SystemIdentityService):
    def _resolve_raw_identifier(self) -> tuple[str, str]:
        return "01:23:45:ab:cd:ef", "mac"

    def _env_or_git(self, env_name: str, *git_args: str) -> str | None:
        return None


class SystemIdentityServiceTests(unittest.TestCase):
    def test_snapshot_defaults_to_v1_and_formats_edge_id_from_mac(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            snapshot = _SystemIdentityServiceForTest()._build_snapshot()

        self.assertEqual(snapshot["app_version"], DEFAULT_APP_VERSION)
        self.assertEqual(snapshot["build_label"], DEFAULT_APP_VERSION)
        self.assertEqual(snapshot["edge_id"], "PV012345ABCDEF")
        self.assertEqual(snapshot["edge_id_source"], "mac")


if __name__ == "__main__":
    unittest.main()

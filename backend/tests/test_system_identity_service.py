import os
import unittest
from unittest.mock import patch

from app.services.system_identity_service import DEFAULT_APP_VERSION, SystemIdentityService


class _SystemIdentityServiceForTest(SystemIdentityService):
    def _resolve_raw_identifier(self) -> tuple[str, str]:
        return "01:23:45:ab:cd:ef", "mac"

    def _env_or_git(self, env_name: str, *git_args: str) -> str | None:
        return None

    def _read_build_metadata(self) -> dict[str, str]:
        return {}


class SystemIdentityServiceTests(unittest.TestCase):
    def test_snapshot_defaults_to_v1_and_formats_edge_id_from_mac(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            snapshot = _SystemIdentityServiceForTest()._build_snapshot()

        self.assertEqual(snapshot["app_version"], DEFAULT_APP_VERSION)
        self.assertIsNone(snapshot["release_tag"])
        self.assertEqual(snapshot["build_label"], DEFAULT_APP_VERSION)
        self.assertEqual(snapshot["edge_id"], "PV012345ABCDEF")
        self.assertEqual(snapshot["edge_id_source"], "mac")

    def test_runtime_version_aliases_and_release_tag_are_supported(self) -> None:
        with patch.dict(
            os.environ,
            {
                "PV_GUARDIAN_VERSION": "v1.2.0-rc1",
                "PV_GUARDIAN_RELEASE_TAG": "v1.2.0-rc1",
            },
            clear=True,
        ):
            snapshot = _SystemIdentityServiceForTest()._build_snapshot()

        self.assertEqual(snapshot["app_version"], "v1.2.0-rc1")
        self.assertEqual(snapshot["release_tag"], "v1.2.0-rc1")

    def test_immutable_image_metadata_wins_over_stale_runtime_build_metadata(self) -> None:
        service = _SystemIdentityServiceForTest()
        service._read_build_metadata = lambda: {
            "PV_EDGE_MANAGER_VERSION": "v1.2.0-rc1",
            "PV_EDGE_MANAGER_RELEASE_TAG": "v1.2.0-rc1",
            "PV_EDGE_MANAGER_BUILD_LABEL": "v1.2.0-rc1-tag-abcdef123456",
            "PV_EDGE_MANAGER_BUILD_COMMIT": "abcdef123456",
            "PV_EDGE_MANAGER_BUILD_TIME": "2026-06-15T10:00:00Z",
        }
        with patch.dict(
            os.environ,
            {
                "PV_EDGE_MANAGER_VERSION": "v1.2.0-rc1",
                "PV_EDGE_MANAGER_BUILD_LABEL": "v1.0.0-docker-production",
                "PV_EDGE_MANAGER_BUILD_COMMIT": "09305feceb40",
                "PV_EDGE_MANAGER_BUILD_TIME": "2026-06-05T12:14:18Z",
            },
            clear=True,
        ):
            snapshot = service._build_snapshot()

        self.assertEqual(snapshot["app_version"], "v1.2.0-rc1")
        self.assertEqual(snapshot["release_tag"], "v1.2.0-rc1")
        self.assertEqual(snapshot["build_label"], "v1.2.0-rc1-tag-abcdef123456")
        self.assertEqual(snapshot["build_commit"], "abcdef123456")
        self.assertEqual(snapshot["build_time"], "2026-06-15T10:00:00Z")


if __name__ == "__main__":
    unittest.main()

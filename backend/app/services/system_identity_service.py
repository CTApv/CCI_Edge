from __future__ import annotations

import os
import platform
import re
import socket
import subprocess
import uuid
from datetime import UTC, datetime
from pathlib import Path

DEFAULT_APP_VERSION = "v1.0.0"
_VIRTUAL_INTERFACE_PREFIXES = ("br-", "docker", "tailscale", "veth", "virbr", "zt")


class SystemIdentityService:
    def __init__(self) -> None:
        self._started_at = datetime.now(UTC).isoformat()
        self._cached_identity: dict[str, object] | None = None

    def get_snapshot(self) -> dict[str, object]:
        if self._cached_identity is None:
            self._cached_identity = self._build_snapshot()
        return {
            **self._cached_identity,
            "backend_started_at": self._started_at,
        }

    def _build_snapshot(self) -> dict[str, object]:
        raw_identifier, identifier_source = self._resolve_raw_identifier()
        edge_id = self._format_edge_id(raw_identifier, source=identifier_source)
        commit = self._env_or_git("PV_EDGE_MANAGER_BUILD_COMMIT", "rev-parse", "--short=12", "HEAD")
        app_version = os.getenv("PV_EDGE_MANAGER_VERSION", DEFAULT_APP_VERSION)
        build_label = (
            os.getenv("PV_EDGE_MANAGER_BUILD_LABEL")
            or app_version
            or commit
        )

        return {
            "edge_id": edge_id,
            "edge_id_source": identifier_source,
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "app_version": app_version,
            "build_label": build_label,
            "build_commit": commit,
            "build_time": os.getenv("PV_EDGE_MANAGER_BUILD_TIME"),
            "backend_path": str(Path(__file__).resolve().parents[2]),
        }

    def _resolve_raw_identifier(self) -> tuple[str, str]:
        explicit_id = os.getenv("PV_EDGE_MANAGER_EDGE_ID")
        if explicit_id and explicit_id.strip():
            return explicit_id.strip(), "env"

        mac_addresses = self._collect_mac_addresses()
        if mac_addresses:
            return mac_addresses[0], "mac"

        for source, path in (
            ("machine-id", Path("/etc/machine-id")),
            ("dbus-machine-id", Path("/var/lib/dbus/machine-id")),
            ("dmi-product-uuid", Path("/sys/class/dmi/id/product_uuid")),
            ("dmi-product-serial", Path("/sys/class/dmi/id/product_serial")),
        ):
            value = self._read_text(path)
            if value:
                return value, source

        return f"{socket.gethostname()}:{uuid.getnode()}", "hostname-mac"

    def _collect_mac_addresses(self) -> list[str]:
        mac_candidates: list[tuple[int, str]] = []
        sys_class_net = Path("/sys/class/net")
        if sys_class_net.exists():
            for address_path in sorted(sys_class_net.glob("*/address")):
                interface_name = address_path.parent.name
                if interface_name == "lo":
                    continue
                value = self._read_text(address_path)
                if value and value != "00:00:00:00:00:00":
                    normalized_mac = self._normalize_mac(value)
                    if normalized_mac is not None:
                        mac_candidates.append(
                            (self._mac_interface_priority(address_path.parent), normalized_mac)
                        )

        node = uuid.getnode()
        if node:
            node_label = ":".join(f"{(node >> shift) & 0xFF:02x}" for shift in range(40, -1, -8))
            normalized_node = self._normalize_mac(node_label)
            if normalized_node is not None and normalized_node != "000000000000":
                mac_candidates.append((100, normalized_node))

        ordered_unique_addresses: list[str] = []
        for _, mac_address in sorted(mac_candidates, key=lambda item: (item[0], item[1])):
            if mac_address not in ordered_unique_addresses:
                ordered_unique_addresses.append(mac_address)
        return ordered_unique_addresses

    def _read_text(self, path: Path) -> str | None:
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError:
            return None
        return value or None

    def _format_edge_id(self, raw_identifier: str, *, source: str) -> str:
        if source == "env":
            return raw_identifier.strip().upper()

        normalized_mac = self._normalize_mac(raw_identifier)
        if normalized_mac is not None:
            return f"PV{normalized_mac}"

        node = uuid.getnode()
        fallback_mac = self._normalize_mac(f"{node:012x}")
        if fallback_mac is not None:
            return f"PV{fallback_mac}"

        sanitized = re.sub(r"[^0-9A-Z]", "", raw_identifier.upper())
        return f"PV{sanitized[:12] or 'UNKNOWN'}"

    def _normalize_mac(self, value: str) -> str | None:
        normalized = re.sub(r"[^0-9A-Fa-f]", "", value).upper()
        if len(normalized) != 12:
            return None
        return normalized

    def _mac_interface_priority(self, interface_path: Path) -> int:
        interface_name = interface_path.name.lower()
        if (interface_path / "device").exists():
            return 0
        if interface_name.startswith(("eth", "en", "wl")):
            return 1
        if interface_name.startswith(_VIRTUAL_INTERFACE_PREFIXES):
            return 50
        return 10

    def _env_or_git(self, env_name: str, *git_args: str) -> str | None:
        env_value = os.getenv(env_name)
        if env_value and env_value.strip():
            return env_value.strip()

        try:
            completed = subprocess.run(
                ["git", *git_args],
                cwd=Path(__file__).resolve().parents[3],
                check=True,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return None

        value = completed.stdout.strip()
        return value or None


system_identity_service = SystemIdentityService()

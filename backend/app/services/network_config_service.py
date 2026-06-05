from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from ipaddress import IPv4Address, ip_address
from threading import Lock, Timer

from app.logger import get_logger
from app.services.network_interface_service import network_interface_service

logger = get_logger("pv_edge_manager.network_config")

NETWORK_CONFIRMATION_TIMEOUT_SECONDS = 30
IGNORED_INTERFACE_PREFIXES = ("veth", "br-", "docker", "virbr", "tap", "tun")


@dataclass(slots=True, frozen=True)
class _InterfaceSnapshot:
    interface_name: str
    connection_name: str | None
    connection_existed: bool
    ipv4_method: str
    addresses: tuple[str, ...]
    gateway: str | None
    dns_servers: tuple[str, ...]
    autoconnect: bool | None
    never_default: bool


@dataclass(slots=True)
class _PendingNetworkChange:
    change_id: str
    interface_name: str
    connection_name: str | None
    created_connection_name: str | None
    expires_at: datetime
    snapshot_before: _InterfaceSnapshot


class NetworkConfigService:
    def __init__(self) -> None:
        self._lock = Lock()
        self._pending_change: _PendingNetworkChange | None = None
        self._rollback_timer: Timer | None = None

    def get_snapshot(self) -> dict[str, object]:
        if not self._is_linux():
            return {
                "supported": False,
                "apply_supported": False,
                "platform": platform.system().lower(),
                "manager": "unsupported",
                "message": "Configurazione IP modificabile dall'app disponibile solo su Linux con NetworkManager.",
                "confirmation_timeout_seconds": NETWORK_CONFIRMATION_TIMEOUT_SECONDS,
                "pending_change": None,
                "interfaces": self._build_read_only_interfaces(),
            }

        if not self._has_nmcli():
            return {
                "supported": False,
                "apply_supported": False,
                "platform": "linux",
                "manager": "missing",
                "message": "NetworkManager o nmcli non sono disponibili su questo sistema.",
                "confirmation_timeout_seconds": NETWORK_CONFIRMATION_TIMEOUT_SECONDS,
                "pending_change": None,
                "interfaces": self._build_read_only_interfaces(),
            }

        pending_change = self._serialize_pending_change()
        interfaces = self._list_linux_interfaces()
        return {
            "supported": True,
            "apply_supported": True,
            "platform": "linux",
            "manager": "networkmanager",
            "message": (
                "Le modifiche IP vengono applicate via NetworkManager e richiedono conferma entro 30 secondi."
            ),
            "confirmation_timeout_seconds": NETWORK_CONFIRMATION_TIMEOUT_SECONDS,
            "pending_change": pending_change,
            "interfaces": interfaces,
        }

    def apply_configuration(
        self,
        *,
        interface_name: str,
        ipv4_method: str,
        address: str | None,
        prefix_length: int | None,
        gateway: str | None,
        dns_servers: list[str],
        autoconnect: bool,
        use_default_route: bool,
        addresses: list[dict[str, object]] | None = None,
    ) -> dict[str, object]:
        if not self._is_linux() or not self._has_nmcli():
            raise ValueError("Configurazione rete modificabile solo su Linux con NetworkManager.")

        normalized_interface = interface_name.strip()
        if normalized_interface == "":
            raise ValueError("Seleziona una scheda di rete valida.")

        method = ipv4_method.strip().lower()
        if method not in {"auto", "manual"}:
            raise ValueError("Metodo IPv4 non supportato.")

        normalized_address = self._normalize_ipv4(address, field_name="Indirizzo IPv4")
        normalized_gateway = self._normalize_ipv4(gateway, field_name="Gateway", allow_empty=True)
        normalized_dns_servers = self._normalize_dns_servers(dns_servers)
        normalized_addresses = self._normalize_ipv4_address_entries(addresses or [])

        if not normalized_addresses and normalized_address is not None:
            if prefix_length is None or not (1 <= int(prefix_length) <= 32):
                raise ValueError("Il prefisso IPv4 deve essere compreso tra 1 e 32.")
            normalized_addresses = [f"{normalized_address}/{int(prefix_length)}"]

        if method == "manual":
            if not normalized_addresses:
                raise ValueError("Per un IP statico devi indicare almeno un indirizzo IPv4.")
        else:
            prefix_length = None
            normalized_addresses = []

        interfaces = self._list_linux_interfaces()
        selected_interface = next(
            (item for item in interfaces if item["interface_name"] == normalized_interface),
            None,
        )
        if selected_interface is None:
            raise ValueError("La scheda di rete selezionata non e disponibile.")
        if not bool(selected_interface.get("editable", False)):
            raise ValueError("La scheda di rete selezionata non e modificabile dall'app.")

        with self._lock:
            if self._pending_change is not None:
                raise ValueError(
                    "E' gia presente una modifica di rete in attesa di conferma o rollback.",
                )

        snapshot_before = self._capture_interface_snapshot(normalized_interface)
        connection_name, created_connection_name = self._ensure_connection_profile(
            normalized_interface,
            preferred_name=snapshot_before.connection_name,
        )

        self._apply_connection_settings(
            connection_name=connection_name,
            interface_name=normalized_interface,
            ipv4_method=method,
            addresses=normalized_addresses,
            gateway=normalized_gateway,
            dns_servers=normalized_dns_servers,
            autoconnect=autoconnect,
            use_default_route=use_default_route,
        )
        self._bring_connection_up(connection_name)

        pending_change = _PendingNetworkChange(
            change_id=datetime.now(UTC).isoformat(),
            interface_name=normalized_interface,
            connection_name=connection_name,
            created_connection_name=created_connection_name,
            expires_at=datetime.now(UTC) + timedelta(seconds=NETWORK_CONFIRMATION_TIMEOUT_SECONDS),
            snapshot_before=snapshot_before,
        )
        self._store_pending_change(pending_change)
        logger.info(
            "Applied network change on %s via %s (%s). Confirmation required within %ss.",
            normalized_interface,
            connection_name,
            method,
            NETWORK_CONFIRMATION_TIMEOUT_SECONDS,
        )
        return self.get_snapshot()

    def confirm_pending_change(self) -> dict[str, object]:
        with self._lock:
            pending_change = self._pending_change
            self._clear_pending_change_locked()

        if pending_change is not None:
            logger.info(
                "Confirmed network change on %s via %s.",
                pending_change.interface_name,
                pending_change.connection_name,
            )
        return self.get_snapshot()

    def rollback_pending_change(self) -> dict[str, object]:
        pending_change = self._pop_pending_change()
        if pending_change is None:
            return self.get_snapshot()

        self._restore_snapshot(pending_change)
        logger.info(
            "Rolled back network change on %s via %s.",
            pending_change.interface_name,
            pending_change.connection_name,
        )
        return self.get_snapshot()

    def _is_linux(self) -> bool:
        return platform.system().strip().lower() == "linux"

    def _has_nmcli(self) -> bool:
        return shutil.which("nmcli") is not None

    def _is_ignored_interface(self, interface_name: str) -> bool:
        normalized = interface_name.strip().lower()
        return any(normalized.startswith(prefix) for prefix in IGNORED_INTERFACE_PREFIXES)

    def _build_read_only_interfaces(self) -> list[dict[str, object]]:
        interfaces: list[dict[str, object]] = []
        for item in network_interface_service.list_ipv4_bind_addresses():
            interface_name = str(item.get("name", "Interface"))
            if self._is_ignored_interface(interface_name):
                continue
            address = str(item.get("address", "")).strip()
            if address in {"", "0.0.0.0", "127.0.0.1"}:
                continue
            parsed_address = self._parse_address_with_prefix(address)
            interfaces.append(
                {
                    "interface_name": interface_name,
                    "device_type": "unknown",
                    "state": "available",
                    "connection_name": None,
                    "mac_address": None,
                    "live_addresses": [parsed_address] if parsed_address is not None else [],
                    "live_gateway": None,
                    "live_dns_servers": [],
                    "ipv4_method": "unknown",
                    "configured_addresses": [parsed_address] if parsed_address is not None else [],
                    "gateway": None,
                    "dns_servers": [],
                    "autoconnect": None,
                    "use_default_route": False,
                    "editable": False,
                }
            )
        return interfaces

    def _list_linux_interfaces(self) -> list[dict[str, object]]:
        device_rows = self._parse_device_status_rows(
            self._run_nmcli(["-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status"]),
        )
        connection_profiles = self._list_connection_profiles()

        interfaces: list[dict[str, object]] = []
        for row in device_rows:
            if row["device_type"] != "ethernet":
                continue
            if self._is_ignored_interface(row["interface_name"]):
                continue

            connection_name = self._resolve_connection_name(
                interface_name=row["interface_name"],
                active_connection_name=row["connection_name"],
                profiles=connection_profiles,
            )
            live_info = self._parse_device_show_output(
                self._run_nmcli(
                    [
                        "-t",
                        "-f",
                        "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
                        "device",
                        "show",
                        row["interface_name"],
                    ]
                ),
            )
            connection_info = (
                self._parse_connection_show_output(
                    self._run_nmcli(
                        [
                            "-t",
                            "-f",
                            "connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns,ipv4.never-default",
                            "connection",
                            "show",
                            connection_name,
                        ]
                    )
                )
                if connection_name
                else None
            )

            interfaces.append(
                {
                    "interface_name": row["interface_name"],
                    "device_type": row["device_type"],
                    "state": row["state"],
                    "connection_name": connection_name,
                    "mac_address": live_info["mac_address"],
                    "live_addresses": live_info["addresses"],
                    "live_gateway": live_info["gateway"],
                    "live_dns_servers": live_info["dns_servers"],
                    "ipv4_method": connection_info["ipv4_method"] if connection_info else "unknown",
                    "configured_addresses": connection_info["addresses"] if connection_info else [],
                    "gateway": connection_info["gateway"] if connection_info else None,
                    "dns_servers": connection_info["dns_servers"] if connection_info else [],
                    "autoconnect": connection_info["autoconnect"] if connection_info else None,
                    "use_default_route": (
                        not connection_info["never_default"] if connection_info else False
                    ),
                    "editable": True,
                }
            )

        interfaces.sort(key=lambda item: str(item["interface_name"]).lower())
        return interfaces

    def _list_connection_profiles(self) -> list[dict[str, str | None]]:
        try:
            return self._parse_connection_profile_rows(
                self._run_nmcli(
                    ["-t", "-f", "NAME,TYPE,connection.interface-name", "connection", "show"],
                ),
            )
        except RuntimeError as exc:
            if "invalid field 'connection.interface-name'" not in str(exc):
                raise

        profiles: list[dict[str, str | None]] = []
        fallback_rows = self._parse_connection_name_rows(
            self._run_nmcli(["-t", "-f", "NAME,TYPE", "connection", "show"]),
        )
        for profile in fallback_rows:
            interface_name: str | None = None
            try:
                raw_value = self._run_nmcli(
                    ["-g", "connection.interface-name", "connection", "show", profile["name"]],
                ).strip()
                interface_name = raw_value or None
            except RuntimeError:
                interface_name = None
            profiles.append(
                {
                    "name": profile["name"],
                    "type": profile["type"],
                    "interface_name": interface_name,
                }
            )
        return profiles

    def _capture_interface_snapshot(self, interface_name: str) -> _InterfaceSnapshot:
        interfaces = self._list_linux_interfaces()
        interface = next(
            (item for item in interfaces if item["interface_name"] == interface_name),
            None,
        )
        if interface is None:
            raise ValueError("Scheda di rete non trovata.")

        configured_addresses = tuple(
            f'{entry["address"]}/{entry["prefix_length"]}'
            for entry in interface["configured_addresses"]
        )
        return _InterfaceSnapshot(
            interface_name=interface_name,
            connection_name=str(interface["connection_name"])
            if interface["connection_name"] is not None
            else None,
            connection_existed=interface["connection_name"] is not None,
            ipv4_method=str(interface["ipv4_method"]),
            addresses=configured_addresses,
            gateway=str(interface["gateway"]) if interface["gateway"] is not None else None,
            dns_servers=tuple(str(item) for item in interface["dns_servers"]),
            autoconnect=(
                bool(interface["autoconnect"])
                if isinstance(interface["autoconnect"], bool)
                else None
            ),
            never_default=not bool(interface["use_default_route"]),
        )

    def _ensure_connection_profile(
        self,
        interface_name: str,
        *,
        preferred_name: str | None,
    ) -> tuple[str, str | None]:
        if preferred_name:
            return preferred_name, None

        connection_name = f"pv-edge-{interface_name}"
        self._run_nmcli(
            [
                "connection",
                "add",
                "type",
                "ethernet",
                "ifname",
                interface_name,
                "con-name",
                connection_name,
                "ipv4.method",
                "auto",
                "ipv6.method",
                "ignore",
            ]
        )
        return connection_name, connection_name

    def _apply_connection_settings(
        self,
        *,
        connection_name: str,
        interface_name: str,
        ipv4_method: str,
        addresses: list[str],
        gateway: str | None,
        dns_servers: list[str],
        autoconnect: bool,
        use_default_route: bool,
    ) -> None:
        addresses_value = ",".join(addresses) if ipv4_method == "manual" else ""
        dns_value = ",".join(dns_servers)
        self._run_nmcli(
            [
                "connection",
                "modify",
                connection_name,
                "connection.interface-name",
                interface_name,
                "connection.autoconnect",
                "yes" if autoconnect else "no",
                "ipv4.method",
                ipv4_method,
                "ipv4.addresses",
                addresses_value,
                "ipv4.gateway",
                gateway or "",
                "ipv4.dns",
                dns_value,
                "ipv4.never-default",
                "no" if use_default_route else "yes",
                "ipv6.method",
                "ignore",
            ]
        )

    def _bring_connection_up(self, connection_name: str) -> None:
        self._run_nmcli(["connection", "up", connection_name])

    def _store_pending_change(self, pending_change: _PendingNetworkChange) -> None:
        with self._lock:
            self._clear_pending_change_locked()
            self._pending_change = pending_change
            self._rollback_timer = Timer(
                NETWORK_CONFIRMATION_TIMEOUT_SECONDS,
                self._auto_rollback_pending_change,
                args=(pending_change.change_id,),
            )
            self._rollback_timer.daemon = True
            self._rollback_timer.start()

    def _serialize_pending_change(self) -> dict[str, object] | None:
        with self._lock:
            pending_change = self._pending_change
            if pending_change is None:
                return None

            remaining_seconds = max(
                0,
                int((pending_change.expires_at - datetime.now(UTC)).total_seconds()),
            )
            return {
                "interface_name": pending_change.interface_name,
                "connection_name": pending_change.connection_name,
                "expires_at": pending_change.expires_at.isoformat(),
                "remaining_seconds": remaining_seconds,
            }

    def _pop_pending_change(self) -> _PendingNetworkChange | None:
        with self._lock:
            pending_change = self._pending_change
            self._clear_pending_change_locked()
            return pending_change

    def _clear_pending_change_locked(self) -> None:
        if self._rollback_timer is not None:
            self._rollback_timer.cancel()
            self._rollback_timer = None
        self._pending_change = None

    def _auto_rollback_pending_change(self, change_id: str) -> None:
        with self._lock:
            pending_change = self._pending_change
            if pending_change is None or pending_change.change_id != change_id:
                return
            self._clear_pending_change_locked()

        try:
            self._restore_snapshot(pending_change)
            logger.warning(
                "Rolled back unconfirmed network change on %s after timeout.",
                pending_change.interface_name,
            )
        except Exception as exc:
            logger.error(
                "Automatic rollback failed for %s: %s",
                pending_change.interface_name,
                str(exc),
            )

    def _restore_snapshot(self, pending_change: _PendingNetworkChange) -> None:
        snapshot = pending_change.snapshot_before
        if not snapshot.connection_existed:
            if pending_change.created_connection_name:
                self._run_nmcli(
                    ["connection", "delete", pending_change.created_connection_name],
                )
            return

        if snapshot.connection_name is None:
            return

        self._run_nmcli(
            [
                "connection",
                "modify",
                snapshot.connection_name,
                "connection.interface-name",
                snapshot.interface_name,
                "connection.autoconnect",
                self._format_bool(snapshot.autoconnect, default="yes"),
                "ipv4.method",
                snapshot.ipv4_method if snapshot.ipv4_method in {"auto", "manual"} else "auto",
                "ipv4.addresses",
                ",".join(snapshot.addresses),
                "ipv4.gateway",
                snapshot.gateway or "",
                "ipv4.dns",
                ",".join(snapshot.dns_servers),
                "ipv4.never-default",
                "yes" if snapshot.never_default else "no",
                "ipv6.method",
                "ignore",
            ]
        )
        self._bring_connection_up(snapshot.connection_name)

    def _format_bool(self, value: bool | None, *, default: str) -> str:
        if value is None:
            return default
        return "yes" if value else "no"

    def _run_nmcli(self, args: list[str]) -> str:
        command = ["nmcli", *args]
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip() or "nmcli failed"
            raise RuntimeError(detail)
        return completed.stdout

    def _parse_device_status_rows(self, output: str) -> list[dict[str, str]]:
        rows: list[dict[str, str]] = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped == "":
                continue
            parts = stripped.split(":", 3)
            if len(parts) < 4:
                continue
            rows.append(
                {
                    "interface_name": parts[0],
                    "device_type": parts[1],
                    "state": parts[2],
                    "connection_name": None if parts[3] in {"", "--"} else parts[3],
                }
            )
        return rows

    def _parse_connection_profile_rows(self, output: str) -> list[dict[str, str | None]]:
        profiles: list[dict[str, str | None]] = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped == "":
                continue
            parts = stripped.split(":", 2)
            if len(parts) < 3:
                continue
            profiles.append(
                {
                    "name": parts[0],
                    "type": parts[1],
                    "interface_name": None if parts[2] == "" else parts[2],
                }
            )
        return profiles

    def _parse_connection_name_rows(self, output: str) -> list[dict[str, str]]:
        profiles: list[dict[str, str]] = []
        for line in output.splitlines():
            stripped = line.strip()
            if stripped == "":
                continue
            parts = stripped.split(":", 1)
            if len(parts) < 2:
                continue
            profiles.append(
                {
                    "name": parts[0],
                    "type": parts[1],
                }
            )
        return profiles

    def _resolve_connection_name(
        self,
        *,
        interface_name: str,
        active_connection_name: str | None,
        profiles: list[dict[str, str | None]],
    ) -> str | None:
        if active_connection_name:
            return active_connection_name

        for profile in profiles:
            if profile["interface_name"] != interface_name:
                continue
            profile_type = str(profile.get("type", "")).lower()
            if profile_type not in {"802-3-ethernet", "ethernet"}:
                continue
            return str(profile["name"])
        return None

    def _parse_device_show_output(self, output: str) -> dict[str, object]:
        mac_address: str | None = None
        addresses: list[dict[str, object]] = []
        gateway: str | None = None
        dns_servers: list[str] = []

        for line in output.splitlines():
            stripped = line.strip()
            if stripped == "":
                continue
            key, _, value = stripped.partition(":")
            if key == "GENERAL.HWADDR":
                mac_address = value or None
            elif key.startswith("IP4.ADDRESS"):
                parsed = self._parse_address_with_prefix(value)
                if parsed is not None:
                    addresses.append(parsed)
            elif key == "IP4.GATEWAY":
                gateway = value or None
            elif key.startswith("IP4.DNS"):
                if value:
                    dns_servers.append(value)

        return {
            "mac_address": mac_address,
            "addresses": addresses,
            "gateway": gateway,
            "dns_servers": dns_servers,
        }

    def _parse_connection_show_output(self, output: str) -> dict[str, object]:
        autoconnect: bool | None = None
        ipv4_method = "unknown"
        addresses: list[dict[str, object]] = []
        gateway: str | None = None
        dns_servers: list[str] = []
        never_default = False

        for line in output.splitlines():
            stripped = line.strip()
            if stripped == "":
                continue
            key, _, value = stripped.partition(":")
            if key == "connection.autoconnect":
                autoconnect = self._parse_bool(value)
            elif key == "ipv4.method":
                ipv4_method = value or "unknown"
            elif key == "ipv4.addresses":
                for item in self._split_csv(value):
                    parsed = self._parse_address_with_prefix(item)
                    if parsed is not None:
                        addresses.append(parsed)
            elif key == "ipv4.gateway":
                gateway = value or None
            elif key == "ipv4.dns":
                dns_servers = self._split_csv(value)
            elif key == "ipv4.never-default":
                never_default = bool(self._parse_bool(value))

        return {
            "autoconnect": autoconnect,
            "ipv4_method": ipv4_method,
            "addresses": addresses,
            "gateway": gateway,
            "dns_servers": dns_servers,
            "never_default": never_default,
        }

    def _split_csv(self, value: str) -> list[str]:
        return [item.strip() for item in value.split(",") if item.strip() != ""]

    def _parse_address_with_prefix(self, value: str) -> dict[str, object] | None:
        normalized = value.strip()
        if normalized == "":
            return None

        address_part, separator, prefix_part = normalized.partition("/")
        try:
            parsed_address = ip_address(address_part.strip())
        except ValueError:
            return None
        if not isinstance(parsed_address, IPv4Address):
            return None

        prefix_length = int(prefix_part) if separator else 32
        return {
            "address": str(parsed_address),
            "prefix_length": prefix_length,
        }

    def _parse_bool(self, value: str) -> bool | None:
        normalized = value.strip().lower()
        if normalized in {"yes", "true", "on", "1"}:
            return True
        if normalized in {"no", "false", "off", "0"}:
            return False
        return None

    def _normalize_ipv4(
        self,
        value: str | None,
        *,
        field_name: str,
        allow_empty: bool = False,
    ) -> str | None:
        normalized = (value or "").strip()
        if normalized == "":
            if allow_empty:
                return None
            return None

        try:
            parsed = ip_address(normalized)
        except ValueError as exc:
            raise ValueError(f"{field_name} non valido.") from exc

        if not isinstance(parsed, IPv4Address):
            raise ValueError(f"{field_name} deve essere IPv4.")
        return str(parsed)

    def _normalize_dns_servers(self, values: list[str]) -> list[str]:
        normalized_values: list[str] = []
        for value in values:
            normalized = value.strip()
            if normalized == "":
                continue
            normalized_values.append(
                self._normalize_ipv4(normalized, field_name="DNS") or normalized,
            )
        return normalized_values

    def _normalize_ipv4_address_entries(self, values: list[dict[str, object]]) -> list[str]:
        normalized_values: list[str] = []
        seen: set[str] = set()
        for index, value in enumerate(values, start=1):
            raw_address = str(value.get("address") or "").strip()
            if raw_address == "":
                continue
            normalized_address = self._normalize_ipv4(
                raw_address,
                field_name=f"Indirizzo IPv4 {index}",
            )
            raw_prefix = value.get("prefix_length")
            try:
                prefix_length = int(raw_prefix)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Prefisso IPv4 {index} non valido.") from exc
            if not (1 <= prefix_length <= 32):
                raise ValueError(f"Il prefisso IPv4 {index} deve essere compreso tra 1 e 32.")
            normalized_entry = f"{normalized_address}/{prefix_length}"
            if normalized_entry in seen:
                continue
            seen.add(normalized_entry)
            normalized_values.append(normalized_entry)
        return normalized_values


network_config_service = NetworkConfigService()

import platform
import re
import socket
import subprocess


class NetworkInterfaceService:
    def list_ipv4_bind_addresses(self) -> list[dict[str, str]]:
        interfaces: list[dict[str, str]] = [
            {"name": "Tutte le interfacce", "address": "0.0.0.0"},
            {"name": "Loopback locale", "address": "127.0.0.1"},
        ]
        seen_addresses = {interface["address"] for interface in interfaces}

        for interface in self._list_platform_ipv4_interfaces():
            address = interface["address"]
            if address in seen_addresses:
                continue
            seen_addresses.add(address)
            interfaces.append(interface)

        return interfaces

    def _list_platform_ipv4_interfaces(self) -> list[dict[str, str]]:
        system_name = platform.system().lower()
        if system_name == "windows":
            return self._list_windows_ipv4_interfaces()
        return self._list_socket_ipv4_interfaces()

    def _list_windows_ipv4_interfaces(self) -> list[dict[str, str]]:
        try:
            result = subprocess.run(
                ["ipconfig"],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="ignore",
                check=False,
            )
        except Exception:
            return self._list_socket_ipv4_interfaces()

        interfaces: list[dict[str, str]] = []
        current_name: str | None = None
        adapter_pattern = re.compile(r"^[^\r\n:]+adapter\s+(.+):\s*$", re.IGNORECASE)
        ipv4_pattern = re.compile(r"IPv4[^:]*:\s*([0-9]{1,3}(?:\.[0-9]{1,3}){3})")

        for line in result.stdout.splitlines():
            stripped = line.strip()
            adapter_match = adapter_pattern.match(stripped)
            if adapter_match:
                current_name = adapter_match.group(1).strip()
                continue

            ipv4_match = ipv4_pattern.search(stripped)
            if ipv4_match:
                interfaces.append(
                    {
                        "name": current_name or "Scheda di rete",
                        "address": ipv4_match.group(1),
                    }
                )

        if interfaces:
            return interfaces
        return self._list_socket_ipv4_interfaces()

    def _list_socket_ipv4_interfaces(self) -> list[dict[str, str]]:
        interfaces: list[dict[str, str]] = []
        try:
            hostname = socket.gethostname()
            address_info = socket.getaddrinfo(hostname, None, family=socket.AF_INET)
        except Exception:
            return interfaces

        for info in address_info:
            address = info[4][0]
            interfaces.append({"name": hostname, "address": address})

        return interfaces


network_interface_service = NetworkInterfaceService()

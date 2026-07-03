import unittest
from unittest.mock import patch

from app.services.network_config_service import NetworkConfigService


class NetworkConfigServiceTests(unittest.TestCase):
    def test_snapshot_is_read_only_outside_linux(self) -> None:
        service = NetworkConfigService()

        with patch("app.services.network_config_service.platform.system", return_value="Windows"):
            snapshot = service.get_snapshot()

        self.assertFalse(snapshot["supported"])
        self.assertFalse(snapshot["apply_supported"])
        self.assertEqual(snapshot["manager"], "unsupported")

    def test_linux_snapshot_parses_networkmanager_state(self) -> None:
        service = NetworkConfigService()

        responses = {
            (
                "-t",
                "-f",
                "DEVICE,TYPE,STATE,CONNECTION",
                "device",
                "status",
            ): (
                "eth0:ethernet:connected:Plant LAN\n"
                "eth1:ethernet:disconnected:--\n"
                "veth1ee7b46:ethernet:connected:--\n"
                "lo:loopback:unmanaged:--\n"
            ),
            (
                "-t",
                "-f",
                "NAME,TYPE,connection.interface-name",
                "connection",
                "show",
            ): "Plant LAN:802-3-ethernet:eth0\nMgmt LAN:802-3-ethernet:eth1\n",
            (
                "-t",
                "-f",
                "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
                "device",
                "show",
                "eth0",
            ): (
                "GENERAL.HWADDR:AA:BB:CC:DD:EE:FF\n"
                "IP4.ADDRESS[1]:192.168.2.249/24\n"
                "IP4.GATEWAY:192.168.2.1\n"
                "IP4.DNS[1]:8.8.8.8\n"
            ),
            (
                "-t",
                "-f",
                "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
                "device",
                "show",
                "eth1",
            ): "GENERAL.HWADDR:11:22:33:44:55:66\n",
            (
                "-t",
                "-f",
                "connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns,ipv4.never-default",
                "connection",
                "show",
                "Plant LAN",
            ): (
                "connection.autoconnect:yes\n"
                "ipv4.method:manual\n"
                "ipv4.addresses:192.168.2.249/24\n"
                "ipv4.gateway:192.168.2.1\n"
                "ipv4.dns:8.8.8.8,1.1.1.1\n"
                "ipv4.never-default:no\n"
            ),
            (
                "-t",
                "-f",
                "connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns,ipv4.never-default",
                "connection",
                "show",
                "Mgmt LAN",
            ): (
                "connection.autoconnect:no\n"
                "ipv4.method:auto\n"
                "ipv4.addresses:\n"
                "ipv4.gateway:\n"
                "ipv4.dns:\n"
                "ipv4.never-default:yes\n"
            ),
        }

        def fake_run_nmcli(args: list[str]) -> str:
            return responses[tuple(args)]

        with (
            patch("app.services.network_config_service.platform.system", return_value="Linux"),
            patch("app.services.network_config_service.shutil.which", return_value="/usr/bin/nmcli"),
            patch.object(service, "_run_nmcli", side_effect=fake_run_nmcli),
        ):
            snapshot = service.get_snapshot()

        self.assertTrue(snapshot["supported"])
        self.assertEqual(snapshot["manager"], "networkmanager")
        self.assertEqual(len(snapshot["interfaces"]), 2)
        self.assertNotIn(
            "veth1ee7b46",
            {item["interface_name"] for item in snapshot["interfaces"]},
        )

        eth0 = next(item for item in snapshot["interfaces"] if item["interface_name"] == "eth0")
        eth1 = next(item for item in snapshot["interfaces"] if item["interface_name"] == "eth1")

        self.assertEqual(eth0["connection_name"], "Plant LAN")
        self.assertEqual(eth0["ipv4_method"], "manual")
        self.assertEqual(eth0["configured_addresses"][0]["address"], "192.168.2.249")
        self.assertEqual(eth0["configured_addresses"][0]["prefix_length"], 24)
        self.assertTrue(eth0["use_default_route"])
        self.assertEqual(eth0["dns_servers"], ["8.8.8.8", "1.1.1.1"])

        self.assertEqual(eth1["connection_name"], "Mgmt LAN")
        self.assertEqual(eth1["ipv4_method"], "auto")
        self.assertFalse(eth1["use_default_route"])
        self.assertEqual(eth1["configured_addresses"], [])

    def test_linux_snapshot_reports_unreachable_networkmanager_as_read_only(self) -> None:
        service = NetworkConfigService()

        with (
            patch("app.services.network_config_service.platform.system", return_value="Linux"),
            patch("app.services.network_config_service.shutil.which", return_value="/usr/bin/nmcli"),
            patch.object(service, "_run_nmcli", side_effect=RuntimeError("Could not connect")),
        ):
            snapshot = service.get_snapshot()

        self.assertFalse(snapshot["supported"])
        self.assertFalse(snapshot["apply_supported"])
        self.assertEqual(snapshot["manager"], "unreachable")
        self.assertIn("NetworkManager", str(snapshot["message"]))

    def test_apply_reports_unreachable_networkmanager(self) -> None:
        service = NetworkConfigService()

        with (
            patch("app.services.network_config_service.platform.system", return_value="Linux"),
            patch("app.services.network_config_service.shutil.which", return_value="/usr/bin/nmcli"),
            patch.object(service, "_run_nmcli", side_effect=RuntimeError("Could not connect")),
        ):
            with self.assertRaisesRegex(ValueError, "NetworkManager non e raggiungibile"):
                service.apply_configuration(
                    interface_name="eth0",
                    ipv4_method="auto",
                    address=None,
                    prefix_length=None,
                    gateway=None,
                    dns_servers=[],
                    autoconnect=True,
                    use_default_route=True,
                )

    def test_linux_snapshot_falls_back_when_nmcli_does_not_support_connection_interface_field(self) -> None:
        service = NetworkConfigService()

        responses = {
            (
                "-t",
                "-f",
                "DEVICE,TYPE,STATE,CONNECTION",
                "device",
                "status",
            ): "eno2:ethernet:connected:Wired connection 1\neno1:ethernet:unavailable:--\n",
            (
                "-t",
                "-f",
                "NAME,TYPE",
                "connection",
                "show",
            ): "Wired connection 1:802-3-ethernet\nWired connection 2:802-3-ethernet\n",
            (
                "-g",
                "connection.interface-name",
                "connection",
                "show",
                "Wired connection 1",
            ): "eno2\n",
            (
                "-g",
                "connection.interface-name",
                "connection",
                "show",
                "Wired connection 2",
            ): "eno1\n",
            (
                "-t",
                "-f",
                "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
                "device",
                "show",
                "eno2",
            ): (
                "GENERAL.HWADDR:AA:BB:CC:DD:EE:FF\n"
                "IP4.ADDRESS[1]:192.168.2.249/24\n"
                "IP4.GATEWAY:192.168.2.1\n"
                "IP4.DNS[1]:8.8.8.8\n"
            ),
            (
                "-t",
                "-f",
                "GENERAL.HWADDR,IP4.ADDRESS,IP4.GATEWAY,IP4.DNS",
                "device",
                "show",
                "eno1",
            ): "GENERAL.HWADDR:11:22:33:44:55:66\n",
            (
                "-t",
                "-f",
                "connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns,ipv4.never-default",
                "connection",
                "show",
                "Wired connection 1",
            ): (
                "connection.autoconnect:yes\n"
                "ipv4.method:manual\n"
                "ipv4.addresses:192.168.2.249/24\n"
                "ipv4.gateway:192.168.2.1\n"
                "ipv4.dns:8.8.8.8\n"
                "ipv4.never-default:no\n"
            ),
            (
                "-t",
                "-f",
                "connection.autoconnect,ipv4.method,ipv4.addresses,ipv4.gateway,ipv4.dns,ipv4.never-default",
                "connection",
                "show",
                "Wired connection 2",
            ): (
                "connection.autoconnect:yes\n"
                "ipv4.method:auto\n"
                "ipv4.addresses:\n"
                "ipv4.gateway:\n"
                "ipv4.dns:\n"
                "ipv4.never-default:yes\n"
            ),
        }

        def fake_run_nmcli(args: list[str]) -> str:
            if tuple(args) == (
                "-t",
                "-f",
                "NAME,TYPE,connection.interface-name",
                "connection",
                "show",
            ):
                raise RuntimeError(
                    "Error: invalid field 'connection.interface-name'; allowed fields: NAME,UUID,TYPE,DEVICE.",
                )
            return responses[tuple(args)]

        with (
            patch("app.services.network_config_service.platform.system", return_value="Linux"),
            patch("app.services.network_config_service.shutil.which", return_value="/usr/bin/nmcli"),
            patch.object(service, "_run_nmcli", side_effect=fake_run_nmcli),
        ):
            snapshot = service.get_snapshot()

        self.assertTrue(snapshot["supported"])
        self.assertEqual(len(snapshot["interfaces"]), 2)
        eno1 = next(item for item in snapshot["interfaces"] if item["interface_name"] == "eno1")
        eno2 = next(item for item in snapshot["interfaces"] if item["interface_name"] == "eno2")
        self.assertEqual(eno2["connection_name"], "Wired connection 1")
        self.assertEqual(eno1["connection_name"], "Wired connection 2")
        self.assertEqual(eno1["ipv4_method"], "auto")

    def test_apply_requires_static_address_for_manual_ipv4(self) -> None:
        service = NetworkConfigService()

        with (
            patch("app.services.network_config_service.platform.system", return_value="Linux"),
            patch("app.services.network_config_service.shutil.which", return_value="/usr/bin/nmcli"),
        ):
            with self.assertRaisesRegex(ValueError, "indirizzo IPv4"):
                service.apply_configuration(
                    interface_name="eth0",
                    ipv4_method="manual",
                    address=None,
                    prefix_length=24,
                    gateway=None,
                    dns_servers=[],
                    autoconnect=True,
                    use_default_route=True,
                )

    def test_apply_connection_settings_writes_multiple_ipv4_addresses(self) -> None:
        service = NetworkConfigService()
        captured_commands: list[list[str]] = []

        def fake_run_nmcli(args: list[str]) -> str:
            captured_commands.append(args)
            return ""

        with patch.object(service, "_run_nmcli", side_effect=fake_run_nmcli):
            service._apply_connection_settings(
                connection_name="Field LAN",
                interface_name="eth1",
                ipv4_method="manual",
                addresses=["192.168.2.249/24", "10.20.30.249/24"],
                gateway="192.168.2.1",
                dns_servers=["8.8.8.8"],
                autoconnect=True,
                use_default_route=True,
            )

        self.assertEqual(len(captured_commands), 1)
        command = captured_commands[0]
        addresses_index = command.index("ipv4.addresses")
        self.assertEqual(command[addresses_index + 1], "192.168.2.249/24,10.20.30.249/24")

    def test_read_only_snapshot_filters_virtual_interfaces(self) -> None:
        service = NetworkConfigService()

        with patch(
            "app.services.network_config_service.network_interface_service.list_ipv4_bind_addresses",
            return_value=[
                {"name": "eth0", "address": "192.168.2.249/24"},
                {"name": "veth1ee7b46", "address": "169.254.10.10/16"},
            ],
        ):
            interfaces = service._build_read_only_interfaces()

        self.assertEqual([item["interface_name"] for item in interfaces], ["eth0"])


if __name__ == "__main__":
    unittest.main()

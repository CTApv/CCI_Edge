import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.schemas.device_overview_schemas import (
    DeviceOverviewDiagnostics,
    DeviceOverviewMetrics,
)
from app.services.dashboard_service import DashboardService
from app.services.live_cache import LiveCacheEntry, PowerSample


class _FakeDeviceService:
    def __init__(self, devices: list[SimpleNamespace]) -> None:
        self._devices = devices

    def list_devices(self) -> list[SimpleNamespace]:
        return list(self._devices)

    def get_device(self, device_id: str) -> SimpleNamespace | None:
        return next((device for device in self._devices if device.device_id == device_id), None)


class _FakeLiveCache:
    def __init__(
        self,
        entries: dict[str, LiveCacheEntry],
        history: dict[str, list[PowerSample]] | None = None,
    ) -> None:
        self._entries = entries
        self._history = history or {}

    def get(self, device_id: str) -> LiveCacheEntry | None:
        return self._entries.get(device_id)

    def get_power_history(self, device_id: str) -> list[PowerSample]:
        return list(self._history.get(device_id, []))


class _FakePowerHistoryService:
    def __init__(self, values: dict[str, list[float]]) -> None:
        self._values = values
        self._labels = ["2026-04-13T10:00:00+00:00", "2026-04-13T10:01:00+00:00"]

    def get_fleet_history_matrix(
        self,
        device_ids: list[str],
        **_: object,
    ) -> tuple[list[str], dict[str, list[float]]]:
        return list(self._labels), {
            device_id: list(self._values.get(device_id, [0.0] * len(self._labels)))[: len(self._labels)]
            for device_id in device_ids
        }

    def get_fleet_timeline(self, **_: object) -> list[str]:
        return list(self._labels)

    def get_device_aligned_history(self, device_id: str, labels: list[str]) -> list[float]:
        values = self._values.get(device_id, [0.0] * len(labels))
        return values[: len(labels)]

    def get_device_history(self, device_id: str, **_: object) -> list[PowerSample]:
        values = self._values.get(device_id, [])
        return [
            PowerSample(timestamp=timestamp, power_kw=value)
            for timestamp, value in zip(self._labels, values, strict=False)
        ]


class _EmptyPowerHistoryService:
    def get_fleet_history_matrix(
        self,
        device_ids: list[str],
        **_: object,
    ) -> tuple[list[str], dict[str, list[float]]]:
        return [], {device_id: [] for device_id in device_ids}

    def get_device_history(self, device_id: str, **_: object) -> list[PowerSample]:
        return []


def _device(
    device_id: str,
    *,
    brand: str,
    model: str,
    status: str = "online",
) -> SimpleNamespace:
    return SimpleNamespace(
        device_id=device_id,
        name=device_id,
        brand=brand,
        model=model,
        protocol="modbus_tcp",
        transport="tcp",
        status=status,
    )


def _entry(power_kw: float) -> LiveCacheEntry:
    return LiveCacheEntry(
        metrics=DeviceOverviewMetrics(
            power_kw=power_kw,
            daily_energy_kwh=1.0,
            total_energy_kwh=10.0,
            temperature_c=25.0,
        ),
        diagnostics=DeviceOverviewDiagnostics(
            last_poll_status="stub_mode=false; stage=read_register",
            response_time_ms=20,
            retries=0,
            last_error=None,
        ),
        telemetry=[],
        timestamp="2026-04-13T10:00:00+00:00",
    )


class DashboardServiceTests(unittest.TestCase):
    def test_summary_excludes_impossible_device_power_from_total(self) -> None:
        devices = [
            _device("inv-good", brand="Ingeteam", model="Ingecon SUN 840HE TL"),
            _device("inv-bad", brand="Xantrex", model="GT Series"),
        ]
        service = DashboardService()

        with (
            patch("app.services.dashboard_service.device_service", _FakeDeviceService(devices)),
            patch(
                "app.services.dashboard_service.live_cache",
                _FakeLiveCache(
                    {
                        "inv-good": _entry(320.0),
                        "inv-bad": _entry(4_271_701.66),
                    }
                ),
            ),
        ):
            summary = service.get_summary()
            active_power = service.get_active_power_sum()

        self.assertEqual(summary.total_power_kw, 320.0)
        self.assertEqual(active_power.active_power_kw, 320.0)
        self.assertEqual(active_power.active_power_w, 320000.0)
        self.assertEqual(active_power.total_devices, 2)
        self.assertEqual(summary.online_devices, 2)

    def test_fleet_power_history_excludes_impossible_samples_from_totals(self) -> None:
        devices = [
            _device("inv-good", brand="Ingeteam", model="Ingecon SUN 840HE TL"),
            _device("inv-bad", brand="Xantrex", model="GT Series"),
        ]
        service = DashboardService()

        with (
            patch("app.services.dashboard_service.device_service", _FakeDeviceService(devices)),
            patch("app.services.dashboard_service.live_cache", _FakeLiveCache({})),
            patch(
                "app.services.dashboard_service.power_history_service",
                _FakePowerHistoryService(
                    {
                        "inv-good": [300.0, 310.0],
                        "inv-bad": [4_271_701.66, 4_271_701.66],
                    }
                ),
            ),
        ):
            history = service.get_fleet_power_history()
            device_history = service.get_device_power_history("inv-bad")

        self.assertEqual(history.total_series.values, [300.0, 310.0])
        self.assertEqual(history.device_series[1].values, [0.0, 0.0])
        self.assertIsNotNone(device_history)
        self.assertEqual(device_history.values, [0.0, 0.0])

    def test_power_history_falls_back_to_live_cache_when_persistent_history_is_empty(self) -> None:
        devices = [
            _device("inv-1", brand="Generic", model="Model"),
            _device("inv-2", brand="Generic", model="Model"),
        ]
        live_history = {
            "inv-1": [
                PowerSample(timestamp="2026-04-13T10:00:00+00:00", power_kw=10.0),
                PowerSample(timestamp="2026-04-13T10:00:05+00:00", power_kw=11.0),
            ],
            "inv-2": [
                PowerSample(timestamp="2026-04-13T10:00:05+00:00", power_kw=20.0),
            ],
        }
        service = DashboardService()

        with (
            patch("app.services.dashboard_service.device_service", _FakeDeviceService(devices)),
            patch(
                "app.services.dashboard_service.live_cache",
                _FakeLiveCache(
                    {"inv-1": _entry(11.0), "inv-2": _entry(20.0)},
                    history=live_history,
                ),
            ),
            patch("app.services.dashboard_service.power_history_service", _EmptyPowerHistoryService()),
        ):
            history = service.get_fleet_power_history()
            device_history = service.get_device_power_history("inv-1")

        self.assertEqual(history.labels, ["2026-04-13T10:00:00+00:00", "2026-04-13T10:00:05+00:00"])
        self.assertEqual(history.total_series.values, [10.0, 31.0])
        self.assertIsNotNone(device_history)
        self.assertEqual(device_history.values, [10.0, 11.0])

    def test_power_history_appends_newer_live_cache_samples_to_persistent_history(self) -> None:
        devices = [
            _device("inv-1", brand="Generic", model="Model"),
            _device("inv-2", brand="Generic", model="Model"),
        ]
        live_history = {
            "inv-1": [
                PowerSample(timestamp="2026-04-13T10:01:05+00:00", power_kw=12.0),
            ],
            "inv-2": [
                PowerSample(timestamp="2026-04-13T10:01:05+00:00", power_kw=22.0),
            ],
        }
        service = DashboardService()

        with (
            patch("app.services.dashboard_service.device_service", _FakeDeviceService(devices)),
            patch(
                "app.services.dashboard_service.live_cache",
                _FakeLiveCache(
                    {"inv-1": _entry(12.0), "inv-2": _entry(22.0)},
                    history=live_history,
                ),
            ),
            patch(
                "app.services.dashboard_service.power_history_service",
                _FakePowerHistoryService(
                    {
                        "inv-1": [10.0, 11.0],
                        "inv-2": [20.0, 21.0],
                    }
                ),
            ),
        ):
            history = service.get_fleet_power_history()
            device_history = service.get_device_power_history("inv-1")

        self.assertEqual(
            history.labels,
            [
                "2026-04-13T10:00:00+00:00",
                "2026-04-13T10:01:00+00:00",
                "2026-04-13T10:01:05+00:00",
            ],
        )
        self.assertEqual(history.total_series.values, [30.0, 32.0, 34.0])
        self.assertIsNotNone(device_history)
        self.assertEqual(device_history.values, [10.0, 11.0, 12.0])


if __name__ == "__main__":
    unittest.main()

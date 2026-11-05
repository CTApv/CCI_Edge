import unittest
from types import SimpleNamespace

from app.models.inverter_model import InverterModel, InverterPoint
from app.services.polling_engine import _build_telemetry_points, _metric_value
from app.services.telemetry_quality_service import telemetry_quality_service


def _point(
    key: str,
    unit: str = "",
    *,
    summary_metric: str | None = None,
    protocol_meta: dict[str, object] | None = None,
) -> InverterPoint:
    meta = dict(protocol_meta or {})
    if summary_metric:
        meta["summary_metric"] = summary_metric
    return InverterPoint(
        key=key,
        label=key,
        kind="telemetry",
        register_type="input",
        address=1,
        length=1,
        datatype="int32",
        unit=unit,
        protocol_meta=meta,
    )


class TelemetryQualityServiceTests(unittest.TestCase):
    def test_rejects_random_simulator_values_but_keeps_plausible_values(self) -> None:
        device = SimpleNamespace(model="SUN2000-60KTL-M0", brand="Huawei", name="Huawei 1")
        points = [
            _point("active_power_kw", "kW", summary_metric="power_kw"),
            _point("mains_frequency_hz", "Hz"),
            _point("total_energy_kwh", "kWh", summary_metric="total_energy_kwh"),
        ]
        values = {
            "active_power_kw": 23.9,
            "mains_frequency_hz": 4995.0,
            "total_energy_kwh": 2_000_000_000.0,
        }

        self.assertEqual(
            telemetry_quality_service.evaluate(
                points[0],
                values["active_power_kw"],
                device=device,
                values=values,
                telemetry_points=points,
            ).state,
            "valid",
        )
        self.assertEqual(
            telemetry_quality_service.evaluate(points[1], values["mains_frequency_hz"]).state,
            "invalid",
        )
        self.assertEqual(
            telemetry_quality_service.evaluate(points[2], values["total_energy_kwh"]).state,
            "invalid",
        )

    def test_frequency_zero_is_warning_for_nighttime_or_disconnected_slave(self) -> None:
        evaluation = telemetry_quality_service.evaluate(_point("frequency_hz", "Hz"), 0)
        self.assertEqual(evaluation.state, "warning")

    def test_explicit_profile_limits_override_generic_rules(self) -> None:
        point = _point(
            "custom_temperature",
            "C",
            protocol_meta={"valid_min": -20, "valid_max": 80},
        )
        self.assertEqual(telemetry_quality_service.evaluate(point, 81).state, "invalid")

    def test_polling_summary_excludes_invalid_energy_and_marks_raw_telemetry(self) -> None:
        energy_point = _point(
            "total_energy_kwh",
            "kWh",
            summary_metric="total_energy_kwh",
        )
        model = InverterModel(
            brand="Test",
            model="Model",
            protocol="modbus_tcp",
            transport="tcp",
            telemetry_points=[energy_point],
        )
        values = {"total_energy_kwh": 2_000_000_000.0}

        metric = _metric_value(
            values=values,
            points=model.telemetry_points,
            canonical_key="total_energy_kwh",
            summary_metric="total_energy_kwh",
            default=0.0,
            validate_quality=True,
        )
        telemetry = _build_telemetry_points(model, values)

        self.assertEqual(metric, 0.0)
        self.assertEqual(telemetry[0].quality, "invalid")
        self.assertIsNotNone(telemetry[0].quality_reason)


if __name__ == "__main__":
    unittest.main()

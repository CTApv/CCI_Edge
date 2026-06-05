import unittest
from types import SimpleNamespace

from app.services.power_value_sanitizer import (
    resolve_nominal_power_kw,
    sanitize_device_power_kw,
)


class PowerValueSanitizerTests(unittest.TestCase):
    def test_rejects_impossible_power_without_nominal_rating(self) -> None:
        device = SimpleNamespace(
            brand="Xantrex",
            model="GT Series",
            name="GT Series 192.168.2.108",
        )

        self.assertIsNone(
            sanitize_device_power_kw(
                4_271_701.66,
                device=device,
            )
        )

    def test_uses_model_nominal_rating_to_reject_outliers(self) -> None:
        device = SimpleNamespace(
            brand="Bonfiglioli",
            model="RPS 420 TL Inverter Module AEC 500 - 50 A",
            name="Inverter 1",
        )

        self.assertEqual(resolve_nominal_power_kw(device=device), 420.0)
        self.assertEqual(
            sanitize_device_power_kw(
                420.0,
                device=device,
            ),
            420.0,
        )
        self.assertIsNone(
            sanitize_device_power_kw(
                3276.6,
                device=device,
            )
        )

    def test_accepts_signed_power_inside_reasonable_range(self) -> None:
        device = SimpleNamespace(
            brand="Ingeteam",
            model="Ingecon SUN 840HE TL",
            name="Inverter 1",
        )

        self.assertEqual(
            sanitize_device_power_kw(
                -211.0,
                device=device,
            ),
            -211.0,
        )


if __name__ == "__main__":
    unittest.main()

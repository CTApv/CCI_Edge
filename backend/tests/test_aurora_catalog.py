import unittest

from app.catalog.aurora_catalog import build_aurora_models, resolve_aurora_candidate_profiles
from app.catalog.aurora_families import aurora_profile_specs


class AuroraCatalogCoverageTests(unittest.TestCase):
    def test_new_identities_have_evidence_and_do_not_inherit_unverified_writes(self):
        models = {m.model: m for m in build_aurora_models() if m.brand == "PowerOne"}
        specs = aurora_profile_specs()
        self.assertEqual(len(specs), len({s["model"] for s in specs}))
        for spec in specs:
            with self.subTest(model=spec["model"]):
                model = models[spec["model"]]
                self.assertEqual(model.command_points, [])
                self.assertNotIn("active power limit", model.features)
                self.assertFalse(model.catalog_meta["field_tested"])
                self.assertTrue(model.catalog_meta["source_document"])
                self.assertTrue(model.telemetry_points)
                self.assertEqual((model.protocol, model.transport), ("aurora", "serial"))

    def test_rack_names_do_not_create_guessed_part_number_matches(self):
        self.assertEqual(resolve_aurora_candidate_profiles("PVI-CENTRAL-150-TL-YY"), ())
        self.assertEqual(resolve_aurora_candidate_profiles("3M22")[0][1],
                         "ABB/Aurora PVI-TRIO-27.6-TL-OUTD-S2X-400")

    def test_existing_profile_keys_and_commands_are_preserved(self):
        models = build_aurora_models()
        keys = [(m.brand, m.model, m.protocol, m.transport) for m in models]
        self.assertEqual(len(keys), len(set(keys)))
        legacy = next(m for m in models if m.model == "Aurora PVI-10.0-OUTD-IT")
        self.assertEqual([p.key for p in legacy.command_points], ["active_power_limit"])
        self.assertEqual(len([m for m in models if m.command_points]), 9)


if __name__ == "__main__":
    unittest.main()

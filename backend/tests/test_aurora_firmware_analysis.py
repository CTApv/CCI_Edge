import unittest

from app.services.aurora_firmware_analysis import classify_firmware, parse_compatibility_table
from app.catalog.aurora_families import aurora_profile_specs, profile_metadata


class CentralFirmwareEvidenceTests(unittest.TestCase):
    # Boundary examples from the installed manufacturer's table dated 2016-01-19.
    TABLE = """[START]
EE; 00; 0A; FE; 00; 10; // eu6
EE; 0B; FF; FE; 11; FF; // eu7
CC; 13; FF; DC; 25; FF; // eu12
CC; 13; FF; cC; 00; FF; // eu12 compatibility branch
[EOF]
"""

    def classify(self, dsp="EE", rev="0A", mcu="FE", mcu_rev="10"):
        return classify_firmware(self.TABLE, dsp_id=dsp, dsp_revision=rev,
                                 mcu_id=mcu, mcu_revision=mcu_rev)

    def test_both_component_revisions_are_required(self):
        self.assertEqual(self.classify()["matching_descriptions"], ["eu6"])
        self.assertEqual(self.classify(rev="0B", mcu_rev="11")["matching_descriptions"], ["eu7"])
        self.assertFalse(self.classify(rev="0B", mcu_rev="10")["an101_listed_by_vendor_software"])
        self.assertFalse(self.classify(rev="0A", mcu_rev="11")["an101_listed_by_vendor_software"])

    def test_firmware_id_case_is_preserved(self):
        match = self.classify("CC", "13", "cC", "00")
        self.assertTrue(match["an101_listed_by_vendor_software"])
        self.assertFalse(match["command_compatibility_confirmed"])
        self.assertFalse(self.classify("CC", "13", "CC", "00")["an101_listed_by_vendor_software"])

    def test_incomplete_malformed_or_reversed_tables_fail(self):
        for text in ("", "[START]\n", "[START]\ninvalid\n[EOF]",
                     "[START]\nCC; FF; 00; DC; 00; FF;\n[EOF]"):
            with self.subTest(text=text), self.assertRaises(ValueError):
                parse_compatibility_table(text)
        for revision in ("0x13", "-1", "100", "GG"):
            with self.subTest(revision=revision), self.assertRaises(ValueError):
                self.classify(rev=revision)

    def test_catalog_preserves_ambiguous_and_case_sensitive_identities(self):
        profiles = {str(spec["model"]): profile_metadata(spec) for spec in aurora_profile_specs()}
        self.assertEqual(profiles["UNO-2.5-I"]["software_model_codes"], ["G"])
        self.assertEqual(profiles["UNO-2.0-I"]["software_model_codes"], ["g"])
        self.assertEqual(profiles["PVI-MODULE-55.0"]["software_model_codes"], ["C"])
        self.assertIn("3M04", profiles["PVI-MODULE-55.0"]["identity_disambiguation"])
        self.assertFalse(profiles["PVI-MODULE-55.0"]["automatic_identity_mapping"])


if __name__ == "__main__":
    unittest.main()

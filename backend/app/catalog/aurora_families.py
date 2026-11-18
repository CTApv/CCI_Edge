"""Aurora identities evidenced by manufacturer software and product manuals.

Software labels are retained verbatim: they are not interchangeable with a
commercial rating or a firmware part number. Presence is not control validation.
"""
from __future__ import annotations

SOFTWARE_SOURCE = "Power-One Aurora Communicator / Aurora Manager TL, installed manufacturer software"
CENTRAL_SOURCE = "Power-One PVI-CENTRAL-XXX-TL-YY user manual, Rev 1.1, 2008-05-30"
PVI_TL_URL = "https://www.fimer.com/sites/default/files/PVI-3.0_3.6_4.2-TL-OUTD-Quick%20Installation%20Guide%20EN-RevF.pdf"
TRIO_URL = "https://www.fimer.com/sites/default/files/TRIO-20.0-27.6_Quick-Installation-Guide_BCM.00202.1.pdf"

# Model byte in the opcode-58 reply, as interpreted by Manager TL. Case matters.
# These are software identities, not a guarantee of model-specific telemetry.
SOFTWARE_MODEL_CODES = {
    "PVI-2000": ("i",), "PVI-3600": ("I",), "PVI-2000-OUTD": ("o",),
    "PVI-3000-OUTD": ("O",), "PVI-3600-OUTD": ("O",),
    "PVI-3.0-OUTD": ("1",), "PVI-3.8-OUTD": ("2",),
    "PVI-3.6-OUTD": ("3",), "PVI-4.2-OUTD": ("4",),
    "PVI-5000-OUTD": ("5",), "PVI-6000-OUTD": ("6",),
    "PVI-MODULE-50": ("C",), "PVI-MODULE-55.0": ("C",),
    "PVI-10.0-OUTD": ("X",), "PVI-12.5-OUTD": ("D",),
    "PVI-4.6-I-OUTD": ("H",), "PVI-3.8-I-OUTD": ("h",),
    "PVI-1700-IND": ("j",), "PVI-1700-OUTD": ("J",),
    "PVI-12.5-I-OUTD": ("T", "U", "V", "Z"),
    "PVI-10.0-I-OUTD": ("t", "u", "v", "z", "w"),
    "PVI-CENTRAL-250": ("M",), "PVI-TRIO-30-OUTD": ("Y",),
    "PVI-TRIO-20-OUTD": ("y",), "UNO-2.5-I": ("G",),
    "UNO-2.0-I": ("g",), "PVI-CENTRAL-350": ("L", "B", "A"),
}

# These are labels actually found in the manufacturer's executable, not inferred
# suffix combinations. Unknown countries/options must be confirmed on the unit.
SOFTWARE_FAMILIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("pvi_legacy", ("PVI-2000", "PVI-3600")),
    ("pvi_outd", (
        "PVI-1700-OUTD", "PVI-2000-OUTD", "PVI-3000-OUTD", "PVI-3600-OUTD",
        "PVI-5000-OUTD", "PVI-6000-OUTD", "PVI-3.0-OUTD", "PVI-3.3-OUTD",
        "PVI-3.6-OUTD", "PVI-3.8-OUTD", "PVI-4.2-OUTD", "PVI-10.0-OUTD", "PVI-12.5-OUTD",
    )),
    ("pvi_indoor", ("PVI-1700-IND",)),
    ("pvi_isolated", (
        "PVI-3.8-I-OUTD", "PVI-4.6-I-OUTD",
        "PVI-10.0-I-OUTD", "PVI-12.5-I-OUTD",
    )),
    ("uno_isolated", ("UNO-2.0-I", "UNO-2.5-I")),
    ("trio_software_identity", ("PVI-TRIO-20-OUTD", "PVI-TRIO-30-OUTD")),
    ("central_module", ("PVI-MODULE-50", "PVI-MODULE-55.0")),
    ("central_software_identity", ("PVI-CENTRAL-50", "PVI-CENTRAL-250", "PVI-CENTRAL-350")),
)


def aurora_profile_specs() -> list[dict[str, object]]:
    profiles: list[dict[str, object]] = []
    for family, names in SOFTWARE_FAMILIES:
        for name in names:
            profiles.append({"model": name, "family": family,
                             "source_document": SOFTWARE_SOURCE,
                             "identity_evidence": "manufacturer_software_label"})
    for name in ("PVI-3.0-TL-OUTD", "PVI-3.6-TL-OUTD", "PVI-4.2-TL-OUTD"):
        profiles.append({"model": name, "family": "pvi_tl_outd",
                         "source_document": "FIMER PVI-3.0/3.6/4.2-TL-OUTD quick installation guide Rev F",
                         "source_url": PVI_TL_URL, "identity_evidence": "manufacturer_manual"})
    for name in ("TRIO-20.0-TL-OUTD", "TRIO-27.6-TL-OUTD"):
        profiles.append({"model": name, "family": "trio_tl_outd",
                         "source_document": "Manufacturer TRIO-20.0/27.6-TL-OUTD installation guide BCM.00202.1",
                         "source_url": TRIO_URL, "identity_evidence": "manufacturer_manual",
                         "notes": "RS485 must be configured for Aurora; Modbus RTU is an alternative device setting, not this driver."})
    for rating in (50, 100, 150, 200, 250, 300):
        profiles.append({"model": f"PVI-CENTRAL-{rating}-TL-YY", "family": "central_modular_tl",
                         "source_document": CENTRAL_SOURCE, "identity_evidence": "manufacturer_manual",
                         "notes": "YY denotes the country variant. Select an individual module address; rack aggregation and control are pending validation."})
    return profiles


def profile_metadata(spec: dict[str, object]) -> dict[str, object]:
    metadata: dict[str, object] = {
        **{key: value for key, value in spec.items() if key != "model"},
        "verification_status": "identity_documented_driver_not_field_tested",
        "field_tested": False,
        "telemetry_status": "generic_aurora_mapping_requires_device_validation",
        "control_status": "not_enabled_pending_model_and_firmware_validation",
        "last_reviewed_at": "2026-11-18",
        "firmware_required": True,
        "country_variant_required": True,
        "automatic_identity_mapping": False,
        "connection_scope": "single_address",
    }
    name = str(spec["model"])
    if name in SOFTWARE_MODEL_CODES:
        metadata["software_model_codes"] = list(SOFTWARE_MODEL_CODES[name])
        metadata["software_model_code_case_sensitive"] = True
    if name in ("PVI-MODULE-50", "PVI-MODULE-55.0"):
        metadata["identity_disambiguation"] = (
            "Manager TL: model byte C plus PN 3M04/3M05/3L07 identifies MODULE-55.0; "
            "other C identities use the MODULE-50 software label. A module PN does not identify rack rating."
        )
    if name in ("PVI-3000-OUTD", "PVI-3600-OUTD"):
        metadata["identity_disambiguation"] = (
            "Manager TL: model byte O uses reply byte 4 == N for PVI-3000-OUTD; otherwise PVI-3600-OUTD."
        )
    return metadata

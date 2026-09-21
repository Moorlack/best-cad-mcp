"""Declared insertion units; never a verification of geometry scale."""

from datetime import datetime, timezone


# Autodesk INSUNITS enumeration (including distinct legacy survey units).
UNIT_NAMES = (
    "unitless", "in", "ft", "mi", "mm", "cm", "m", "km",
    "microinches", "mils", "yd", "angstroms", "nm", "microns",
    "dm", "dam", "hm", "gm", "au", "light_years", "parsecs",
    "us_survey_ft", "us_survey_in", "us_survey_yd", "us_survey_mi",
)


def unit_metadata(value=None, *, captured=False):
    valid = type(value) is int and 0 <= value < len(UNIT_NAMES)
    return {
        "units": UNIT_NAMES[value] if valid else "unknown",
        "insunits": value if type(value) is int else None,
        "source": "AutoCAD.INSUNITS" if captured else None,
        "status": "declared" if valid and value else "unknown",
        "geometry_scale_verified": False,
        "captured_at": datetime.now(timezone.utc).isoformat() if captured else None,
    }

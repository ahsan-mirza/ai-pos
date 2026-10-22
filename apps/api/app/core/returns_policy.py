from typing import Final

# Mirrored in packages/catalog/seed.json so registers can price returns offline.
RETURN_WINDOW_DAYS: Final = 30
OPEN_BOX_FEE_BPS: Final = 1500
MAX_CLOCK_SKEW_SECONDS: Final = 300

# Where a returned serialized unit goes, by condition. Only resealable units are sellable again.
SERIAL_STATUS_BY_CONDITION: Final[dict[str, str]] = {
    "unopened_resealable": "in_stock",
    "open_box": "quarantine",
    "defective_doa": "repair",
}

# A cashier crossing this many manager overrides inside one reporting period is flagged for review.
OVERRIDE_FLAG_THRESHOLD: Final = 3

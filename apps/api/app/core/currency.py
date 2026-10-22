import uuid

# Amounts are stored as integer cents, so only currencies with two minor-unit digits are allowed.
SUPPORTED_CURRENCIES: tuple[str, ...] = ("USD", "EUR", "GBP", "AED", "SAR", "QAR", "PKR", "INR")
DEFAULT_CURRENCY = "USD"

BUSINESS_SETTINGS_ID = uuid.UUID("00000000-0000-4000-8000-0000000000b1")

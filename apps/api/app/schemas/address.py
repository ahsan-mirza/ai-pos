"""Physical store address text.

Leading and trailing whitespace is removed. Spaces, punctuation and letters
from any language stay. This is not a store code and it is not a slug.
"""

ADDRESS_MAX_LENGTH = 255


def clean_address(value: object, *, required: bool) -> str | None:
    if value is None:
        if required:
            raise ValueError("Enter the store address.")
        return None
    if not isinstance(value, str):
        raise ValueError("Enter the store address.")
    if value.strip() == "":
        if required or value != "":
            raise ValueError("Enter the store address.")
        return None
    text = value.strip()
    if len(text) > ADDRESS_MAX_LENGTH:
        raise ValueError("Use 255 characters or fewer.")
    return text

import re

_NOT_DIGIT = re.compile(r"\D")


def normalize_phone(raw: str) -> str | None:
    """Canonical "+<digits>" form, assuming Tunisia (+216) for 8-digit local numbers.

    Returns None when the input cannot be a phone number.
    """
    stripped = raw.strip()
    digits = _NOT_DIGIT.sub("", stripped)
    if stripped.startswith("00"):
        digits = digits[2:]
    elif not stripped.startswith("+") and len(digits) == 8:
        digits = "216" + digits
    if not 8 <= len(digits) <= 15:
        return None
    return "+" + digits


def mask_phone(phone: str) -> str:
    """Show only the last 3 digits, for cards and logs."""
    return f"{phone[:4]}•••••{phone[-3:]}" if len(phone) > 7 else "•••"

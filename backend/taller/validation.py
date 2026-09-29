"""Input checks. Syntax/checksums are NOT identity or tax-census validation."""
import re
import unicodedata
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo
from .errors import AppError, require

TZ = ZoneInfo("Europe/Madrid")
LETTERS = "TRWAGMYFPDXBNJZSQVHLCKE"

def now() -> str:
    # UTC + one canonical representation allows safe ISO text ordering in SQLite.
    return datetime.now(timezone.utc).isoformat(timespec="seconds")

def today() -> str:
    return datetime.now(TZ).date().isoformat()

def normalized(value) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    return " ".join("".join(c for c in text if not unicodedata.combining(c)).split())

def plate(value) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(value or "").upper())

def clean_text(data: dict, key: str, max_length: int = 250, required: bool = False) -> str:
    require(isinstance(data, dict), "Datos no validos.")
    value = data.get(key, "")
    if value is None:
        value = ""
    require(isinstance(value, str), f"{key}: debe ser texto.")
    value = value.strip()
    require(not required or bool(value), f"{key}: completa este campo.")
    require(len(value) <= max_length, f"{key}: maximo {max_length} caracteres.")
    require(not any(ord(c) < 32 and c not in "\n\r\t" for c in value), f"{key}: caracteres no admitidos.")
    return value

def iso_date(value) -> str:
    require(isinstance(value, str) and re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}", value), "Fecha no valida. Usa AAAA-MM-DD.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError as exc:
        raise AppError("La fecha no existe.") from exc

def aware_date(value) -> datetime:
    require(isinstance(value, str) and len(value) <= 40, "Fecha y hora no validas.")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise AppError("Fecha y hora no validas.") from exc
    require(result.tzinfo is not None and result.utcoffset() is not None, "La fecha debe incluir su zona horaria.")
    return result

def valid_tax_id(value) -> bool:
    value = plate(value)
    if re.fullmatch(r"[0-9]{8}[A-Z]", value):
        return LETTERS[int(value[:8]) % 23] == value[-1]
    if re.fullmatch(r"[XYZ][0-9]{7}[A-Z]", value):
        return LETTERS[int(str("XYZ".index(value[0])) + value[1:8]) % 23] == value[-1]
    # NIFs K/L/M use the same check alphabet, with seven numeric characters.
    if re.fullmatch(r"[KLM][0-9]{7}[A-Z]", value):
        return LETTERS[int(value[1:8]) % 23] == value[-1]
    if not re.fullmatch(r"[ABCDEFGHJNPQRSUVW][0-9]{7}[0-9A-J]", value):
        return False
    digits = [int(c) for c in value[1:8]]
    even = sum(digits[1::2])
    odd = sum(sum(divmod(n * 2, 10)) for n in digits[::2])
    control = (10 - ((even + odd) % 10)) % 10
    numeric, alpha = str(control), "JABCDEFGHI"[control]
    if value[0] in "ABEH":
        return value[-1] == numeric
    if value[0] in "NPQRSW":
        return value[-1] == alpha
    return value[-1] in (numeric, alpha)

def valid_iban(value) -> bool:
    # Syntax + MOD97; account existence and ownership require external checks.
    text = re.sub(r"\s+", "", str(value or "")).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9]{2}[A-Z0-9]{11,30}", text):
        return False
    if text.startswith("ES") and (len(text) != 24 or not text[4:].isdigit()):
        return False
    rearranged = text[4:] + text[:4]
    numeric = "".join(str(ord(c)-55) if c.isalpha() else c for c in rearranged)
    return int(numeric) % 97 == 1

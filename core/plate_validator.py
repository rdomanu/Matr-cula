"""Validacion de formato de matriculas espanolas (modernas y antiguas)."""

import re


# Letras validas en matriculas modernas espanolas (sin vocales ni Q ni N con tilde)
MODERN_VALID_LETTERS = "BCDFGHJKLMNPRSTVWXYZ"

# Formato moderno (desde 2000): 4 digitos + 3 letras consonantes
MODERN_PATTERN = re.compile(
    r"^(\d{4})\s?([" + MODERN_VALID_LETTERS + r"]{3})$"
)

# Codigos provinciales validos (sistema antiguo, antes de 2000)
PROVINCIAL_CODES = {
    "A", "AB", "AL", "AV", "B", "BA", "BI", "BU", "C", "CA", "CC", "CE",
    "CO", "CR", "CS", "CU", "GC", "GE", "GI", "GR", "GU", "H", "HU", "J",
    "L", "LE", "LO", "LU", "M", "MA", "ML", "MU", "NA", "O", "OR", "OU",
    "P", "PM", "PO", "S", "SA", "SE", "SG", "SO", "SS", "T", "TE", "TF",
    "TO", "V", "VA", "VI", "Z", "ZA",
}

# Formato antiguo con letras: Provincia + 4 digitos + 2 letras
OLD_ALPHA_PATTERN = re.compile(
    r"^([A-Z]{1,2})\s?(\d{4})\s?([A-Z]{2})$"
)

# Formato antiguo solo numerico: Provincia + 6 digitos
OLD_NUMERIC_PATTERN = re.compile(
    r"^([A-Z]{1,2})\s?(\d{6})$"
)

# Matriculas especiales
SPECIAL_PATTERNS = {
    "diplomatic": re.compile(r"^CD\s?\d{4}$"),          # Cuerpo diplomatico
    "temporary": re.compile(r"^R\s?\d{4}\s?[A-Z]{3}$"),  # Temporal/turistico
    "historic": re.compile(r"^H\s?\d{4}\s?[A-Z]{3}$"),   # Vehiculo historico
}


def normalize_plate(text):
    """Normaliza el texto de una matricula: mayusculas, sin espacios extra."""
    if not text:
        return ""
    # Quitar espacios, guiones y puntos
    cleaned = re.sub(r"[\s\-\.]", "", text.upper().strip())
    return cleaned


def validate_modern(text):
    """Valida formato moderno (2000+): 1234 BCD."""
    normalized = normalize_plate(text)
    match = MODERN_PATTERN.match(normalized)
    if match:
        digits, letters = match.groups()
        return {
            "valid": True,
            "type": "modern",
            "plate": f"{digits} {letters}",
            "normalized": normalized,
            "digits": digits,
            "letters": letters,
        }
    return None


def validate_old_alpha(text):
    """Valida formato antiguo con letras: M 1234 AB."""
    normalized = normalize_plate(text)
    match = OLD_ALPHA_PATTERN.match(normalized)
    if match:
        province, digits, letters = match.groups()
        if province in PROVINCIAL_CODES:
            return {
                "valid": True,
                "type": "old_alpha",
                "plate": f"{province} {digits} {letters}",
                "normalized": normalized,
                "province": province,
                "digits": digits,
                "letters": letters,
            }
    return None


def validate_old_numeric(text):
    """Valida formato antiguo numerico: M 123456."""
    normalized = normalize_plate(text)
    match = OLD_NUMERIC_PATTERN.match(normalized)
    if match:
        province, digits = match.groups()
        if province in PROVINCIAL_CODES:
            return {
                "valid": True,
                "type": "old_numeric",
                "plate": f"{province} {digits}",
                "normalized": normalized,
                "province": province,
                "digits": digits,
            }
    return None


def validate_plate(text):
    """Valida una matricula espanola en cualquier formato conocido.

    Returns:
        dict con info de la matricula si es valida, None si no lo es.
    """
    if not text or len(text) < 4:
        return None

    # Intentar todos los formatos, empezando por el mas comun
    result = validate_modern(text)
    if result:
        return result

    result = validate_old_alpha(text)
    if result:
        return result

    result = validate_old_numeric(text)
    if result:
        return result

    # Intentar formatos especiales
    normalized = normalize_plate(text)
    for special_type, pattern in SPECIAL_PATTERNS.items():
        if pattern.match(normalized):
            return {
                "valid": True,
                "type": special_type,
                "plate": normalized,
                "normalized": normalized,
            }

    return None


def format_plate(text):
    """Formatea una matricula para mostrar con espacios estandar.

    Returns:
        str formateado o el texto original si no se reconoce.
    """
    result = validate_plate(text)
    if result:
        return result["plate"]
    return text.upper().strip()

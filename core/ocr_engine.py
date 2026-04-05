"""Motor OCR para lectura de matriculas usando EasyOCR."""

import re
import time
from collections import OrderedDict

import config

# Importacion lazy de EasyOCR (pesado, solo cargar cuando se necesite)
_reader = None


def _get_reader():
    """Inicializa EasyOCR reader de forma lazy."""
    global _reader
    if _reader is None:
        import easyocr
        _reader = easyocr.Reader(
            config.OCR_LANGUAGES,
            gpu=config.OCR_GPU,
            verbose=False,
        )
    return _reader


# Cache LRU de matriculas recientes para deduplicacion
class PlateCache:
    """Cache con expiracion temporal para evitar re-procesar matriculas recientes."""

    def __init__(self, max_size=100, ttl_seconds=5):
        self._cache = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def contains(self, plate_normalized):
        """Comprueba si la matricula esta en cache y no ha expirado."""
        if plate_normalized in self._cache:
            timestamp = self._cache[plate_normalized]
            if time.time() - timestamp < self._ttl:
                return True
            else:
                del self._cache[plate_normalized]
        return False

    def add(self, plate_normalized):
        """Anade matricula al cache."""
        self._cache[plate_normalized] = time.time()
        # Limpiar entradas mas antiguas si excede el tamano
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self):
        """Limpia el cache."""
        self._cache.clear()


# Instancia global del cache
plate_cache = PlateCache(
    max_size=config.RECENT_PLATES_CACHE_SIZE,
    ttl_seconds=config.RECENT_PLATES_TTL_SECONDS,
)


# Tabla de correcciones comunes en OCR de matriculas
CHAR_CORRECTIONS = {
    # En posiciones donde se esperan digitos
    "digits": {
        "O": "0", "o": "0",
        "I": "1", "i": "1", "l": "1", "|": "1",
        "Z": "2", "z": "2",
        "S": "5", "s": "5",
        "G": "6", "g": "6",
        "T": "7",
        "B": "8",
        "g": "9",
    },
    # En posiciones donde se esperan letras
    "letters": {
        "0": "O",
        "1": "I",
        "2": "Z",
        "5": "S",
        "6": "G",
        "8": "B",
    },
}


def _correct_ocr_text(text):
    """Aplica correcciones post-OCR especificas para matriculas espanolas."""
    if not text:
        return text

    # Limpiar caracteres no alfanumericos
    cleaned = re.sub(r"[^A-Za-z0-9]", "", text.upper())

    if len(cleaned) < 4:
        return cleaned

    # Intentar correccion para formato moderno: 4 digitos + 3 letras
    if len(cleaned) == 7:
        digits_part = list(cleaned[:4])
        letters_part = list(cleaned[4:])

        # Corregir digitos
        for i, ch in enumerate(digits_part):
            if ch in CHAR_CORRECTIONS["digits"]:
                digits_part[i] = CHAR_CORRECTIONS["digits"][ch]

        # Corregir letras
        for i, ch in enumerate(letters_part):
            if ch in CHAR_CORRECTIONS["letters"]:
                letters_part[i] = CHAR_CORRECTIONS["letters"][ch]

        corrected = "".join(digits_part) + "".join(letters_part)
        return corrected

    # Para formato antiguo: intentar separar provincia + numeros + letras
    # Ej: M1234AB, BA1234CD
    match = re.match(r"^([A-Z]{1,2})(\d{4,6})([A-Z]{0,2})$", cleaned)
    if match:
        return cleaned

    return cleaned


def read_plate(image):
    """Lee el texto de una imagen de matricula preprocesada.

    Args:
        image: Imagen de la matricula (BGR o escala de grises).

    Returns:
        Tupla (texto, confianza) o (None, 0) si no se puede leer.
    """
    if image is None or image.size == 0:
        return None, 0.0

    reader = _get_reader()

    try:
        results = reader.readtext(
            image,
            detail=1,
            paragraph=False,
            allowlist="0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
        )
    except Exception:
        return None, 0.0

    if not results:
        return None, 0.0

    # Concatenar todos los textos detectados (puede haber multiples bloques)
    full_text = ""
    total_confidence = 0
    count = 0

    for (_, text, confidence) in results:
        if confidence >= config.OCR_CONFIDENCE_THRESHOLD:
            full_text += text
            total_confidence += confidence
            count += 1

    if count == 0:
        return None, 0.0

    avg_confidence = total_confidence / count

    # Aplicar correcciones
    corrected = _correct_ocr_text(full_text)

    return corrected, avg_confidence


def read_plate_cached(image, plate_validator_fn):
    """Lee una matricula con deduplicacion via cache.

    Args:
        image: Imagen de la matricula.
        plate_validator_fn: Funcion que valida y normaliza la matricula.

    Returns:
        Tupla (resultado_validacion, confianza) o (None, 0) si duplicada/invalida.
    """
    text, confidence = read_plate(image)
    if text is None:
        return None, 0.0

    # Validar formato espanol
    validation = plate_validator_fn(text)
    if validation is None:
        return None, 0.0

    # Comprobar cache para deduplicacion
    normalized = validation["normalized"]
    if plate_cache.contains(normalized):
        return None, 0.0  # Ya leida recientemente

    # Anadir al cache
    plate_cache.add(normalized)

    return validation, confidence

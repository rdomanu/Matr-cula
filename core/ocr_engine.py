"""Motor OCR para lectura de matriculas usando Tesseract."""

import re
import time
from collections import OrderedDict

import pytesseract
from PIL import Image
import numpy as np

import config


# Cache LRU de matriculas recientes para deduplicacion
class PlateCache:
    """Cache con expiracion temporal para evitar re-procesar matriculas recientes."""

    def __init__(self, max_size=100, ttl_seconds=5):
        self._cache = OrderedDict()
        self._max_size = max_size
        self._ttl = ttl_seconds

    def contains(self, plate_normalized):
        if plate_normalized in self._cache:
            timestamp = self._cache[plate_normalized]
            if time.time() - timestamp < self._ttl:
                return True
            else:
                del self._cache[plate_normalized]
        return False

    def add(self, plate_normalized):
        self._cache[plate_normalized] = time.time()
        while len(self._cache) > self._max_size:
            self._cache.popitem(last=False)

    def clear(self):
        self._cache.clear()


plate_cache = PlateCache(
    max_size=config.RECENT_PLATES_CACHE_SIZE,
    ttl_seconds=config.RECENT_PLATES_TTL_SECONDS,
)


# Configuracion de Tesseract optimizada para matriculas
TESSERACT_CONFIG = (
    "--oem 3 --psm 7 "  # PSM 7 = tratar como una linea de texto
    "-c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
)


# Tabla de correcciones comunes en OCR de matriculas
CHAR_CORRECTIONS = {
    "digits": {
        "O": "0", "o": "0",
        "I": "1", "i": "1", "l": "1", "|": "1",
        "Z": "2", "z": "2",
        "S": "5", "s": "5",
        "G": "6", "g": "6",
        "T": "7",
        "B": "8",
    },
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

    cleaned = re.sub(r"[^A-Za-z0-9]", "", text.upper())

    if len(cleaned) < 4:
        return cleaned

    # Formato moderno: 4 digitos + 3 letras
    if len(cleaned) == 7:
        digits_part = list(cleaned[:4])
        letters_part = list(cleaned[4:])

        for i, ch in enumerate(digits_part):
            if ch in CHAR_CORRECTIONS["digits"]:
                digits_part[i] = CHAR_CORRECTIONS["digits"][ch]

        for i, ch in enumerate(letters_part):
            if ch in CHAR_CORRECTIONS["letters"]:
                letters_part[i] = CHAR_CORRECTIONS["letters"][ch]

        return "".join(digits_part) + "".join(letters_part)

    # Formato antiguo
    match = re.match(r"^([A-Z]{1,2})(\d{4,6})([A-Z]{0,2})$", cleaned)
    if match:
        return cleaned

    return cleaned


def read_plate(image):
    """Lee el texto de una imagen de matricula usando Tesseract.

    Args:
        image: Imagen de la matricula (numpy array BGR o escala de grises).

    Returns:
        Tupla (texto, confianza) o (None, 0) si no se puede leer.
    """
    if image is None or image.size == 0:
        return None, 0.0

    try:
        # Convertir numpy array a PIL Image
        if len(image.shape) == 3:
            pil_image = Image.fromarray(image[:, :, ::-1])  # BGR -> RGB
        else:
            pil_image = Image.fromarray(image)

        # Obtener texto con datos de confianza
        data = pytesseract.image_to_data(
            pil_image,
            config=TESSERACT_CONFIG,
            output_type=pytesseract.Output.DICT,
        )

        # Extraer texto y confianza
        texts = []
        confidences = []
        for i, conf in enumerate(data["conf"]):
            conf_val = int(conf) if str(conf).lstrip('-').isdigit() else 0
            text = data["text"][i].strip()
            if conf_val > 0 and text:
                texts.append(text)
                confidences.append(conf_val / 100.0)

        if not texts:
            return None, 0.0

        full_text = "".join(texts)
        avg_confidence = sum(confidences) / len(confidences)

        # Aplicar correcciones
        corrected = _correct_ocr_text(full_text)

        if not corrected or len(corrected) < 4:
            return None, 0.0

        return corrected, avg_confidence

    except Exception:
        return None, 0.0


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

    validation = plate_validator_fn(text)
    if validation is None:
        return None, 0.0

    normalized = validation["normalized"]
    if plate_cache.contains(normalized):
        return None, 0.0

    plate_cache.add(normalized)

    return validation, confidence

"""Deteccion de matriculas escaneando texto en el frame completo con Tesseract."""

import re
import numpy as np
from PIL import Image, ImageDraw

import config
from core.plate_validator import validate_plate, normalize_plate


def _scan_frame_for_text(pil_image):
    """Escanea un frame completo con Tesseract y devuelve bloques de texto con posicion.

    Returns:
        Lista de dicts con: text, x, y, w, h, conf
    """
    import pytesseract

    # Preprocesar para mejorar deteccion
    gray = pil_image.convert("L")

    # Tesseract: obtener todos los bloques de texto con posicion y confianza
    try:
        data = pytesseract.image_to_data(
            gray,
            config="--oem 3 --psm 11 -c tessedit_char_whitelist=0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ",
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return []

    blocks = []
    n = len(data["text"])
    for i in range(n):
        text = data["text"][i].strip()
        conf = int(data["conf"][i]) if str(data["conf"][i]).lstrip('-').isdigit() else 0
        if text and conf > 20 and len(text) >= 2:
            blocks.append({
                "text": text.upper(),
                "x": data["left"][i],
                "y": data["top"][i],
                "w": data["width"][i],
                "h": data["height"][i],
                "conf": conf / 100.0,
            })

    return blocks


def _merge_nearby_blocks(blocks, max_gap=50):
    """Une bloques de texto cercanos horizontalmente (caracteres de una misma matricula)."""
    if not blocks:
        return []

    # Ordenar por posicion Y luego X
    sorted_blocks = sorted(blocks, key=lambda b: (b["y"], b["x"]))

    merged = []
    current = dict(sorted_blocks[0])

    for b in sorted_blocks[1:]:
        # Si estan en la misma linea (Y similar) y cerca horizontalmente
        y_overlap = abs(b["y"] - current["y"]) < max(current["h"], b["h"])
        x_gap = b["x"] - (current["x"] + current["w"])

        if y_overlap and 0 <= x_gap <= max_gap:
            # Unir
            current["text"] += b["text"]
            new_x2 = max(current["x"] + current["w"], b["x"] + b["w"])
            current["w"] = new_x2 - current["x"]
            current["h"] = max(current["h"], b["h"])
            current["conf"] = (current["conf"] + b["conf"]) / 2
        else:
            merged.append(current)
            current = dict(b)

    merged.append(current)
    return merged


def detect_all_plates(frame):
    """Detecta matriculas escaneando texto en el frame completo.

    Estrategia: Tesseract lee TODO el texto visible en el frame,
    luego filtramos con regex los que coinciden con formato de matricula espanola.

    Args:
        frame: numpy array RGB del frame.

    Returns:
        boxes: Lista de (x, y, w, h) de matriculas encontradas.
        plate_images: Lista de numpy arrays recortados.
    """
    if frame is None or frame.size == 0:
        return [], []

    pil_image = Image.fromarray(frame) if isinstance(frame, np.ndarray) else frame

    # Escanear todo el texto del frame
    blocks = _scan_frame_for_text(pil_image)

    # Unir bloques cercanos (una matricula puede ser detectada como varios trozos)
    merged = _merge_nearby_blocks(blocks)

    # Filtrar los que parecen matriculas espanolas
    boxes = []
    plate_images = []

    for block in merged:
        text = re.sub(r"[^A-Z0-9]", "", block["text"])

        # Intentar validar como matricula
        validation = validate_plate(text)
        if validation:
            x, y, w, h = block["x"], block["y"], block["w"], block["h"]

            # Margen extra
            margin = 10
            y1 = max(0, y - margin)
            y2 = min(frame.shape[0], y + h + margin)
            x1 = max(0, x - margin)
            x2 = min(frame.shape[1], x + w + margin)

            plate_img = frame[y1:y2, x1:x2]
            if plate_img.size > 0:
                boxes.append((x1, y1, x2 - x1, y2 - y1))
                plate_images.append(plate_img)

    return boxes, plate_images


def draw_detections(frame, boxes, texts=None, alert_plates=None):
    """Dibuja rectangulos sobre las matriculas detectadas."""
    if frame is None:
        return frame

    pil_image = Image.fromarray(frame) if isinstance(frame, np.ndarray) else frame.copy()
    draw = ImageDraw.Draw(pil_image)
    alert_plates = alert_plates or set()

    for i, (x, y, w, h) in enumerate(boxes):
        text = texts[i] if texts and i < len(texts) else ""
        is_alert = text.replace(" ", "").upper() in alert_plates

        color = (255, 0, 0) if is_alert else (0, 255, 0)
        width = 3 if is_alert else 2

        draw.rectangle([x, y, x + w, y + h], outline=color, width=width)
        if text:
            draw.rectangle([x, y - 18, x + len(text) * 10, y], fill=color)
            draw.text((x + 2, y - 16), text, fill=(255, 255, 255))

    return np.array(pil_image)

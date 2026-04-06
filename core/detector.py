"""Deteccion de regiones de matricula en un frame (sin OpenCV, solo Pillow+numpy)."""

import numpy as np
from PIL import Image, ImageDraw

import config


def _find_plate_regions(np_image):
    """Detecta regiones rectangulares que podrian ser matriculas.

    Usa analisis de bordes simplificado con numpy.
    Las matriculas espanolas son rectangulos blancos con ratio ~4.7:1.
    """
    if np_image is None or np_image.size == 0:
        return []

    h, w = np_image.shape[:2]

    # Convertir a escala de grises si es color
    if len(np_image.shape) == 3:
        gray = np.mean(np_image, axis=2).astype(np.uint8)
    else:
        gray = np_image

    # Buscar regiones blancas/claras (fondo de matricula)
    # Las matriculas espanolas tienen fondo blanco (valor alto)
    white_mask = gray > 180

    # Buscar filas con suficientes pixeles blancos consecutivos
    candidates = []

    # Escanear en bloques para encontrar regiones claras rectangulares
    step_y = max(2, h // 80)
    step_x = max(2, w // 80)

    for y in range(0, h - config.PLATE_MIN_HEIGHT, step_y):
        for x in range(0, w - config.PLATE_MIN_WIDTH, step_x):
            # Probar varios tamanos de ventana
            for pw in range(config.PLATE_MIN_WIDTH, min(config.PLATE_MAX_WIDTH, w - x), 40):
                ph = int(pw / 4.7)  # Ratio de matricula espanola
                if ph < config.PLATE_MIN_HEIGHT or y + ph > h:
                    continue
                if ph > config.PLATE_MAX_HEIGHT:
                    break

                # Comprobar si la region es mayoritariamente blanca
                region = white_mask[y:y + ph, x:x + pw]
                white_ratio = np.mean(region)

                if 0.4 <= white_ratio <= 0.85:
                    # Comprobar que hay variacion (caracteres oscuros sobre fondo claro)
                    region_gray = gray[y:y + ph, x:x + pw]
                    std = np.std(region_gray)
                    if std > 35:
                        candidates.append((x, y, pw, ph, std))

    # Eliminar duplicados solapados (NMS simple)
    candidates.sort(key=lambda c: c[4], reverse=True)  # Ordenar por contraste
    filtered = []
    for cand in candidates:
        x, y, pw, ph, _ = cand
        overlap = False
        for fx, fy, fpw, fph in filtered:
            # Comprobar solapamiento
            ox = max(0, min(x + pw, fx + fpw) - max(x, fx))
            oy = max(0, min(y + ph, fy + fph) - max(y, fy))
            overlap_area = ox * oy
            cand_area = pw * ph
            if overlap_area > 0.3 * cand_area:
                overlap = True
                break
        if not overlap:
            filtered.append((x, y, pw, ph))
            if len(filtered) >= 10:  # Maximo 10 candidatos
                break

    return filtered


def detect_all_plates(frame):
    """Detecta todas las matriculas en un frame.

    Args:
        frame: numpy array RGB del frame de la camara.

    Returns:
        Lista de tuplas (x, y, w, h) de las regiones detectadas.
        Lista de numpy arrays recortados de cada region.
    """
    if frame is None or frame.size == 0:
        return [], []

    regions = _find_plate_regions(frame)

    plate_images = []
    valid_boxes = []
    for (x, y, w, h) in regions:
        # Margen extra del 5%
        margin_x = int(w * 0.05)
        margin_y = int(h * 0.05)
        y1 = max(0, y - margin_y)
        y2 = min(frame.shape[0], y + h + margin_y)
        x1 = max(0, x - margin_x)
        x2 = min(frame.shape[1], x + w + margin_x)

        plate_img = frame[y1:y2, x1:x2]
        if plate_img.size > 0:
            plate_images.append(plate_img)
            valid_boxes.append((x1, y1, x2 - x1, y2 - y1))

    return valid_boxes, plate_images


def draw_detections(frame, boxes, texts=None, alert_plates=None):
    """Dibuja rectangulos sobre las matriculas detectadas.

    Returns:
        numpy array RGB con anotaciones.
    """
    if frame is None:
        return frame

    pil_image = Image.fromarray(frame)
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

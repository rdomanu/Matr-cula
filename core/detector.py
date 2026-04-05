"""Deteccion de multiples regiones de matricula en un frame."""

import cv2
import numpy as np

import config


def _non_max_suppression(boxes, overlap_threshold=0.3):
    """Elimina detecciones solapadas manteniendo la mejor de cada grupo."""
    if len(boxes) == 0:
        return []

    boxes_array = np.array(boxes)
    x1 = boxes_array[:, 0]
    y1 = boxes_array[:, 1]
    x2 = boxes_array[:, 0] + boxes_array[:, 2]
    y2 = boxes_array[:, 1] + boxes_array[:, 3]
    areas = boxes_array[:, 2] * boxes_array[:, 3]

    # Ordenar por area (las mas grandes primero, suelen ser mejores candidatas)
    order = areas.argsort()[::-1]
    keep = []

    while len(order) > 0:
        i = order[0]
        keep.append(i)

        xx1 = np.maximum(x1[i], x1[order[1:]])
        yy1 = np.maximum(y1[i], y1[order[1:]])
        xx2 = np.minimum(x2[i], x2[order[1:]])
        yy2 = np.minimum(y2[i], y2[order[1:]])

        w = np.maximum(0, xx2 - xx1)
        h = np.maximum(0, yy2 - yy1)
        overlap = (w * h) / areas[order[1:]]

        remaining = np.where(overlap <= overlap_threshold)[0]
        order = order[remaining + 1]

    return [boxes[i] for i in keep]


def detect_plates_contour(frame):
    """Detecta regiones de matricula usando deteccion de contornos.

    Args:
        frame: Imagen BGR del frame completo.

    Returns:
        Lista de tuplas (x, y, w, h) con las regiones de matriculas detectadas.
    """
    # Convertir a escala de grises
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

    # Filtro bilateral: reduce ruido preservando bordes
    filtered = cv2.bilateralFilter(gray, 11, 17, 17)

    # Deteccion de bordes Canny
    edges = cv2.Canny(filtered, 30, 200)

    # Dilatar para conectar bordes cercanos
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3))
    dilated = cv2.dilate(edges, kernel, iterations=1)

    # Encontrar contornos
    contours, _ = cv2.findContours(dilated, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for contour in contours:
        # Aproximar el contorno a un poligono
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.02 * perimeter, True)

        # Las matriculas son rectangulares (4 vertices)
        if len(approx) >= 4 and len(approx) <= 8:
            x, y, w, h = cv2.boundingRect(approx)

            # Filtrar por tamano
            if w < config.PLATE_MIN_WIDTH or w > config.PLATE_MAX_WIDTH:
                continue
            if h < config.PLATE_MIN_HEIGHT or h > config.PLATE_MAX_HEIGHT:
                continue

            # Filtrar por ratio de aspecto
            aspect_ratio = w / h
            if aspect_ratio < config.PLATE_ASPECT_RATIO_MIN:
                continue
            if aspect_ratio > config.PLATE_ASPECT_RATIO_MAX:
                continue

            # Verificar que la region tiene suficiente contraste (caracteres)
            roi = gray[y:y + h, x:x + w]
            if roi.size > 0:
                std_dev = np.std(roi)
                if std_dev > 30:  # Suficiente variacion = posibles caracteres
                    candidates.append((x, y, w, h))

    # Eliminar detecciones solapadas
    return _non_max_suppression(candidates)


def detect_plates_color(frame):
    """Detecta matriculas por color (fondo blanco con borde/banda azul EU).

    Complementa la deteccion por contornos.
    """
    # Convertir a HSV para deteccion de color
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)

    # Rango para blanco (fondo de matricula)
    lower_white = np.array([0, 0, 180])
    upper_white = np.array([180, 50, 255])
    white_mask = cv2.inRange(hsv, lower_white, upper_white)

    # Operaciones morfologicas para limpiar mascara
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (15, 5))
    closed = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel)
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)

    # Encontrar contornos en la mascara
    contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    candidates = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)

        if w < config.PLATE_MIN_WIDTH or w > config.PLATE_MAX_WIDTH:
            continue
        if h < config.PLATE_MIN_HEIGHT or h > config.PLATE_MAX_HEIGHT:
            continue

        aspect_ratio = w / h
        if aspect_ratio < config.PLATE_ASPECT_RATIO_MIN:
            continue
        if aspect_ratio > config.PLATE_ASPECT_RATIO_MAX:
            continue

        # Verificar que el porcentaje de blancos es razonable (40-90%)
        roi_mask = white_mask[y:y + h, x:x + w]
        if roi_mask.size > 0:
            white_ratio = np.count_nonzero(roi_mask) / roi_mask.size
            if 0.3 <= white_ratio <= 0.9:
                candidates.append((x, y, w, h))

    return _non_max_suppression(candidates)


def detect_all_plates(frame):
    """Detecta todas las matriculas en un frame combinando ambos metodos.

    Args:
        frame: Imagen BGR del frame completo de la camara.

    Returns:
        Lista de tuplas (x, y, w, h) de todas las matriculas detectadas.
        Lista de imagenes recortadas de cada matricula.
    """
    if frame is None or frame.size == 0:
        return [], []

    # Combinar ambos metodos de deteccion
    contour_plates = detect_plates_contour(frame)
    color_plates = detect_plates_color(frame)

    # Unir todas las detecciones
    all_candidates = contour_plates + color_plates

    # NMS final para eliminar duplicados entre ambos metodos
    final_plates = _non_max_suppression(all_candidates, overlap_threshold=0.3)

    # Recortar imagenes de matricula
    plate_images = []
    valid_boxes = []
    for (x, y, w, h) in final_plates:
        # Margen extra del 5% para capturar bordes completos
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
    """Dibuja rectangulos y texto sobre las matriculas detectadas en el frame.

    Args:
        frame: Imagen BGR original.
        boxes: Lista de (x, y, w, h).
        texts: Lista de textos reconocidos (opcional).
        alert_plates: Set de matriculas normalizadas que son alertas.

    Returns:
        Frame con anotaciones dibujadas.
    """
    annotated = frame.copy()
    alert_plates = alert_plates or set()

    for i, (x, y, w, h) in enumerate(boxes):
        text = texts[i] if texts and i < len(texts) else ""
        is_alert = text.replace(" ", "").upper() in alert_plates

        # Color: rojo para alertas, verde para normales
        color = (0, 0, 255) if is_alert else (0, 255, 0)
        thickness = 3 if is_alert else 2

        cv2.rectangle(annotated, (x, y), (x + w, y + h), color, thickness)

        if text:
            # Fondo para el texto
            font = cv2.FONT_HERSHEY_SIMPLEX
            font_scale = 0.7
            text_size = cv2.getTextSize(text, font, font_scale, 2)[0]
            cv2.rectangle(
                annotated,
                (x, y - text_size[1] - 10),
                (x + text_size[0], y),
                color, -1,
            )
            cv2.putText(
                annotated, text, (x, y - 5),
                font, font_scale, (255, 255, 255), 2,
            )

    return annotated

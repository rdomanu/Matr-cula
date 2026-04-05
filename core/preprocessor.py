"""Preprocesamiento de imagenes de matriculas para mejorar la lectura OCR."""

import cv2
import numpy as np


# Tamano estandar de matricula espanola para OCR
STANDARD_WIDTH = 520
STANDARD_HEIGHT = 110


def resize_plate(image, width=STANDARD_WIDTH, height=STANDARD_HEIGHT):
    """Redimensiona la imagen de la matricula a tamano estandar."""
    return cv2.resize(image, (width, height), interpolation=cv2.INTER_CUBIC)


def to_grayscale(image):
    """Convierte a escala de grises si es necesario."""
    if len(image.shape) == 3:
        return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    return image


def apply_clahe(image):
    """Aplica CLAHE (Contrast Limited Adaptive Histogram Equalization)."""
    gray = to_grayscale(image)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    return clahe.apply(gray)


def denoise(image):
    """Reduce ruido manteniendo bordes con filtro bilateral."""
    gray = to_grayscale(image)
    return cv2.bilateralFilter(gray, 11, 17, 17)


def binarize(image):
    """Binarizacion adaptativa para separar caracteres del fondo."""
    gray = to_grayscale(image)
    # Otsu para determinar umbral optimo automaticamente
    _, binary = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    return binary


def binarize_adaptive(image):
    """Binarizacion adaptativa para condiciones de iluminacion variable."""
    gray = to_grayscale(image)
    return cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
    )


def morphology_clean(image):
    """Operaciones morfologicas para limpiar caracteres."""
    # Kernel pequeno para limpiar ruido sin destruir caracteres
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    # Cierre: rellenar huecos en caracteres
    closed = cv2.morphologyEx(image, cv2.MORPH_CLOSE, kernel)
    # Apertura: eliminar puntos de ruido
    opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)
    return opened


def correct_skew(image):
    """Corrige la inclinacion de la matricula."""
    gray = to_grayscale(image)
    # Detectar bordes
    edges = cv2.Canny(gray, 50, 150, apertureSize=3)
    # Detectar lineas con Hough
    lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 50, minLineLength=50, maxLineGap=10)

    if lines is None or len(lines) == 0:
        return image

    # Calcular angulo medio de las lineas detectadas
    angles = []
    for line in lines:
        x1, y1, x2, y2 = line[0]
        angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
        if abs(angle) < 30:  # Solo considerar lineas casi horizontales
            angles.append(angle)

    if not angles:
        return image

    median_angle = np.median(angles)
    if abs(median_angle) < 0.5:  # No corregir angulos insignificantes
        return image

    # Rotar imagen
    h, w = image.shape[:2]
    center = (w // 2, h // 2)
    rotation_matrix = cv2.getRotationMatrix2D(center, median_angle, 1.0)
    rotated = cv2.warpAffine(
        image, rotation_matrix, (w, h),
        flags=cv2.INTER_CUBIC,
        borderMode=cv2.BORDER_REPLICATE,
    )
    return rotated


def sharpen(image):
    """Aplica enfoque para mejorar bordes de caracteres."""
    kernel = np.array([[-1, -1, -1], [-1, 9, -1], [-1, -1, -1]])
    return cv2.filter2D(image, -1, kernel)


def preprocess_plate(image):
    """Pipeline completo de preprocesamiento para una imagen de matricula.

    Args:
        image: Imagen BGR de la matricula recortada.

    Returns:
        Imagen preprocesada lista para OCR (escala de grises, binarizada).
    """
    if image is None or image.size == 0:
        return None

    # 1. Redimensionar a tamano estandar
    resized = resize_plate(image)

    # 2. Corregir inclinacion
    deskewed = correct_skew(resized)

    # 3. Mejorar contraste
    enhanced = apply_clahe(deskewed)

    # 4. Reducir ruido
    denoised = denoise(enhanced)

    # 5. Binarizar
    binary = binarize(denoised)

    # 6. Limpiar con morfologia
    cleaned = morphology_clean(binary)

    return cleaned


def preprocess_for_easyocr(image):
    """Preprocesamiento optimizado para EasyOCR.

    EasyOCR funciona mejor con imagenes en color o escala de grises
    con buen contraste, no necesariamente binarizadas.
    """
    if image is None or image.size == 0:
        return None

    # 1. Redimensionar
    resized = resize_plate(image)

    # 2. Corregir inclinacion
    deskewed = correct_skew(resized)

    # 3. Mejorar contraste con CLAHE
    enhanced = apply_clahe(deskewed)

    # 4. Enfoque suave
    sharpened = sharpen(enhanced)

    return sharpened

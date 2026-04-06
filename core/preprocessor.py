"""Preprocesamiento de imagenes de matriculas para OCR (sin OpenCV, solo Pillow+numpy)."""

import numpy as np
from PIL import Image, ImageFilter, ImageEnhance, ImageOps

STANDARD_WIDTH = 520
STANDARD_HEIGHT = 110


def resize_plate(image, width=STANDARD_WIDTH, height=STANDARD_HEIGHT):
    """Redimensiona la imagen de la matricula a tamano estandar."""
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    return image.resize((width, height), Image.LANCZOS)


def to_grayscale(image):
    """Convierte a escala de grises."""
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    return image.convert("L")


def enhance_contrast(image):
    """Mejora el contraste de la imagen."""
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    if image.mode != "L":
        image = image.convert("L")
    enhancer = ImageEnhance.Contrast(image)
    return enhancer.enhance(2.0)


def sharpen(image):
    """Aplica enfoque."""
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    return image.filter(ImageFilter.SHARPEN)


def denoise(image):
    """Reduce ruido con filtro de mediana."""
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    return image.filter(ImageFilter.MedianFilter(size=3))


def binarize(image, threshold=128):
    """Binariza la imagen usando umbral de Otsu simplificado."""
    if isinstance(image, np.ndarray):
        image = Image.fromarray(image)
    if image.mode != "L":
        image = image.convert("L")

    # Calcular umbral Otsu
    np_img = np.array(image)
    hist, _ = np.histogram(np_img.flatten(), bins=256, range=(0, 256))
    total = np_img.size
    sum_total = np.sum(np.arange(256) * hist)

    weight_bg = 0
    sum_bg = 0
    max_variance = 0
    best_threshold = threshold

    for t in range(256):
        weight_bg += hist[t]
        if weight_bg == 0:
            continue
        weight_fg = total - weight_bg
        if weight_fg == 0:
            break
        sum_bg += t * hist[t]
        mean_bg = sum_bg / weight_bg
        mean_fg = (sum_total - sum_bg) / weight_fg
        variance = weight_bg * weight_fg * (mean_bg - mean_fg) ** 2
        if variance > max_variance:
            max_variance = variance
            best_threshold = t

    return image.point(lambda x: 255 if x > best_threshold else 0)


def preprocess_for_easyocr(image):
    """Preprocesamiento optimizado para Tesseract OCR.

    Nombre mantenido por compatibilidad con app.py.
    """
    if image is None:
        return None

    if isinstance(image, np.ndarray):
        if image.size == 0:
            return None
        image = Image.fromarray(image)

    # 1. Redimensionar
    resized = resize_plate(image)

    # 2. Escala de grises
    gray = to_grayscale(resized)

    # 3. Mejorar contraste
    enhanced = enhance_contrast(gray)

    # 4. Enfocar
    sharpened = sharpen(enhanced)

    # 5. Reducir ruido
    denoised = denoise(sharpened)

    return np.array(denoised)

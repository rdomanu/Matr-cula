#!/usr/bin/env python3
"""
MatriScan - Generador de imagenes sinteticas de matriculas espanolas.

Genera cientos de imagenes de matriculas con variaciones realistas
para entrenar el OCR sin necesidad de fotos reales.

Uso:
    python -m training.generate_plates
    python -m training.generate_plates --count 500
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter

import config
from core.plate_validator import MODERN_VALID_LETTERS, PROVINCIAL_CODES


# --- Generadores de texto de matriculas ---

def random_modern_plate():
    """Genera una matricula moderna aleatoria: 1234 BCD"""
    digits = "".join([str(random.randint(0, 9)) for _ in range(4)])
    letters = "".join(random.choices(MODERN_VALID_LETTERS, k=3))
    return f"{digits} {letters}"


def random_old_plate():
    """Genera una matricula antigua aleatoria: M 1234 AB"""
    province = random.choice(list(PROVINCIAL_CODES))
    digits = "".join([str(random.randint(0, 9)) for _ in range(4)])
    letters = "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ", k=2))
    return f"{province} {digits} {letters}"


# Matriculas concretas para incluir siempre (ejemplos comunes)
FIXED_PLATES = [
    "0000 BBB", "1234 BCD", "5678 FGH", "9999 ZZZ",
    "0001 BBB", "4820 GNT", "7234 BKM", "0091 HLC",
    "5567 FGR", "8901 KLN", "3456 DPW", "6712 JVR",
    "2468 MNP", "1357 RST", "8024 CVG", "3691 HBK",
    "4507 FLW", "7890 TBX", "6543 DGM", "2109 KPN",
    # Antiguas
    "M 1234 AB", "B 5678 CD", "V 9012 FG", "MA 3456 HJ",
    "SE 7890 KL", "BI 2345 MN", "GR 6789 PQ", "SS 1234 RS",
    "CA 5678 TV", "Z 9012 WX",
]


def render_plate_image(plate_text, width=520, height=110):
    """Renderiza una imagen de matricula espanola realista.

    Args:
        plate_text: Texto de la matricula (ej: "1234 BCD").
        width: Ancho de la imagen.
        height: Alto de la imagen.

    Returns:
        PIL Image de la matricula.
    """
    img = Image.new("RGB", (width, height), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Borde negro de la matricula
    draw.rectangle([0, 0, width - 1, height - 1], outline=(0, 0, 0), width=3)

    # Banda azul EU a la izquierda
    blue_width = int(width * 0.08)
    draw.rectangle([3, 3, blue_width, height - 4], fill=(0, 51, 160))
    # Estrellitas EU (simplificado)
    star_y_positions = [15, 25, 35, 45, 55, 65, 75, 85, 95]
    for sy in star_y_positions:
        if sy < height - 10:
            draw.text((blue_width // 2 - 3, sy - 4), "*", fill=(255, 204, 0))
    # "E" de Espana
    draw.text((blue_width // 2 - 4, height - 25), "E", fill=(255, 255, 255))

    # Texto de la matricula
    # Intentar usar una fuente monospace grande
    font_size = int(height * 0.55)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", font_size)
    except (IOError, OSError):
        try:
            font = ImageFont.truetype("/data/data/com.termux/files/usr/share/fonts/TTF/DejaVuSansMono-Bold.ttf", font_size)
        except (IOError, OSError):
            try:
                font = ImageFont.truetype("DejaVuSansMono-Bold.ttf", font_size)
            except (IOError, OSError):
                font = ImageFont.load_default()

    # Centrar texto
    text_area_x = blue_width + 10
    text_area_w = width - text_area_x - 10

    bbox = draw.textbbox((0, 0), plate_text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    text_x = text_area_x + (text_area_w - text_w) // 2
    text_y = (height - text_h) // 2 - 5

    draw.text((text_x, text_y), plate_text, fill=(0, 0, 0), font=font)

    return img


def apply_augmentation(img):
    """Aplica variaciones aleatorias para simular condiciones reales."""
    augmented = img.copy()

    # Rotacion leve (-5 a +5 grados)
    angle = random.uniform(-5, 5)
    augmented = augmented.rotate(angle, fillcolor=(200, 200, 200), expand=False)

    # Brillo aleatorio (simular dia/noche)
    from PIL import ImageEnhance
    brightness = random.uniform(0.5, 1.3)
    augmented = ImageEnhance.Brightness(augmented).enhance(brightness)

    # Contraste
    contrast = random.uniform(0.7, 1.3)
    augmented = ImageEnhance.Contrast(augmented).enhance(contrast)

    # Blur leve (simular movimiento/desenfoque)
    if random.random() < 0.4:
        blur_radius = random.uniform(0.5, 1.5)
        augmented = augmented.filter(ImageFilter.GaussianBlur(radius=blur_radius))

    # Ruido (simular camara de baja calidad)
    if random.random() < 0.3:
        np_img = np.array(augmented).astype(np.float32)
        noise = np.random.normal(0, random.uniform(5, 20), np_img.shape)
        np_img = np.clip(np_img + noise, 0, 255).astype(np.uint8)
        augmented = Image.fromarray(np_img)

    # Redimensionar (simular diferentes distancias)
    scale = random.uniform(0.5, 1.0)
    new_w = int(augmented.width * scale)
    new_h = int(augmented.height * scale)
    if new_w > 50 and new_h > 15:
        augmented = augmented.resize((new_w, new_h), Image.LANCZOS)
        # Volver a tamano original (simula pixelacion por distancia)
        augmented = augmented.resize((img.width, img.height), Image.LANCZOS)

    # Perspectiva leve (simular angulo de vision)
    if random.random() < 0.3:
        w, h = augmented.size
        # Deformacion sutil
        dx = random.randint(0, int(w * 0.05))
        dy = random.randint(0, int(h * 0.05))
        coeffs = [
            1 + random.uniform(-0.02, 0.02),  # a
            random.uniform(-0.02, 0.02),       # b
            dx,                                 # c
            random.uniform(-0.02, 0.02),       # d
            1 + random.uniform(-0.02, 0.02),   # e
            dy,                                 # f
            0, 0                                # g, h
        ]
        augmented = augmented.transform((w, h), Image.AFFINE, coeffs[:6], Image.BICUBIC)

    return augmented


def generate_dataset(count=200, output_dir=None):
    """Genera un dataset completo de matriculas sinteticas.

    Args:
        count: Numero total de imagenes a generar.
        output_dir: Directorio de salida.
    """
    output_dir = output_dir or config.TRAINING_PLATES_DIR
    os.makedirs(output_dir, exist_ok=True)

    labels = {}
    generated = 0

    print(f"Generando {count} imagenes de matriculas sinteticas...")
    print(f"Directorio: {output_dir}")

    # Primero las matriculas fijas (siempre incluidas)
    for plate_text in FIXED_PLATES:
        if generated >= count:
            break

        # Version limpia
        img = render_plate_image(plate_text)
        filename = f"synth_{generated:04d}_{plate_text.replace(' ', '')}.jpg"
        filepath = os.path.join(output_dir, filename)
        img.save(filepath, "JPEG", quality=95)
        normalized = plate_text.replace(" ", "")
        labels[f"synth_{generated:04d}"] = {
            "filename": filename,
            "ocr_text": plate_text,
            "corrected_text": normalized,
            "confidence": 1.0,
            "timestamp": "synthetic",
            "verified": True,
            "reason": "synthetic",
        }
        generated += 1

        # Version con augmentacion
        if generated < count:
            aug_img = apply_augmentation(img)
            aug_filename = f"synth_{generated:04d}_{plate_text.replace(' ', '')}_aug.jpg"
            aug_filepath = os.path.join(output_dir, aug_filename)
            aug_img.save(aug_filepath, "JPEG", quality=90)
            labels[f"synth_{generated:04d}"] = {
                "filename": aug_filename,
                "ocr_text": plate_text,
                "corrected_text": normalized,
                "confidence": 1.0,
                "timestamp": "synthetic",
                "verified": True,
                "reason": "synthetic",
            }
            generated += 1

    # Luego matriculas aleatorias
    while generated < count:
        # 70% modernas, 30% antiguas
        if random.random() < 0.7:
            plate_text = random_modern_plate()
        else:
            plate_text = random_old_plate()

        img = render_plate_image(plate_text)

        # 60% de probabilidad de aplicar augmentacion
        if random.random() < 0.6:
            img = apply_augmentation(img)

        normalized = plate_text.replace(" ", "")
        filename = f"synth_{generated:04d}_{normalized}.jpg"
        filepath = os.path.join(output_dir, filename)
        img.save(filepath, "JPEG", quality=random.randint(75, 95))

        labels[f"synth_{generated:04d}"] = {
            "filename": filename,
            "ocr_text": plate_text,
            "corrected_text": normalized,
            "confidence": 1.0,
            "timestamp": "synthetic",
            "verified": True,
            "reason": "synthetic",
        }
        generated += 1

        if generated % 50 == 0:
            print(f"  {generated}/{count} generadas...")

    # Guardar labels
    import json
    labels_file = config.LABELS_FILE
    existing_labels = {}
    if os.path.exists(labels_file):
        try:
            with open(labels_file, "r") as f:
                existing_labels = json.load(f)
        except (json.JSONDecodeError, OSError):
            pass

    existing_labels.update(labels)
    with open(labels_file, "w") as f:
        json.dump(existing_labels, f, indent=2, ensure_ascii=False)

    print(f"\nCompletado: {generated} imagenes generadas")
    print(f"Labels guardadas en: {labels_file}")
    print(f"Total en dataset: {len(existing_labels)} imagenes")


def main():
    parser = argparse.ArgumentParser(description="Genera matriculas sinteticas para entrenamiento")
    parser.add_argument("--count", "-c", type=int, default=200, help="Numero de imagenes (default: 200)")
    args = parser.parse_args()
    generate_dataset(count=args.count)


if __name__ == "__main__":
    main()

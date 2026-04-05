#!/usr/bin/env python3
"""
MatriScan - Importacion masiva de imagenes de matriculas para entrenamiento.

Uso:
    python -m training.bulk_import --folder ./mis_fotos_matriculas
    python -m training.bulk_import --folder ./fotos --auto-detect

Modos:
  1. Con nombres de archivo como etiqueta:
     Nombra las fotos con el texto de la matricula:
       1234BCD.jpg, M1234AB.png, 5678FGH_foto1.jpg
     El script extrae la matricula del nombre del archivo.

  2. Con deteccion automatica (--auto-detect):
     El script intenta detectar y leer la matricula de cada foto
     usando el pipeline completo (detector + OCR).
     Luego puedes corregir las lecturas desde la web.

  3. Con archivo CSV de etiquetas (--labels archivo.csv):
     CSV con columnas: nombre_archivo;matricula
     Ej: foto1.jpg;1234 BCD
"""

import argparse
import os
import re
import sys

# Anadir directorio raiz al path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cv2

import config
from core.plate_validator import validate_plate, normalize_plate
from training.collector import TrainingCollector


def extract_plate_from_filename(filename):
    """Intenta extraer la matricula del nombre del archivo.

    Busca patrones como: 1234BCD.jpg, M-1234-AB.png, 5678_FGH_foto.jpg
    """
    # Quitar extension
    name = os.path.splitext(filename)[0]

    # Limpiar separadores comunes
    cleaned = re.sub(r"[-_\s]+", "", name.upper())

    # Intentar encontrar patron de matricula moderna (4 digitos + 3 letras)
    match = re.search(r"(\d{4}[A-Z]{3})", cleaned)
    if match:
        text = match.group(1)
        validation = validate_plate(text)
        if validation:
            return validation["plate"]

    # Intentar formato antiguo (1-2 letras + 4 digitos + 2 letras)
    match = re.search(r"([A-Z]{1,2}\d{4}[A-Z]{2})", cleaned)
    if match:
        text = match.group(1)
        validation = validate_plate(text)
        if validation:
            return validation["plate"]

    # Intentar con el nombre completo limpio
    validation = validate_plate(cleaned)
    if validation:
        return validation["plate"]

    return None


def auto_detect_plate(image_path):
    """Detecta y lee la matricula de una imagen usando el pipeline completo."""
    from core.detector import detect_all_plates
    from core.preprocessor import preprocess_for_easyocr
    from core.ocr_engine import read_plate

    image = cv2.imread(image_path)
    if image is None:
        return None, None, 0

    boxes, plate_images = detect_all_plates(image)

    for plate_img in plate_images:
        processed = preprocess_for_easyocr(plate_img)
        if processed is None:
            continue

        text, confidence = read_plate(processed)
        if text:
            validation = validate_plate(text)
            if validation:
                return validation["plate"], plate_img, confidence

    return None, None, 0


def import_from_folder(folder, auto_detect=False, labels_file=None):
    """Importa imagenes de matriculas desde una carpeta.

    Args:
        folder: Ruta a la carpeta con imagenes.
        auto_detect: Si True, usa OCR para detectar matriculas.
        labels_file: Ruta a CSV con etiquetas (nombre_archivo;matricula).
    """
    collector = TrainingCollector()
    image_extensions = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}

    # Cargar etiquetas desde CSV si se proporciona
    labels_map = {}
    if labels_file and os.path.exists(labels_file):
        import csv
        with open(labels_file, "r", encoding="utf-8") as f:
            reader = csv.reader(f, delimiter=";")
            for row in reader:
                if len(row) >= 2:
                    labels_map[row[0].strip()] = row[1].strip().upper()
        print(f"Cargadas {len(labels_map)} etiquetas desde {labels_file}")

    # Listar imagenes
    files = sorted(os.listdir(folder))
    image_files = [f for f in files if os.path.splitext(f)[1].lower() in image_extensions]

    if not image_files:
        print(f"No se encontraron imagenes en {folder}")
        return

    print(f"Encontradas {len(image_files)} imagenes en {folder}")
    print()

    stats = {"imported": 0, "skipped": 0, "failed": 0, "auto_detected": 0}

    for i, filename in enumerate(image_files, 1):
        filepath = os.path.join(folder, filename)
        plate_text = None
        confidence = 1.0

        # Prioridad 1: CSV de etiquetas
        if filename in labels_map:
            plate_text = labels_map[filename]

        # Prioridad 2: Nombre del archivo
        if plate_text is None:
            plate_text = extract_plate_from_filename(filename)

        # Prioridad 3: Deteccion automatica
        if plate_text is None and auto_detect:
            print(f"  [{i}/{len(image_files)}] Detectando en {filename}...", end=" ")
            detected, plate_img, conf = auto_detect_plate(filepath)
            if detected:
                plate_text = detected
                confidence = conf
                stats["auto_detected"] += 1
                print(f"-> {plate_text} (confianza: {conf:.2f})")
            else:
                print("-> No detectada")

        if plate_text is None:
            stats["skipped"] += 1
            if not auto_detect:
                print(f"  [{i}/{len(image_files)}] {filename} -> No se pudo extraer matricula (saltando)")
            continue

        # Leer imagen
        image = cv2.imread(filepath)
        if image is None:
            stats["failed"] += 1
            print(f"  [{i}/{len(image_files)}] {filename} -> Error leyendo imagen")
            continue

        # Guardar para entrenamiento
        image_id = collector.save_plate_image(image, plate_text, confidence)
        if image_id:
            # Marcar como verificada si viene de nombre de archivo o CSV (etiqueta manual)
            if filename in labels_map or extract_plate_from_filename(filename):
                collector.correct_label(image_id, normalize_plate(plate_text))

            stats["imported"] += 1
            print(f"  [{i}/{len(image_files)}] {filename} -> {plate_text} (OK)")
        else:
            stats["failed"] += 1
            print(f"  [{i}/{len(image_files)}] {filename} -> Error guardando")

    print()
    print("=" * 50)
    print(f"  Resultados de importacion:")
    print(f"  - Importadas: {stats['imported']}")
    print(f"  - Saltadas:   {stats['skipped']}")
    print(f"  - Errores:    {stats['failed']}")
    if auto_detect:
        print(f"  - Auto-detectadas: {stats['auto_detected']}")
    print(f"  Total en dataset: {collector.get_stats()['total_images']}")
    print("=" * 50)

    if stats["auto_detected"] > 0:
        print()
        print("Las matriculas auto-detectadas pueden tener errores.")
        print("Revisa y corrige desde la interfaz web: http://localhost:5000")
        print("(seccion Entrenamiento)")


def main():
    parser = argparse.ArgumentParser(
        description="MatriScan - Importar imagenes de matriculas para entrenamiento"
    )
    parser.add_argument(
        "--folder", "-f", required=True,
        help="Carpeta con imagenes de matriculas"
    )
    parser.add_argument(
        "--auto-detect", "-a", action="store_true",
        help="Usar OCR para detectar matriculas automaticamente"
    )
    parser.add_argument(
        "--labels", "-l", default=None,
        help="Archivo CSV con etiquetas (nombre_archivo;matricula)"
    )

    args = parser.parse_args()

    if not os.path.isdir(args.folder):
        print(f"Error: La carpeta '{args.folder}' no existe")
        sys.exit(1)

    import_from_folder(args.folder, auto_detect=args.auto_detect, labels_file=args.labels)


if __name__ == "__main__":
    main()

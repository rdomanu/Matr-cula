"""Recopilacion y etiquetado de imagenes de matriculas para entrenamiento."""

import json
import os
import uuid
from datetime import datetime

import cv2

import config


class TrainingCollector:
    """Recopila pares (imagen, texto) para entrenar el modelo de OCR."""

    def __init__(self):
        self.plates_dir = config.TRAINING_PLATES_DIR
        self.labels_file = config.LABELS_FILE
        self._labels = {}

        os.makedirs(self.plates_dir, exist_ok=True)
        self._load_labels()

    def _load_labels(self):
        """Carga etiquetas existentes."""
        if os.path.exists(self.labels_file):
            try:
                with open(self.labels_file, "r", encoding="utf-8") as f:
                    self._labels = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._labels = {}

    def _save_labels(self):
        """Guarda etiquetas a disco."""
        try:
            with open(self.labels_file, "w", encoding="utf-8") as f:
                json.dump(self._labels, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def save_plate_image(self, image, ocr_text, confidence):
        """Guarda una imagen de matricula para entrenamiento.

        Args:
            image: Imagen BGR de la matricula recortada.
            ocr_text: Texto leido por OCR.
            confidence: Confianza del OCR.

        Returns:
            ID de la imagen guardada o None si se alcanzo el limite.
        """
        if not config.TRAINING_AUTO_SAVE:
            return None

        # Verificar limite
        if len(self._labels) >= config.TRAINING_MAX_IMAGES:
            return None

        # Generar nombre unico
        image_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{image_id}.jpg"
        filepath = os.path.join(self.plates_dir, filename)

        try:
            cv2.imwrite(filepath, image)
        except Exception:
            return None

        # Guardar etiqueta
        self._labels[image_id] = {
            "filename": filename,
            "ocr_text": ocr_text,
            "corrected_text": None,  # El usuario lo corregira via web
            "confidence": confidence,
            "timestamp": timestamp,
            "verified": False,
        }
        self._save_labels()

        return image_id

    def correct_label(self, image_id, corrected_text):
        """Corrige la etiqueta de una imagen (el usuario indica el texto real).

        Args:
            image_id: ID de la imagen.
            corrected_text: Texto correcto de la matricula.
        """
        if image_id in self._labels:
            self._labels[image_id]["corrected_text"] = corrected_text.upper().strip()
            self._labels[image_id]["verified"] = True
            self._save_labels()
            return True
        return False

    def get_unverified(self, limit=20):
        """Obtiene imagenes sin verificar para que el usuario las corrija."""
        unverified = []
        for image_id, info in self._labels.items():
            if not info["verified"]:
                unverified.append({
                    "id": image_id,
                    "filename": info["filename"],
                    "ocr_text": info["ocr_text"],
                    "confidence": info["confidence"],
                })
            if len(unverified) >= limit:
                break
        return unverified

    def get_verified_dataset(self):
        """Obtiene el dataset verificado para entrenamiento.

        Returns:
            Lista de tuplas (filepath, texto_correcto).
        """
        dataset = []
        for image_id, info in self._labels.items():
            if info["verified"] and info["corrected_text"]:
                filepath = os.path.join(self.plates_dir, info["filename"])
                if os.path.exists(filepath):
                    dataset.append((filepath, info["corrected_text"]))
        return dataset

    def get_stats(self):
        """Estadisticas del dataset."""
        total = len(self._labels)
        verified = sum(1 for v in self._labels.values() if v["verified"])
        return {
            "total_images": total,
            "verified": verified,
            "unverified": total - verified,
            "max_images": config.TRAINING_MAX_IMAGES,
        }

"""Recopilacion y etiquetado de imagenes de matriculas para entrenamiento."""

import json
import os
import random
import time
import uuid
from datetime import datetime

import numpy as np
from PIL import Image

import config


# Categorias de captura para filtrado en la UI
CAPTURE_REASON_MANUAL = "manual"           # Subida por el usuario
CAPTURE_REASON_FAILED = "ocr_failed"       # OCR no pudo leer nada
CAPTURE_REASON_INVALID = "invalid_format"  # OCR leyo pero formato invalido
CAPTURE_REASON_LOW_CONF = "low_confidence" # Confianza baja
CAPTURE_REASON_RANDOM = "random_sample"    # Muestreo aleatorio de lecturas correctas


class TrainingCollector:
    """Recopila pares (imagen, texto) para entrenar el modelo de OCR."""

    def __init__(self):
        self.plates_dir = config.TRAINING_PLATES_DIR
        self.labels_file = config.LABELS_FILE
        self._labels = {}
        self._difficult_count_this_minute = 0
        self._last_minute_reset = time.time()

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

    def _check_rate_limit(self):
        """Controla que no se guarden demasiados frames dificiles por minuto."""
        now = time.time()
        if now - self._last_minute_reset >= 60:
            self._difficult_count_this_minute = 0
            self._last_minute_reset = now
        return self._difficult_count_this_minute < config.TRAINING_MAX_DIFFICULT_PER_MIN

    def save_plate_image(self, image, ocr_text, confidence, reason=CAPTURE_REASON_MANUAL):
        """Guarda una imagen de matricula para entrenamiento.

        Args:
            image: Imagen BGR de la matricula recortada.
            ocr_text: Texto leido por OCR (puede ser None si fallo).
            confidence: Confianza del OCR (0 si fallo).
            reason: Razon de captura (manual, ocr_failed, low_confidence, etc.)

        Returns:
            ID de la imagen guardada o None si se alcanzo el limite.
        """
        if not config.TRAINING_AUTO_SAVE:
            return None

        # Verificar limite total
        if len(self._labels) >= config.TRAINING_MAX_IMAGES:
            return None

        # Generar nombre unico
        image_id = str(uuid.uuid4())[:8]
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"{timestamp}_{image_id}.jpg"
        filepath = os.path.join(self.plates_dir, filename)

        try:
            if isinstance(image, np.ndarray):
                pil_img = Image.fromarray(image)
            else:
                pil_img = image
            pil_img.save(filepath, "JPEG")
        except Exception:
            return None

        # Guardar etiqueta
        self._labels[image_id] = {
            "filename": filename,
            "ocr_text": ocr_text or "",
            "corrected_text": None,  # El usuario lo corregira via web
            "confidence": confidence,
            "timestamp": timestamp,
            "verified": False,
            "reason": reason,
        }
        self._save_labels()

        return image_id

    def save_difficult_frame(self, image, ocr_text, confidence, reason):
        """Guarda automaticamente un frame dificil para entrenamiento.

        Se llama desde el detection loop cuando:
        - OCR no pudo leer nada (reason=ocr_failed)
        - Formato invalido tras OCR (reason=invalid_format)
        - Confianza baja (reason=low_confidence)
        - Muestreo aleatorio (reason=random_sample)

        Incluye rate limiting para no saturar el disco.
        """
        if not self._check_rate_limit():
            return None

        image_id = self.save_plate_image(image, ocr_text, confidence, reason=reason)
        if image_id:
            self._difficult_count_this_minute += 1
        return image_id

    def should_random_sample(self):
        """Decide aleatoriamente si capturar un frame valido como muestra."""
        return random.random() < config.TRAINING_RANDOM_SAMPLE_RATE

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

    def get_unverified(self, limit=20, reason_filter=None):
        """Obtiene imagenes sin verificar para que el usuario las corrija.

        Args:
            limit: Numero maximo de resultados.
            reason_filter: Filtrar por razon de captura (opcional).
        """
        unverified = []
        for image_id, info in self._labels.items():
            if not info["verified"]:
                reason = info.get("reason", CAPTURE_REASON_MANUAL)
                if reason_filter and reason != reason_filter:
                    continue
                unverified.append({
                    "id": image_id,
                    "filename": info["filename"],
                    "ocr_text": info["ocr_text"],
                    "confidence": info["confidence"],
                    "reason": reason,
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
        by_reason = {}
        for v in self._labels.values():
            r = v.get("reason", CAPTURE_REASON_MANUAL)
            by_reason[r] = by_reason.get(r, 0) + 1
        return {
            "total_images": total,
            "verified": verified,
            "unverified": total - verified,
            "max_images": config.TRAINING_MAX_IMAGES,
            "by_reason": by_reason,
        }

    def discard_image(self, image_id):
        """Descarta una imagen de entrenamiento (no es una matricula real, basura, etc.)."""
        if image_id in self._labels:
            info = self._labels[image_id]
            filepath = os.path.join(self.plates_dir, info["filename"])
            try:
                os.remove(filepath)
            except OSError:
                pass
            del self._labels[image_id]
            self._save_labels()
            return True
        return False

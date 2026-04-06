"""Sistema de alertas, watchlist y gestion de imagenes de matriculas encontradas."""

import json
import os
import time
import threading
from datetime import datetime

import numpy as np
from PIL import Image

import config


class AlertManager:
    """Gestiona la watchlist de matriculas y genera alertas."""

    def __init__(self, watchlist_file=None, alerts_dir=None):
        self.watchlist_file = watchlist_file or config.WATCHLIST_FILE
        self.alerts_dir = alerts_dir or config.ALERTS_DIR
        self._watchlist = {}
        self._cooldowns = {}
        self._lock = threading.Lock()
        self._alert_callbacks = []

        os.makedirs(os.path.dirname(self.watchlist_file), exist_ok=True)
        os.makedirs(self.alerts_dir, exist_ok=True)
        self._load_watchlist()

    def _load_watchlist(self):
        if os.path.exists(self.watchlist_file):
            try:
                with open(self.watchlist_file, "r", encoding="utf-8") as f:
                    self._watchlist = json.load(f)
            except (json.JSONDecodeError, OSError):
                self._watchlist = {}

    def _save_watchlist(self):
        try:
            with open(self.watchlist_file, "w", encoding="utf-8") as f:
                json.dump(self._watchlist, f, indent=2, ensure_ascii=False)
        except OSError:
            pass

    def add_plate(self, plate_normalized, alias=""):
        key = plate_normalized.upper().replace(" ", "")
        with self._lock:
            if key in self._watchlist:
                return False
            self._watchlist[key] = {
                "alias": alias,
                "added": datetime.now().strftime(config.CSV_DATETIME_FORMAT),
                "plate_display": plate_normalized,
            }
            self._save_watchlist()
        return True

    def remove_plate(self, plate_normalized):
        key = plate_normalized.upper().replace(" ", "")
        with self._lock:
            if key in self._watchlist:
                del self._watchlist[key]
                self._save_watchlist()
                return True
        return False

    def update_alias(self, plate_normalized, alias):
        key = plate_normalized.upper().replace(" ", "")
        with self._lock:
            if key in self._watchlist:
                self._watchlist[key]["alias"] = alias
                self._save_watchlist()
                return True
        return False

    def get_watchlist(self):
        with self._lock:
            return dict(self._watchlist)

    def get_watchlist_plates(self):
        with self._lock:
            return set(self._watchlist.keys())

    def is_watched(self, plate_normalized):
        key = plate_normalized.upper().replace(" ", "")
        with self._lock:
            return key in self._watchlist

    def check_and_alert(self, plate_normalized, plate_image=None, location=None):
        key = plate_normalized.upper().replace(" ", "")

        with self._lock:
            if key not in self._watchlist:
                return None
            now = time.time()
            if key in self._cooldowns:
                elapsed = now - self._cooldowns[key]
                if elapsed < config.ALERT_COOLDOWN_SECONDS:
                    return None
            self._cooldowns[key] = now
            plate_info = self._watchlist[key]

        # Guardar imagen usando PIL
        image_path = None
        if plate_image is not None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_filename = f"{key}_{timestamp}.jpg"
            image_path = os.path.join(self.alerts_dir, image_filename)
            try:
                if isinstance(plate_image, np.ndarray):
                    pil_img = Image.fromarray(plate_image)
                else:
                    pil_img = plate_image
                pil_img.save(image_path, "JPEG")
            except Exception:
                image_path = None

        alert_data = {
            "plate": key,
            "plate_display": plate_info.get("plate_display", key),
            "alias": plate_info.get("alias", ""),
            "timestamp": datetime.now().strftime(config.CSV_DATETIME_FORMAT),
            "image_path": image_path,
            "location": location,
        }

        for callback in self._alert_callbacks:
            try:
                callback(alert_data)
            except Exception:
                pass

        return alert_data

    def on_alert(self, callback):
        self._alert_callbacks.append(callback)

    def get_alert_images(self, plate_normalized=None, limit=50):
        images = []
        if not os.path.exists(self.alerts_dir):
            return images
        filter_key = plate_normalized.upper().replace(" ", "") if plate_normalized else None
        for filename in sorted(os.listdir(self.alerts_dir), reverse=True):
            if not filename.endswith(".jpg"):
                continue
            if filter_key and not filename.startswith(filter_key):
                continue
            images.append({"filename": filename, "path": os.path.join(self.alerts_dir, filename)})
            if len(images) >= limit:
                break
        return images

    def import_watchlist(self, data):
        with self._lock:
            for key, value in data.items():
                normalized = key.upper().replace(" ", "")
                if normalized not in self._watchlist:
                    if isinstance(value, dict):
                        self._watchlist[normalized] = value
                    else:
                        self._watchlist[normalized] = {
                            "alias": str(value),
                            "added": datetime.now().strftime(config.CSV_DATETIME_FORMAT),
                            "plate_display": key,
                        }
            self._save_watchlist()

    def export_watchlist(self):
        with self._lock:
            return json.dumps(self._watchlist, indent=2, ensure_ascii=False)

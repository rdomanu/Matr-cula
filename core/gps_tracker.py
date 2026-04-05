"""Obtencion de ubicacion GPS usando Termux API."""

import json
import subprocess
import threading
import time

import config


class GPSTracker:
    """Obtiene y cachea la ubicacion GPS del telefono via termux-location."""

    def __init__(self, update_interval=None, provider=None):
        self.update_interval = update_interval or config.GPS_UPDATE_INTERVAL_SECONDS
        self.provider = provider or config.GPS_PROVIDER

        self._latitude = None
        self._longitude = None
        self._accuracy = None
        self._last_update = 0
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

    def start(self):
        """Inicia el tracker GPS en un hilo separado."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._update_loop, daemon=True)
        self._thread.start()

    def _update_loop(self):
        """Loop de actualizacion GPS."""
        while self._running:
            self._fetch_location()
            time.sleep(self.update_interval)

    def _fetch_location(self):
        """Obtiene la ubicacion actual via termux-location."""
        try:
            result = subprocess.run(
                [
                    "termux-location",
                    "-p", self.provider,
                    "-r", "once",
                ],
                capture_output=True,
                text=True,
                timeout=config.GPS_TIMEOUT_MS / 1000 + 5,
            )

            if result.returncode == 0 and result.stdout.strip():
                data = json.loads(result.stdout)
                with self._lock:
                    self._latitude = data.get("latitude")
                    self._longitude = data.get("longitude")
                    self._accuracy = data.get("accuracy")
                    self._last_update = time.time()

        except FileNotFoundError:
            # termux-location no disponible (no estamos en Termux)
            pass
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError):
            pass

    def get_location(self):
        """Obtiene la ultima ubicacion conocida.

        Returns:
            dict con latitude, longitude, accuracy, timestamp o None.
        """
        with self._lock:
            if self._latitude is not None:
                return {
                    "latitude": self._latitude,
                    "longitude": self._longitude,
                    "accuracy": self._accuracy,
                    "timestamp": self._last_update,
                }
        return None

    def get_coords_str(self):
        """Obtiene las coordenadas como string para CSV.

        Returns:
            Tupla (lat_str, lon_str) o ("", "").
        """
        loc = self.get_location()
        if loc:
            return (
                f"{loc['latitude']:.6f}",
                f"{loc['longitude']:.6f}",
            )
        return ("", "")

    def stop(self):
        """Detiene el tracker GPS."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    @property
    def is_running(self):
        return self._running

    @property
    def has_fix(self):
        """Indica si tiene una ubicacion valida reciente."""
        with self._lock:
            if self._latitude is not None:
                age = time.time() - self._last_update
                return age < self.update_interval * 3
        return False

    def set_manual_location(self, latitude, longitude):
        """Permite establecer ubicacion manualmente (para testing o fallback)."""
        with self._lock:
            self._latitude = latitude
            self._longitude = longitude
            self._accuracy = 0
            self._last_update = time.time()

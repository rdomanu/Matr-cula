"""Captura de video via navegador web (getUserMedia).

En vez de usar OpenCV (no disponible en Termux), la camara se captura
desde el navegador del movil usando JavaScript getUserMedia.
Los frames se envian como JPEG base64 al servidor via WebSocket.
"""

import base64
import threading
import time
from io import BytesIO

import numpy as np
from PIL import Image


class Camera:
    """Gestor de frames recibidos desde el navegador."""

    def __init__(self):
        self._frame = None  # PIL Image
        self._frame_np = None  # numpy array
        self._lock = threading.Lock()
        self._running = False
        self._frame_count = 0
        self._start_time = None

    def start(self):
        self._running = True
        self._start_time = time.time()
        self._frame_count = 0

    def stop(self):
        self._running = False
        with self._lock:
            self._frame = None
            self._frame_np = None

    def receive_frame(self, data_url):
        """Recibe un frame del navegador como data URL base64.

        Args:
            data_url: String "data:image/jpeg;base64,..." del canvas del navegador.
        """
        try:
            # Extraer base64 del data URL
            if "," in data_url:
                base64_data = data_url.split(",", 1)[1]
            else:
                base64_data = data_url

            image_bytes = base64.b64decode(base64_data)
            pil_image = Image.open(BytesIO(image_bytes)).convert("RGB")
            np_image = np.array(pil_image)

            with self._lock:
                self._frame = pil_image
                self._frame_np = np_image
                self._frame_count += 1

        except Exception:
            pass

    def read(self):
        """Obtiene el frame mas reciente como numpy array (RGB).

        Returns:
            numpy array RGB o None.
        """
        with self._lock:
            if self._frame_np is not None:
                return self._frame_np.copy()
            return None

    def read_pil(self):
        """Obtiene el frame mas reciente como PIL Image."""
        with self._lock:
            if self._frame is not None:
                return self._frame.copy()
            return None

    def get_frame_jpeg(self):
        """Obtiene el frame actual como bytes JPEG."""
        with self._lock:
            if self._frame is None:
                return None
            buffer = BytesIO()
            self._frame.save(buffer, format="JPEG", quality=70)
            return buffer.getvalue()

    @property
    def is_running(self):
        return self._running

    @property
    def fps_actual(self):
        if self._start_time and self._frame_count > 0:
            elapsed = time.time() - self._start_time
            if elapsed > 0:
                return self._frame_count / elapsed
        return 0

    @property
    def frame_count(self):
        return self._frame_count

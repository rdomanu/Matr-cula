"""Captura de video optimizada para deteccion de matriculas en movimiento."""

import time
import threading

import cv2

import config


class Camera:
    """Gestor de captura de video con buffer circular y control de FPS."""

    def __init__(self, source=None, fps=None, width=None, height=None):
        self.source = source if source is not None else config.CAMERA_SOURCE
        self.target_fps = fps or config.CAMERA_FPS
        self.width = width or config.CAMERA_WIDTH
        self.height = height or config.CAMERA_HEIGHT

        self._cap = None
        self._frame = None
        self._lock = threading.Lock()
        self._running = False
        self._thread = None
        self._frame_count = 0
        self._start_time = None

    def start(self):
        """Inicia la captura de video en un hilo separado."""
        if self._running:
            return

        self._cap = cv2.VideoCapture(self.source)
        if not self._cap.isOpened():
            raise RuntimeError(
                f"No se puede abrir la camara: {self.source}. "
                "Verifica que la camara esta disponible o la URL es correcta."
            )

        # Configurar resolucion
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)

        # Buffer minimo para reducir latencia
        self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 2)

        self._running = True
        self._start_time = time.time()
        self._frame_count = 0

        # Hilo de captura para no bloquear el procesamiento
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def _capture_loop(self):
        """Loop de captura en hilo separado."""
        frame_interval = 1.0 / self.target_fps

        while self._running:
            start = time.time()

            ret, frame = self._cap.read()
            if ret:
                with self._lock:
                    self._frame = frame
                    self._frame_count += 1

            # Controlar FPS
            elapsed = time.time() - start
            sleep_time = frame_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def read(self):
        """Obtiene el frame mas reciente.

        Returns:
            Frame BGR o None si no hay frame disponible.
        """
        with self._lock:
            if self._frame is not None:
                return self._frame.copy()
            return None

    def stop(self):
        """Detiene la captura de video."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()
            self._cap = None
        self._frame = None

    @property
    def is_running(self):
        return self._running

    @property
    def fps_actual(self):
        """FPS real medidos."""
        if self._start_time and self._frame_count > 0:
            elapsed = time.time() - self._start_time
            if elapsed > 0:
                return self._frame_count / elapsed
        return 0

    @property
    def frame_count(self):
        return self._frame_count

    def get_frame_jpeg(self):
        """Obtiene el frame actual codificado como JPEG para streaming web.

        Returns:
            bytes JPEG o None.
        """
        frame = self.read()
        if frame is None:
            return None
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 70])
        return buffer.tobytes()

    def __del__(self):
        self.stop()

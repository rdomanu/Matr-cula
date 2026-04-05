"""Registro CSV de todas las matriculas detectadas y busqueda historica."""

import csv
import os
import threading
from datetime import datetime, date

import config


class DetectionLogger:
    """Registra todas las detecciones en archivos CSV diarios y permite busqueda."""

    def __init__(self, data_dir=None):
        self.data_dir = data_dir or config.DATA_DIR
        self._lock = threading.Lock()
        self._current_date = None
        self._current_file = None
        self._current_writer = None
        self._session_count = 0

    def _get_csv_path(self, for_date=None):
        """Genera la ruta del archivo CSV para una fecha dada."""
        d = for_date or date.today()
        filename = f"detections_{d.strftime(config.CSV_DATE_FORMAT)}.csv"
        return os.path.join(self.data_dir, filename)

    def _ensure_file(self):
        """Asegura que el archivo CSV del dia actual esta abierto."""
        today = date.today()
        if self._current_date != today or self._current_file is None:
            self._close_file()
            path = self._get_csv_path(today)
            file_exists = os.path.exists(path)

            self._current_file = open(path, "a", newline="", encoding="utf-8")
            self._current_writer = csv.writer(
                self._current_file, delimiter=config.CSV_SEPARATOR
            )

            # Escribir cabecera si es archivo nuevo
            if not file_exists:
                self._current_writer.writerow([
                    "fecha", "hora", "matricula", "tipo", "confianza",
                    "latitud", "longitud",
                ])

            self._current_date = today

    def _close_file(self):
        """Cierra el archivo CSV actual."""
        if self._current_file:
            self._current_file.flush()
            self._current_file.close()
            self._current_file = None
            self._current_writer = None

    def log_detection(self, plate_text, plate_type, confidence, latitude="", longitude=""):
        """Registra una deteccion de matricula.

        Args:
            plate_text: Texto de la matricula (formateado).
            plate_type: Tipo (modern, old_alpha, old_numeric, etc.).
            confidence: Confianza OCR (0-1).
            latitude: Latitud GPS.
            longitude: Longitud GPS.
        """
        now = datetime.now()
        with self._lock:
            self._ensure_file()
            self._current_writer.writerow([
                now.strftime(config.CSV_DATE_FORMAT),
                now.strftime("%H:%M:%S"),
                plate_text,
                plate_type,
                f"{confidence:.2f}",
                latitude,
                longitude,
            ])
            self._current_file.flush()
            self._session_count += 1

    def search_plate(self, plate_normalized):
        """Busca una matricula en todos los archivos CSV historicos.

        Args:
            plate_normalized: Matricula normalizada (sin espacios, mayusculas).

        Returns:
            Lista de dict con fecha, hora, latitud, longitud de cada avistamiento.
        """
        results = []
        plate_upper = plate_normalized.upper().replace(" ", "")

        # Flush del archivo actual antes de buscar
        with self._lock:
            if self._current_file:
                self._current_file.flush()

        # Buscar en todos los archivos CSV del directorio
        if not os.path.exists(self.data_dir):
            return results

        for filename in sorted(os.listdir(self.data_dir)):
            if not filename.startswith("detections_") or not filename.endswith(".csv"):
                continue

            filepath = os.path.join(self.data_dir, filename)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    reader = csv.DictReader(f, delimiter=config.CSV_SEPARATOR)
                    for row in reader:
                        csv_plate = row.get("matricula", "").replace(" ", "").upper()
                        if csv_plate == plate_upper:
                            results.append({
                                "fecha": row.get("fecha", ""),
                                "hora": row.get("hora", ""),
                                "latitud": row.get("latitud", ""),
                                "longitud": row.get("longitud", ""),
                                "confianza": row.get("confianza", ""),
                            })
            except (OSError, csv.Error):
                continue

        return results

    def get_recent_detections(self, limit=20):
        """Obtiene las detecciones mas recientes del dia actual.

        Returns:
            Lista de las ultimas N detecciones.
        """
        path = self._get_csv_path()
        if not os.path.exists(path):
            return []

        # Flush antes de leer
        with self._lock:
            if self._current_file:
                self._current_file.flush()

        detections = []
        try:
            with open(path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f, delimiter=config.CSV_SEPARATOR)
                for row in reader:
                    detections.append(row)
        except (OSError, csv.Error):
            pass

        # Devolver las ultimas N
        return detections[-limit:]

    def get_stats(self):
        """Obtiene estadisticas de la sesion actual."""
        return {
            "session_count": self._session_count,
            "today_file": self._get_csv_path(),
        }

    def get_csv_files(self):
        """Lista todos los archivos CSV disponibles."""
        files = []
        if os.path.exists(self.data_dir):
            for filename in sorted(os.listdir(self.data_dir), reverse=True):
                if filename.startswith("detections_") and filename.endswith(".csv"):
                    filepath = os.path.join(self.data_dir, filename)
                    size = os.path.getsize(filepath)
                    files.append({
                        "filename": filename,
                        "path": filepath,
                        "size_kb": round(size / 1024, 1),
                    })
        return files

    def close(self):
        """Cierra el logger."""
        self._close_file()

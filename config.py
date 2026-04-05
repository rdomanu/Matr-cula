"""Configuracion global del sistema de reconocimiento de matriculas."""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
ALERTS_DIR = os.path.join(DATA_DIR, "alerts")
TRAINING_DIR = os.path.join(DATA_DIR, "training")
TRAINING_PLATES_DIR = os.path.join(TRAINING_DIR, "plates")

# --- Camara ---
CAMERA_SOURCE = 0  # 0 = camara local, o URL de IP cam (ej: "http://192.168.1.5:8080/video")
CAMERA_FPS = 10
CAMERA_WIDTH = 1280
CAMERA_HEIGHT = 720

# --- Deteccion ---
# Ratio de aspecto de matriculas espanolas: ~4.7:1
PLATE_ASPECT_RATIO_MIN = 2.5
PLATE_ASPECT_RATIO_MAX = 6.0
PLATE_MIN_WIDTH = 80
PLATE_MAX_WIDTH = 600
PLATE_MIN_HEIGHT = 15
PLATE_MAX_HEIGHT = 120

# --- OCR ---
OCR_LANGUAGES = ["en"]  # EasyOCR: 'en' cubre caracteres latinos de matriculas
OCR_CONFIDENCE_THRESHOLD = 0.4
OCR_GPU = False  # En Termux/Android normalmente no hay GPU CUDA

# --- Cache y deduplicacion ---
RECENT_PLATES_CACHE_SIZE = 100
RECENT_PLATES_TTL_SECONDS = 5  # No re-procesar misma matricula en 5 seg

# --- Alertas ---
ALERT_COOLDOWN_SECONDS = 300  # 5 min entre alertas repetidas de misma matricula
ALERT_SOUND_FILE = os.path.join(BASE_DIR, "static", "sounds", "alert.mp3")

# --- GPS ---
GPS_UPDATE_INTERVAL_SECONDS = 15  # Pedir GPS cada 15 seg
GPS_PROVIDER = "gps"  # "gps", "network", o "passive"
GPS_TIMEOUT_MS = 5000

# --- Registro CSV ---
CSV_SEPARATOR = ";"
CSV_DATE_FORMAT = "%Y-%m-%d"
CSV_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

# --- Servidor web ---
FLASK_HOST = "0.0.0.0"
FLASK_PORT = 5000
SECRET_KEY = os.urandom(24).hex()

# --- Rutas de datos ---
WATCHLIST_FILE = os.path.join(DATA_DIR, "watchlist.json")
LABELS_FILE = os.path.join(TRAINING_DIR, "labels.json")

# --- Entrenamiento ---
TRAINING_AUTO_SAVE = True  # Guardar automaticamente imagenes de matriculas para entrenamiento
TRAINING_MAX_IMAGES = 5000  # Maximo de imagenes guardadas para entrenamiento

# Captura automatica de frames dificiles para entrenamiento
TRAINING_CAPTURE_FAILED = True      # Guardar frames donde OCR no pudo leer o fallo validacion
TRAINING_CAPTURE_LOW_CONF = True    # Guardar frames con confianza baja
TRAINING_LOW_CONF_THRESHOLD = 0.65  # Por debajo de esto se considera "baja confianza"
TRAINING_RANDOM_SAMPLE_RATE = 0.1   # 10% de lecturas correctas se guardan aleatoriamente
TRAINING_MAX_DIFFICULT_PER_MIN = 10 # Maximo de frames dificiles guardados por minuto (evitar spam)

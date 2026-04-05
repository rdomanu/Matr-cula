"""MatriScan - Servidor principal Flask con WebSocket para deteccion de matriculas."""

import os
import time
import threading
from datetime import datetime

from flask import Flask, render_template, Response, jsonify, request, send_file
from flask_socketio import SocketIO

import config
from core.camera import Camera
from core.detector import detect_all_plates, draw_detections
from core.preprocessor import preprocess_for_easyocr
from core.ocr_engine import read_plate_cached, plate_cache
from core.plate_validator import validate_plate, normalize_plate
from core.alert_manager import AlertManager
from core.detection_logger import DetectionLogger
from core.gps_tracker import GPSTracker

# --- Inicializar Flask ---
app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# --- Componentes del sistema ---
camera = Camera()
alert_manager = AlertManager()
detection_logger = DetectionLogger()
gps_tracker = GPSTracker()

# --- Estado global ---
detection_running = False
detection_thread = None
log_all_plates = True
annotated_frame = None
frame_lock = threading.Lock()

# --- Settings en memoria ---
current_settings = {
    "fps": config.CAMERA_FPS,
    "cooldown": config.ALERT_COOLDOWN_SECONDS,
    "log_all": True,
    "sound": True,
    "camera_source": config.CAMERA_SOURCE,
}


def detection_loop():
    """Bucle principal de deteccion de matriculas."""
    global detection_running, annotated_frame, log_all_plates

    while detection_running:
        frame = camera.read()
        if frame is None:
            time.sleep(0.1)
            continue

        # Detectar todas las matriculas en el frame
        boxes, plate_images = detect_all_plates(frame)

        texts = []
        watchlist_plates = alert_manager.get_watchlist_plates()

        for i, plate_img in enumerate(plate_images):
            # Preprocesar para OCR
            processed = preprocess_for_easyocr(plate_img)
            if processed is None:
                texts.append("")
                continue

            # Leer con OCR + cache de deduplicacion
            validation, confidence = read_plate_cached(processed, validate_plate)

            if validation is None:
                texts.append("")
                continue

            plate_text = validation["plate"]
            plate_normalized = validation["normalized"]
            plate_type = validation["type"]
            texts.append(plate_text)

            # Obtener GPS
            lat, lon = gps_tracker.get_coords_str()

            # Registrar en CSV
            if log_all_plates:
                detection_logger.log_detection(
                    plate_text, plate_type, confidence, lat, lon
                )

            # Comprobar watchlist
            is_alert = False
            alert_data = alert_manager.check_and_alert(
                plate_normalized, plate_img,
                location=gps_tracker.get_location(),
            )
            if alert_data:
                is_alert = True
                socketio.emit("alert_triggered", alert_data)

            # Notificar al frontend
            socketio.emit("plate_detected", {
                "plate": plate_text,
                "type": plate_type,
                "confidence": round(confidence, 2),
                "time": datetime.now().strftime("%H:%M:%S"),
                "is_alert": is_alert,
                "session_count": detection_logger.get_stats()["session_count"],
            })

        # Dibujar anotaciones en el frame para streaming
        annotated = draw_detections(frame, boxes, texts, watchlist_plates)
        with frame_lock:
            annotated_frame = annotated

        # Enviar stats periodicamente
        socketio.emit("stats_update", {
            "session_count": detection_logger.get_stats()["session_count"],
            "fps": round(camera.fps_actual, 1),
            "gps_status": "OK" if gps_tracker.has_fix else "Sin GPS",
        })

    # Limpiar al detener
    with frame_lock:
        annotated_frame = None


def generate_video_feed():
    """Generador MJPEG para streaming de video."""
    while detection_running:
        with frame_lock:
            frame = annotated_frame

        if frame is None:
            time.sleep(0.05)
            continue

        import cv2
        _, buffer = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
        frame_bytes = buffer.tobytes()

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" + frame_bytes + b"\r\n"
        )
        time.sleep(1.0 / current_settings["fps"])


# --- Rutas de pagina ---
@app.route("/")
def index():
    return render_template("index.html")


# --- API: Video feed ---
@app.route("/api/video_feed")
def video_feed():
    return Response(
        generate_video_feed(),
        mimetype="multipart/x-mixed-replace; boundary=frame",
    )


# --- API: Watchlist ---
@app.route("/api/watchlist", methods=["GET"])
def get_watchlist():
    return jsonify(alert_manager.get_watchlist())


@app.route("/api/watchlist", methods=["POST"])
def add_to_watchlist():
    data = request.get_json()
    plate = data.get("plate", "").strip()
    alias = data.get("alias", "").strip()

    if not plate:
        return jsonify({"error": "Matricula requerida"}), 400

    normalized = normalize_plate(plate)
    added = alert_manager.add_plate(normalized, alias)

    # Buscar en historico
    history = detection_logger.search_plate(normalized)

    return jsonify({
        "added": added,
        "plate": normalized,
        "history": history,
    })


@app.route("/api/watchlist", methods=["DELETE"])
def remove_from_watchlist():
    data = request.get_json()
    plate = data.get("plate", "").strip()
    normalized = normalize_plate(plate)
    removed = alert_manager.remove_plate(normalized)
    return jsonify({"removed": removed})


@app.route("/api/watchlist/export")
def export_watchlist():
    content = alert_manager.export_watchlist()
    return Response(
        content,
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=watchlist.json"},
    )


@app.route("/api/watchlist/import", methods=["POST"])
def import_watchlist():
    data = request.get_json()
    alert_manager.import_watchlist(data)
    return jsonify({"success": True})


# --- API: Historial ---
@app.route("/api/history/recent")
def history_recent():
    limit = request.args.get("limit", 50, type=int)
    detections = detection_logger.get_recent_detections(limit)
    return jsonify(detections)


@app.route("/api/history/search")
def history_search():
    plate = request.args.get("plate", "")
    if not plate:
        return jsonify([])
    normalized = normalize_plate(plate)
    results = detection_logger.search_plate(normalized)
    return jsonify(results)


@app.route("/api/history/files")
def history_files():
    files = detection_logger.get_csv_files()
    return jsonify(files)


@app.route("/api/history/export")
def history_export():
    """Exporta el CSV del dia actual."""
    stats = detection_logger.get_stats()
    csv_path = stats["today_file"]
    if os.path.exists(csv_path):
        return send_file(csv_path, as_attachment=True)
    return jsonify({"error": "No hay datos de hoy"}), 404


# --- API: Settings ---
@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        "fps": current_settings["fps"],
        "cooldown": current_settings["cooldown"],
        "log_all": current_settings["log_all"],
        "sound": current_settings["sound"],
        "camera_source": current_settings["camera_source"],
        "running": detection_running,
        "session_count": detection_logger.get_stats()["session_count"],
        "actual_fps": round(camera.fps_actual, 1) if detection_running else 0,
        "gps_status": "OK" if gps_tracker.has_fix else "No disponible",
    })


@app.route("/api/settings", methods=["POST"])
def update_settings():
    global log_all_plates
    data = request.get_json()

    if "fps" in data:
        current_settings["fps"] = max(3, min(15, int(data["fps"])))
    if "cooldown" in data:
        current_settings["cooldown"] = max(30, min(3600, int(data["cooldown"])))
        config.ALERT_COOLDOWN_SECONDS = current_settings["cooldown"]
    if "log_all" in data:
        current_settings["log_all"] = bool(data["log_all"])
        log_all_plates = current_settings["log_all"]
    if "sound" in data:
        current_settings["sound"] = bool(data["sound"])
    if "camera_source" in data:
        current_settings["camera_source"] = data["camera_source"]

    return jsonify({"success": True})


# --- WebSocket: Control de deteccion ---
@socketio.on("start_detection")
def handle_start():
    global detection_running, detection_thread

    if detection_running:
        return

    try:
        source = current_settings["camera_source"]
        if isinstance(source, str) and source.isdigit():
            source = int(source)
        camera.source = source
        camera.target_fps = current_settings["fps"]
        camera.start()
    except RuntimeError as e:
        socketio.emit("error", {"message": str(e)})
        return

    # Iniciar GPS
    gps_tracker.start()

    # Iniciar deteccion
    detection_running = True
    detection_thread = threading.Thread(target=detection_loop, daemon=True)
    detection_thread.start()

    socketio.emit("detection_started")


@socketio.on("stop_detection")
def handle_stop():
    global detection_running

    detection_running = False
    camera.stop()
    gps_tracker.stop()
    plate_cache.clear()

    socketio.emit("detection_stopped")


# --- Punto de entrada ---
if __name__ == "__main__":
    # Asegurar que existen los directorios de datos
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.ALERTS_DIR, exist_ok=True)
    os.makedirs(config.TRAINING_PLATES_DIR, exist_ok=True)

    print("=" * 50)
    print("  MatriScan - Lector de Matriculas Espanolas")
    print(f"  Servidor: http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    print("=" * 50)

    socketio.run(
        app,
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
        allow_unsafe_werkzeug=True,
    )

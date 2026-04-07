"""MatriScan - Servidor Flask. El OCR corre en el navegador (Tesseract.js)."""

import os
from datetime import datetime

from flask import Flask, render_template, jsonify, request, send_file
from flask_socketio import SocketIO

import config
from core.plate_validator import validate_plate, normalize_plate
from core.alert_manager import AlertManager
from core.detection_logger import DetectionLogger
from core.gps_tracker import GPSTracker
from training.collector import TrainingCollector
from training.trainer import PlateTrainer

# --- Inicializar Flask ---
app = Flask(__name__)
app.config["SECRET_KEY"] = config.SECRET_KEY
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# --- Componentes del sistema ---
alert_manager = AlertManager()
detection_logger = DetectionLogger()
gps_tracker = GPSTracker()
training_collector = TrainingCollector()
plate_trainer = PlateTrainer()

# --- Estado global ---
detection_running = False
log_all_plates = True
current_settings = {
    "fps": config.CAMERA_FPS,
    "cooldown": config.ALERT_COOLDOWN_SECONDS,
    "log_all": True,
    "sound": True,
}


# --- Pagina principal ---
@app.route("/")
def index():
    return render_template("index.html")


# --- WebSocket: el navegador envia matriculas detectadas ---
@socketio.on("start_detection")
def handle_start():
    global detection_running
    detection_running = True
    gps_tracker.start()
    socketio.emit("detection_started")


@socketio.on("stop_detection")
def handle_stop():
    global detection_running
    detection_running = False
    gps_tracker.stop()
    socketio.emit("detection_stopped")


@socketio.on("plate_found")
def handle_plate_found(data):
    """Recibe una matricula detectada por el OCR del navegador."""
    global log_all_plates

    plate = data.get("plate", "")
    normalized = data.get("normalized", "")
    plate_type = data.get("type", "unknown")
    confidence = data.get("confidence", 0)

    if not normalized:
        return

    # Validar formato
    validation = validate_plate(normalized)
    if validation is None:
        return

    plate_text = validation["plate"]
    plate_normalized = validation["normalized"]

    # GPS
    lat, lon = gps_tracker.get_coords_str()

    # Registrar en CSV
    if log_all_plates:
        detection_logger.log_detection(
            plate_text, plate_type, confidence, lat, lon
        )

    # Comprobar watchlist
    is_alert = False
    alert_data = alert_manager.check_and_alert(
        plate_normalized, location=gps_tracker.get_location(),
    )
    if alert_data:
        is_alert = True
        socketio.emit("alert_triggered", alert_data)

    # Notificar a todos los clientes
    socketio.emit("plate_detected", {
        "plate": plate_text,
        "type": plate_type,
        "confidence": round(confidence, 2),
        "time": datetime.now().strftime("%H:%M:%S"),
        "is_alert": is_alert,
        "alias": alert_data["alias"] if alert_data else "",
        "session_count": detection_logger.get_stats()["session_count"],
    })


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
    history = detection_logger.search_plate(normalized)
    return jsonify({"added": added, "plate": normalized, "history": history})


@app.route("/api/watchlist", methods=["DELETE"])
def remove_from_watchlist():
    data = request.get_json()
    plate = data.get("plate", "").strip()
    removed = alert_manager.remove_plate(normalize_plate(plate))
    return jsonify({"removed": removed})


@app.route("/api/watchlist/export")
def export_watchlist():
    from flask import Response
    return Response(
        alert_manager.export_watchlist(),
        mimetype="application/json",
        headers={"Content-Disposition": "attachment; filename=watchlist.json"},
    )


@app.route("/api/watchlist/import", methods=["POST"])
def import_watchlist():
    alert_manager.import_watchlist(request.get_json())
    return jsonify({"success": True})


# --- API: Historial ---
@app.route("/api/history/recent")
def history_recent():
    return jsonify(detection_logger.get_recent_detections(50))


@app.route("/api/history/search")
def history_search():
    plate = request.args.get("plate", "")
    if not plate:
        return jsonify([])
    return jsonify(detection_logger.search_plate(normalize_plate(plate)))


@app.route("/api/history/files")
def history_files():
    return jsonify(detection_logger.get_csv_files())


@app.route("/api/history/export")
def history_export():
    stats = detection_logger.get_stats()
    if os.path.exists(stats["today_file"]):
        return send_file(stats["today_file"], as_attachment=True)
    return jsonify({"error": "No hay datos de hoy"}), 404


# --- API: Settings ---
@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify({
        **current_settings,
        "running": detection_running,
        "session_count": detection_logger.get_stats()["session_count"],
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
    return jsonify({"success": True})


# --- API: Training ---
@app.route("/api/training/stats")
def training_stats():
    return jsonify(plate_trainer.get_training_stats())


@app.route("/api/training/learn", methods=["POST"])
def training_learn():
    return jsonify(plate_trainer.learn_corrections())


@app.route("/api/training/image/<filename>")
def training_image(filename):
    filepath = os.path.join(config.TRAINING_PLATES_DIR, filename)
    if os.path.exists(filepath):
        return send_file(filepath)
    return jsonify({"error": "No encontrada"}), 404


# --- Punto de entrada ---
if __name__ == "__main__":
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.ALERTS_DIR, exist_ok=True)
    os.makedirs(config.TRAINING_PLATES_DIR, exist_ok=True)

    print("=" * 50)
    print("  MatriScan - Lector de Matriculas Espanolas")
    print(f"  Servidor: http://{config.FLASK_HOST}:{config.FLASK_PORT}")
    print("  OCR: Tesseract.js (corre en el navegador)")
    print("=" * 50)

    socketio.run(
        app,
        host=config.FLASK_HOST,
        port=config.FLASK_PORT,
        debug=False,
        allow_unsafe_werkzeug=True,
    )

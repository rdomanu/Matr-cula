#!/bin/bash
# ==============================================
# MatriScan - Script de instalacion para Termux
# ==============================================
# Ejecutar en Termux con: bash setup_termux.sh
# ==============================================

echo "============================================="
echo "  MatriScan - Instalacion en Termux"
echo "============================================="

# Actualizar Termux
echo ""
echo "[1/6] Actualizando Termux..."
pkg update -y && pkg upgrade -y

# Instalar dependencias del sistema
echo ""
echo "[2/6] Instalando dependencias del sistema..."
pkg install -y python python-pip git
pkg install -y python-numpy
pkg install -y opencv-python
pkg install -y tesseract        # Motor OCR - funciona nativo en Termux
pkg install -y libjpeg-turbo libpng
pkg install -y termux-api       # Para GPS
pkg install -y pulseaudio       # Para sonido

# Instalar dependencias Python via pip
echo ""
echo "[3/6] Instalando dependencias Python..."
pip install --upgrade pip
pip install flask flask-socketio Pillow gevent gevent-websocket pytesseract

# Crear directorios de datos
echo ""
echo "[4/6] Creando estructura de directorios..."
mkdir -p data/training/plates
mkdir -p data/alerts
mkdir -p static/sounds

# Generar sonido de alerta
echo ""
echo "[5/6] Generando sonido de alerta..."
python -c "
import struct, wave, math
sample_rate = 44100
samples = []
for beep in range(3):
    for i in range(int(sample_rate * 0.15)):
        t = i / sample_rate
        v = 0.8 * math.sin(2 * math.pi * 880 * t)
        env = min(i / 200, 1.0) * min((int(sample_rate * 0.15) - i) / 200, 1.0)
        samples.append(int(v * env * 32767))
    samples.extend([0] * int(sample_rate * 0.1))
with wave.open('static/sounds/alert.wav', 'w') as f:
    f.setnchannels(1); f.setsampwidth(2); f.setframerate(sample_rate)
    f.writeframes(struct.pack('<' + 'h' * len(samples), *samples))
print('OK')
" 2>/dev/null || echo "(se generara despues)"

# Crear script de lanzamiento
echo ""
echo "[6/6] Creando script de lanzamiento..."
cat > launch.sh << 'LAUNCH'
#!/bin/bash
cd "$(dirname "$0")"
echo "==========================================="
echo "  MatriScan - Lector de Matriculas"
echo "==========================================="
echo "Iniciando servidor..."
python app.py &
SERVER_PID=$!
sleep 4
am start -a android.intent.action.VIEW -d "http://localhost:5000" 2>/dev/null || \
    termux-open-url "http://localhost:5000" 2>/dev/null || \
    echo "Abre: http://localhost:5000"
echo "MatriScan corriendo (PID: $SERVER_PID)"
echo "Para detener: Ctrl+C"
wait $SERVER_PID
LAUNCH
chmod +x launch.sh

echo ""
echo "============================================="
echo "  Instalacion completada!"
echo "============================================="
echo ""
echo "  Ejecuta: ./launch.sh"
echo "============================================="

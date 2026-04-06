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
echo "[1/7] Actualizando Termux..."
pkg update -y && pkg upgrade -y

# Instalar dependencias del sistema (incluyendo numpy y opencv precompilados)
echo ""
echo "[2/7] Instalando dependencias del sistema..."
pkg install -y python python-pip git
pkg install -y python-numpy    # numpy precompilado para Termux
pkg install -y opencv-python   # opencv precompilado para Termux
pkg install -y libjpeg-turbo libpng
pkg install -y termux-api      # Para GPS y notificaciones
pkg install -y pulseaudio      # Para reproducir sonidos de alerta

# NO usamos venv porque necesitamos acceder a los paquetes del sistema
# (numpy y opencv instalados con pkg no son visibles dentro de un venv)

# Instalar dependencias Python ligeras via pip
echo ""
echo "[3/7] Instalando dependencias Python..."
pip install --upgrade pip
pip install -r requirements.txt

# Instalar EasyOCR (el motor OCR)
echo ""
echo "[4/7] Instalando EasyOCR (esto tarda unos minutos)..."
pip install easyocr

# Crear directorios de datos
echo ""
echo "[5/7] Creando estructura de directorios..."
mkdir -p data/training/plates
mkdir -p data/alerts
mkdir -p static/sounds

# Generar sonido de alerta si no existe
echo ""
echo "[6/7] Generando sonido de alerta..."
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
print('Sonido generado OK')
" 2>/dev/null && echo "  OK" || echo "  (se generara despues)"

# Crear script de lanzamiento rapido
echo ""
echo "[7/7] Creando script de lanzamiento..."
cat > launch.sh << 'LAUNCH'
#!/bin/bash
# MatriScan - Lanzamiento rapido
cd "$(dirname "$0")"

echo "==========================================="
echo "  MatriScan - Lector de Matriculas"
echo "==========================================="

echo "Iniciando servidor..."
python app.py &
SERVER_PID=$!

# Esperar a que el servidor arranque
sleep 4

# Abrir navegador
echo "Abriendo navegador..."
am start -a android.intent.action.VIEW -d "http://localhost:5000" 2>/dev/null || \
    termux-open-url "http://localhost:5000" 2>/dev/null || \
    echo "Abre manualmente: http://localhost:5000"

echo ""
echo "MatriScan corriendo (PID: $SERVER_PID)"
echo "Para detener: Ctrl+C o 'kill $SERVER_PID'"
wait $SERVER_PID
LAUNCH
chmod +x launch.sh

echo ""
echo "============================================="
echo "  Instalacion completada!"
echo "============================================="
echo ""
echo "Para ejecutar:"
echo "  ./launch.sh"
echo ""
echo "Se abrira el navegador automaticamente en:"
echo "  http://localhost:5000"
echo "============================================="

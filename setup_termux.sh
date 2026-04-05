#!/bin/bash
# ==============================================
# MatriScan - Script de instalacion para Termux
# ==============================================
# Ejecutar en Termux con: bash setup_termux.sh
# ==============================================

set -e

echo "============================================="
echo "  MatriScan - Instalacion en Termux"
echo "============================================="

# Actualizar Termux
echo "[1/6] Actualizando Termux..."
pkg update -y && pkg upgrade -y

# Instalar dependencias del sistema
echo "[2/6] Instalando dependencias del sistema..."
pkg install -y python python-pip git
pkg install -y cmake clang libpng libjpeg-turbo
pkg install -y termux-api  # Para GPS y notificaciones
pkg install -y pulseaudio  # Para reproducir sonidos de alerta

# Crear entorno virtual
echo "[3/6] Creando entorno virtual Python..."
python -m venv venv
source venv/bin/activate

# Instalar dependencias Python
echo "[4/6] Instalando dependencias Python (esto puede tardar unos minutos)..."
pip install --upgrade pip
pip install -r requirements.txt

# Crear directorios de datos
echo "[5/6] Creando estructura de directorios..."
mkdir -p data/training/plates
mkdir -p data/alerts
mkdir -p static/sounds

# Crear script de lanzamiento rapido
echo "[6/6] Creando script de lanzamiento..."
cat > launch.sh << 'LAUNCH'
#!/bin/bash
# MatriScan - Lanzamiento rapido
cd "$(dirname "$0")"
source venv/bin/activate

echo "Iniciando MatriScan..."
python app.py &
SERVER_PID=$!

# Esperar a que el servidor arranque
sleep 3

# Abrir navegador
echo "Abriendo navegador..."
am start -a android.intent.action.VIEW -d "http://localhost:5000" 2>/dev/null || \
    termux-open-url "http://localhost:5000" 2>/dev/null || \
    echo "Abre manualmente: http://localhost:5000"

echo "MatriScan corriendo (PID: $SERVER_PID)"
echo "Para detener: kill $SERVER_PID"
wait $SERVER_PID
LAUNCH
chmod +x launch.sh

# Solicitar permisos de Termux
echo ""
echo "============================================="
echo "  Instalacion completada!"
echo "============================================="
echo ""
echo "IMPORTANTE: Necesitas conceder estos permisos:"
echo "  1. Camara: termux-setup-storage"
echo "  2. GPS: se pedira al usar termux-location"
echo ""
echo "Para ejecutar:"
echo "  ./launch.sh    (inicia todo + abre navegador)"
echo "  O manualmente: source venv/bin/activate && python app.py"
echo ""
echo "CONSEJO: Instala 'Termux:Widget' desde F-Droid para crear"
echo "un acceso directo en la pantalla de inicio."
echo "  1. Copia launch.sh a ~/.shortcuts/"
echo "  2. Anade widget de Termux:Widget a tu pantalla"
echo "============================================="

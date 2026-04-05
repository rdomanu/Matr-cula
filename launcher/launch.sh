#!/bin/bash
# MatriScan - Lanzamiento rapido para Termux
# Copia este archivo a ~/.shortcuts/ para usar con Termux:Widget

SCRIPT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$SCRIPT_DIR"

# Activar entorno virtual
source venv/bin/activate 2>/dev/null || {
    echo "Error: No se encontro el entorno virtual."
    echo "Ejecuta primero: bash setup_termux.sh"
    exit 1
}

# Matar instancia anterior si existe
pkill -f "python app.py" 2>/dev/null
sleep 1

echo "==========================================="
echo "  MatriScan - Lector de Matriculas"
echo "==========================================="

# Iniciar servidor en background
python app.py &
SERVER_PID=$!
echo "Servidor iniciado (PID: $SERVER_PID)"

# Esperar a que el servidor este listo
echo "Esperando al servidor..."
for i in $(seq 1 10); do
    if curl -s http://localhost:5000 > /dev/null 2>&1; then
        echo "Servidor listo!"
        break
    fi
    sleep 1
done

# Abrir navegador automaticamente
am start -a android.intent.action.VIEW -d "http://localhost:5000" 2>/dev/null || \
    termux-open-url "http://localhost:5000" 2>/dev/null || \
    echo "Abre tu navegador en: http://localhost:5000"

echo ""
echo "MatriScan corriendo. Para detener: kill $SERVER_PID"
echo "O presiona Ctrl+C"

# Mantener el proceso activo
wait $SERVER_PID

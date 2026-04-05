/**
 * MatriScan - Frontend JavaScript
 * Gestion de la interfaz web SPA con WebSocket para actualizaciones en tiempo real.
 */

const socket = io();
let isRunning = false;
let soundEnabled = true;

// --- Navegacion SPA ---
document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const section = tab.dataset.section;
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.add('hidden'));
        tab.classList.add('active');
        document.getElementById('section-' + section).classList.remove('hidden');

        // Cargar datos al cambiar de seccion
        if (section === 'watchlist') loadWatchlist();
        if (section === 'history') loadHistory();
        if (section === 'training') loadTraining();
        if (section === 'settings') loadSettings();
    });
});

// --- Dashboard: Start/Stop ---
document.getElementById('btn-start').addEventListener('click', () => {
    socket.emit('start_detection');
});

document.getElementById('btn-stop').addEventListener('click', () => {
    socket.emit('stop_detection');
});

socket.on('detection_started', () => {
    isRunning = true;
    document.getElementById('btn-start').classList.add('hidden');
    document.getElementById('btn-stop').classList.remove('hidden');
    document.getElementById('video-placeholder').classList.add('hidden');
    document.getElementById('video-feed').src = '/api/video_feed?' + Date.now();
});

socket.on('detection_stopped', () => {
    isRunning = false;
    document.getElementById('btn-stop').classList.add('hidden');
    document.getElementById('btn-start').classList.remove('hidden');
    document.getElementById('video-feed').src = '';
    document.getElementById('video-placeholder').classList.remove('hidden');
});

// --- Actualizaciones en tiempo real ---
socket.on('plate_detected', (data) => {
    updatePlatesList(data);
    document.getElementById('stat-count').textContent = data.session_count || '0';
});

socket.on('alert_triggered', (data) => {
    showAlert(data);
});

socket.on('stats_update', (data) => {
    document.getElementById('stat-count').textContent = data.session_count || '0';
    document.getElementById('stat-fps').textContent = data.fps || '0';
    document.getElementById('stat-gps').textContent = data.gps_status || '--';
});

// --- Lista de matriculas detectadas ---
function updatePlatesList(data) {
    const list = document.getElementById('plates-list');
    const emptyMsg = list.querySelector('.empty-msg');
    if (emptyMsg) emptyMsg.remove();

    const item = document.createElement('div');
    item.className = 'plate-item' + (data.is_alert ? ' is-alert' : '');
    item.innerHTML = `
        <span class="plate-text">${data.plate || ''}</span>
        <span class="plate-time">${data.time || ''}</span>
    `;

    list.insertBefore(item, list.firstChild);

    // Mantener maximo 50 items
    while (list.children.length > 50) {
        list.removeChild(list.lastChild);
    }
}

// --- Alerta visual y sonora ---
function showAlert(data) {
    const banner = document.getElementById('alert-banner');
    document.getElementById('alert-plate').textContent = data.plate_display || data.plate || '';
    document.getElementById('alert-alias').textContent = data.alias ? ' - ' + data.alias : '';
    banner.classList.remove('hidden');

    // Sonido
    if (soundEnabled) {
        const audio = document.getElementById('alert-sound');
        audio.currentTime = 0;
        audio.play().catch(() => {});
    }

    // Auto-ocultar despues de 10 segundos
    setTimeout(() => {
        banner.classList.add('hidden');
    }, 10000);
}

document.getElementById('alert-dismiss').addEventListener('click', () => {
    document.getElementById('alert-banner').classList.add('hidden');
});

// --- Watchlist ---
function loadWatchlist() {
    fetch('/api/watchlist')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('watchlist-items');
            if (Object.keys(data).length === 0) {
                container.innerHTML = '<p class="empty-msg">No hay matriculas en la lista de vigilancia</p>';
                return;
            }
            container.innerHTML = '';
            for (const [plate, info] of Object.entries(data)) {
                const item = document.createElement('div');
                item.className = 'wl-item';
                item.innerHTML = `
                    <div class="wl-item-info">
                        <div class="wl-item-plate">${info.plate_display || plate}</div>
                        <div class="wl-item-alias">${info.alias || ''}</div>
                    </div>
                    <button class="btn-remove" onclick="removePlate('${plate}')">X</button>
                `;
                container.appendChild(item);
            }
        })
        .catch(() => {});
}

document.getElementById('btn-add-plate').addEventListener('click', () => {
    const plate = document.getElementById('wl-plate').value.trim();
    const alias = document.getElementById('wl-alias').value.trim();
    if (!plate) return;

    fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate, alias })
    })
    .then(r => r.json())
    .then(data => {
        document.getElementById('wl-plate').value = '';
        document.getElementById('wl-alias').value = '';
        loadWatchlist();

        // Mostrar historial si se encontraron avistamientos previos
        const histResult = document.getElementById('wl-history-result');
        const histContent = document.getElementById('wl-history-content');
        if (data.history && data.history.length > 0) {
            histResult.classList.remove('hidden');
            histContent.innerHTML = data.history.map(h =>
                `<div>${h.fecha} ${h.hora} - GPS: ${h.latitud || '--'}, ${h.longitud || '--'}</div>`
            ).join('');
        } else {
            histResult.classList.remove('hidden');
            histContent.innerHTML = '<div>Esta matricula no se ha visto anteriormente.</div>';
        }
    })
    .catch(() => {});
});

function removePlate(plate) {
    fetch('/api/watchlist', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate })
    })
    .then(() => loadWatchlist())
    .catch(() => {});
}

// Exportar watchlist
document.getElementById('btn-export-wl').addEventListener('click', () => {
    fetch('/api/watchlist/export')
        .then(r => r.blob())
        .then(blob => {
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = 'watchlist.json';
            a.click();
            URL.revokeObjectURL(url);
        })
        .catch(() => {});
});

// Importar watchlist
document.getElementById('btn-import-wl').addEventListener('change', (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
        try {
            const data = JSON.parse(ev.target.result);
            fetch('/api/watchlist/import', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(data)
            })
            .then(() => loadWatchlist())
            .catch(() => {});
        } catch (err) {
            // JSON invalido
        }
    };
    reader.readAsText(file);
});

// --- Historial ---
function loadHistory() {
    fetch('/api/history/recent')
        .then(r => r.json())
        .then(data => {
            const tbody = document.getElementById('history-tbody');
            tbody.innerHTML = '';
            data.reverse().forEach(row => {
                const tr = document.createElement('tr');
                const lat = row.latitud || '--';
                const lon = row.longitud || '--';
                const loc = (lat !== '--' && lon !== '--') ? `${lat}, ${lon}` : '--';
                tr.innerHTML = `
                    <td>${row.fecha || ''}</td>
                    <td>${row.hora || ''}</td>
                    <td>${row.matricula || ''}</td>
                    <td>${row.tipo || ''}</td>
                    <td>${loc}</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(() => {});

    // Cargar lista de archivos CSV
    fetch('/api/history/files')
        .then(r => r.json())
        .then(files => {
            const container = document.getElementById('csv-files-list');
            container.innerHTML = '';
            files.forEach(f => {
                const item = document.createElement('div');
                item.className = 'csv-file-item';
                item.innerHTML = `
                    <span>${f.filename}</span>
                    <span>${f.size_kb} KB</span>
                `;
                container.appendChild(item);
            });
        })
        .catch(() => {});
}

document.getElementById('btn-search-hist').addEventListener('click', () => {
    const query = document.getElementById('hist-search').value.trim();
    if (!query) {
        loadHistory();
        return;
    }
    fetch('/api/history/search?plate=' + encodeURIComponent(query))
        .then(r => r.json())
        .then(data => {
            const tbody = document.getElementById('history-tbody');
            tbody.innerHTML = '';
            data.forEach(row => {
                const tr = document.createElement('tr');
                const loc = (row.latitud && row.longitud) ?
                    `${row.latitud}, ${row.longitud}` : '--';
                tr.innerHTML = `
                    <td>${row.fecha || ''}</td>
                    <td>${row.hora || ''}</td>
                    <td>${query.toUpperCase()}</td>
                    <td>--</td>
                    <td>${loc}</td>
                `;
                tbody.appendChild(tr);
            });
        })
        .catch(() => {});
});

document.getElementById('btn-export-csv').addEventListener('click', () => {
    window.open('/api/history/export', '_blank');
});

// --- Settings ---
function loadSettings() {
    fetch('/api/settings')
        .then(r => r.json())
        .then(data => {
            document.getElementById('set-fps').value = data.fps || 10;
            document.getElementById('set-fps-value').textContent = data.fps || 10;
            document.getElementById('set-cooldown').value = data.cooldown || 300;
            document.getElementById('set-log-all').checked = data.log_all !== false;
            document.getElementById('set-sound').checked = data.sound !== false;
            soundEnabled = data.sound !== false;

            const status = document.getElementById('system-status');
            status.innerHTML = `
                <div>Estado: ${data.running ? 'Activo' : 'Detenido'}</div>
                <div>Matriculas sesion: ${data.session_count || 0}</div>
                <div>FPS real: ${data.actual_fps || 0}</div>
                <div>GPS: ${data.gps_status || 'No disponible'}</div>
            `;
        })
        .catch(() => {});
}

document.getElementById('set-fps').addEventListener('input', (e) => {
    document.getElementById('set-fps-value').textContent = e.target.value;
});

document.getElementById('set-camera').addEventListener('change', (e) => {
    const urlInput = document.getElementById('set-camera-url');
    urlInput.classList.toggle('hidden', e.target.value !== 'ip');
});

document.getElementById('btn-save-settings').addEventListener('click', () => {
    const cameraSelect = document.getElementById('set-camera');
    let cameraSource = cameraSelect.value;
    if (cameraSource === 'ip') {
        cameraSource = document.getElementById('set-camera-url').value;
    }

    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            camera_source: cameraSource,
            fps: parseInt(document.getElementById('set-fps').value),
            cooldown: parseInt(document.getElementById('set-cooldown').value),
            log_all: document.getElementById('set-log-all').checked,
            sound: document.getElementById('set-sound').checked,
        })
    })
    .then(() => {
        soundEnabled = document.getElementById('set-sound').checked;
        loadSettings();
    })
    .catch(() => {});
});

// --- Training ---
let currentTrainingFilter = '';

const REASON_LABELS = {
    'ocr_failed': 'OCR fallo',
    'invalid_format': 'Formato invalido',
    'low_confidence': 'Baja confianza',
    'random_sample': 'Muestreo aleatorio',
    'manual': 'Manual',
};

function loadTraining() {
    // Stats
    fetch('/api/training/stats')
        .then(r => r.json())
        .then(data => {
            const byReason = data.by_reason || {};
            const reasonBreakdown = Object.entries(byReason)
                .map(([k, v]) => `${REASON_LABELS[k] || k}: ${v}`)
                .join(', ');
            document.getElementById('training-stats').innerHTML = `
                <strong>Dataset:</strong> ${data.total_images || 0} imagenes
                (${data.verified || 0} verificadas, ${data.unverified || 0} pendientes)<br>
                <strong>Reglas aprendidas:</strong> ${data.correction_rules || 0}
                | Max: ${data.max_images || 5000}<br>
                <span style="font-size:0.85em;color:var(--text-secondary)">${reasonBreakdown || 'Sin datos'}</span>
            `;
        })
        .catch(() => {});

    loadUnverified(currentTrainingFilter);
}

function loadUnverified(reasonFilter) {
    const url = '/api/training/unverified?limit=30' + (reasonFilter ? '&reason=' + reasonFilter : '');
    fetch(url)
        .then(r => r.json())
        .then(items => {
            const container = document.getElementById('corrections-list');
            if (items.length === 0) {
                container.innerHTML = '<p class="empty-msg">No hay lecturas pendientes de corregir</p>';
                return;
            }
            container.innerHTML = '';
            items.forEach(item => {
                const reason = item.reason || 'manual';
                const reasonLabel = REASON_LABELS[reason] || reason;
                const div = document.createElement('div');
                div.className = 'correction-item';
                div.id = 'item-' + item.id;
                div.innerHTML = `
                    <img src="/api/training/image/${item.filename}" alt="Matricula">
                    <div class="correction-info">
                        <div>
                            <span class="reason-badge reason-${reason}">${reasonLabel}</span>
                            OCR: <span class="correction-ocr">${item.ocr_text || '???'}</span>
                            <span style="color:var(--text-secondary);font-size:0.8em">(${(item.confidence * 100).toFixed(0)}%)</span>
                        </div>
                        <div class="correction-input">
                            <input type="text" id="correct-${item.id}" placeholder="Escribe matricula correcta" value="${item.ocr_text || ''}" maxlength="12">
                            <button class="btn btn-primary" onclick="submitCorrection('${item.id}')">OK</button>
                            <button class="btn-discard" onclick="discardImage('${item.id}')">Descartar</button>
                        </div>
                    </div>
                `;
                container.appendChild(div);
            });
        })
        .catch(() => {});
}

// Filter buttons
document.querySelectorAll('.btn-filter').forEach(btn => {
    btn.addEventListener('click', () => {
        document.querySelectorAll('.btn-filter').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        currentTrainingFilter = btn.dataset.filter;
        loadUnverified(currentTrainingFilter);
    });
});

function submitCorrection(imageId) {
    const input = document.getElementById('correct-' + imageId);
    const text = input.value.trim();
    if (!text) return;

    fetch('/api/training/correct', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_id: imageId, corrected_text: text })
    })
    .then(r => r.json())
    .then(() => {
        // Eliminar visualmente el item corregido
        const item = document.getElementById('item-' + imageId);
        if (item) item.remove();
        loadTraining();
    })
    .catch(() => {});
}

function discardImage(imageId) {
    fetch('/api/training/discard', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ image_id: imageId })
    })
    .then(r => r.json())
    .then(() => {
        const item = document.getElementById('item-' + imageId);
        if (item) item.remove();
    })
    .catch(() => {});
}

// Upload form
document.getElementById('upload-form').addEventListener('submit', (e) => {
    e.preventDefault();
    const fileInput = document.getElementById('upload-image');
    const plateText = document.getElementById('upload-plate-text').value.trim();
    const resultDiv = document.getElementById('upload-result');

    if (!fileInput.files.length || !plateText) {
        resultDiv.classList.remove('hidden');
        resultDiv.textContent = 'Selecciona una imagen y escribe el texto de la matricula.';
        return;
    }

    const formData = new FormData();
    formData.append('image', fileInput.files[0]);
    formData.append('plate_text', plateText);

    fetch('/api/training/upload', {
        method: 'POST',
        body: formData
    })
    .then(r => r.json())
    .then(data => {
        resultDiv.classList.remove('hidden');
        if (data.success) {
            resultDiv.textContent = 'Imagen guardada correctamente para entrenamiento.';
            fileInput.value = '';
            document.getElementById('upload-plate-text').value = '';
            loadTraining();
        } else {
            resultDiv.textContent = 'Error: ' + (data.error || 'desconocido');
        }
    })
    .catch(() => {
        resultDiv.classList.remove('hidden');
        resultDiv.textContent = 'Error de conexion.';
    });
});

// Learn button
document.getElementById('btn-learn').addEventListener('click', () => {
    const resultDiv = document.getElementById('learn-result');
    resultDiv.classList.remove('hidden');
    resultDiv.textContent = 'Analizando correcciones...';

    fetch('/api/training/learn', { method: 'POST' })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'success') {
                resultDiv.textContent = `Aprendizaje completado: ${data.rules_count} reglas generadas a partir de ${data.dataset_size} imagenes.`;
            } else {
                resultDiv.textContent = 'No hay suficientes datos verificados para aprender. Sube y corrige mas imagenes.';
            }
            loadTraining();
        })
        .catch(() => {
            resultDiv.textContent = 'Error al ejecutar aprendizaje.';
        });
});

// --- Inicializacion ---
socket.on('connect', () => {
    console.log('Conectado al servidor MatriScan');
});

socket.on('disconnect', () => {
    console.log('Desconectado del servidor');
});

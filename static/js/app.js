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

// --- Inicializacion ---
socket.on('connect', () => {
    console.log('Conectado al servidor MatriScan');
});

socket.on('disconnect', () => {
    console.log('Desconectado del servidor');
});

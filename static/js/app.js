/**
 * MatriScan - Frontend con OCR en el navegador (Tesseract.js)
 *
 * Todo el procesamiento OCR corre directamente en Chrome,
 * sin necesidad de enviar frames al servidor Python.
 * El servidor solo gestiona watchlist, historial y datos.
 */

const socket = io();
let isRunning = false;
let soundEnabled = true;
let cameraStream = null;
let ocrWorker = null;
let processing = false;

// --- Regex de matriculas espanolas ---
const MODERN_REGEX = /\b(\d{4})\s?([BCDFGHJKLMNPRSTVWXYZ]{3})\b/g;
const OLD_REGEX = /\b([A-Z]{1,2})\s?(\d{4})\s?([A-Z]{2})\b/g;

// Correcciones OCR comunes
const DIGIT_FIX = {'O':'0','o':'0','I':'1','i':'1','l':'1','S':'5','s':'5','Z':'2','z':'2','B':'8','G':'6','T':'7'};
const LETTER_FIX = {'0':'O','1':'I','2':'Z','5':'S','6':'G','8':'B'};
const MODERN_LETTERS = 'BCDFGHJKLMNPRSTVWXYZ';

function correctPlateText(raw) {
    let cleaned = raw.replace(/[^A-Za-z0-9]/g, '').toUpperCase();
    if (cleaned.length === 7) {
        // Intentar formato moderno: 4 digitos + 3 letras
        let digits = cleaned.slice(0, 4).split('').map(c => DIGIT_FIX[c] || c).join('');
        let letters = cleaned.slice(4).split('').map(c => LETTER_FIX[c] || c).join('');
        let corrected = digits + letters;
        if (/^\d{4}[A-Z]{3}$/.test(corrected)) {
            let validLetters = letters.split('').every(l => MODERN_LETTERS.includes(l));
            if (validLetters) return corrected;
        }
    }
    return cleaned;
}

function findPlates(text) {
    let plates = [];
    let seen = new Set();

    // Limpiar texto
    let cleaned = text.toUpperCase().replace(/[^A-Z0-9\s\n]/g, '');

    // Buscar fragmentos de 6-10 caracteres alfanumericos consecutivos
    let words = cleaned.split(/\s+/);

    // Intentar unir palabras consecutivas
    for (let i = 0; i < words.length; i++) {
        // Probar palabra sola
        let tests = [words[i]];
        // Probar union con siguiente
        if (i + 1 < words.length) tests.push(words[i] + words[i+1]);
        // Probar union con 2 siguientes
        if (i + 2 < words.length) tests.push(words[i] + words[i+1] + words[i+2]);

        for (let raw of tests) {
            let corrected = correctPlateText(raw);
            if (corrected.length < 5 || corrected.length > 10) continue;

            // Formato moderno: 4 digitos + 3 letras consonantes
            let modernMatch = corrected.match(/^(\d{4})([BCDFGHJKLMNPRSTVWXYZ]{3})$/);
            if (modernMatch && !seen.has(corrected)) {
                seen.add(corrected);
                plates.push({
                    plate: modernMatch[1] + ' ' + modernMatch[2],
                    normalized: corrected,
                    type: 'modern'
                });
            }

            // Formato antiguo: 1-2 letras + 4 digitos + 2 letras
            let oldMatch = corrected.match(/^([A-Z]{1,2})(\d{4})([A-Z]{2})$/);
            if (oldMatch && !seen.has(corrected)) {
                seen.add(corrected);
                plates.push({
                    plate: oldMatch[1] + ' ' + oldMatch[2] + ' ' + oldMatch[3],
                    normalized: corrected,
                    type: 'old_alpha'
                });
            }
        }
    }
    return plates;
}

// --- Inicializar Tesseract.js ---
async function initOCR() {
    try {
        document.getElementById('video-placeholder').textContent = 'Cargando motor OCR...';
        ocrWorker = await Tesseract.createWorker('eng', 1, {
            workerPath: 'https://cdn.jsdelivr.net/npm/tesseract.js@5/dist/worker.min.js',
            corePath: 'https://cdn.jsdelivr.net/npm/tesseract.js-core@5/tesseract-core-simd-lstm.wasm.js',
        });
        await ocrWorker.setParameters({
            tessedit_char_whitelist: '0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ',
            tessedit_pageseg_mode: '11', // Sparse text
        });
        console.log('Tesseract.js listo');
        document.getElementById('video-placeholder').textContent = 'Pulsa START para iniciar la camara';
    } catch (err) {
        console.error('Error cargando Tesseract.js:', err);
        document.getElementById('video-placeholder').textContent = 'Error cargando OCR. Recarga la pagina.';
    }
}

// --- Navegacion SPA ---
document.querySelectorAll('.nav-tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const section = tab.dataset.section;
        document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.section').forEach(s => s.classList.add('hidden'));
        tab.classList.add('active');
        document.getElementById('section-' + section).classList.remove('hidden');
        if (section === 'watchlist') loadWatchlist();
        if (section === 'history') loadHistory();
        if (section === 'training') loadTraining();
        if (section === 'settings') loadSettings();
    });
});

// --- Cache de deduplicacion ---
let recentPlates = {};
function isRecent(normalized) {
    let now = Date.now();
    if (recentPlates[normalized] && now - recentPlates[normalized] < 5000) return true;
    recentPlates[normalized] = now;
    // Limpiar antiguos
    for (let k in recentPlates) {
        if (now - recentPlates[k] > 30000) delete recentPlates[k];
    }
    return false;
}

// --- Dashboard: Start/Stop ---
document.getElementById('btn-start').addEventListener('click', async () => {
    if (!ocrWorker) {
        alert('Motor OCR aun cargando. Espera unos segundos.');
        return;
    }
    try {
        cameraStream = await navigator.mediaDevices.getUserMedia({
            video: { facingMode: 'environment', width: { ideal: 1280 }, height: { ideal: 720 } },
            audio: false
        });
        const video = document.getElementById('camera-video');
        video.srcObject = cameraStream;
        video.style.display = 'block';
        document.getElementById('video-placeholder').style.display = 'none';

        isRunning = true;
        document.getElementById('btn-start').classList.add('hidden');
        document.getElementById('btn-stop').classList.remove('hidden');

        socket.emit('start_detection');
        processFrames();

    } catch (err) {
        alert('No se puede acceder a la camara: ' + err.message);
    }
});

document.getElementById('btn-stop').addEventListener('click', () => {
    isRunning = false;
    socket.emit('stop_detection');
    stopCamera();
    document.getElementById('btn-stop').classList.add('hidden');
    document.getElementById('btn-start').classList.remove('hidden');
    document.getElementById('video-placeholder').style.display = 'flex';
    document.getElementById('video-placeholder').textContent = 'Pulsa START para iniciar';
});

function stopCamera() {
    if (cameraStream) { cameraStream.getTracks().forEach(t => t.stop()); cameraStream = null; }
}

// --- Bucle de procesamiento OCR en el navegador ---
async function processFrames() {
    const video = document.getElementById('camera-video');
    const canvas = document.getElementById('camera-canvas');
    const ctx = canvas.getContext('2d');
    let frameCount = 0;

    while (isRunning) {
        if (processing || video.videoWidth === 0) {
            await new Promise(r => setTimeout(r, 200));
            continue;
        }

        processing = true;
        frameCount++;

        try {
            // Capturar frame del video
            canvas.width = video.videoWidth;
            canvas.height = video.videoHeight;
            ctx.drawImage(video, 0, 0);

            // OCR con Tesseract.js (corre en el navegador)
            const { data } = await ocrWorker.recognize(canvas);

            // Buscar matriculas en el texto detectado
            let plates = findPlates(data.text);

            for (let plate of plates) {
                if (isRecent(plate.normalized)) continue;

                // Enviar al servidor para registrar
                socket.emit('plate_found', {
                    plate: plate.plate,
                    normalized: plate.normalized,
                    type: plate.type,
                    confidence: 0.8,
                });
            }

            // Actualizar stats
            document.getElementById('stat-count').textContent = frameCount;
            document.getElementById('stat-fps').textContent =
                (frameCount / ((Date.now() - (window._startTime || Date.now())) / 1000)).toFixed(1);
            if (!window._startTime) window._startTime = Date.now();

        } catch (err) {
            console.error('Error OCR:', err);
        }

        processing = false;

        // Esperar antes del siguiente frame (~2 fps)
        await new Promise(r => setTimeout(r, 500));
    }
}

// --- Eventos del servidor ---
socket.on('plate_detected', (data) => {
    updatePlatesList(data);
    document.getElementById('stat-count').textContent = data.session_count || '0';
});

socket.on('alert_triggered', (data) => {
    showAlert(data);
});

socket.on('stats_update', (data) => {
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
        <span class="plate-time">${data.time || new Date().toLocaleTimeString()}${data.alias ? ' - ' + data.alias : ''}</span>
    `;
    list.insertBefore(item, list.firstChild);
    while (list.children.length > 50) list.removeChild(list.lastChild);
}

// --- Alerta visual y sonora ---
function showAlert(data) {
    const banner = document.getElementById('alert-banner');
    document.getElementById('alert-plate').textContent = data.plate_display || data.plate || '';
    document.getElementById('alert-alias').textContent = data.alias ? ' - ' + data.alias : '';
    banner.classList.remove('hidden');

    if (soundEnabled) {
        const audio = document.getElementById('alert-sound');
        audio.currentTime = 0;
        audio.play().catch(() => {});
    }

    setTimeout(() => { banner.classList.add('hidden'); }, 10000);
}

document.getElementById('alert-dismiss').addEventListener('click', () => {
    document.getElementById('alert-banner').classList.add('hidden');
});

// --- Watchlist ---
function loadWatchlist() {
    fetch('/api/watchlist').then(r => r.json()).then(data => {
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
    }).catch(() => {});
}

document.getElementById('btn-add-plate').addEventListener('click', () => {
    const plate = document.getElementById('wl-plate').value.trim();
    const alias = document.getElementById('wl-alias').value.trim();
    if (!plate) return;

    fetch('/api/watchlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate, alias })
    }).then(r => r.json()).then(data => {
        document.getElementById('wl-plate').value = '';
        document.getElementById('wl-alias').value = '';
        loadWatchlist();

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
    }).catch(() => {});
});

function removePlate(plate) {
    fetch('/api/watchlist', {
        method: 'DELETE',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ plate })
    }).then(() => loadWatchlist()).catch(() => {});
}

document.getElementById('btn-export-wl').addEventListener('click', () => {
    fetch('/api/watchlist/export').then(r => r.blob()).then(blob => {
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = 'watchlist.json';
        a.click();
    }).catch(() => {});
});

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
            }).then(() => loadWatchlist());
        } catch (err) {}
    };
    reader.readAsText(file);
});

// --- Historial ---
function loadHistory() {
    fetch('/api/history/recent').then(r => r.json()).then(data => {
        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '';
        data.reverse().forEach(row => {
            const tr = document.createElement('tr');
            const loc = (row.latitud && row.longitud) ? `${row.latitud}, ${row.longitud}` : '--';
            tr.innerHTML = `<td>${row.fecha||''}</td><td>${row.hora||''}</td><td>${row.matricula||''}</td><td>${row.tipo||''}</td><td>${loc}</td>`;
            tbody.appendChild(tr);
        });
    }).catch(() => {});

    fetch('/api/history/files').then(r => r.json()).then(files => {
        const container = document.getElementById('csv-files-list');
        container.innerHTML = '';
        files.forEach(f => {
            container.innerHTML += `<div class="csv-file-item"><span>${f.filename}</span><span>${f.size_kb} KB</span></div>`;
        });
    }).catch(() => {});
}

document.getElementById('btn-search-hist').addEventListener('click', () => {
    const q = document.getElementById('hist-search').value.trim();
    if (!q) { loadHistory(); return; }
    fetch('/api/history/search?plate=' + encodeURIComponent(q)).then(r => r.json()).then(data => {
        const tbody = document.getElementById('history-tbody');
        tbody.innerHTML = '';
        data.forEach(row => {
            const tr = document.createElement('tr');
            const loc = (row.latitud && row.longitud) ? `${row.latitud}, ${row.longitud}` : '--';
            tr.innerHTML = `<td>${row.fecha||''}</td><td>${row.hora||''}</td><td>${q.toUpperCase()}</td><td>--</td><td>${loc}</td>`;
            tbody.appendChild(tr);
        });
    }).catch(() => {});
});

document.getElementById('btn-export-csv').addEventListener('click', () => {
    window.open('/api/history/export', '_blank');
});

// --- Settings ---
function loadSettings() {
    fetch('/api/settings').then(r => r.json()).then(data => {
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
            <div>GPS: ${data.gps_status || 'No disponible'}</div>
            <div>OCR: Tesseract.js (navegador)</div>
        `;
    }).catch(() => {});
}

document.getElementById('set-fps').addEventListener('input', (e) => {
    document.getElementById('set-fps-value').textContent = e.target.value;
});

document.getElementById('set-camera').addEventListener('change', (e) => {
    document.getElementById('set-camera-url').classList.toggle('hidden', e.target.value !== 'ip');
});

document.getElementById('btn-save-settings').addEventListener('click', () => {
    fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
            fps: parseInt(document.getElementById('set-fps').value),
            cooldown: parseInt(document.getElementById('set-cooldown').value),
            log_all: document.getElementById('set-log-all').checked,
            sound: document.getElementById('set-sound').checked,
        })
    }).then(() => {
        soundEnabled = document.getElementById('set-sound').checked;
        loadSettings();
    }).catch(() => {});
});

// --- Training (simplified) ---
let currentTrainingFilter = '';
const REASON_LABELS = {'ocr_failed':'OCR fallo','invalid_format':'Formato invalido','low_confidence':'Baja confianza','random_sample':'Muestreo','manual':'Manual','synthetic':'Sintetico'};

function loadTraining() {
    fetch('/api/training/stats').then(r => r.json()).then(data => {
        document.getElementById('training-stats').innerHTML = `
            <strong>Dataset:</strong> ${data.total_images||0} imagenes (${data.verified||0} verificadas)<br>
            <strong>Reglas:</strong> ${data.correction_rules||0}
        `;
    }).catch(() => {});
}

document.getElementById('btn-learn').addEventListener('click', () => {
    const r = document.getElementById('learn-result');
    r.classList.remove('hidden');
    r.textContent = 'Analizando...';
    fetch('/api/training/learn', {method:'POST'}).then(r=>r.json()).then(data => {
        document.getElementById('learn-result').textContent = data.status === 'success'
            ? `${data.rules_count} reglas generadas` : 'No hay suficientes datos';
    }).catch(() => {});
});

// --- Inicializacion ---
socket.on('connect', () => console.log('Conectado'));
socket.on('disconnect', () => console.log('Desconectado'));

// Cargar Tesseract.js al iniciar
initOCR();

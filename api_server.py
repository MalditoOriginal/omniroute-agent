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
                background: #0d1117;
            }
            #logs::-webkit-scrollbar-thumb {
                background: #30363d;
                border-radius: 5px;
            }
            .controls {
                display: flex;
                gap: 12px;
                position: sticky;
                bottom: 0;
                background: #0d1117;
                padding-top: 12px;
            }
            #msg-input {
                flex-grow: 1;
                padding: 10px 12px;
                background: #21262d;
                color: #ffffff;
                border: 1px solid #30363d;
                border-radius: 6px;
                font-size: 14px;
                font-family: inherit;
                transition: border-color 0.2s ease;
            }
            #msg-input:focus {
                border-color: #58a6ff;
                outline: none;
            }
            .btn {
                border-radius: 6px;
                padding: 10px 20px;
                cursor: pointer;
                border: none;
                font-weight: bold;
                font-size: 14px;
                font-family: inherit;
            }
            .btn-send {
                background: linear-gradient(to bottom, #238636, #2ea043);
                color: #ffffff;
            }
            .btn-clear {
                background: #21262d;
                border: 1px solid #30363d;
                color: #c9d1d9;
            }
        </style>
    </head>
    <body>
        <div class="status-bar">
            <div class="status-info"><span id="status-provider">Provider: --</span> | <span id="status-model">Model: --</span></div>
            <div class="status-mode"><span class="indicator-thinking" id="thinking-indicator"></span> THINKING MODE</div>
        </div>
        <div class="sidebar">
            <h3>Project Files</h3>
            <ul id="file-list" style="padding: 0; margin: 0;"></ul>
        </div>
        <div class="main-content">
            <h2>Multiagent Router PRO</h2>
            <div id="logs"></div>
            <div class="controls">
                <input type="text" id="msg-input" placeholder="Введите команду..." autocomplete="off">
                <button class="btn btn-send" onclick="send()">Send</button>
                <button class="btn btn-clear" onclick="clearLogs()">Clear</button>
            </div>
        </div>
        <script>
            let ws;

            function initWebSocket() {
                ws = new WebSocket("ws://" + location.host + "/ws");
                ws.onmessage = function(event) {
                    const text = event.data;
                    const logs = document.getElementById('logs');
                    logs.textContent += text + "\\n";
                    logs.scrollTo({ top: logs.scrollHeight, behavior: 'smooth' });
                };
            }

            function clearLogs() {
                document.getElementById('logs').textContent = '';
            }

            function send() {
                const msgInput = document.getElementById('msg-input');
                const msg = msgInput.value;
                if(!msg) return;
                ws.send(msg);
                msgInput.value = '';
            }

            document.addEventListener('DOMContentLoaded', function() {
                initWebSocket();
                loadFileList();

                const msgInput = document.getElementById('msg-input');
                msgInput.addEventListener('keydown', function(event) {
                    if (event.key === "Enter") {
                        event.preventDefault();
                        send();
                    }
                });
            });

            async function loadFileList() {
                try {
                    const response = await fetch('/files');
                    if (!response.ok) return;
                    const files = await response.json();
                    const fileList = document.getElementById('file-list');
                    if (!fileList) return;
                    fileList.innerHTML = '';
                    files.forEach(file => {
                        const li = document.createElement('li');
                        li.className = 'file-item';
                        li.textContent = file;
                        li.onclick = () => {
                            document.getElementById('msg-input').value = '/exec python ' + file;
                            send();
                        };
                        fileList.appendChild(li);
                    });
                } catch (error) {
                    console.error('Failed to load file list:', error);
                }
            }
        </script>
    </body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
async def get():
    return HTML

@app.get("/files")
async def get_py_files():
    files = [
        f for f in os.listdir(".")
        if f.endswith(".py")
        and not f.startswith("__pycache__")
        and not f.startswith(".")
        and f != "api_server.py"
    ]
    return files

class QueueStreamer:
    def __init__(self, q, original_stdout):
        self.q = q
        self.original_stdout = original_stdout
        
    def write(self, data):
        if data.strip():
            self.original_stdout.write(data)
            self.original_stdout.flush()
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
                    err_msg = f"CRITICAL ERROR in thread: {e}"
                    sys.stdout.write(err_msg)
                finally:
                    sys.stdout = original_stdout
                    q.put(None)

            thread = threading.Thread(target=run_agent_task)
            thread.start()

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

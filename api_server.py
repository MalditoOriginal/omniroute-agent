import asyncio
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
            body { font-family: sans-serif; background: #1e1e1e; color: #d4d4d4; margin: 20px; }
            #logs { white-space: pre-wrap; background: #000; color: #0f0; padding: 15px; height: 60vh; overflow-y: auto; border-radius: 5px; border: 1px solid #333; }
            input { width: 80%; padding: 10px; background: #333; color: #fff; border: none; border-radius: 5px; }
            button { padding: 10px 20px; background: #007acc; color: #fff; border: none; border-radius: 5px; cursor: pointer; }
        </style>
    </head>
    <body>
        <h2>🚀 Multiagent Router PRO (Web UI)</h2>
        <div id="logs"></div>
        <br>
        <input type="text" id="msg" autofocus placeholder="Введите запрос (например: /evolve ... или /consilium ...)">
        <button onclick="send()">Send</button>
        <script>
            const ws = new WebSocket("ws://localhost:8000/ws");
            const logs = document.getElementById('logs');
            ws.onmessage = function(event) { logs.textContent += event.data + "\\n"; logs.scrollTop = logs.scrollHeight; };
            function send() {
                const msg = document.getElementById('msg').value;
                if(!msg) return;
                ws.send(msg);
                logs.textContent += "\\n> " + msg + "\\n";
                document.getElementById('msg').value = '';
            }
            document.getElementById('msg').addEventListener('keypress', function (e) { if (e.key === 'Enter') send(); });
        </script>
    </body>
</html>
"""

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
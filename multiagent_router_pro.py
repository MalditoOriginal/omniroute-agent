#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multiagent_router_pro.py
Мультиагентная система маршрутизации на базе OmniRoute и Aider.
Версия: routing-rules + normalizer + LLM fallback router.
"""

import os
import sys
import json
import base64
import requests
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

SHARED_MEMORY_FILE = Path("shared_memory.json")
ROUTING_RULES_FILE = Path("routing_rules.json")
OMNIROUTE_BASE = "http://localhost:20128/v1"

AGENTS: Dict[str, Dict[str, str]] = {
    "terminal": {
        "name": "TerminalAgent",
        "combo": "TerminalAgent",
        "task": "...",
        "engine": "chat"  # вместо aider
    },
    "coding": {
        "name": "CodingAgent",
        "combo": "CodingAgent",
        "task": "Написание кода, рефакторинг, простой дев",
        "engine": "aider"
    },
    "media": {
        "name": "MediaAgent",
        "combo": "MediaAgent",
        "task": "Базовый мультимодальный анализ (Vision)",
        "engine": "chat"
    },
    "prod_coding": {
        "name": "ProdCodingAgent",
        "combo": "ProdCoding",
        "task": "Сложная архитектура, тяжелый рефакторинг",
        "engine": "aider"
    },
    "prod_stocks_text": {
        "name": "ProdStocksTextAgent",
        "combo": "ProdStocksText",
        "task": "Фундаментальный анализ акций, парсинг отчетов, логика",
        "engine": "chat"
    },
    "prod_stocks_vision": {
        "name": "ProdStocksVisionAgent",
        "combo": "ProdStocksVision",
        "task": "Анализ графиков TradingView, скан-копий PDF-отчетов",
        "engine": "chat"
    },
    "router": {
        "name": "RouterAgent",
        "combo": "RouterAgent",
        "task": "Дешевый fallback-роутер для сложных/неясных интентов",
        "engine": "chat"
    }
}

DEFAULT_ROUTING_RULES = {
    "stocks": [
        "акци", "дивиденд", "brent", "мосбирж", "насдак", "nasdaq", "отчетн",
        "фундаментальн", "тикер", "портфел", "stock", "stocks", "earnings"
    ],
    "vision": [
        "график", "скрин", "pdf", "паттерн", "картин", "изображен", "визуал",
        ".png", ".jpg", ".jpeg", ".webp", "image", "picture", "chart", "screenshot"
    ],
    "terminal": [
        "лог", "логи", "терминал", "команд", "bash", "powershell", "убить процесс", "ping",
        "logs", "log", "error log", "errors", "search logs", "find in logs",
        "stderr", "stdout", "traceback", "exception", "crash", "stack trace",
        "folder", "directory", "pwd", "current dir", "current directory", "папка", "директория"
    ],
    "coding": [
        "скрипт", "код", "исправ", "рефактор", "bug", "json", "парсер", "падае",
        "python", "javascript", "function", "refactor", "fix code", "router architecture"
    ],
    "complex_error": ["ошибк", "сбой", "падае", "error", "failed", "failure"],
    "complex_code": ["код", "скрипт", "code", "script", "router", "module"]
}

NORMALIZATION_MAP = {
    "erros": "errors",
    "eror": "error",
    "loggs": "logs",
    "foldr": "folder",
    "diractory": "directory",
    "whcihc": "which",
    "wich": "which",
    "analize": "analyze",
    "analyse": "analyze",
    "img": "image",
    "pic": "picture",
    "exception": "ошибка exception",
    "traceback": "ошибка traceback",
    "logs": "логи",
    "log": "лог",
    "folder": "папка",
    "directory": "директория"
}

class AgentOrchestrator:
    def __init__(self):
        self.memory = self._load_memory()
        self.routing_rules = self._load_routing_rules()
        self._check_environment()

    def _check_environment(self):
        if not os.getenv("OPENAI_API_KEY"):
            print("❌ [Критическая ошибка] Переменная окружения OPENAI_API_KEY не найдена.")
            sys.exit(1)

    def _load_memory(self) -> Dict[str, Any]:
        if SHARED_MEMORY_FILE.exists():
            try:
                with open(SHARED_MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ [Предупреждение] Файл памяти поврежден. Создается чистый контекст.")
        return {"logs": [], "errors": [], "scripts": [], "finance_insights": []}

    def _save_memory(self) -> None:
        try:
            with open(SHARED_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, ensure_ascii=False, indent=4)
        except IOError as e:
            print(f"❌ [Ошибка] Не удалось сохранить память: {e}")

    def _load_routing_rules(self) -> Dict[str, Any]:
        if ROUTING_RULES_FILE.exists():
            try:
                with open(ROUTING_RULES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError:
                print("⚠️ [Предупреждение] routing_rules.json поврежден. Используются дефолтные правила.")
        return DEFAULT_ROUTING_RULES

    def normalize_prompt(self, text: str) -> str:
        normalized = text.lower().strip()
        for src, dst in NORMALIZATION_MAP.items():
            normalized = normalized.replace(src, dst)
        return " ".join(normalized.split())

    def route_request(self, user_prompt: str) -> Tuple[str, str]:
        prompt_lower = self.normalize_prompt(user_prompt)

        if prompt_lower.startswith(("/prod", "!prod")):
            return "prod_coding", "Принудительный вызов тяжелого кодера (Cloud.ru)"
        if prompt_lower.startswith(("/stock", "!stock", "/stocks")):
            return "prod_stocks_text", "Принудительный вызов аналитика акций (Cloud.ru)"
        if prompt_lower.startswith(("/vision", "!vision")):
            return "prod_stocks_vision", "Принудительный вызов мультимодального аналитика (Cloud.ru)"

        if any(x in prompt_lower for x in self.routing_rules["complex_error"]) and any(x in prompt_lower for x in self.routing_rules["complex_code"]):
            return "complex_debug", "Сложный дебаг (Конвейер: Terminal -> Coding)"

        if any(w in prompt_lower for w in self.routing_rules["stocks"]) and any(w in prompt_lower for w in self.routing_rules["vision"]):
            return "prod_stocks_vision", "Анализ финансовой графики/документов"
        if any(w in prompt_lower for w in self.routing_rules["stocks"]):
            return "prod_stocks_text", "Текстовая финансовая аналитика"
        if any(w in prompt_lower for w in self.routing_rules["terminal"]):
            return "terminal", "Выполнение системных операций и логов"
        if any(w in prompt_lower for w in self.routing_rules["vision"]):
            return "media", "Анализ медиа/изображений"
        if any(w in prompt_lower for w in self.routing_rules["coding"]):
            return "coding", "Инженерия кода"

        llm_agent = self._llm_route_request(prompt_lower)
        if llm_agent in AGENTS:
            return llm_agent, f"Fallback-маршрутизация через RouterAgent -> {llm_agent}"

        return "coding", "Неопределенный интент -> Легкий CodingAgent (Free)"

    def _llm_route_request(self, prompt: str) -> Optional[str]:
        url = f"{OMNIROUTE_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": AGENTS["router"]["combo"],
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Ты классификатор интентов. Верни только один токен из списка: "
                        "terminal, coding, media, prod_coding, prod_stocks_text, prod_stocks_vision. "
                        "Без пояснений."
                    )
                },
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "temperature": 0
        }
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=20)
            if response.status_code != 200:
                return None
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
            text = text.split()[0].strip().lower()
            return text if text in AGENTS else None
        except Exception:
            return None

    def call_agent(self, agent_key: str, prompt: str) -> str:
        if agent_key not in AGENTS:
            return f"Ошибка: Агент '{agent_key}' не зарегистрирован."

        agent = AGENTS[agent_key]
        clean_prompt = prompt.replace("/prod", "").replace("/stock", "").replace("/vision", "").strip()

        print(f"\n[🤖 Роутер] Направляю задачу в -> {agent['name']} ({agent['combo']})")
        print(f"       [Движок]: {agent['engine'].upper()}")
        print(f"       [Цель]: {agent['task']}")
        print(f"       [Ожидание ответа от OmniRoute...]\n" + "-" * 60)

        if agent["engine"] == "chat":
            return self._execute_native_chat(agent["combo"], clean_prompt)
        return self._execute_aider(agent["combo"], clean_prompt)

    def _execute_native_chat(self, combo_name: str, prompt: str) -> str:
        url = f"{OMNIROUTE_BASE}/chat/completions"
        headers = {
            "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY')}",
            "Content-Type": "application/json"
        }

        image_path = None
        user_content: Any = prompt

        for word in prompt.split():
            clean_word = word.strip('"\' ,;()')
            if clean_word.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                p = Path(clean_word)
                if p.exists() and p.is_file():
                    image_path = clean_word
                    break

        if image_path:
            print(f"📸 [Vision] Обнаружен локальный файл изображения: {image_path}")
            try:
                with open(image_path, "rb") as img_file:
                    b64_data = base64.b64encode(img_file.read()).decode("utf-8")
                ext = Path(image_path).suffix.lower().replace(".", "")
                mime_type = f"image/{ext}" if ext in ["png", "jpeg", "jpg", "webp"] else "image/jpeg"
                clean_text = prompt.replace(image_path, "").strip() or "Проанализируй это изображение."
                user_content = [
                    {"type": "text", "text": clean_text},
                    {"type": "image_url", "image_url": {"url": f"data:{mime_type};base64,{b64_data}"}}
                ]
            except Exception as img_err:
                print(f"⚠️ [Ошибка чтения изображения]: {img_err}. Отправляю как текст.")
                user_content = prompt

        payload = {
            "model": combo_name,
            "messages": [
                {"role": "system", "content": "Ты — профессиональный аналитик и эксперт. Давай глубокие, развернутые ответы на русском языке."},
                {"role": "user", "content": user_content}
            ],
            "stream": True
        }

        full_response = ""
        try:
            response = requests.post(url, headers=headers, json=payload, stream=True, timeout=60)
            if response.status_code != 200:
                return f"❌ Ошибка API OmniRoute: Код {response.status_code}\n{response.text}"

            for line in response.iter_lines():
                if line:
                    decoded_line = line.decode("utf-8").strip()
                    if decoded_line.startswith("data: "):
                        decoded_line = decoded_line[6:]
                    if decoded_line == "[DONE]":
                        break
                    try:
                        chunk = json.loads(decoded_line)
                        content = chunk["choices"][0]["delta"].get("content", "")
                        if content:
                            print(content, end="", flush=True)
                            full_response += content
                    except Exception:
                        pass
            print("\n" + "-" * 60)
            self.memory["finance_insights"].append({"prompt": prompt, "insight": full_response})
            self._save_memory()
            return "✅ Аналитический отчет успешно сформирован."
        except Exception as e:
            print("\n" + "-" * 60)
            return f"🚨 Системная ошибка чат-движка: {e}"

    def _execute_aider(self, combo_name: str, prompt: str) -> str:
        os.environ["OPENAI_API_BASE"] = OMNIROUTE_BASE
        os.environ["OPENAI_BASE_URL"] = OMNIROUTE_BASE

        cmd = ["aider", "--model", f"openai/{combo_name}", "--message", prompt, "--no-git", "--exit"]
        try:
            result = subprocess.run(
                cmd,
                shell=False,
                timeout=300,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace"
            )
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            print(output)
            print("-" * 60)

            lowered = output.lower()
            if "no files shared" in lowered or "please share the router file" in lowered:
                return "⚠️ Aider не получил ни одного файла. Сначала нужно передать файл(ы) проекта в контекст."
            if result.returncode == 0:
                return "✅ Aider отработал без системной ошибки."
            return f"❌ Агент разработки завершился с кодом ошибки: {result.returncode}"
        except subprocess.TimeoutExpired:
            return "🚨 Ошибка: Превышен лимит времени выполнения (300 сек)."
        except Exception as e:
            return f"🚨 Системный сбой субпроцесса Aider: {e}"

    def handle_complex_debug(self, user_prompt: str) -> str:
        print(f"\n⚡ [Оркестратор] Запуск пайплайна отладки для: '{user_prompt[:50]}...'")
        term_out = self.call_agent("terminal", f"Найди причину сбоя/прочитай логи для: {user_prompt}")
        self.memory["errors"].append({"prompt": user_prompt, "analysis": term_out})
        self._save_memory()

        coding_out = self.call_agent("prod_coding", f"Опираясь на системный анализ:\n{term_out}\nИсправь код согласно запросу: {user_prompt}")
        self.memory["scripts"].append({"status": "fixed", "details": coding_out})
        self._save_memory()

        return f"=== ЭТАП 1 (Логи ОС) ===\n{term_out}\n\n=== ЭТАП 2 (Прод-Кодер) ===\n{coding_out}"


def main():
    app = AgentOrchestrator()
    print("\n🚀 Мультиагентное ядро управления PRO запущено!")
    print("=========================================================")
    print("Активные пулы маршрутизации:")
    for key, data in AGENTS.items():
        if key == "router":
            continue
        prefix = "💎 [PROD]" if "prod" in key else "🔹 [FREE]"
        engine_label = f"[{data['engine'].upper()}]"
        print(f" {prefix} {key.ljust(18)} -> {data['combo'].ljust(16)} {engine_label.ljust(8)} ({data['task']})")
    print("=========================================================")
    print("💡 Подсказка: Укажите путь к .png/.jpg прямо в запросе для активации Vision.")
    print("💡 Для выхода введите 'exit'.")

    while True:
        try:
            user_prompt = input("\n[Ввод] Ваш запрос: ").strip()
            if not user_prompt:
                continue
            if user_prompt.lower() in ["exit", "quit", "выход"]:
                print("👋 Работа завершена. Контекст сохранен в shared_memory.json.")
                break

            try:
                agent_key, task_desc = app.route_request(user_prompt)
                print(f"\n[Маршрутизация] {task_desc}")
                if agent_key == "complex_debug":
                    final_result = app.handle_complex_debug(user_prompt)
                else:
                    final_result = app.call_agent(agent_key, user_prompt)
                print("\n✅ [Итог операции]")
                print("-" * 60)
                print(final_result)
                print("-" * 60)
            except Exception as internal_err:
                print(f"\n❌ [Внутренняя ошибка ядра]: {internal_err}")
        except KeyboardInterrupt:
            print("\n👋 Принудительный выход.")
            break

if __name__ == "__main__":
    main()

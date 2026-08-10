#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multiagent_router_pro.py
Мультиагентная система маршрутизации на базе OmniRoute и Aider.
Версия: routing-rules + normalizer + LLM fallback router + Evolution Pipeline.
"""

import re
import os
import sys
import json
import time
import base64
import logging
import requests
import subprocess
from pathlib import Path
from typing import Dict, Any, Tuple, Optional

SHARED_MEMORY_FILE = Path("shared_memory.json")
ROUTING_RULES_FILE = Path("routing_rules.json")
EVOLUTION_MEMORY_FILE = Path("evolution_memory.json")
OMNIROUTE_BASE = "http://localhost:20128/v1"
LOG_FILE = Path("router.log")

AGENTS: Dict[str, Dict[str, str]] = {
    "terminal": {
        "name": "TerminalAgent",
        "combo": "TerminalAgent",
        "task": "...",
        "engine": "chat"
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
    },
    "architect": {
        "name": "ArchitectAgent",
        "combo": "ProdCoding",
        "task": "Анализ кода и написание строгого ТЗ для самомодификации",
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
        self.LOG_FILE = LOG_FILE
        self.logger = None
        self._setup_logging()
        self.memory = self._load_memory()
        self.routing_rules = self._load_routing_rules()
        self._check_environment()

    def _setup_logging(self):
        self.logger = logging.getLogger("RouterLogger")
        self.logger.setLevel(logging.DEBUG)
        
        if not self.logger.handlers:
            file_handler = logging.FileHandler(self.LOG_FILE, mode='a', encoding='utf-8')
            file_handler.setLevel(logging.DEBUG)
            formatter = logging.Formatter('%(asctime)s | %(levelname)-8s | %(message)s')
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
            
        self.logger.info("=== Инициализация AgentOrchestrator ===")

    def _check_environment(self):
        if not os.getenv("OPENAI_API_KEY"):
            msg = "Переменная окружения OPENAI_API_KEY не найдена."
            print(f"❌ [Критическая ошибка] {msg}")
            self.logger.critical(msg)
            sys.exit(1)
        else:
            self.logger.info("Переменная окружения OPENAI_API_KEY проверена.")

    def _load_memory(self) -> Dict[str, Any]:
        self.logger.debug(f"Загрузка shared memory из {SHARED_MEMORY_FILE}")
        if SHARED_MEMORY_FILE.exists():
            try:
                with open(SHARED_MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                msg = f"Файл памяти поврежден: {e}. Создается чистый контекст."
                print(f"⚠️ [Предупреждение] {msg}")
                self.logger.error(msg)
        return {"logs": [], "errors": [], "scripts": [], "finance_insights": []}

    def _save_memory(self) -> None:
        try:
            with open(SHARED_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.memory, f, ensure_ascii=False, indent=4)
        except IOError as e:
            print(f"❌ [Ошибка] Не удалось сохранить память: {e}")
            self.logger.error(f"Не удалось сохранить память: {e}")

    def _load_routing_rules(self) -> Dict[str, Any]:
        self.logger.debug(f"Загрузка routing rules из {ROUTING_RULES_FILE}")
        if ROUTING_RULES_FILE.exists():
            try:
                with open(ROUTING_RULES_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                msg = f"routing_rules.json поврежден: {e}. Используются дефолтные правила."
                print(f"⚠️ [Предупреждение] {msg}")
                self.logger.error(msg)
                return DEFAULT_ROUTING_RULES
        else:
            self.logger.warning("routing_rules.json не найден. Используются DEFAULT_ROUTING_RULES.")
            return DEFAULT_ROUTING_RULES

    def _load_evolution_memory(self) -> list:
        if EVOLUTION_MEMORY_FILE.exists():
            try:
                with open(EVOLUTION_MEMORY_FILE, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                self.logger.error(f"Ошибка загрузки evolution_memory.json: {e}")
        return []

    def _save_evolution_memory(self, memory: list) -> None:
        try:
            with open(EVOLUTION_MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(memory, f, ensure_ascii=False, indent=4)
        except Exception as e:
            self.logger.error(f"Ошибка сохранения evolution_memory.json: {e}")

    def normalize_prompt(self, text: str) -> str:
        self.logger.debug(f'Оригинальный интент: "{text}"')
        normalized = text.lower().strip()
        for src, dst in NORMALIZATION_MAP.items():
            normalized = normalized.replace(src, dst)
        normalized = " ".join(normalized.split())
        self.logger.debug(f'Нормализованный интент: "{normalized}"')
        return normalized

    def route_request(self, user_prompt: str) -> Tuple[str, str]:
        prompt_lower = self.normalize_prompt(user_prompt)

        # ПРЯМЫЕ КОМАНДЫ ИДУТ В САМОЕ НАЧАЛО (чтобы слова вроде "лог" не перехватили запрос)
        if prompt_lower.startswith(("/evolve", "!evolve")):
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: evolution | Совпадение: /evolve")
            return "evolution", "Автономная самомодификация кода (Консилиум)"
        if prompt_lower.startswith(("/prod", "!prod")):
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: prod_coding | Совпадение: /prod")
            return "prod_coding", "Принудительный вызов тяжелого кодера (Cloud.ru)"
        if prompt_lower.startswith(("/stock", "!stock", "/stocks")):
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: prod_stocks_text | Совпадение: /stock")
            return "prod_stocks_text", "Принудительный вызов аналитика акций (Cloud.ru)"
        if prompt_lower.startswith(("/vision", "!vision")):
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: prod_stocks_vision | Совпадение: /vision")
            return "prod_stocks_vision", "Принудительный вызов мультимодального аналитика (Cloud.ru)"

        if any(x in prompt_lower for x in self.routing_rules["complex_error"]) and any(x in prompt_lower for x in self.routing_rules["complex_code"]):
            matched_err = next((x for x in self.routing_rules["complex_error"] if x in prompt_lower), "")
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: complex_debug | Совпадение: {matched_err}")
            return "complex_debug", "Сложный дебаг (Конвейер: Terminal -> Coding)"

        if any(w in prompt_lower for w in self.routing_rules["stocks"]) and any(w in prompt_lower for w in self.routing_rules["vision"]):
            matched_w = next((w for w in self.routing_rules["stocks"] if w in prompt_lower), "")
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: prod_stocks_vision | Совпадение: {matched_w}")
            return "prod_stocks_vision", "Анализ финансовой графики/документов"
        if any(w in prompt_lower for w in self.routing_rules["stocks"]):
            matched_w = next((w for w in self.routing_rules["stocks"] if w in prompt_lower), "")
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: prod_stocks_text | Совпадение: {matched_w}")
            return "prod_stocks_text", "Текстовая финансовая аналитика"
        if any(w in prompt_lower for w in self.routing_rules["terminal"]):
            matched_w = next((w for w in self.routing_rules["terminal"] if w in prompt_lower), "")
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: terminal | Совпадение: {matched_w}")
            return "terminal", "Выполнение системных операций и логов"
        if any(w in prompt_lower for w in self.routing_rules["vision"]):
            matched_w = next((w for w in self.routing_rules["vision"] if w in prompt_lower), "")
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: media | Совпадение: {matched_w}")
            return "media", "Анализ медиа/изображений"
        if any(w in prompt_lower for w in self.routing_rules["coding"]):
            matched_w = next((w for w in self.routing_rules["coding"] if w in prompt_lower), "")
            self.logger.info(f"Найдено совпадение по правилам. Целевой агент: coding | Совпадение: {matched_w}")
            return "coding", "Инженерия кода"

        self.logger.info("Rule-based маршрутизация не удалась. Передача в LLM fallback.")
        llm_agent = self._llm_route_request(prompt_lower)
        if llm_agent in AGENTS:
            self.logger.info(f"LLM роутер выбрал агента: {llm_agent}")
            return llm_agent, f"Fallback-маршрутизация через RouterAgent -> {llm_agent}"

        self.logger.info("LLM fallback не сработал или вернул неизвестного агента. Используется дефолтный агент: coding")
        return "coding", "Неопределенный интент -> Легкий CodingAgent (Free)"

    def _llm_route_request(self, prompt: str) -> Optional[str]:
        self.logger.info(f'Запрос к LLM роутеру для интента: "{prompt}"')
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
                self.logger.error(f"Ошибка API LLM роутера. Код: {response.status_code}. Ответ: {response.text}")
                return None
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
            text = text.split()[0].strip().lower()
            return text if text in AGENTS else None
        except Exception as e:
            self.logger.error(f"Сбой при вызове LLM роутера. Ошибка: {str(e)}")
            return None

    def call_agent(self, agent_key: str, prompt: str, stream_output: bool = True) -> str:
        if agent_key not in AGENTS:
            msg = f"Ошибка: Агент '{agent_key}' не зарегистрирован."
            self.logger.error(msg)
            return msg

        agent = AGENTS[agent_key]
        clean_prompt = prompt.replace("/prod", "").replace("/stock", "").replace("/vision", "").strip()

        self.logger.info(f"Вызов агента {agent['name']} (Engine: {agent['engine']})")
        print(f"\n[🤖 Роутер] Направляю задачу в -> {agent['name']} ({agent['combo']})")
        print(f"       [Движок]: {agent['engine'].upper()}")
        print(f"       [Цель]: {agent['task']}")
        print(f"       [Ожидание ответа от OmniRoute...]\n" + "-" * 60)

        start_time = time.time()
        try:
            if agent["engine"] == "chat":
                response = self._execute_native_chat(agent["combo"], clean_prompt, stream_output)
            else:
                response = self._execute_aider(agent["combo"], clean_prompt)
            
            elapsed_time = time.time() - start_time
            self.logger.info(f"Агент {agent_key} вернул ответ за {elapsed_time:.2f} сек. Длина ответа: {len(response)} символов.")
            return response
        except Exception as e:
            elapsed_time = time.time() - start_time
            self.logger.error(f"Сбой при вызове агента {agent_key} за {elapsed_time:.2f} сек. Ошибка: {str(e)}")
            return f"🚨 Системная ошибка при вызове агента: {e}"

    def _execute_native_chat(self, combo_name: str, prompt: str, stream_output: bool = True) -> str:
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
            if not stream_output:
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
            "stream": stream_output
        }

        full_response = ""
        try:
            response = requests.post(url, headers=headers, json=payload, stream=stream_output, timeout=60)
            if response.status_code != 200:
                err_msg = f"❌ Ошибка API OmniRoute: Код {response.status_code}\n{response.text}"
                self.logger.error(f"Ошибка API OmniRoute (chat). Код: {response.status_code}")
                return err_msg

            if stream_output:
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
            else:
                data = response.json()
                full_response = data["choices"][0]["message"]["content"]

            self.memory["finance_insights"].append({"prompt": prompt, "insight": full_response})
            self._save_memory()
            
            if stream_output:
                return "✅ Аналитический отчет успешно сформирован."
            return full_response
        except Exception as e:
            if stream_output:
                print("\n" + "-" * 60)
            self.logger.error(f"Системная ошибка чат-движка: {e}")
            return f"🚨 Системная ошибка чат-движка: {e}"

    def _execute_aider(self, combo_name: str, prompt: str) -> str:
        os.environ["OPENAI_API_BASE"] = OMNIROUTE_BASE
        os.environ["OPENAI_BASE_URL"] = OMNIROUTE_BASE

        files = re.findall(r'\b[\w\-./\\]+\.(?:py|js|json|txt|md|html|css|java|c|cpp|ts)\b', prompt)
        
        cmd = [
            "aider",
            "--model", f"openai/{combo_name}",
            "--message", prompt,
            "--yes-always",                 
            "--no-stream",                  
            "--no-pretty",                  
            "--no-show-model-warnings",     
            "--no-check-update",            
            "--auto-commits",               
            "--dirty-commits",              
            "--edit-format", "whole",       
            "--exit"                        
        ]
        
        if files:
            cmd.extend(files)
            print(f"📁 [Aider] В контекст добавлены файлы: {', '.join(files)}")
        else:
            print("⚠️ [Aider] В запросе не указаны файлы. Aider будет работать как чат-бот.")

        try:
            print("⏳ [Aider] Агент начал работу (Git-контроль активен)...")
            
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"

            result = subprocess.run(
                cmd,
                shell=False,
                timeout=180, 
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,                
                stdin=subprocess.DEVNULL 
            )
            
            output = (result.stdout or "") + "\n" + (result.stderr or "")
            if len(output) > 4000:
                output = output[:4000] + "\n... [Вывод обрезан] ..."
                
            print(output.strip())
            print("-" * 60)

            if result.returncode == 0:
                if "commit" in output.lower():
                    return "✅ Aider успешно изменил код и сделал Git commit."
                return "✅ Aider успешно завершил работу над кодом."
            return f"❌ Агент разработки завершился с кодом ошибки: {result.returncode}"
            
        except subprocess.TimeoutExpired as e:
            out = (e.stdout or "") + "\n" + (e.stderr or "")
            print("🚨 [Таймаут] Aider завис. Лог до зависания:")
            print(out.strip() if out else "(Лог пуст)")
            self.logger.error("Таймаут субпроцесса Aider (180 сек).")
            return "🚨 Ошибка: Превышен лимит времени (180 сек)."
        except Exception as e:
            self.logger.error(f"Системный сбой субпроцесса Aider: {e}")
            return f"🚨 Системный сбой субпроцесса Aider: {e}"

    def handle_complex_debug(self, user_prompt: str) -> str:
        self.logger.info(f"Запущен процесс complex_debug. Входящий запрос: {user_prompt}")
        print(f"\n⚡ [Оркестратор] Запуск пайплайна отладки для: '{user_prompt[:50]}...'")
        
        term_out = self.call_agent("terminal", f"Найди причину сбоя/прочитай логи для: {user_prompt}", stream_output=False)
        self.memory["errors"].append({"prompt": user_prompt, "analysis": term_out})
        self._save_memory()

        coding_out = self.call_agent("prod_coding", f"Опираясь на системный анализ:\n{term_out}\nИсправь код согласно запросу: {user_prompt}", stream_output=False)
        self.memory["scripts"].append({"status": "fixed", "details": coding_out})
        self._save_memory()

        return f"=== ЭТАП 1 (Логи ОС) ===\n{term_out}\n\n=== ЭТАП 2 (Прод-Кодер) ===\n{coding_out}"
        
    def handle_evolution_pipeline(self, user_prompt: str) -> str:
        print(f"\n🧬 [ЭВОЛЮЦИЯ] Запуск пайплайна самомодификации...")
        
        files = re.findall(r'\b[\w\-./\\]+\.(?:py|js|json|txt|md|html|css|java|c|cpp|ts)\b', user_prompt)
        target_file = files[0] if files else "multiagent_router_pro.py"
        
        if not Path(target_file).exists():
            return f"❌ [Ошибка] Целевой файл {target_file} не найден. Эволюция отменена."

        # --- ЭТАП 1: АРХИТЕКТОР ---
        print(f"\n=== ЭТАП 1: АРХИТЕКТОР (Анализ {target_file}) ===")
        try:
            current_code = Path(target_file).read_text(encoding="utf-8")
        except Exception as e:
            return f"❌ Не удалось прочитать {target_file}: {e}"

        ev_memory = self._load_evolution_memory()
        ev_history = "\n\nПРЕДЫДУЩИЕ УСПЕШНЫЕ ЭВОЛЮЦИИ (не повторяй их):\n" + "\n".join([f"- {m}" for m in ev_memory[-5:]]) if ev_memory else ""

        arch_prompt = (
            f"Ты — Главный Архитектор ИИ-систем. Твоя задача — проанализировать код и запрос пользователя, "
            f"затем написать СТРОГОЕ ТЕХНИЧЕСКОЕ ЗАДАНИЕ для агента-кодера.\n"
            f"{ev_history}\n\n"
            f"ЗАПРОС ПОЛЬЗОВАТЕЛЯ:\n{user_prompt}\n\n"
            f"ТЕКУЩИЙ КОД ФАЙЛА {target_file}:\n```\n{current_code[:4000]}\n```\n\n"
            f"Напиши четкую инструкцию, какие именно функции добавить, изменить или удалить. "
            f"Не пиши сам код, пиши только пошаговое ТЗ для другого агента."
        )
        
        arch_result = self._execute_native_chat(AGENTS["architect"]["combo"], arch_prompt, stream_output=False)
        print(f"📝 [ТЗ Архитектора]:\n{arch_result[:1000]}...\n")
        
        # --- ЭТАП 2: КОДЕР (AIDER) ---
        print(f"=== ЭТАП 2: КОДЕР (Aider применяет ТЗ к {target_file}) ===")
        coder_prompt = f"Следуй этому техническому заданию строго. Файл для правки: {target_file}.\n\nТЗ ОТ АРХИТЕКТОРА:\n{arch_result}"
        coder_result = self._execute_aider(AGENTS["prod_coding"]["combo"], coder_prompt)
        print(f"🛠️ [Результат Кодера]: {coder_result}\n")

        # --- ЭТАП 3: ТЕСТИРОВЩИК (ПРОВЕРКА ИМПОРТА И СИНТАКСИСА) ---
        print(f"=== ЭТАП 3: ТЕСТИРОВЩИК (Проверка импорта и синтаксиса) ===")
        module_name = Path(target_file).stem
        test_cmd = [sys.executable, "-c", f"import {module_name}"]
        
        try:
            test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=30)
            if test_result.returncode == 0:
                print("✅ [Тестировщик] Импорт и синтаксис корректны. Код жив.")
                
                # Сохраняем успешную эволюцию в память
                ev_memory.append(f"Запрос: {user_prompt}\nТЗ: {arch_result[:200]}")
                self._save_evolution_memory(ev_memory)
                
                # --- ЭТАП 5: СИНХРОНИЗАТОР (GIT PUSH) ---
                print(f"=== ЭТАП 4: СИНХРОНИЗАТОР (Отправка в GitHub) ===")
                push_cmd = ["git", "push"]
                push_result = subprocess.run(push_cmd, capture_output=True, text=True, cwd=os.getcwd())
                
                if push_result.returncode == 0:
                    print("🚀 [Синхронизатор] Изменения успешно отправлены в GitHub.")
                    return "🧬 ЭВОЛЮЦИЯ УСПЕШНА: Код изменен, протестирован, закоммичен и отправлен в GitHub."
                else:
                    print("⚠️ [Синхронизатор] Не удалось сделать git push (возможно, нет интернета или ключей).")
                    print(f"Ошибка: {push_result.stderr}")
                    return "🧬 Эволюция успешна локально, но отправка в GitHub не удалась. Проверь ключи SSH/токены."

            else:
                # --- ЭТАП СТРАЖ (ОТКАТ) ---
                print("🚨 [Тестировщик] ОБНАРУЖЕНА ОШИБКА ИМПОРТА/СИНТАКСИСА!")
                print(f"Ошибка:\n{test_result.stderr}")
                print("⏪ [Страж] Запускаю откат последнего коммита (git reset --hard HEAD~1)...")
                
                rollback_cmd = ["git", "reset", "--hard", "HEAD~1"]
                rollback_result = subprocess.run(rollback_cmd, capture_output=True, text=True, cwd=os.getcwd())
                
                if rollback_result.returncode == 0:
                    return "🛡️ Эволюция провалена: Aider сломал код. Страж успешно откатил изменения к рабочему состоянию."
                else:
                    return f"🚨 КРИТИЧЕСКАЯ ОШИБКА: Код сломан, и откат не удался!\n{rollback_result.stderr}"
        except Exception as e:
            return f"🚨 Сбой на этапе тестирования: {e}"

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
                elif agent_key == "evolution":
                    final_result = app.handle_evolution_pipeline(user_prompt)
                else:
                    final_result = app.call_agent(agent_key, user_prompt)
                    
                print("\n✅ [Итог операции]")
                print("-" * 60)
                print(final_result)
                print("-" * 60)
            except Exception as internal_err:
                print(f"\n❌ [Внутренняя ошибка ядра]: {internal_err}")
                app.logger.error(f"Внутренняя ошибка ядра: {internal_err}", exc_info=True)
        except KeyboardInterrupt:
            print("\n👋 Принудительный выход.")
            break

if __name__ == "__main__":
    main()

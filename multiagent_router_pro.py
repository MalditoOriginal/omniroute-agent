#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
multiagent_router_pro.py
Мультиагентная система маршрутизации на базе OmniRoute и Aider.
Версия: routing-rules + normalizer + LLM fallback router + Evolution Pipeline + Semantic Cache.
"""

import re
import os
import sys
import json
import time
import base64
import logging
import datetime
import requests
import subprocess
import hashlib
import random
import uuid
import statistics
from pathlib import Path
from typing import Dict, Any, Tuple, Optional, List

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
    },
    "arbiter": {
        "name": "ArbiterAgent",
        "combo": "ProdCoding", # Самая умная модель для оценки
        "task": "Анализ предложений и выбор лучшего решения",
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

class CacheManager:
    """
    Semantic Cache Proxy (CacheManager)
    Intercepts LLM routing requests to reduce latency and token costs via exact and semantic matching.
    """
    def __init__(self, logger, cache_version: str = "v1", ttl_seconds: int = 86400, threshold: float = 0.95):
        self.logger = logger
        self.cache_version = cache_version
        self.ttl_seconds = ttl_seconds
        self.threshold = threshold
        
        # In-memory stores simulating Redis (Exact) and Vector Store (Semantic)
        self.exact_store: Dict[str, dict] = {}
        self.vector_store: List[dict] = []
        
        # Telemetry
        self.metrics = {
            "total_requests": 0,
            "exact_hits": 0,
            "semantic_hits": 0,
            "misses": 0,
            "tokens_saved": 0,
            "latencies_hit": [],
            "latencies_miss": []
        }
        
        # Guardrails regex for dynamic entities (dates, times, UUIDs, IDs)
        self.guardrails_regex = re.compile(
            r'\b(\d{4}-\d{2}-\d{2}|\d{2}:\d{2}(:\d{2})?|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}|order\s*#?\s*\d+)\b|'
            r'(сегодня|вчера|завтра|сейчас|today|yesterday|tomorrow|now)'
        )

    def _is_cacheable(self, text: str) -> bool:
        """Guardrails Filter: checks if the text contains dynamic context."""
        if self.guardrails_regex.search(text):
            return False
        return True

    def _get_embedding(self, text: str) -> List[float]:
        """
        Mock Embedding model.
        In production, replace with local 'bge-micro' or API 'text-embedding-3-small'.
        Generates a deterministic vector based on character frequencies for basic semantic similarity.
        """
        # Simple mock vector: 16 dimensions based on char counts
        vec = [0.0] * 16
        for char in text:
            vec[ord(char) % 16] += 1.0
        # Normalize vector
        norm = sum(v*v for v in vec)**0.5
        if norm == 0:
            return vec
        return [v / norm for v in vec]

    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """Calculates cosine similarity between two vectors."""
        dot_product = sum(v1 * v2 for v1, v2 in zip(vec1, vec2))
        norm1 = sum(v*v for v in vec1)**0.5
        norm2 = sum(v*v for v in vec2)**0.5
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return dot_product / (norm1 * norm2)

    def _get_cache_key(self, normalized_text: str, user_context: str = "global") -> str:
        """Generates composite key: [cache_version]:[user_context]:[hash]"""
        text_hash = hashlib.sha256(normalized_text.encode('utf-8')).hexdigest()
        return f"{self.cache_version}:{user_context}:{text_hash}"

    def lookup(self, normalized_text: str, user_context: str = "global") -> Optional[str]:
        """
        Two-level cache lookup.
        Returns the cached agent_key if found, else None.
        """
        start_time = time.time()
        self.metrics["total_requests"] += 1
        
        # Step 1: Guardrails Filter
        if not self._is_cacheable(normalized_text):
            self.logger.debug("CacheManager: Request non-cacheable (dynamic context). Pass-through.")
            self.metrics["misses"] += 1
            return None

        cache_key = self._get_cache_key(normalized_text, user_context)
        
        # Level 1: Exact Match (O(1))
        if cache_key in self.exact_store:
            entry = self.exact_store[cache_key]
            if time.time() - entry["timestamp"] < self.ttl_seconds:
                self.logger.info(f"CacheManager: EXACT HIT for key {cache_key[:20]}...")
                self.metrics["exact_hits"] += 1
                self.metrics["tokens_saved"] += len(normalized_text.split()) # Rough estimate
                self.metrics["latencies_hit"].append((time.time() - start_time) * 1000)
                return entry["agent_key"]
            else:
                # Expired
                del self.exact_store[cache_key]

        # Level 2: Semantic Match (KNN)
        query_vec = self._get_embedding(normalized_text)
        
        best_match_agent = None
        best_similarity = 0.0
        
        for entry in self.vector_store:
            if time.time() - entry["timestamp"] > self.ttl_seconds:
                continue # Skip expired
                
            # In a real Vector DB, this would be a KNN search filtered by user_context prefix
            if entry["user_context"] == user_context:
                sim = self._cosine_similarity(query_vec, entry["vector"])
                if sim > best_similarity:
                    best_similarity = sim
                    best_match_agent = entry["agent_key"]

        if best_match_agent and best_similarity >= self.threshold:
            self.logger.info(f"CacheManager: SEMANTIC HIT (Sim: {best_similarity:.4f})")
            self.metrics["semantic_hits"] += 1
            self.metrics["tokens_saved"] += len(normalized_text.split())
            self.metrics["latencies_hit"].append((time.time() - start_time) * 1000)
            
            # Write-back to exact cache for future O(1) hits
            self.exact_store[cache_key] = {
                "agent_key": best_match_agent,
                "timestamp": time.time()
            }
            return best_match_agent

        self.logger.debug("CacheManager: MISS. Passing to LLM Router.")
        self.metrics["misses"] += 1
        self.metrics["latencies_miss"].append((time.time() - start_time) * 1000)
        return None

    def write_back(self, normalized_text: str, agent_key: str, user_context: str = "global") -> None:
        """
        Writes successful routing results back to both cache levels.
        Does not cache errors or fallbacks.
        """
        if not self._is_cacheable(normalized_text):
            return
            
        if not agent_key or agent_key == "coding": # Assuming 'coding' is the fallback, do not cache
            self.logger.debug(f"CacheManager: Skipping write-back for fallback/error agent '{agent_key}'.")
            return

        cache_key = self._get_cache_key(normalized_text, user_context)
        timestamp = time.time()
        
        # Write to Exact Store
        self.exact_store[cache_key] = {
            "agent_key": agent_key,
            "timestamp": timestamp
        }
        
        # Write to Vector Store
        vec = self._get_embedding(normalized_text)
        self.vector_store.append({
            "vector": vec,
            "agent_key": agent_key,
            "user_context": user_context,
            "timestamp": timestamp,
            "exact_hash": cache_key # Link for potential invalidation
        })
        
        self.logger.debug(f"CacheManager: Write-back successful for agent '{agent_key}'.")

    def get_stats(self) -> Dict[str, Any]:
        """Returns collected telemetry metrics."""
        total = self.metrics["total_requests"]
        hit_ratio = (self.metrics["exact_hits"] + self.metrics["semantic_hits"]) / total * 100 if total > 0 else 0
        avg_latency_hit = statistics.mean(self.metrics["latencies_hit"]) if self.metrics["latencies_hit"] else 0
        avg_latency_miss = statistics.mean(self.metrics["latencies_miss"]) if self.metrics["latencies_miss"] else 0
        
        return {
            "total_requests": total,
            "exact_hits": self.metrics["exact_hits"],
            "semantic_hits": self.metrics["semantic_hits"],
            "misses": self.metrics["misses"],
            "hit_ratio_%": round(hit_ratio, 2),
            "tokens_saved_est": self.metrics["tokens_saved"],
            "avg_latency_hit_ms": round(avg_latency_hit, 2),
            "avg_latency_miss_ms": round(avg_latency_miss, 2)
        }

class AgentOrchestrator:
    def __init__(self):
        self.LOG_FILE = LOG_FILE
        self.logger = None
        self._setup_logging()
        self.memory = self._load_memory()
        self.routing_rules = self._load_routing_rules()
        self.cache_manager = CacheManager(self.logger)
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
        if prompt_lower.startswith(("/consilium", "!consilium")):
            return "consilium", "Мультиагентный консилиум (Генерация -> Оценка -> Кодинг)"
        if prompt_lower.startswith(("/exec", "!exec")):
            return "os_exec", "Выполнение команды в ОС (Sandboxed)"
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
        
        # --- CACHE PROXY INTERCEPTION ---
        cached_agent = self.cache_manager.lookup(prompt_lower)
        if cached_agent and cached_agent in AGENTS:
            self.logger.info(f"Cache HIT: Возвращен агент из кэша: {cached_agent}")
            return cached_agent, f"Cache Hit (Semantic/Exact) -> {cached_agent}"

        llm_agent = self._llm_route_request(prompt_lower)
        if llm_agent in AGENTS:
            self.logger.info(f"LLM роутер выбрал агента: {llm_agent}")
            # Write-back to cache on successful LLM response
            self.cache_manager.write_back(prompt_lower, llm_agent)
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
        import threading
        import queue
        
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
            if stream_output:
                # Используем поток и очередь для неблокирующего чтения и умного таймаута
                q = queue.Queue()
                
                def stream_reader():
                    try:
                        response = requests.post(url, headers=headers, json=payload, stream=True, timeout=(10, 120))
                        if response.status_code != 200:
                            q.put(f"❌ Ошибка API OmniRoute: Код {response.status_code}\n{response.text}")
                            return
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
                                        q.put(content)
                                except Exception:
                                    pass
                    except Exception as e:
                        q.put(e)
                    finally:
                        q.put(None) # Сигнал завершения потока

                t = threading.Thread(target=stream_reader, daemon=True)
                t.start()
                
                last_activity_time = time.time()
                IDLE_TIMEOUT = 120  # 2 минуты тишины = disconnect

                while True:
                    try:
                        item = q.get(timeout=1.0)
                        if item is None:
                            break # Поток завершен
                        if isinstance(item, Exception):
                            raise item
                        if isinstance(item, str) and item.startswith("❌ Ошибка API"):
                            return item
                            
                        print(item, end="", flush=True)
                        full_response += item
                        last_activity_time = time.time() # Обновляем время активности
                    except queue.Empty:
                        # Если вывода нет, проверяем Idle Timeout
                        if time.time() - last_activity_time > IDLE_TIMEOUT:
                            print("\n🚨 [Idle Timeout] Модель замолчала более чем на 2 минуты. Отключаюсь.")
                            return "🚨 Ошибка: Модель не отвечает (Idle Timeout)."
                
                print("\n" + "-" * 60)
                
                self.memory["finance_insights"].append({"prompt": prompt, "insight": full_response})
                self._save_memory()
                return full_response
                
            else:
                # Без стриминга - жесткий таймаут на весь запрос (10 минут)
                response = requests.post(url, headers=headers, json=payload, timeout=600)
                if response.status_code != 200:
                    err_msg = f"❌ Ошибка API OmniRoute: Код {response.status_code}\n{response.text}"
                    self.logger.error(f"Ошибка API OmniRoute (chat). Код: {response.status_code}")
                    return err_msg
                data = response.json()
                full_response = data["choices"][0]["message"]["content"]

                self.memory["finance_insights"].append({"prompt": prompt, "insight": full_response})
                self._save_memory()
                return full_response
                
        except Exception as e:
            if stream_output:
                print("\n" + "-" * 60)
            self.logger.error(f"Системная ошибка чат-движка: {e}")
            return f"🚨 Системная ошибка чат-движка: {e}"
            
    def _execute_aider(self, combo_name: str, prompt: str) -> str:
        import threading
        import queue
        
        os.environ["OPENAI_API_BASE"] = OMNIROUTE_BASE
        os.environ["OPENAI_BASE_URL"] = OMNIROUTE_BASE

        files = re.findall(r'\b[\w\-./\\]+\.(?:py|js|json|txt|md|html|css|java|c|cpp|ts)\b', prompt)
        
        cmd = [
            "aider",
            "--model", f"openai/{combo_name}",
            "--message", prompt,
            "--yes-always",                 
            # УБРАЛИ "--no-stream", чтобы видеть мысли модели
            "--no-pretty",                  
            "--no-show-model-warnings",     
            "--no-check-update",            
            "--auto-commits",               
            "--dirty-commits",              
            "--edit-format", "diff",
            "--exit"                        
        ]
        
        if files:
            cmd.extend(files)
            print(f"📁 [Aider] В контекст добавлены файлы: {', '.join(files)}")
        else:
            print("⚠️ [Aider] В запросе не указаны файлы. Aider будет работать как чат-бот.")

        try:
            print("⏳ [Aider] Агент начал работу (Стриминг + Idle Timer активен)...")
            
            env = os.environ.copy()
            env["PYTHONUTF8"] = "1"
            env["PYTHONIOENCODING"] = "utf-8"

            # Запускаем процесс
            process = subprocess.Popen(
                cmd,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,                
                stdin=subprocess.DEVNULL 
            )

            # Очередь для неблокирующего чтения
            q = queue.Queue()
            def enqueue_output():
                for line in iter(process.stdout.readline, ''):
                    q.put(line)
                process.stdout.close()

            # Поток для чтения вывода
            t = threading.Thread(target=enqueue_output, daemon=True)
            t.start()

            output = ""
            last_activity_time = time.time()
            IDLE_TIMEOUT = 120  # 2 минуты тишины = disconnect

            while True:
                try:
                    # Читаем строку с таймаутом 1 секунда
                    line = q.get(timeout=1.0)
                    if line:
                        output += line
                        print(line, end="")  # Стримим в консоль/UI
                        last_activity_time = time.time()  # Обновляем время активности
                except queue.Empty:
                    # Если вывода нет, проверяем, не завис ли процесс
                    if process.poll() is not None:
                        break  # Процесс завершился
                    
                    # Проверяем Idle Timeout
                    idle_time = time.time() - last_activity_time
                    if idle_time > IDLE_TIMEOUT:
                        process.kill()
                        print("\n🚨 [Idle Timeout] Aider замолчал более чем на 2 минуты. Похоже на disconnect.")
                        self.logger.error("Aider disconnect (Idle Timeout 120 сек).")
                        return "🚨 Ошибка: Disconnect (нет данных 120 сек)."
            
            process.wait()  # Дожидаемся завершения

            if len(output) > 4000:
                output = output[:4000] + "\n... [Вывод обрезан] ..."
                
            print("-" * 60)

            if process.returncode == 0:
                if "commit" in output.lower():
                    return "✅ Aider успешно изменил код и сделал Git commit."
                return "✅ Aider успешно завершил работу над кодом."
            return f"❌ Агент разработки завершился с кодом ошибки: {process.returncode}"
            
        except Exception as e:
            self.logger.error(f"Системный сбой субпроцесса Aider: {e}", exc_info=True)
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
        
    def handle_os_exec(self, user_prompt: str) -> str:
        """Путь 3: Безопасное выполнение команд ОС с таймаутом"""
        # Извлекаем команду (убираем /exec)
        command = re.sub(r'^(/exec|!exec)\s*', '', user_prompt, flags=re.IGNORECASE).strip()
        if not command:
            return "❌ [OS Exec] Команда не указана. Пример: /exec ping 8.8.8.8"
        
        print(f"\n⚙️ [OS Exec] Запуск команды: {command}")
        
        # Разбиваем команду для безопасности (без shell=True)
        try:
            # Используем shlex для корректного парсинга аргументов
            import shlex
            args = shlex.split(command)
            
            # Жесткий таймаут 15 секунд, чтобы агент не повесил систему
            result = subprocess.run(
                args, 
                capture_output=True, 
                text=True, 
                timeout=15, 
                encoding="utf-8", 
                errors="replace"
            )
            
            output = f"--- STDOUT ---\n{result.stdout}\n"
            if result.stderr:
                output += f"--- STDERR ---\n{result.stderr}\n"
            output += f"--- EXIT CODE: {result.returncode} ---"
            
            print(output)
            self.memory["logs"].append({"command": command, "output": output})
            self._save_memory()
            return f"✅ Команда выполнена. Код возврата: {result.returncode}"
            
        except subprocess.TimeoutExpired:
            return "🚨 [OS Exec] Превышен лимит времени (15 сек). Процесс убит."
        except Exception as e:
            return f"🚨 [OS Exec] Ошибка выполнения: {e}"

        # Branch Manager is active
        """Путь 4: Автономная самомодификация кода (Эволюция)"""
        print(f"\n🧬 [ЭВОЛЮЦИЯ] Запуск пайплайна самомодификации...")

        # Определяем целевой файл (по умолчанию multiagent_router_pro.py)
        target_file = "multiagent_router_pro.py"
        match = re.search(r'\b[\w\-./\\]+\.(?:py|js|json|txt|md|html|css|java|c|cpp|ts)\b', user_prompt)
        if match:
            target_file = match.group(0)

        ev_memory = self._load_evolution_memory()

        # --- ЭТАП 1: АРХИТЕКТОР ---
        print(f"=== ЭТАП 1: АРХИТЕКТОР (Анализ {target_file}) ===")
        arch_prompt = (
            f"Прочитай файл {target_file}. Проанализируй историю предыдущих эволюций: {ev_memory[-5:]}. "
            f"Напиши строгое ТЗ для Aider, чтобы выполнить задачу: {user_prompt}. "
            f"ТЗ должно содержать конкретные имена методов и ожидаемую логику."
        )
        arch_result = self._execute_native_chat(AGENTS["architect"]["combo"], arch_prompt, stream_output=False)
        print(f"📝 [ТЗ Архитектора]:\n{arch_result[:1000]}...\n")

        # --- ЭТАП 2: КОДЕР (AIDER) ---
        print(f"=== ЭТАП 2: КОДЕР (Aider применяет ТЗ к {target_file}) ===")

        # Branch Manager: создаём новую ветку перед запуском Aider
        try:
            self.create_evolution_branch()
        except Exception as branch_err:
            return f"🚨 Ошибка Branch Manager на этапе создания ветки: {branch_err}"

        coder_prompt = f"Следуй этому техническому заданию строго. Файл для правки: {target_file}.\n\nТЗ ОТ АРХИТЕКТОРА:\n{arch_result}"
        coder_result = self._execute_aider(AGENTS["prod_coding"]["combo"], coder_prompt)
        print(f"🛠️ [Результат Кодера]: {coder_result}\n")

        # ЗАЩИТА ОТ ПУСТЫШЕК: Если Aider завис или выдал ошибку, прерываем пайплайн
        if "🚨" in coder_result or "ошибка" in coder_result.lower():
            print("🚨 [Страж] Кодер не смог завершить работу (таймаут или сбой). Откат изменений...")
            subprocess.run(["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True)
            subprocess.run(["git", "checkout", "main"], capture_output=True, text=True) # Возвращаемся в main
            return "🧬 Эволюция прервана: Агент-Кодер не справился с задачей за отведенное время."

        # --- ЭТАП 3: ТЕСТИРОВЩИК (ЗАПУСК PYTEST) ---
        print(f"=== ЭТАП 3: ТЕСТИРОВЩИК (Запуск юнит-тестов pytest) ===")
        if not Path("test_core.py").exists():
            print("⚠️ [Тестировщик] Файл test_core.py не найден. Пропуск тестов.")
            return "🧬 Эволюция прошла без тестов (test_core.py отсутствует)."

        test_cmd = [sys.executable, "-m", "pytest", "test_core.py", "-v"]

        try:
            test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=60)
            print(test_result.stdout)
            if test_result.returncode == 0:
                print("✅ [Тестировщик] Все юнит-тесты пройдены. Код логически стабилен.")

                ev_memory.append(f"Запрос: {user_prompt}\nТЗ: {arch_result[:200]}")
                self._save_evolution_memory(ev_memory)
                
                # --- ЭТАП 3.5: ДОКУМЕНТАТОР (Обновление README и docstrings) ---
                print(f"=== ЭТАП 3.5: ДОКУМЕНТАТОР (Обновление документации) ===")
                doc_prompt = (
                    f"Обновите файл README.md, добавив описание новой функциональности: {user_prompt}. "
                    f"Также добавьте docstrings к измененным методам в файле {target_file}."
                )
                doc_result = self._execute_aider(AGENTS["prod_coding"]["combo"], doc_prompt)
                print(f"📝 [Результат Документатора]: {doc_result}\n")

                # --- ЭТАП 4: СИНХРОНИЗАТОР (Отправка ветки в GitHub) ---
                print(f"=== ЭТАП 4: СИНХРОНИЗАТОР (Отправка ветки evolve-feature в GitHub) ===")
                try:
                    self.push_evolution_branch()
                    print("🚀 [Синхронизатор] Ветка evolve-feature успешно отправлена в GitHub.")
                    
                    pr_link = self.generate_pr_link()
                    print(f"🔗 Pull Request для ветки evolve-feature: {pr_link}")
                    
                    # Возвращаемся в ветку main, чтобы продолжить работу
                    subprocess.run(["git", "checkout", "main"], capture_output=True, text=True)
                    
                    return f"🧬 ЭВОЛЮЦИЯ УСПЕШНА: Код изменен, тесты пройдены, ветка отправлена в GitHub.\nСсылка на PR: {pr_link}"
                except Exception as e:
                    print("⚠️ [Синхронизатор] Не удалось отправить ветку evolve-feature.")
                    return "🧬 Эволюция и тесты успешны локально, но отправка в GitHub не удалась."
            else:
                # --- ЭТАП СТРАЖ (ОТКАТ) ---
                print("🚨 [Тестировщик] ТЕСТЫ УПАЛИ! Aider сломал логику.")
                print("⏪ [Страж] Запускаю откат последнего коммита (git reset --hard HEAD~1)...")
                subprocess.run(["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True)
                subprocess.run(["git", "checkout", "main"], capture_output=True, text=True)
                return "🛡️ Эволюция провалена: Aider сломал тесты. Страж успешно откатил изменения."
        except subprocess.TimeoutExpired:
            print("⏪ [Страж] Тесты зависли. Откат последнего коммита...")
            subprocess.run(["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True)
            subprocess.run(["git", "checkout", "main"], capture_output=True, text=True)
            return "🛡️ Эволюция провалена: Тесты зависли. Страж откатил изменения."
        """Путь 4: Мультиагентный консилиум"""
        print(f"\n🧠 [КОНСИЛИУМ] Запуск дебатов агентов...")
        
        clean_prompt = user_prompt.replace("/consilium", "").replace("!consilium", "").strip()
        proposals = {}
        
        # ЭТАП 1: Генерация предложений разными агентами
        agents_to_consult = ["prod_coding", "coding", "architect"]
        
        for agent_key in agents_to_consult:
            agent = AGENTS[agent_key]
            print(f"\n💬 [{agent['name']}] генерирует предложение...")
            prompt = (
                f"Предложи архитектурное решение для следующей задачи. Не пиши готовый код, опиши только подход.\n"
                f"ЗАДАЧА: {clean_prompt}"
            )
            # Используем тихий режим
            response = self._execute_native_chat(agent["combo"], prompt, stream_output=False)
            proposals[agent_key] = response
            print(f"✅ [{agent['name']}] ответ готов.")
        
        # ЭТАП 2: Агент-Арбитр выбирает лучшее
        print(f"\n⚖️ [ArbiterAgent] Анализирует предложения и выбирает лучшее...")
        arbiter_prompt = "ПРЕДЛОЖЕНИЯ АГЕНТОВ:\n\n"
        for agent_key, prop in proposals.items():
            arbiter_prompt += f"ПРЕДЛОЖЕНИЕ ОТ {agent_key.upper()}:\n{prop}\n\n---\n\n"
        
        arbiter_prompt += """
Ты — Агент-Арбитр. Твоя задача — составить строгое и конкретное Техническое Задание (ТЗ) для агента-кодера (Aider).
На основе предложений агентов выше, напиши ТЗ в формате списка действий (Action Items).

ПРАВИЛА:
1. Запрещено писать введения, цели и абстрактные рассуждения.
2. Указывай конкретные имена функций, классов и переменных, которые нужно изменить.
3. Формат ТЗ:
   - ФАЙЛ: <имя файла>
   - ФУНКЦИЯ/КЛАСС: <имя>
   - ДЕЙСТВИЕ: <добавить/изменить/удалить>
   - КОД: <ожидаемая логика или snippet>
"""
        
        final_tz = self._execute_native_chat(AGENTS["arbiter"]["combo"], arbiter_prompt, stream_output=False)
        print(f"📝 [Финальное ТЗ Арбитра]:\n{final_tz[:500]}...\n")
        
        # ЭТАП 3: Кодер внедряет ТЗ
        print(f"=== ЭТАП 3: КОДЕР (Aider применяет ТЗ Арбитра) ===")
        coder_prompt = f"Следуй этому техническому заданию строго. Файл для правки: multiagent_router_pro.py.\n\nТЗ ОТ АРБИТРА:\n{final_tz}"
        coder_result = self._execute_aider(AGENTS["prod_coding"]["combo"], coder_prompt)
        
        return f"🧠 Консилиум завершен.\nУчаствовало агентов: {len(agents_to_consult)}.\nРезультат кодера: {coder_result}"
     
        # ===== Branch Manager (Новые методы) =====
    def create_evolution_branch(self):
        """Создание (или пересоздание) ветки evolve-feature перед запуском Aider."""
        self.logger.info("BranchManager: создание/пересоздание ветки evolve-feature")
        print("🌿 [BranchManager] Создание ветки evolve-feature...")
        try:
            subprocess.run(["git", "checkout", "-B", "evolve-feature"], check=True, capture_output=True, text=True)
            self.logger.info("BranchManager: ветка evolve-feature успешно создана/пересоздана")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"BranchManager: ошибка при создании ветки: {e.stderr.strip()}")
            raise

    def push_evolution_branch(self):
        """Отправляет текущую ветку в remote origin."""
        try:
            # Получаем имя текущей ветки
            current_branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
            current_branch = current_branch_result.stdout.strip()
            
            self.logger.info(f"Branch Manager: пуш ветки '{current_branch}' в origin")
            
            # Используем -u для установки upstream (обязательно для новых веток)
            result = subprocess.run(
                ["git", "push", "-u", "origin", current_branch],
                check=True, capture_output=True, text=True
            )
            self.logger.info(f"Branch Manager: ветка отправлена: {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Branch Manager: ошибка при пуше ветки: {e.stderr.strip()}")
            raise

    def generate_pr_link(self):
        """Генерация ссылки на Pull Request для GitHub/GitLab."""
        try:
            result = subprocess.run(["git", "config", "--get", "remote.origin.url"], capture_output=True, text=True, check=True)
            remote_url = result.stdout.strip()
        except Exception:
            return "Не удалось определить remote URL. Создайте Pull Request вручную."

        if not remote_url:
            return "Не удалось определить remote URL. Создайте Pull Request вручную."

        # Преобразуем SSH (git@...) в HTTPS
        if remote_url.startswith("git@"):
            https_url = remote_url.replace(":", "/").replace("git@", "https://").replace(".git", "")
        elif remote_url.startswith("https://"):
            https_url = remote_url.replace(".git", "")
        else:
            return f"Создайте Pull Request вручную: {remote_url}"

        # Определяем хостинг
        if "gitlab" in https_url.lower():
            return f"{https_url}/-/merge_requests/new?merge_request[source_branch]=evolve-feature"

        # По умолчанию считаем, что это GitHub
        return f"{https_url}/pull/new/evolve-feature"
        
    # ===== Branch Manager (Вспомогательные методы) =====
    def _create_git_branch(self, branch_name: str) -> bool:
        """Создает новую Git-ветку и переключается на нее."""
        try:
            result = subprocess.run(
                ["git", "checkout", "-b", branch_name],
                capture_output=True, text=True, timeout=30, cwd=os.getcwd()
            )
            if result.returncode == 0:
                self.logger.info(f"Branch Manager: ветка '{branch_name}' успешно создана и активирована.")
                print(f"🌿 [Branch Manager] Создана и активирована ветка: {branch_name}")
                return True
            self.logger.error(f"Branch Manager: ошибка создания ветки '{branch_name}': {result.stderr.strip()}")
            print(f"⚠️ [Branch Manager] git checkout -b завершился с ошибкой: {result.stderr.strip()}")
            return False
        except Exception as e:
            self.logger.error(f"Branch Manager: системный сбой при создании ветки '{branch_name}': {e}")
            print(f"🚨 [Branch Manager] Системный сбой: {e}")
            return False

    def push_evolution_branch(self, branch_name: str):
        """Отправляет текущую ветку в remote origin."""
        self.logger.info(f"Branch Manager: пуш ветки '{branch_name}' в origin")
        try:
            # Используем переменную текущей ветки
            current_branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
            current_branch = current_branch_result.stdout.strip()
            result = subprocess.run(
                ["git", "push", "origin", current_branch],
                check=True,
                capture_output=True,
                text=True
            )
            self.logger.info(f"Branch Manager: ветка отправлена: {result.stdout.strip()}")
        except subprocess.CalledProcessError as e:
            self.logger.error(f"Branch Manager: ошибка при пуше ветки: {e.stderr.strip()}")
            raise

    def generate_pr_link(self) -> str:
        """Генерирует динамическую ссылку на Pull Request для GitHub/GitLab."""
        try:
            result = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True, text=True, timeout=15, cwd=os.getcwd()
            )
            remote_url = result.stdout.strip()
        except Exception:
            return "Не удалось определить remote URL. Создайте Pull Request вручную."

        if not remote_url:
            return "Не удалось определить remote URL. Создайте Pull Request вручную."

        # Преобразуем SSH (git@...) в HTTPS
        if remote_url.startswith("git@"):
            https_url = remote_url.replace(":", "/").replace("git@", "https://").replace(".git", "")
        elif remote_url.startswith("https://"):
            https_url = remote_url.replace(".git", "")
        else:
            return f"Создайте Pull Request вручную: {remote_url}"

        # Определяем текущую ветку
        try:
            branch_result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True)
            current_branch = branch_result.stdout.strip()
        except Exception:
            current_branch = "evolve-feature"

        if "gitlab" in https_url.lower():
            return f"{https_url}/-/merge_requests/new?merge_request[source_branch]={current_branch}"

        return f"{https_url}/pull/new/{current_branch}"
     
    def handle_evolution_pipeline(self, user_prompt: str) -> str:
        # Branch Manager is active
        """Пайплайн автономной самомодификации с системой Branch Manager."""
        print(f"\n🧬 [ЭВОЛЮЦИЯ] Запуск пайплайна самомодификации...")

        files = re.findall(r'\b[\w\-./\\]+\.(?:py|js|json|txt|md|html|css|java|c|cpp|ts)\b', user_prompt)
        target_file = files[0] if files else "multiagent_router_pro.py"

        # --- ЭТАП 1: АРХИТЕКТОР ---
        print(f"=== ЭТАП 1: АРХИТЕКТОР (Анализ {target_file}) ===")
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

        # --- ЭТАП 1.5: BRANCH MANAGER (Создание изолированной ветки эволюции) ---
        print(f"=== ЭТАП 1.5: BRANCH MANAGER (Создание ветки эволюции) ===")
        try:
            orig_branch_result = subprocess.run(
                ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                capture_output=True, text=True, timeout=15, cwd=os.getcwd()
            )
            original_branch = orig_branch_result.stdout.strip() if orig_branch_result.returncode == 0 else "main"
        except Exception:
            original_branch = "main"
        
        branch_name = "evolve-feature"
        if not self._create_git_branch(branch_name):
            branch_name = f"evolve-feature-{datetime.datetime.now().strftime('%Y%m%d-%H%M%S')}"
            if not self._create_git_branch(branch_name):
                return "❌ [Ошибка] Branch Manager: не удалось создать ветку эволюции. Эволюция отменена."

        # --- ЭТАП 2: КОДЕР (AIDER) ---
        print(f"=== ЭТАП 2: КОДЕР (Aider применяет ТЗ к {target_file} в ветке '{branch_name}') ===")
        coder_prompt = f"Следуй этому техническому заданию строго. Файл для правки: {target_file}.\n\nТЗ ОТ АРХИТЕКТОРА:\n{arch_result}"
        coder_result = self._execute_aider(AGENTS["prod_coding"]["combo"], coder_prompt)
        print(f"🛠️ [Результат Кодера]: {coder_result}\n")

        # ЗАЩИТА ОТ ПУСТЫШЕК
        if "🚨" in coder_result or "ошибка" in coder_result.lower():
            print("🚨 [Страж] Кодер не смог завершить работу. Откат изменений...")
            subprocess.run(["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True)
            subprocess.run(["git", "checkout", original_branch], capture_output=True, text=True)
            return "🧬 Эволюция прервана: Агент-Кодер не справился с задачей."

        # --- ЭТАП 3: ТЕСТИРОВЩИК (ЗАПУСК PYTEST) ---
        print(f"=== ЭТАП 3: ТЕСТИРОВЩИК (Запуск юнит-тестов pytest) ===")
        if not Path("test_core.py").exists():
            print("⚠️ [Тестировщик] Файл test_core.py не найден. Пропуск тестов.")
            return "🧬 Эволюция прошла без тестов (test_core.py отсутствует)."

        test_cmd = [sys.executable, "-m", "pytest", "test_core.py", "-v"]

        try:
            test_result = subprocess.run(test_cmd, capture_output=True, text=True, timeout=60)
            print(test_result.stdout)
            
            if test_result.returncode == 0:
                print("✅ [Тестировщик] Все юнит-тесты пройдены. Код логически стабилен.")
                ev_memory.append(f"Запрос: {user_prompt}\nТЗ: {arch_result[:200]}")
                self._save_evolution_memory(ev_memory)

                # --- ЭТАП 4: СИНХРОНИЗАТОР (Push ветки в GitHub) ---
                print(f"=== ЭТАП 4: СИНХРОНИЗАТОР (Push ветки '{branch_name}' в origin) ===")
                try:
                    self.push_evolution_branch()
                    print(f"🚀 [Синхронизатор] Ветка '{branch_name}' успешно отправлена в GitHub.")
                    
                    pr_link = self.generate_pr_link()
                    print(f"🔗 Pull Request для эволюции создан: {pr_link}")
                    
                    subprocess.run(["git", "checkout", original_branch], capture_output=True, text=True)
                    
                    return f"🧬 ЭВОЛЮЦИЯ УСПЕШНА: Код изменен в ветке '{branch_name}', тесты пройдены.\nСсылка на PR: {pr_link}"
                except Exception as e:
                    print("⚠️ [Синхронизатор] Не удалось отправить ветку evolve-feature.")
                    return "🧬 Эволюция и тесты успешны локально, но отправка в GitHub не удалась."
            else:
                # --- ЭТАП СТРАЖ (ОТКАТ) ---
                print("🚨 [Тестировщик] ТЕСТЫ УПАЛИ! Aider сломал логику.")
                print(f"⏪ [Страж] Возврат в исходную ветку '{original_branch}' и удаление ветки '{branch_name}'...")
                
                subprocess.run(["git", "reset", "--hard", "HEAD"], capture_output=True, text=True, cwd=os.getcwd())
                subprocess.run(["git", "checkout", original_branch], capture_output=True, text=True, cwd=os.getcwd())
                subprocess.run(["git", "branch", "-D", branch_name], capture_output=True, text=True, cwd=os.getcwd())
                
                return "🛡️ Эволюция провалена: Aider сломал тесты. Страж успешно откатил изменения."
        except subprocess.TimeoutExpired:
            return "🚨 [Тестировщик] Превышен лимит времени выполнения тестов (60 сек)."
            
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
                elif agent_key == "consilium":  # НОВОЕ
                    final_result = app.handle_consilium_pipeline(user_prompt)
                elif agent_key == "os_exec":    # НОВОЕ
                    final_result = app.handle_os_exec(user_prompt)
                else:
                    final_result = app.call_agent(agent_key, user_prompt)
                    
                print("\n✅ [Итог операции]")
                # ... (остальное)
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
    current_time = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"Скрипт запущен: {current_time}")
    main()

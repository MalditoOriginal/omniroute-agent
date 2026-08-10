import os
import sys
import re
import pytest

# Подделываем переменную окружения, чтобы оркестратор не упал при инициализации
os.environ["OPENAI_API_KEY"] = "test_key_fake"

# Импортируем ядро
from multiagent_router_pro import AgentOrchestrator, AGENTS

# Фикстура pytest: создаем экземпляр оркестратора один раз для всех тестов
@pytest.fixture
def orchestrator():
    return AgentOrchestrator()

# ==========================================
# ТЕСТ 1: Проверка нормализатора текста
# ==========================================
def test_normalize_prompt(orchestrator):
    # Проверяем исправление опечаток
    assert orchestrator.normalize_prompt("erros in foldr") == "errors in папка"
    # Проверяем приведение к нижнему регистру и удаление лишних пробелов
    assert orchestrator.normalize_prompt("   FIX   CODE   ") == "fix code"
    # Проверяем замену синонимов
    assert orchestrator.normalize_prompt("show me the img") == "show me the image"

# ==========================================
# ТЕСТ 2: Проверка маршрутизации (Прямые команды)
# ==========================================
def test_route_direct_commands(orchestrator):
    agent_key, _ = orchestrator.route_request("/evolve добавь фичу")
    assert agent_key == "evolution"
    
    agent_key, _ = orchestrator.route_request("/consilium как лучше написать кэш")
    assert agent_key == "consilium"
    
    agent_key, _ = orchestrator.route_request("/exec ping 8.8.8.8")
    assert agent_key == "os_exec"

# ==========================================
# ТЕСТ 3: Проверка маршрутизации (Ключевые слова)
# ==========================================
def test_route_keywords(orchestrator):
    # Финансы + Картинки = Vision
    agent_key, _ = orchestrator.route_request("проанализируй график акций сбербанка")
    assert agent_key == "prod_stocks_vision"
    
    # Просто финансы
    agent_key, _ = orchestrator.route_request("какие дивиденды у лукойла")
    assert agent_key == "prod_stocks_text"
    
    # Код
    agent_key, _ = orchestrator.route_request("исправь баг в парсере")
    assert agent_key == "coding"
    
    # Медиа
    agent_key, _ = orchestrator.route_request("что на этом скрине?")
    assert agent_key == "media"

# ==========================================
# ТЕСТ 4: Проверка регулярки извлечения файлов
# ==========================================
def test_file_extraction_regex():
    # Та самая регулярка из _execute_aider и handle_evolution_pipeline
    regex = r'\b[\w\-./\\]+\.(?:py|js|json|txt|md|html|css|java|c|cpp|ts)\b'
    
    text1 = "исправь опечатку в скрипте main.py"
    assert re.findall(regex, text1) == ["main.py"]
    
    text2 = "обнови стили в index.css и логику в app.js"
    assert re.findall(regex, text2) == ["index.css", "app.js"]
    
    text3 = "просто текст без файлов"
    assert re.findall(regex, text3) == []

# ==========================================
# ТЕСТ 5: Проверка словаря AGENTS
# ==========================================
def test_agents_configuration():
    # Убеждаемся, что все ключевые агенты на месте
    required_agents = ["terminal", "coding", "media", "prod_coding", "router", "architect", "arbiter"]
    for agent in required_agents:
        assert agent in AGENTS
        assert "combo" in AGENTS[agent]
        assert "engine" in AGENTS[agent]
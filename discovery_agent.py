import subprocess
from pathlib import Path

class DiscoveryAgent:
    """
    Агент-Исследователь (Discovery Agent).
    Автономно сканирует локальную среду и GitHub для сбора базы знаний.
    """
    def __init__(self, github_repo_url: str = None, local_path: str = None):
        self.github_repo_url = github_repo_url
        self.local_path = local_path
        self.cache_dir = Path(".knowledge_cache")

    def discover_local_omniroute(self) -> str:
        """Читает .md, .yaml и .json файлы из локальной папки OmniRoute."""
        if not self.local_path or not Path(self.local_path).exists():
            return f"Локальный путь {self.local_path} не найден."
            
        print(f"🔍 [Discovery] Чтение локальной папки OmniRoute: {self.local_path}...")
        local_path = Path(self.local_path)
        knowledge = ""
        
        # Ищем файлы конфигов и инструкций
        for ext in ("*.md", "*.yaml", "*.yml", "*.json", "*.env"):
            for f in local_path.glob(ext):
                if f.stat().st_size < 50000: # Не читаем файлы больше 50KB
                    try:
                        knowledge += f"\n--- LOCAL FILE: {f.name} ---\n{f.read_text(encoding='utf-8')}\n"
                    except Exception:
                        pass
        return knowledge or "Локальные инструкции не найдены."

    def sync_github_repo(self) -> str:
        """Клонирует или обновляет (git pull) репозиторий OmniRoute для анализа."""
        if not self.github_repo_url:
            return "GitHub репозиторий не указан."
            
        print(f"🌐 [Discovery] Синхронизация с GitHub: {self.github_repo_url}...")
        self.cache_dir.mkdir(exist_ok=True)
        repo_name = self.github_repo_url.split("/")[-1].replace(".git", "")
        repo_path = self.cache_dir / repo_name

        try:
            if repo_path.exists():
                subprocess.run(["git", "-C", str(repo_path), "pull"], capture_output=True, text=True)
            else:
                subprocess.run(["git", "clone", "--depth", "1", self.github_repo_url, str(repo_path)], capture_output=True, text=True)
            
            # Собираем все .md файлы из скачанного репозитория
            knowledge = ""
            for f in repo_path.rglob("*.md"):
                if f.stat().st_size < 50000:
                    knowledge += f"\n--- GITHUB FILE: {f.relative_to(repo_path)} ---\n{f.read_text(encoding='utf-8')}\n"
            return knowledge or "В репозитории нет .md файлов."
        except Exception as e:
            print(f"⚠️ [Discovery] Ошибка синхронизации GitHub: {e}")
            return ""

    def gather_knowledge(self) -> str:
        """Собирает все знания воедино для передачи Архитектору."""
        local_knowledge = self.discover_local_omniroute()
        github_knowledge = self.sync_github_repo()
        
        combined = f"=== ЛОКАЛЬНЫЕ КОНФИГИ И ИНСТРУКЦИИ ===\n{local_knowledge}\n\n"
        combined += f"=== ОФИЦИАЛЬНАЯ ДОКУМЕНТАЦИЯ С GITHUB ===\n{github_knowledge}"
        
        # Обрезаем, чтобы не превысить лимит токенов LLM
        if len(combined) > 15000:
            combined = combined[:15000] + "\n... [База знаний обрезана]"
            
        return combined
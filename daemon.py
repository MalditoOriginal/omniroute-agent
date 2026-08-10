import time
import schedule
import subprocess
from multiagent_router_pro import AgentOrchestrator

daemon_app = AgentOrchestrator()

def auto_heal_job():
    print("\n🔍 [DAEMON] Запланированная проверка здоровья системы...")
    
    # 1. Читаем логи напрямую, чтобы гарантированно получить текст
    try:
        with open("router.log", "r", encoding="utf-8") as f:
            logs = f.read()
    except FileNotFoundError:
        print("⚠️ [DAEMON] Файл router.log не найден. Система здорова (нет логов).")
        return

    # 2. Если найдено слово CRITICAL, запускаем Консилиум
    if "CRITICAL" in logs:
        print("🚨 [DAEMON] Обнаружены критические ошибки! Запуск Консилиума для создания патча...")
        
        # Запускаем пайплайн Консилиума
        daemon_app.handle_consilium_pipeline(
            "/consilium Проанализируй критические ошибки в router.log и исправь их причину в multiagent_router_pro.py"
        )
        
        print("\n" + "="*50)
        print("⚠️ ВНИМАНИЕ: Демон создал локальный коммит с исправлением!")
        print("Пожалуйста, проверьте изменения в Git (git diff HEAD~1).")
        print("Введите команду: ")
        print("  'approve' - чтобы отправить фикс в GitHub")
        print("  'reject'  - чтобы откатить изменения (git reset --hard HEAD~1)")
        print("  'skip'    - чтобы отложить решение до следующего цикла")
        print("="*50)
        
        # Блокируем цикл демона, пока человек не примет решение
        while True:
            user_input = input("[DAEMON] Ожидание решения: ").strip().lower()
            if user_input == "approve":
                push_result = subprocess.run(["git", "push"], capture_output=True, text=True)
                if push_result.returncode == 0:
                    print("🚀 [DAEMON] Исправление успешно отправлено в GitHub.")
                else:
                    print(f"❌ [DAEMON] Ошибка пуша: {push_result.stderr}")
                break
            elif user_input == "reject":
                subprocess.run(["git", "reset", "--hard", "HEAD~1"], capture_output=True, text=True)
                print("⏪ [DAEMON] Изменения откатаны. Код возвращен к рабочему состоянию.")
                break
            elif user_input == "skip":
                print("⏸️ [DAEMON] Решение отложено. Патч остался в локальном Git.")
                break
            else:
                print("Неверная команда. Используйте approve, reject или skip.")
    else:
        print("✅ [DAEMON] Система здорова. Критических ошибок не найдено.")

# Настройка расписания (оставил 1 минуту для удобства тестов)
schedule.every(1).minutes.do(auto_heal_job)

if __name__ == "__main__":
    print("🤖 [SAFE DAEMON] Безопасный автономный демон запущен. Проверка каждую минуту.")
    print("💡 Демон НЕ будет отправлять изменения в GitHub без вашего подтверждения.")
    
    # Запускаем первую проверку сразу при старте, чтобы не ждать минуту
    auto_heal_job()
    
    while True:
        schedule.run_pending()
        time.sleep(1)
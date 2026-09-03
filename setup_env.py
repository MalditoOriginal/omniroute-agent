#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
setup_env.py
Скрипт для настройки переменных окружения (TELEGRAM_TOKEN).
Создает или перезаписывает файл .env в корневой директории проекта.
"""
import os
from pathlib import Path

def main():
    print("=== Настройка окружения для Telegram Бота ===")
    token = input("Введите TELEGRAM_TOKEN: ").strip()

    if not token:
        print("❌ [Ошибка] Токен не может быть пустым. Выполнение прервано.")
        return

    env_path = Path(".env")
    try:
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f"TELEGRAM_TOKEN={token}\n")
        print(f"✅ Токен успешно сохранен в файл: {env_path.resolve()}")
        print("ℹ️ Убедитесь, что файл .env добавлен в .gitignore.")
    except IOError as e:
        print(f"❌ [Ошибка] Не удалось записать файл .env: {e}")

if __name__ == "__main__":
    main()

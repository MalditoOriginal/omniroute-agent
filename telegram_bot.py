#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
telegram_bot.py
Асинхронный Telegram-бот для удаленного управления мультиагентным ядром.
Версия: 1.0
"""
import os
import asyncio
import logging
from dotenv import load_dotenv

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# Импортируем ядро системы
from multiagent_router_pro import AgentOrchestrator

# Настройка логирования
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("telegram_bot.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger(__name__)

# Инициализация ядра
try:
    orchestrator = AgentOrchestrator()
    logger.info("AgentOrchestrator успешно инициализирован для Telegram бота.")
except Exception as e:
    logger.critical(f"Критическая ошибка инициализации AgentOrchestrator: {e}")
    orchestrator = None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Приветствие и список команд."""
    user = update.effective_user
    if not orchestrator:
        await update.message.reply_text("⚠️ Ошибка: Ядро системы не инициализировано.")
        return

    welcome_text = (
        f"Привет, {user.mention_html()}! 👋\n\n"
        "Я бот управления мультиагентной системой. Доступные команды:\n\n"
        "/evolve <запрос> — запуск эволюционного пайплайна.\n"
        "/manage_omniroute <запрос> — управление настройками роутера.\n"
        "/consilium <запрос> — запуск режима консилиума.\n"
    )
    await update.message.reply_html(welcome_text)

async def evolve(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запуск эволюционного пайплайна."""
    if not orchestrator:
        await update.message.reply_text("⚠️ Ошибка: Ядро системы не инициализировано.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /evolve <запрос>")
        return

    user_prompt = " ".join(context.args)
    await update.message.reply_text(f"🧬 Запуск эволюции для: {user_prompt}...")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, orchestrator.handle_evolution_pipeline, user_prompt
        )
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Ошибка при выполнении /evolve: {e}", exc_info=True)
        await update.message.reply_text(f"🚨 Ошибка выполнения: {e}")

async def manage_omniroute(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Управление настройками OmniRoute."""
    if not orchestrator:
        await update.message.reply_text("⚠️ Ошибка: Ядро системы не инициализировано.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /manage_omniroute <запрос>")
        return

    user_prompt = " ".join(context.args)
    await update.message.reply_text(f"⚙️ Настройка OmniRoute: {user_prompt}...")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, orchestrator.handle_omniroute_management, user_prompt
        )
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Ошибка при выполнении /manage_omniroute: {e}", exc_info=True)
        await update.message.reply_text(f"🚨 Ошибка выполнения: {e}")

async def consilium(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Запуск режима консилиума."""
    if not orchestrator:
        await update.message.reply_text("⚠️ Ошибка: Ядро системы не инициализировано.")
        return

    if not context.args:
        await update.message.reply_text("Использование: /consilium <запрос>")
        return

    user_prompt = " ".join(context.args)
    await update.message.reply_text(f"🧠 Запуск консилиума для: {user_prompt}...")

    loop = asyncio.get_event_loop()
    try:
        result = await loop.run_in_executor(
            None, orchestrator.handle_consilium_pipeline, user_prompt
        )
        await update.message.reply_text(result)
    except Exception as e:
        logger.error(f"Ошибка при выполнении /consilium: {e}", exc_info=True)
        await update.message.reply_text(f"🚨 Ошибка выполнения: {e}")

def main() -> None:
    """Запуск бота."""
    load_dotenv()
    token = os.getenv("TELEGRAM_TOKEN")

    if not token:
        print("❌ [Критическая ошибка] Переменная окружения TELEGRAM_TOKEN не найдена.")
        print("Пожалуйста, задайте её в файле .env или через переменные окружения.")
        return

    application = Application.builder().token(token).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("evolve", evolve))
    application.add_handler(CommandHandler("manage_omniroute", manage_omniroute))
    application.add_handler(CommandHandler("consilium", consilium))

    logger.info("Telegram бот запущен. Нажмите Ctrl-C для остановки.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()

"""Точка входа бота.

Запуск:  python -m letovo_bot.bot.main

Требует переменные окружения: TELEGRAM_BOT_TOKEN (обязательно),
ANTHROPIC_API_KEY (опционально — включает уровень C проверки).
Банк должен быть собран заранее: python -m letovo_bot.data.build_bank
"""
from __future__ import annotations

import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties

from .. import config
from ..core import db
from .handlers import router, set_scheduler
from .scheduler import DailyScheduler


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    if not config.TELEGRAM_BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN не задан в окружении.")
    if not config.BANK_PATH.exists():
        raise SystemExit(f"Банк не найден: {config.BANK_PATH}. "
                         "Собери его: python -m letovo_bot.data.build_bank")

    # таблицы users/attempts создаются в том же файле банка
    conn = db.connect(config.BANK_PATH)
    db.init_db(conn)
    conn.close()

    bot = Bot(token=config.TELEGRAM_BOT_TOKEN,
              default=DefaultBotProperties(parse_mode="HTML"))
    dp = Dispatcher()
    dp.include_router(router)

    scheduler = DailyScheduler(bot)
    set_scheduler(scheduler)        # чтобы /settings перепланировал рассылку сразу
    scheduler.start()

    logging.info("Бот запущен. LLM-судья: %s", "вкл" if config.ENABLE_LLM_JUDGE else "выкл")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())

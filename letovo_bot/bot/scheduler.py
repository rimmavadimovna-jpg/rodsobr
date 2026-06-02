"""Ежедневная рассылка наборов через APScheduler.

Для каждого пользователя из таблицы users планируется ежедневная задача в его
часовом поясе на его daily_time. При изменении настроек задачи перепланируются.
"""
from __future__ import annotations

import asyncio
import sqlite3

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

from .. import config
from ..core import db
from .handlers import send_daily


class DailyScheduler:
    def __init__(self, bot) -> None:
        self.bot = bot
        self.scheduler = AsyncIOScheduler()

    def _conn(self) -> sqlite3.Connection:
        return db.connect(config.BANK_PATH)

    def reschedule_all(self) -> None:
        conn = self._conn()
        users = conn.execute("SELECT chat_id, timezone, daily_time FROM users").fetchall()
        conn.close()
        for u in users:
            self.schedule_user(u["chat_id"], u["timezone"], u["daily_time"])

    def schedule_user(self, chat_id: int, timezone: str, daily_time: str) -> None:
        hour, _, minute = (daily_time or config.DEFAULT_DAILY_TIME).partition(":")
        job_id = f"daily-{chat_id}"
        self.scheduler.add_job(
            self._fire, id=job_id, replace_existing=True,
            trigger=CronTrigger(hour=int(hour), minute=int(minute or 0),
                                timezone=timezone or config.DEFAULT_TIMEZONE),
            args=[chat_id],
        )

    async def _fire(self, chat_id: int) -> None:
        try:
            await send_daily(chat_id, self.bot)
        except Exception as e:  # pragma: no cover
            print(f"[scheduler] ошибка рассылки для {chat_id}: {e}")

    def start(self) -> None:
        self.reschedule_all()
        self.scheduler.start()

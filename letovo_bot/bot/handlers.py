"""Хендлеры aiogram 3.x: выдача заданий, приём ответов, обратная связь.

Задания с множеством номеров (зад. 2, 6, 11) — inline-кнопки-тогглы + «Готово».
Открытые ответы — текстом. После каждого ответа — мгновенная проверка
конвейером §3 с разбором по критериям, эталоном и ссылкой на правило.
"""
from __future__ import annotations

import sqlite3
from html import escape as _esc

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (CallbackQuery, InlineKeyboardButton,
                           InlineKeyboardMarkup, Message)

from .. import config
from ..core import assembler, checker, db
from ..core.llm import LLMJudge
from ..core.models import MULTI_NUMBER_TYPES, Task, TaskType, Verdict
from .session import SessionStore

router = Router()
store = SessionStore()
_judge = LLMJudge() if config.ENABLE_LLM_JUDGE else None

# Ссылка на планировщик (устанавливается из main.py), чтобы /settings
# перепланировал рассылку немедленно, без перезапуска бота.
_scheduler = None


def set_scheduler(scheduler) -> None:
    global _scheduler
    _scheduler = scheduler


def _conn() -> sqlite3.Connection:
    return db.connect(config.BANK_PATH)


# --------------------------------------------------------------------------- #
# Пользователи и попытки
# --------------------------------------------------------------------------- #
def ensure_user(conn: sqlite3.Connection, chat_id: int, name: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO users (chat_id, name, timezone, daily_time) VALUES (?,?,?,?)",
        (chat_id, name, config.DEFAULT_TIMEZONE, config.DEFAULT_DAILY_TIME),
    )
    conn.commit()


def save_attempt(conn: sqlite3.Connection, chat_id: int, task: Task, v: Verdict, answer: str) -> None:
    conn.execute(
        "INSERT INTO attempts (chat_id, task_id, task_type, topic, score, user_answer, needs_review)"
        " VALUES (?,?,?,?,?,?,?)",
        (chat_id, task.id, int(task.task_type), task.topic, v.score, answer, int(v.needs_review)),
    )
    conn.commit()


# --------------------------------------------------------------------------- #
# Рендеринг
# --------------------------------------------------------------------------- #
def render_task(task: Task, idx: int, total: int) -> str:
    """Текст задания для Telegram. Весь динамический материал из банка
    экранируется (_esc), чтобы символы < > & в данных не ломали HTML-разметку."""
    p = task.payload
    if int(task.task_type) == int(TaskType.QUIZ):
        head = f"<b>Вопрос {idx + 1}/{total}</b>  ({_esc(task.topic)})\n\n"
        body = _esc(p.get("stem", ""))
        opts = p.get("options") or []
        if opts:
            body += "\n\n" + "\n".join(f"  {i + 1}) {_esc(o)}" for i, o in enumerate(opts))
            body += "\n\n<i>Выберите вариант кнопкой ниже.</i>"
        else:
            body += "\n\n<i>Напишите ответ одним словом.</i>"
        return head + body
    head = (f"<b>Задание {idx + 1}/{total}</b> "
            f"(тип {int(task.task_type)}, тема: {_esc(task.topic)})\n")
    body = _esc(p.get("instruction", ""))
    tt = TaskType(task.task_type)
    if tt == TaskType.THIRD_EXTRA:
        rows = "\n".join(f"{i + 1}) " + ", ".join(_esc(w) for w in r["words"])
                         + f"  — {_esc(r['principle'])}"
                         for i, r in enumerate(p["rows"]))
        body += "\n\n" + rows + "\n\n<i>Ответ: по одному слову на строку, в верном написании.</i>"
    elif tt == TaskType.CONJUGATION:
        body += "\n\n" + ", ".join(_esc(f) for f in p["forms"])
    elif tt == TaskType.SCHEMES:
        body += "\n\n" + "\n".join(f"{i + 1}) {_esc(s)}" for i, s in enumerate(p["sentences"]))
        body += "\n\n<i>Схемы — по одной на строку.</i>"
    elif tt == TaskType.PUNCTUATION:
        body += "\n\n" + "\n".join(f"{i + 1}) {_esc(s)}" for i, s in enumerate(p["sentences"]))
    elif tt == TaskType.CONSTRUCT:
        words = "\n".join(f"• {_esc(w['word'])} — {_esc(w['meaning'])}" for w in p["words"])
        phr = "\n".join(f"• {_esc(x['phraseme'])} — {_esc(x['meaning'])}" for x in p["phrasemes"])
        body += f"\n\nСлова:\n{words}\n\nФразеологизмы:\n{phr}"
    elif tt == TaskType.GRAMMAR_FIX:
        body += "\n\n" + "\n".join(f"{i + 1}) {_esc(s)}" for i, s in enumerate(p["sentences"]))
        body += "\n\n<i>Отметьте ошибочные кнопками, затем пришлите исправленные варианты текстом.</i>"
    elif tt == TaskType.PHONETICS:
        body += f"\n\nПредложение: «{_esc(p['sentence'])}»\nЗвук: {_esc(p['sound'])}"
    elif tt == TaskType.SYNONYMS:
        body += f"\n\nКонтекст: «{_esc(p['context'])}»\n<i>5 синонимов через запятую.</i>"
    elif tt == TaskType.WORD_FORMATION:
        body += "\n\nСлова: " + ", ".join(_esc(w) for w in p["words"]) \
            + f"\nРазобрать: «{_esc(p['target_word'])}»"
    elif tt == TaskType.FOURTH_EXTRA:
        rows = "\n".join(f"{i + 1}) " + ", ".join(_esc(w) for w in r["words"])
                         for i, r in enumerate(p["rows"]))
        body += "\n\n" + rows + "\n\n<i>По одному лишнему слову на строку.</i>"
    elif tt == TaskType.TEXT_STATEMENTS:
        st = "\n".join(f"{i + 1}) {_esc(s)}" for i, s in enumerate(p["statements"]))
        body += f"\n\n{_esc(p['text'])}\n\nУтверждения:\n{st}"
    elif tt == TaskType.PHRASEME:
        body += f"\n\n{_esc(p['text'])}\n\nАбзац № {p['paragraph']}."
    return head + body


def numbers_keyboard(task: Task, selected: set[int]) -> InlineKeyboardMarkup:
    """Кнопки-тогглы для заданий с выбором номеров."""
    p = task.payload
    count = len(p.get("sentences") or p.get("statements") or [])
    buttons = []
    row = []
    for n in range(1, count + 1):
        mark = "✅" if n in selected else "▫️"
        row.append(InlineKeyboardButton(text=f"{mark}{n}", callback_data=f"tog:{task.id}:{n}"))
        if len(row) == 5:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)
    buttons.append([InlineKeyboardButton(text="Готово ✓", callback_data=f"done:{task.id}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def quiz_keyboard(task: Task) -> InlineKeyboardMarkup:
    """Кнопки одиночного выбора для теста (нажатие сразу отправляет ответ)."""
    opts = task.payload.get("options") or []
    rows = [[InlineKeyboardButton(text=str(i + 1), callback_data=f"qz:{task.id}:{i + 1}")]
            for i in range(len(opts))]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def render_verdict(v: Verdict) -> str:
    lines = [_esc(v.summary_line())]
    for c in v.criteria:
        icon = "✓" if c.passed else "✗"
        detail = f" — {_esc(c.detail)}" if c.detail else ""
        lines.append(f"  {icon} {_esc(c.name)}{detail}")
    if v.reference_answer:
        lines.append(f"\n<b>Образец:</b>\n{_esc(v.reference_answer)}")
    if v.rule_source:
        lines.append(f"\n📖 Правило: {_esc(v.rule_source)}")
    if v.needs_review:
        lines.append("\n<i>Часть ответа отправлена на ручную проверку преподавателю.</i>")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# Команды
# --------------------------------------------------------------------------- #
@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    conn = _conn()
    ensure_user(conn, message.chat.id, message.from_user.full_name if message.from_user else "")
    conn.close()
    await message.answer(
        "Привет! Я тренажёр по русскому языку — курс из 15 дней.\n"
        f"Каждый день в {config.DEFAULT_DAILY_TIME} ({config.DEFAULT_TIMEZONE}) я присылаю "
        "набор из 9 вопросов (по 1 из тем 1–3 и по 2 из тем 4–6) и сразу проверяю их "
        "с объяснением.\n\n"
        "Команды: /today — вопросы сейчас, /stats — прогресс, "
        "/theory «тема», /restart — начать курс заново, /settings."
    )


@router.message(Command("today"))
async def cmd_today(message: Message) -> None:
    await send_daily(message.chat.id, message.bot)


@router.message(Command("stats"))
async def cmd_stats(message: Message) -> None:
    conn = _conn()
    rows = conn.execute(
        "SELECT topic, COUNT(*) n, AVG(score) avg FROM attempts WHERE chat_id=? GROUP BY topic "
        "ORDER BY avg ASC", (message.chat.id,)).fetchall()
    conn.close()
    if not rows:
        await message.answer("Пока нет попыток. Нажми /today, чтобы начать.")
        return
    lines = ["<b>Прогресс по темам</b> (от слабых к сильным):"]
    for r in rows:
        lines.append(f"• {_esc(r['topic'])}: {r['avg']:.0%} (попыток: {r['n']})")
    await message.answer("\n".join(lines))


@router.message(Command("theory"))
async def cmd_theory(message: Message) -> None:
    topic = (message.text or "").partition(" ")[2].strip()
    conn = _conn()
    if topic:
        rows = conn.execute("SELECT DISTINCT topic, source FROM tasks WHERE topic LIKE ? AND verified=1",
                            (f"%{topic}%",)).fetchall()
    else:
        rows = conn.execute("SELECT DISTINCT topic, source FROM tasks WHERE verified=1").fetchall()
    conn.close()
    if not rows:
        await message.answer("Не нашёл такой темы. Доступные темы — в /stats.")
        return
    lines = ["<b>Правила и источники</b>:"]
    for r in rows:
        lines.append(f"• {_esc(r['topic'])}: {_esc(r['source'])}")
    await message.answer("\n".join(lines))


def _reschedule(conn: sqlite3.Connection, chat_id: int) -> None:
    """Перепланировать ежедневную рассылку пользователю по текущим настройкам."""
    if _scheduler is None:
        return
    row = conn.execute("SELECT timezone, daily_time FROM users WHERE chat_id=?",
                       (chat_id,)).fetchone()
    if row:
        _scheduler.schedule_user(chat_id, row["timezone"], row["daily_time"])


@router.message(Command("settings"))
async def cmd_settings(message: Message) -> None:
    parts = (message.text or "").split()
    conn = _conn()
    ensure_user(conn, message.chat.id, "")
    if len(parts) >= 3 and parts[1] == "time":
        conn.execute("UPDATE users SET daily_time=? WHERE chat_id=?", (parts[2], message.chat.id))
        conn.commit()
        _reschedule(conn, message.chat.id)
        await message.answer(f"Время рассылки обновлено: {parts[2]} (применено сразу).")
    elif len(parts) >= 3 and parts[1] == "tz":
        conn.execute("UPDATE users SET timezone=? WHERE chat_id=?", (parts[2], message.chat.id))
        conn.commit()
        _reschedule(conn, message.chat.id)
        await message.answer(f"Часовой пояс обновлён: {parts[2]} (применено сразу).")
    else:
        row = conn.execute("SELECT timezone, daily_time FROM users WHERE chat_id=?",
                           (message.chat.id,)).fetchone()
        tz = row["timezone"] if row else config.DEFAULT_TIMEZONE
        tm = row["daily_time"] if row else config.DEFAULT_DAILY_TIME
        await message.answer(
            f"Часовой пояс: {tz}\nВремя рассылки: {tm}\n\n"
            "Изменить: <code>/settings time 10:00</code> или <code>/settings tz Europe/Moscow</code>")
    conn.close()


# --------------------------------------------------------------------------- #
# Выдача набора и приём ответов
# --------------------------------------------------------------------------- #
async def send_daily(chat_id: int, bot) -> None:
    conn = _conn()
    ensure_user(conn, chat_id, "")
    # если набор уже идёт и не завершён — не начинаем новый день, продолжаем
    active = store.get(chat_id)
    if active is not None and not active.finished:
        conn.close()
        await _send_current(chat_id, bot)
        return
    day = assembler.get_course_day(conn, chat_id)        # 0-based
    tasks = assembler.build_course_today(conn, chat_id)
    conn.close()
    if not tasks:
        await bot.send_message(
            chat_id, "🎓 Курс из 15 дней пройден! Можно начать заново — напишите /restart.")
        return
    store.start(chat_id, tasks)
    await bot.send_message(
        chat_id, f"📚 День {day + 1} из {assembler.COURSE_DAYS}: {len(tasks)} вопросов. Поехали!")
    await _send_current(chat_id, bot)


async def _send_current(chat_id: int, bot) -> None:
    s = store.get(chat_id)
    if s is None or s.finished:
        await _finish_day(chat_id, bot)
        return
    task = s.current
    text = render_task(task, s.index, len(s.tasks))
    if int(task.task_type) == int(TaskType.QUIZ) and (task.payload.get("options")):
        await bot.send_message(chat_id, text, reply_markup=quiz_keyboard(task), parse_mode="HTML")
    elif task.task_type in MULTI_NUMBER_TYPES:
        kb = numbers_keyboard(task, s.selected_numbers.get(task.id, set()))
        await bot.send_message(chat_id, text, reply_markup=kb, parse_mode="HTML")
    else:
        await bot.send_message(chat_id, text, parse_mode="HTML")


async def _finish_day(chat_id: int, bot) -> None:
    s = store.get(chat_id)
    if s and s.day_scores:
        avg = sum(s.day_scores) / len(s.day_scores)
        conn = _conn()
        assembler.advance_course_day(conn, chat_id)       # переходим к следующему дню курса
        new_day = assembler.get_course_day(conn, chat_id)
        conn.close()
        tail = ("Это был последний день курса! 🎓" if new_day >= assembler.COURSE_DAYS
                else "Возвращайтесь завтра за следующим набором — или сразу /today.")
        await bot.send_message(
            chat_id, f"🏁 Итог дня: {avg:.0%} верных. {tail}\n/stats — прогресс по темам.")
    store.clear(chat_id)


@router.callback_query(F.data.startswith("tog:"))
async def on_toggle(cb: CallbackQuery) -> None:
    _, tid, n = cb.data.split(":")
    s = store.get(cb.message.chat.id)
    if s is None or s.current is None or s.current.id != int(tid):
        await cb.answer("Это задание уже не активно.")
        return
    selected = s.toggle(int(tid), int(n))
    await cb.message.edit_reply_markup(reply_markup=numbers_keyboard(s.current, selected))
    await cb.answer()


@router.callback_query(F.data.startswith("done:"))
async def on_done(cb: CallbackQuery) -> None:
    _, tid = cb.data.split(":")
    s = store.get(cb.message.chat.id)
    if s is None or s.current is None or s.current.id != int(tid):
        await cb.answer("Это задание уже не активно.")
        return
    task = s.current
    selected = sorted(s.selected_numbers.get(task.id, set()))
    answer = ",".join(str(x) for x in selected)
    await cb.answer()
    await _grade_and_advance(cb.message.chat.id, cb.bot, answer)


@router.callback_query(F.data.startswith("qz:"))
async def on_quiz_answer(cb: CallbackQuery) -> None:
    _, tid, opt = cb.data.split(":")
    s = store.get(cb.message.chat.id)
    if s is None or s.current is None or s.current.id != int(tid):
        await cb.answer("Этот вопрос уже не активен.")
        return
    await cb.answer()
    # убираем кнопки у отвеченного вопроса
    try:
        await cb.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass
    await _grade_and_advance(cb.message.chat.id, cb.bot, opt)


@router.message(Command("restart"))
async def cmd_restart(message: Message) -> None:
    conn = _conn()
    ensure_user(conn, message.chat.id, "")
    conn.execute("UPDATE users SET course_day=0 WHERE chat_id=?", (message.chat.id,))
    conn.commit()
    conn.close()
    store.clear(message.chat.id)
    await message.answer("Курс сброшен на день 1. Напишите /today, чтобы начать заново.")


@router.message(F.text)
async def on_text_answer(message: Message) -> None:
    s = store.get(message.chat.id)
    if s is None or s.finished:
        return  # вне сессии — игнор (команды обрабатываются выше)
    await _grade_and_advance(message.chat.id, message.bot, message.text or "")


async def _grade_and_advance(chat_id: int, bot, answer: str) -> None:
    s = store.get(chat_id)
    if s is None or s.current is None:
        return
    task = s.current
    verdict = checker.check(task, answer, judge=_judge)
    conn = _conn()
    save_attempt(conn, chat_id, task, verdict, answer)
    conn.close()
    await bot.send_message(chat_id, render_verdict(verdict), parse_mode="HTML")
    s.advance(verdict.score)
    await _send_current(chat_id, bot)

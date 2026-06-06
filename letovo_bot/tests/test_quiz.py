"""Тесты тестового режима (QUIZ) и 15-дневного курса."""
from __future__ import annotations

import sqlite3

import pytest

from letovo_bot.core import assembler, checker, db
from letovo_bot.core.models import TaskType
from letovo_bot.data import build_bank


@pytest.fixture()
def quiz_bank() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    questions = build_bank.load_quiz_questions()
    build_bank.seed_quiz(conn, questions)
    return conn


def test_bank_has_135_quiz(quiz_bank):
    tasks = [t for t in db.all_tasks(quiz_bank, verified_only=True)
             if int(t.task_type) == int(TaskType.QUIZ)]
    assert len(tasks) == 135


def test_quiz_mcq_grading(quiz_bank):
    t = next(t for t in db.all_tasks(quiz_bank)
             if t.payload.get("theme") == 1 and t.payload.get("idx") == 1)
    correct = t.answer["correct"]
    assert checker.check(t, str(correct)).score == 1.0
    assert checker.check(t, str((correct % 4) + 1)).score == 0.0
    # объяснение присутствует в обратной связи
    assert checker.check(t, "9").reference_answer


def test_quiz_open_grading(quiz_bank):
    t = next(t for t in db.all_tasks(quiz_bank)
             if not t.payload.get("options"))
    assert checker.check(t, t.answer["answer_text"]).score == 1.0
    assert checker.check(t, "заведомо неверно").score == 0.0


def test_course_day_structure(quiz_bank):
    tasks = assembler.course_day_set(quiz_bank, 0)
    assert len(tasks) == 9
    themes = [t.payload["theme"] for t in tasks]
    assert themes.count(1) == 1 and themes.count(2) == 1 and themes.count(3) == 1
    assert themes.count(4) == 2 and themes.count(5) == 2 and themes.count(6) == 2


def test_course_covers_all_without_repeats(quiz_bank):
    seen = {th: [] for th in (1, 2, 3, 4, 5, 6)}
    for day in range(assembler.COURSE_DAYS):
        for t in assembler.course_day_set(quiz_bank, day):
            seen[t.payload["theme"]].append(t.payload["idx"])
    for th in (1, 2, 3):
        assert sorted(seen[th]) == list(range(1, 16))      # 15 вопросов, по 1/день
    for th in (4, 5, 6):
        assert sorted(seen[th]) == list(range(1, 31))      # 30 вопросов, по 2/день
        assert len(seen[th]) == len(set(seen[th]))          # без повторов


def test_themes_456_are_shuffled(quiz_bank):
    """Темы 4–6 идут не подряд (перемешаны)."""
    day0 = [t.payload["idx"] for t in assembler.course_day_set(quiz_bank, 0)
            if t.payload["theme"] == 4]
    assert day0 != [1, 2]   # не первые по порядку


def test_course_finished_returns_empty(quiz_bank):
    assert assembler.course_day_set(quiz_bank, assembler.COURSE_DAYS) == []

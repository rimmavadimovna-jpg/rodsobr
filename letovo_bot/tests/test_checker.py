"""Тесты конвейера проверки (уровни A/B без LLM-судьи).

Проверяем, что эталонный ответ из банка получает полный балл, а заведомо
неверный — низкий. LLM-судья (уровень C) здесь не вызывается (judge=None).
"""
from __future__ import annotations

import pytest

from letovo_bot.core import checker, db
from letovo_bot.core.models import TaskType


def perfect_answer(task) -> str:
    """Строит образцовый ответ из эталона задания (для sanity-проверки банка)."""
    a, tt = task.answer, int(task.task_type)
    if tt == 1:
        return "\n".join(r["spelling"] for r in a["rows"])
    if tt == 2:
        return ", ".join(a["expected_forms"]) + "; " + ", ".join(a["expected_infinitives"])
    if tt == 3:
        return "\n".join(it["canonical"] for it in a["items"])
    if tt == 4:
        return "\n".join(it["reference"] for it in a["items"])
    if tt == 5:
        return a["example"]
    if tt == 6:
        nums = ",".join(str(n) for n in a["wrong"])
        return nums + ". " + " ".join(fx["corrected"] for fx in a["fixes"].values())
    if tt == 7:
        return str(a["count"])
    if tt == 8:
        return ", ".join(x["syn"] for x in a["allowed"][:5])
    if tt == 9:
        m = a["morphemes"]
        return (f"{' → '.join(a['chain'])}. Способ: {a['method']}. "
                f"Разбор: {m['root']} {m.get('suffix', '')} {m.get('ending', '')}")
    if tt == 10:
        return "\n".join(r["extra"] for r in a["rows"])
    if tt == 11:
        return ",".join(str(k) for k in a["key"])
    if tt == 12:
        ph = a["allowed"][0]
        return f"Предложение с фразеологизмом «{ph['phraseme']}». Это значит: {ph['meaning']}."
    return ""


# минимальный приемлемый балл по типу при ответе-эталоне (без LLM-судьи)
MIN_SCORE = {1: 1.0, 2: 0.9, 3: 1.0, 4: 0.8, 5: 0.4, 6: 1.0, 7: 1.0,
             8: 1.0, 9: 0.8, 10: 1.0, 11: 1.0, 12: 1.0}


def test_every_task_reference_scores_well(bank):
    """Каждое задание банка (оба варианта) на своём эталоне даёт высокий балл."""
    tasks = db.all_tasks(bank, verified_only=True)
    assert len(tasks) >= 24
    for t in tasks:
        v = checker.check(t, perfect_answer(t))
        assert v.score >= MIN_SCORE[int(t.task_type)], \
            f"задание {t.id} (тип {int(t.task_type)}): {v.score:.2f} < порога"


def _task(bank, tt):
    return next(t for t in db.all_tasks(bank) if t.task_type == tt)


def test_task1_perfect(bank):
    t = _task(bank, TaskType.THIRD_EXTRA)
    ans = "\n".join(r["spelling"] for r in t.answer["rows"])
    v = checker.check(t, ans)
    assert v.score == 1.0 and v.correct


def test_task1_partial(bank):
    t = _task(bank, TaskType.THIRD_EXTRA)
    rows = t.answer["rows"]
    lines = [r["spelling"] for r in rows]
    lines[0] = "неправильно"
    v = checker.check(t, "\n".join(lines))
    assert 0.0 < v.score < 1.0 and v.partial


def test_task2_selection_and_infinitives(bank):
    t = _task(bank, TaskType.CONJUGATION)
    ans = "клеишь, терпишь, дышишь; клеить, терпеть, дышать"
    v = checker.check(t, ans)
    assert v.score > 0.9


def test_task3_schemes(bank):
    t = _task(bank, TaskType.SCHEMES)
    ans = "\n".join(it["canonical"] for it in t.answer["items"])
    v = checker.check(t, ans)
    assert v.score == 1.0


def test_task4_punctuation(bank):
    t = _task(bank, TaskType.PUNCTUATION)
    ans = "\n".join(it["reference"] for it in t.answer["items"])
    v = checker.check(t, ans)
    assert v.score > 0.8  # пунктуация + основы


def test_task5_uses_words_and_phraseme(bank):
    t = _task(bank, TaskType.CONSTRUCT)
    v = checker.check(t, t.answer["example"])
    # без LLM структура определяется грубыми детекторами, но слова/фразеологизм засчитаны
    assert v.score > 0.4
    assert any("слов" in c.name.lower() for c in v.criteria)


def test_task6_grammar_fix_full(bank):
    t = _task(bank, TaskType.GRAMMAR_FIX)
    ans = ("2, 3, 5. Согласно приказу мы вышли. Он оплатил проезд в автобусе. "
           "Этот фильм более интересный, чем предыдущий.")
    v = checker.check(t, ans)
    assert v.score == 1.0


def test_task6_grammar_fix_variant_accepted(bank):
    """Допустимый вариант исправления засчитывается; неисправленный фрагмент — нет."""
    t = _task(bank, TaskType.GRAMMAR_FIX)
    ans = ("2,3,5. Согласно приказу. Он заплатил за проезд. Фильм интереснее предыдущего.")
    v = checker.check(t, ans)
    assert v.score == 1.0


def test_task6_uncorrected_wrong_fragment_not_counted(bank):
    """Если ошибочный фрагмент остался — исправление не засчитывается."""
    t = _task(bank, TaskType.GRAMMAR_FIX)
    # правильно выбраны номера, но «более интереснее» не исправлено
    ans = "2,3,5. Согласно приказу. Он оплатил проезд. Этот фильм более интереснее."
    v = checker.check(t, ans)
    assert v.score < 1.0


def test_task7_phonetics_exact(bank):
    t = _task(bank, TaskType.PHONETICS)
    v = checker.check(t, str(t.answer["count"]))
    assert v.score == 1.0
    v2 = checker.check(t, "99")
    assert v2.score == 0.0


def test_task8_synonyms_from_bank(bank):
    t = _task(bank, TaskType.SYNONYMS)
    syns = ", ".join(x["syn"] for x in t.answer["allowed"][:5])
    v = checker.check(t, syns)
    assert v.score == 1.0


def test_task9_word_formation(bank):
    t = _task(bank, TaskType.WORD_FORMATION)
    a = t.answer
    ans = f"{' → '.join(a['chain'])}. Способ: {a['method']}. " \
          f"Разбор: {a['morphemes']['root']} {a['morphemes']['suffix']} {a['morphemes']['ending']}"
    v = checker.check(t, ans)
    assert v.score > 0.8


def test_task10_fourth_extra(bank):
    t = _task(bank, TaskType.FOURTH_EXTRA)
    ans = "\n".join(r["extra"] for r in t.answer["rows"])
    v = checker.check(t, ans)
    assert v.score == 1.0


def test_task11_statements_exact(bank):
    t = _task(bank, TaskType.TEXT_STATEMENTS)
    key = t.answer["key"]
    v = checker.check(t, ",".join(str(k) for k in key))
    assert v.score == 1.0
    v2 = checker.check(t, "1")
    assert v2.score < 1.0


def test_task12_phraseme_found(bank):
    t = _task(bank, TaskType.PHRASEME)
    ph = t.answer["allowed"][1]["phraseme"]
    v = checker.check(t, f"Лесник работал {ph}, обходя участок.")
    # без судьи фразеологизм найден; толкование уходит на ручную проверку
    assert any(c.passed for c in v.criteria)

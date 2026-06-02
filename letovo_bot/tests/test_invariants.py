"""Тесты инвариантов банка (§5). CI должен падать при их нарушении."""
from __future__ import annotations

import copy

import pytest

from letovo_bot.core import db
from letovo_bot.core.assembler import InvariantError, validate_task
from letovo_bot.core.detectors import norm_word
from letovo_bot.core.models import TaskType


def test_all_seed_tasks_valid(bank):
    """Все выданные задания проходят инварианты, и присутствуют все 12 типов."""
    tasks = db.all_tasks(bank, verified_only=True)
    assert len(tasks) >= 12
    types_present = {int(t.task_type) for t in tasks}
    assert types_present == set(range(1, 13)), f"не все типы: {sorted(types_present)}"
    for t in tasks:
        validate_task(t)  # бросит InvariantError при нарушении


def test_task1_one_extra_per_row(bank):
    """Зад. 1: в каждом ряду ровно одно «лишнее», оно входит в ряд, есть написание."""
    t = next(t for t in db.all_tasks(bank) if t.task_type == TaskType.THIRD_EXTRA)
    for p_row, a_row in zip(t.payload["rows"], t.answer["rows"]):
        assert len(p_row["words"]) == 3
        norm = [norm_word(w) for w in p_row["words"]]
        assert norm_word(a_row["extra"]) in norm
        assert a_row["spelling"]
        assert p_row["principle"]


def test_task10_one_extra_per_row(bank):
    """Зад. 10: в каждом ряду ровно одно лишнее по морфологии, входит в ряд."""
    t = next(t for t in db.all_tasks(bank) if t.task_type == TaskType.FOURTH_EXTRA)
    for p_row, a_row in zip(t.payload["rows"], t.answer["rows"]):
        assert len(p_row["words"]) == 4
        assert norm_word(a_row["extra"]) in [norm_word(w) for w in p_row["words"]]
        assert a_row["feature"]


def test_task7_count_is_stored(bank):
    """Зад. 7: число хранится в банке (не вычисляется на лету)."""
    t = next(t for t in db.all_tasks(bank) if t.task_type == TaskType.PHONETICS)
    assert isinstance(t.answer["count"], int)


def test_task9_steps_have_wiktionary_source(bank):
    """Зад. 9: у каждого шага цепочки есть ссылка-подтверждение из Викисловаря."""
    t = next(t for t in db.all_tasks(bank) if t.task_type == TaskType.WORD_FORMATION)
    chain = t.answer["chain"]
    steps = t.answer["steps"]
    assert len(steps) == len(chain) - 1
    for st in steps:
        assert "ru.wiktionary.org" in st["source"]
        assert st.get("confirmed") is True
    assert t.answer["morphemes"]


def test_every_task_has_nonempty_reference_and_source(bank):
    for t in db.all_tasks(bank, verified_only=True):
        assert t.answer, f"задание {t.id} без эталона"
        assert t.source, f"задание {t.id} без источника"


def test_unverified_task_rejected(bank):
    """Невыверенное задание не проходит инвариант (в выдачу нельзя)."""
    t = next(t for t in db.all_tasks(bank))
    bad = copy.deepcopy(t)
    bad.verified = False
    with pytest.raises(InvariantError):
        validate_task(bad)


def test_task1_extra_outside_row_rejected(bank):
    """Если «лишнее» не входит в ряд — инвариант падает."""
    t = next(t for t in db.all_tasks(bank) if t.task_type == TaskType.THIRD_EXTRA)
    bad = copy.deepcopy(t)
    bad.answer["rows"][0]["extra"] = "несуществующее"
    bad.answer["rows"][0]["spelling"] = "несуществующее"
    with pytest.raises(InvariantError):
        validate_task(bad)


def test_odd_one_out_helper():
    """Хелпер находит единственный отличающийся элемент или None при неоднозначности."""
    from letovo_bot.core.assembler import odd_one_out_index
    assert odd_one_out_index(["при", "при", "пре"]) == 2
    assert odd_one_out_index(["н", "н", "нн", "н"]) == 2
    # два кандидата на «лишнее» → None
    assert odd_one_out_index(["а", "а", "б", "в"]) is None
    # все одинаковые → None
    assert odd_one_out_index(["а", "а", "а"]) is None


def test_task1_two_candidates_rejected(bank):
    """Если в ряду два слова нарушают принцип (два кандидата) — инвариант падает."""
    t = next(t for t in db.all_tasks(bank) if t.task_type == TaskType.THIRD_EXTRA)
    bad = copy.deepcopy(t)
    bad.answer["rows"][0]["props"] = ["при", "пре", "пере"]  # три разных → неоднозначно
    with pytest.raises(InvariantError):
        validate_task(bad)


def test_task1_props_match_extra(bank):
    """В каждом ряду отличающееся по props слово совпадает с «лишним»."""
    from letovo_bot.core.assembler import odd_one_out_index
    from letovo_bot.core.detectors import norm_word
    t = next(t for t in db.all_tasks(bank) if t.task_type == TaskType.THIRD_EXTRA)
    for p_row, a_row in zip(t.payload["rows"], t.answer["rows"]):
        odd = odd_one_out_index(a_row["props"])
        assert odd is not None
        assert norm_word(p_row["words"][odd]) == norm_word(a_row["extra"])


def test_task10_props_match_extra(bank):
    from letovo_bot.core.assembler import odd_one_out_index
    from letovo_bot.core.detectors import norm_word
    t = next(t for t in db.all_tasks(bank) if t.task_type == TaskType.FOURTH_EXTRA)
    for p_row, a_row in zip(t.payload["rows"], t.answer["rows"]):
        odd = odd_one_out_index(a_row["props"])
        assert odd is not None
        assert norm_word(p_row["words"][odd]) == norm_word(a_row["extra"])


def test_text_for_11_12_not_letovo(bank):
    """Текст зад. 11–12 — собственный/лицензированный, не из Летово."""
    row = bank.execute("SELECT body, license FROM texts").fetchone()
    assert row is not None
    assert "летово" not in row["body"].lower()
    assert row["license"]

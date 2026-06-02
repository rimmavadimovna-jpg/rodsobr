"""Тесты уровня C: интеграция LLM-судьи (через стаб) и безопасный парсинг JSON."""
from __future__ import annotations

from letovo_bot.core import checker, db
from letovo_bot.core.llm import safe_parse_json
from letovo_bot.core.models import TaskType


def _task(bank, tt):
    return next(t for t in db.all_tasks(bank) if t.task_type == tt)


class FakeJudge:
    """Подменяет LLM-судью: возвращает заранее заданный JSON по ключам схемы."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = 0

    @property
    def enabled(self):
        return True

    def judge(self, prompt, expected_keys):
        self.calls += 1
        return self.responses


def test_safe_parse_json_strips_fences():
    assert safe_parse_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert safe_parse_json("текст до {\"x\": true} текст после") == {"x": True}
    assert safe_parse_json("не json") is None
    assert safe_parse_json("") is None


def test_task5_levelc_positive(bank):
    t = _task(bank, TaskType.CONSTRUCT)
    judge = FakeJudge({
        "author_words_after_speech": True,
        "has_homogeneous_members": True,
        "words_used_appropriately": True,
        "comment": "ок",
    })
    v = checker.check(t, t.answer["example"], judge=judge)
    assert judge.calls == 1
    assert v.score > 0.8


def test_task5_invalid_json_marks_review(bank):
    t = _task(bank, TaskType.CONSTRUCT)
    # judge.judge возвращает None (невалидный/недоступный ответ) → needs_review
    judge = FakeJudge(None)
    v = checker.check(t, t.answer["example"], judge=judge)
    assert v.needs_review


def test_task12_levelc_definition(bank):
    t = _task(bank, TaskType.PHRASEME)
    ph = t.answer["allowed"][1]["phraseme"]
    judge = FakeJudge({
        "phraseme_fits_meaning": True,
        "definition_matches_reference": True,
        "comment": "верно",
    })
    v = checker.check(t, f"Лесник работал {ph}. Это значит усердно, без устали.", judge=judge)
    assert v.score == 1.0
    assert any(c.source == "llm" for c in v.criteria)


def test_task8_synonym_outside_bank_via_judge(bank):
    t = _task(bank, TaskType.SYNONYMS)
    # 4 из банка + 1 вне банка, который судья подтверждает как синоним с другим корнем
    syns = [x["syn"] for x in t.answer["allowed"][:4]] + ["пригожий"]
    judge = FakeJudge({"is_synonym": True, "different_root": True})
    v = checker.check(t, ", ".join(syns), judge=judge)
    assert v.score == 1.0

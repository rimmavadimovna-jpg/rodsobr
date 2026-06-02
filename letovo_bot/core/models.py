"""Pydantic-модели для заданий, ответов и результатов проверки.

Задания хранятся в SQLite как JSON в полях payload_json / answer_json / rubric_json.
Эти модели описывают структуру этого JSON для каждого из 12 типов и
используются слоем сборки (assembler) и слоем проверки (checker).
"""
from __future__ import annotations

from enum import IntEnum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TaskType(IntEnum):
    THIRD_EXTRA = 1          # «Третий лишний» по правописанию
    CONJUGATION = 2          # Глаголы заданного спряжения
    SCHEMES = 3              # Схемы предложений
    PUNCTUATION = 4          # Пунктуация + грамматические основы + объяснение
    CONSTRUCT = 5            # Конструирование предложений
    GRAMMAR_FIX = 6          # Исправление грамматических ошибок
    PHONETICS = 7            # Фонетика: подсчёт звука
    SYNONYMS = 8             # Синонимы с разными корнями
    WORD_FORMATION = 9       # Словообразовательная цепочка + морфемика
    FOURTH_EXTRA = 10        # «Четвёртое лишнее» по морфологии
    TEXT_STATEMENTS = 11     # Верные/ошибочные утверждения
    PHRASEME = 12            # Фразеологизм в текст + толкование


# Открытые задания (проверяются конвейером §3 с возможным уровнем C).
OPEN_ANSWER_TYPES = {3, 4, 5, 7, 8, 9, 10, 12}
# Задания с выбором множества номеров (inline-тогглы в боте).
MULTI_NUMBER_TYPES = {2, 6, 11}


class Verdict(BaseModel):
    """Результат проверки одного ответа ученика."""

    score: float = Field(ge=0.0, le=1.0)          # доля от максимума [0..1]
    max_score: float = 1.0
    correct: bool = False
    partial: bool = False
    needs_review: bool = False                    # отправить преподавателю
    criteria: list["CriterionResult"] = Field(default_factory=list)
    reference_answer: Optional[str] = None        # эталон/образец из банка
    rule_source: Optional[str] = None             # ссылка на правило
    comment: str = ""

    def summary_line(self) -> str:
        if self.correct:
            return f"✅ Верно ({self.score:.0%})"
        if self.partial or 0.0 < self.score < 1.0:
            return f"🟡 Частично ({self.score:.0%})"
        if self.needs_review:
            return "🔍 Нужна ручная проверка"
        return f"❌ Неверно ({self.score:.0%})"


class CriterionResult(BaseModel):
    """Разбор по одному критерию рубрики."""

    name: str
    passed: bool
    detail: str = ""
    source: str = "detector"   # detector | reference | llm


Verdict.model_rebuild()


# --- Task: то, что лежит в таблице tasks ---
class Task(BaseModel):
    id: int
    task_type: TaskType
    topic: str = ""
    difficulty: int = 1
    payload: dict[str, Any]      # условие + материал (payload_json)
    answer: dict[str, Any]       # эталон (answer_json)
    rubric: Optional[dict[str, Any]] = None  # критерии для уровня C
    source: str = ""
    verified: bool = False

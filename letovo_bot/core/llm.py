"""Уровень C конвейера: LLM-судья.

Вызывается ТОЛЬКО когда уровни A/B не закрыли вопрос, и только по остаточным
субъективным критериям. Жёсткие правила:
  * промпт всегда содержит эталон и запрет «придумывать» новый верный ответ;
  * LLM не засчитывает как верное то, чего нет в банке (для объективных частей);
  * ответ парсится безопасно; при невалидном JSON → needs_review (не угадываем).

Без ANTHROPIC_API_KEY судья отключён и любой остаточный вопрос помечается как
needs_review — это безопасное поведение по умолчанию.
"""
from __future__ import annotations

import json
import re
from typing import Any, Optional

from .. import config

try:  # pragma: no cover
    import anthropic
except Exception:  # pragma: no cover
    anthropic = None


SYSTEM_PROMPT = (
    "Ты — строгий проверяющий по русскому языку для вступительного теста. "
    "Ты получаешь ЭТАЛОН и критерии. Твоя задача — оценить ответ ученика "
    "СТРОГО по переданным критериям. Категорически запрещено: придумывать новый "
    "правильный ответ, засчитывать то, чего нет в эталоне для объективных частей, "
    "отклоняться от рубрики. Отвечай ТОЛЬКО валидным JSON по запрошенной схеме, "
    "без пояснений вне JSON."
)


class LLMJudge:
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key if api_key is not None else config.ANTHROPIC_API_KEY
        self.model = model or config.ANTHROPIC_MODEL_JUDGE
        self._client = None
        if self.api_key and anthropic is not None:
            self._client = anthropic.Anthropic(api_key=self.api_key)

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def judge(self, prompt: str, expected_keys: list[str]) -> Optional[dict[str, Any]]:
        """Отправляет запрос судье, возвращает распарсенный JSON или None.

        None означает «не удалось получить валидный ответ» → вызывающий код
        ставит needs_review.
        """
        if not self.enabled:
            return None
        try:  # pragma: no cover - сеть
            msg = self._client.messages.create(
                model=self.model,
                max_tokens=512,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            text = "".join(
                block.text for block in msg.content if getattr(block, "type", None) == "text"
            )
        except Exception:
            return None
        data = safe_parse_json(text)
        if data is None or not all(k in data for k in expected_keys):
            return None
        return data


def safe_parse_json(text: str) -> Optional[dict[str, Any]]:
    """Безопасный парсинг JSON из ответа модели (strip ```json, try/except)."""
    if not text:
        return None
    t = text.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    # выдрать первый {...} блок, если вокруг есть текст
    m = re.search(r"\{.*\}", t, re.DOTALL)
    candidate = m.group(0) if m else t
    try:
        data = json.loads(candidate)
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, ValueError):
        return None


# --- Конструкторы промптов для конкретных заданий (всегда с эталоном) --- #
def prompt_task5(answer: str, words: list[str], phrasemes: list[dict[str, str]],
                 sentence_requirements: str) -> str:
    ph = "\n".join(f"- {p['phraseme']}: {p['meaning']}" for p in phrasemes)
    wl = ", ".join(words)
    return (
        f"Заданные слова (можно менять форму): {wl}\n"
        f"Заданные фразеологизмы и их толкования:\n{ph}\n"
        f"Требования к предложению: {sentence_requirements}\n\n"
        f"Ответ ученика:\n«{answer}»\n\n"
        "Верни JSON: {\"author_words_after_speech\": bool, \"has_homogeneous_members\": bool, "
        "\"words_used_appropriately\": bool, \"comment\": str}. "
        "Не придумывай слова за ученика; оценивай только то, что он написал."
    )


def prompt_task8_synonym(synonym: str, source_word: str, context: str) -> str:
    return (
        f"Исходное слово: «{source_word}». Контекст: «{context}».\n"
        f"Кандидат в синонимы: «{synonym}».\n\n"
        "Верни JSON: {\"is_synonym\": bool, \"different_root\": bool}. "
        "different_root — отличается ли корень кандидата от корня исходного слова."
    )


def prompt_task12(answer: str, reference_definition: str, phraseme: str) -> str:
    return (
        f"Фразеологизм: «{phraseme}». Словарное толкование (ЭТАЛОН): "
        f"«{reference_definition}».\n\n"
        f"Ответ ученика (предложение с фразеологизмом и/или толкование):\n«{answer}»\n\n"
        "Верни JSON: {\"phraseme_fits_meaning\": bool, \"definition_matches_reference\": bool, "
        "\"comment\": str}. Толкование ученика верно, только если по смыслу совпадает с эталоном."
    )


def prompt_task4_explanation(answer: str, rule: str) -> str:
    return (
        f"Правило (ЭТАЛОН): «{rule}».\n\n"
        f"Объяснение ученика:\n«{answer}»\n\n"
        "Верни JSON: {\"explanation_valid\": bool, \"comment\": str}. "
        "Объяснение верно, если соответствует переданному правилу."
    )

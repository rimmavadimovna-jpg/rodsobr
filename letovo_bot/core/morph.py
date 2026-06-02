"""Обёртка над pymorphy3.

Морфологический анализатор используется и при сборке банка, и в детекторах
(зад. 2, 5, 6, 8, 10). Здесь — единая точка доступа с ленивой инициализацией
и аккуратной деградацией, если pymorphy3 не установлен (тогда часть детекторов
честно сообщает needs_review вместо угадывания).
"""
from __future__ import annotations

import functools
import re
from typing import Optional

try:  # pragma: no cover - зависит от окружения
    import pymorphy3

    _ANALYZER = pymorphy3.MorphAnalyzer()
except Exception:  # pragma: no cover
    _ANALYZER = None


def available() -> bool:
    return _ANALYZER is not None


@functools.lru_cache(maxsize=4096)
def normal_form(word: str) -> str:
    """Лемма слова (нормальная форма). Без pymorphy3 — слово в нижнем регистре."""
    if _ANALYZER is None:
        return word.lower()
    return _ANALYZER.parse(word)[0].normal_form


@functools.lru_cache(maxsize=4096)
def pos(word: str) -> Optional[str]:
    """Часть речи (тег pymorphy3, напр. 'NOUN', 'VERB')."""
    if _ANALYZER is None:
        return None
    return _ANALYZER.parse(word)[0].tag.POS


@functools.lru_cache(maxsize=4096)
def tag(word: str) -> Optional[str]:
    if _ANALYZER is None:
        return None
    return str(_ANALYZER.parse(word)[0].tag)


def lemmas_set(text: str) -> set[str]:
    """Множество лемм всех слов текста — для проверки использования заданных слов."""
    return {normal_form(w) for w in re.findall(r"[А-Яа-яЁёA-Za-z\-]+", text)}


def contains_lemma(text: str, target_word: str) -> bool:
    """Есть ли в тексте слово с той же леммой, что у target_word (учёт смены формы)."""
    target = normal_form(target_word)
    return target in lemmas_set(text)

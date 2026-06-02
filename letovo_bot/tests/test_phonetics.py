"""Тесты офлайн-фонетики (зад. 7). Только надёжные школьные случаи.

Модуль приближённый и в рантайме не используется (число берётся из банка),
поэтому проверяем лишь однозначные явления: оглушение, озвончение, мягкость.
"""
from __future__ import annotations

import pytest

from letovo_bot.data import phonetics as P


@pytest.mark.parametrize("sentence,target,expected", [
    ("Сдобный пирог.", "[з]", 1),   # озвончение с→з перед д
    ("год", "[т]", 1),              # оглушение д→т на конце
    ("лодка", "[т]", 1),           # оглушение д→т перед к
    ("зуб", "[п]", 1),             # оглушение б→п на конце
    ("просьба", "[с']", 0),        # с озвончается → не [с']
    ("просьба", "[з']", 1),        # с → [з'] (озвончение + мягкость перед ь)
    ("коса", "[с]", 1),            # без ассимиляции
    ("коза", "[з]", 1),
])
def test_count_sound(sentence, target, expected):
    n, _steps = P.count_sound(sentence, target)
    assert n == expected


def test_parse_target():
    assert P.parse_target("[з]") == ("з", False)
    assert P.parse_target("[с']") == ("с", True)


def test_transcribe_returns_softness():
    sounds = P.transcribe_consonants("мяч")
    # м мягкий (перед я), ч всегда мягкий
    assert ("м", True) in sounds
    assert ("ч", True) in sounds

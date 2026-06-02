"""Офлайн-фонетика для зад. 7 (подсчёт согласного звука).

ВАЖНО: это вспомогательный модуль ДЛЯ НАПОЛНЕНИЯ/ВЫВЕРКИ банка, а не источник
истины в рантайме. В рантайме число берётся из банка (инвариант §5). Здесь —
школьная (приближённая) транскрипция согласных, чтобы человек/сильная LLM могли
сверить заранее посчитанное число. Результат всегда помечается как требующий
выверки.

Учитываются:
  * оглушение парных звонких на конце слова и перед глухими;
  * озвончение парных глухих перед звонкими шумными (кроме перед «в»);
  * мягкость согласного перед е/ё/и/ю/я/ь (кроме всегда твёрдых ж, ш, ц).

НЕ учитываются (ограничения, поэтому нужна ручная выверка): редукция гласных,
долгие согласные на стыке, ассимилятивная мягкость (гость → [с'т']), стыки слов,
непроизносимые согласные (солнце), [j] в йотированных гласных.
"""
from __future__ import annotations

import re

VOWELS = set("аеёиоуыэюя")
CONSONANTS = set("бвгджзйклмнпрстфхцчшщ")
SOFTENING = set("еёиюя")  # после согласной дают ей мягкость (плюс ь)

# Пары по звонкости/глухости: звонкая → глухая
VOICED_TO_VOICELESS = {"б": "п", "в": "ф", "г": "к", "д": "т", "ж": "ш", "з": "с"}
VOICELESS_TO_VOICED = {v: k for k, v in VOICED_TO_VOICELESS.items()}

ALWAYS_HARD = set("жшц")
ALWAYS_SOFT = set("чщй")

# Триггеры ассимиляции по звонкости (по «звуковой» букве):
VOICED_OBSTRUENTS = set("бгджз")          # вызывают озвончение предыдущего
VOICELESS_OBSTRUENTS = set("пфктшсцхчщ")  # вызывают оглушение предыдущего
NEUTRAL_SOUNDS = set("лмнрйв")            # сонорные и «в» — не триггеры

UNPAIRED_VOICED = set("лмнрйв")           # «в» здесь как звонкий по умолчанию


def _is_paired(letter: str) -> bool:
    return letter in VOICED_TO_VOICELESS or letter in VOICELESS_TO_VOICED


def _inherent_voiced(letter: str) -> bool:
    if letter in VOICED_TO_VOICELESS:
        return True
    if letter in VOICELESS_TO_VOICED:
        return False
    return letter in set("лмнрй") or letter == "в"


def _softness(word: list[str], i: int) -> bool:
    base = word[i]
    if base in ALWAYS_HARD:
        return False
    if base in ALWAYS_SOFT:
        return True
    nxt = word[i + 1] if i + 1 < len(word) else ""
    return nxt in SOFTENING or nxt == "ь"


def _voicing_rtl(word: list[str]) -> dict[int, bool]:
    """Звонкость каждого согласного, справа налево (учёт ассимиляции и конца слова)."""
    result: dict[int, bool] = {}
    for i in range(len(word) - 1, -1, -1):
        ch = word[i]
        if ch not in CONSONANTS:
            continue
        if not _is_paired(ch):
            result[i] = _inherent_voiced(ch)
            continue
        # ищем следующий влияющий звук, пропуская ь/ъ
        j = i + 1
        while j < len(word) and word[j] in ("ь", "ъ"):
            j += 1
        if j >= len(word):
            result[i] = False  # конец слова → оглушение парного
            continue
        nxt = word[j]
        if nxt in VOWELS or nxt in NEUTRAL_SOUNDS:
            result[i] = _inherent_voiced(ch)
        elif nxt in CONSONANTS:
            # ориентируемся на уже вычисленную звонкость следующего согласного
            nxt_voiced = result.get(j, _inherent_voiced(nxt))
            nxt_sound = _sound_letter(nxt, nxt_voiced)
            if nxt_sound in VOICED_OBSTRUENTS:
                result[i] = True
            elif nxt_sound in VOICELESS_OBSTRUENTS:
                result[i] = False
            else:
                result[i] = _inherent_voiced(ch)
        else:
            result[i] = _inherent_voiced(ch)
    return result


def _sound_letter(base: str, voiced: bool) -> str:
    if not _is_paired(base):
        return base
    if voiced:
        return base if base in VOICED_TO_VOICELESS else VOICELESS_TO_VOICED[base]
    return base if base in VOICELESS_TO_VOICED else VOICED_TO_VOICELESS[base]


def transcribe_consonants(word: str) -> list[tuple[str, bool]]:
    """Список согласных звуков слова как (буква_звука, мягкость)."""
    w = list(word.lower().replace("ё", "ё"))
    voicing = _voicing_rtl(w)
    out: list[tuple[str, bool]] = []
    for i, ch in enumerate(w):
        if ch not in CONSONANTS:
            continue
        voiced = voicing.get(i, _inherent_voiced(ch))
        out.append((_sound_letter(ch, voiced), _softness(w, i)))
    return out


def parse_target(target: str) -> tuple[str, bool]:
    """«[з]» → ('з', False); «[с']» → ('с', True)."""
    t = target.strip().strip("[]")
    soft = t.endswith("'") or t.endswith("’")
    letter = t.rstrip("'’").lower()
    return letter, soft


def count_sound(sentence: str, target: str) -> tuple[int, list[str]]:
    """Сколько раз согласный звук target встречается в предложении.

    Возвращает (число, пошаговая транскрипция по словам). Число — приближённое,
    подлежит ручной выверке перед занесением в банк.
    """
    letter, soft = parse_target(target)
    total = 0
    steps: list[str] = []
    for word in re.findall(r"[а-яё\-]+", sentence.lower()):
        sounds = transcribe_consonants(word)
        hits = sum(1 for (s, sf) in sounds if s == letter and sf == soft)
        total += hits
        trans = " ".join(f"[{s}{'ʲ' if sf else ''}]" for s, sf in sounds)
        steps.append(f"{word}: {trans} → {hits}")
    return total, steps

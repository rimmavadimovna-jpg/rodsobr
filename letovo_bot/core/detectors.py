"""Уровень A конвейера проверки: детерминированные детекторы.

Здесь НЕТ обращений к LLM. Только структурно-измеримые признаки:
нормализация, сравнение множеств/строк, токенизация, проверка пунктуации,
выделения основ, схем, использования заданных слов, различия корней и т. п.

Каждый детектор возвращает примитив (bool / float / set / dict) — оркестровку
в баллы и критерии делает checker.py.
"""
from __future__ import annotations

import re
from typing import Iterable, Optional

from . import morph

try:  # pragma: no cover
    from razdel import tokenize as _razdel_tokenize
except Exception:  # pragma: no cover
    _razdel_tokenize = None

PUNCT = set(".,;:—–-?!…\"«»()")


# --------------------------------------------------------------------------- #
# Нормализация
# --------------------------------------------------------------------------- #
def norm_text(s: str) -> str:
    """trim, ё→е, нижний регистр, схлопывание пробелов."""
    s = s.strip().lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s)
    return s


def norm_word(s: str) -> str:
    """Нормализация одиночного слова: убрать обрамляющую пунктуацию, ё→е, регистр."""
    s = s.strip().strip("".join(PUNCT)).lower().replace("ё", "е")
    return s


def parse_number_set(s: str) -> set[int]:
    """Разбор ответа-множества номеров.

    Принимает формы «35», «3,5», «3 5», «3, 5», «3;5». «35» трактуем как {3,5}
    (номера предложений одноразрядные), но многоразрядные через разделители — как есть.
    """
    s = s.strip()
    parts = re.split(r"[\s,;.]+", s)
    parts = [p for p in parts if p]
    if len(parts) == 1 and parts[0].isdigit() and len(parts[0]) > 1:
        # слитная запись вида «35» → отдельные цифры
        return {int(ch) for ch in parts[0]}
    out: set[int] = set()
    for p in parts:
        if p.isdigit():
            out.add(int(p))
    return out


def normalize_scheme(s: str) -> str:
    """Нормализация схемы предложения (зад. 3).

    Унифицируем символы, убираем пробелы, ё→е, заглавную О оставляем как маркер
    однородного члена.
    """
    s = s.strip().replace("ё", "е")
    s = s.replace("[", "[").replace("]", "]")
    # унификация тире/дефисов и кавычек
    s = re.sub(r"[–—-]", "-", s)
    s = re.sub(r"\s+", "", s)
    return s


# --------------------------------------------------------------------------- #
# Множества номеров (зад. 1, 2, 6, 11) и числа (зад. 7)
# --------------------------------------------------------------------------- #
def number_set_matches(user: str, expected: Iterable[int]) -> tuple[bool, set[int], set[int]]:
    exp = set(expected)
    got = parse_number_set(user)
    return got == exp, got, exp


def number_set_partial(user: str, expected: Iterable[int]) -> float:
    """Доля совпадения множеств номеров: |пересечение| − |лишние|, нормируем на |эталон|."""
    exp = set(expected)
    got = parse_number_set(user)
    if not exp:
        return 1.0 if not got else 0.0
    hits = len(exp & got)
    extra = len(got - exp)
    return max(0.0, (hits - extra) / len(exp))


def exact_int(user: str, expected: int) -> bool:
    m = re.search(r"-?\d+", user)
    return m is not None and int(m.group()) == expected


# --------------------------------------------------------------------------- #
# Токенизация и пунктуация (зад. 4)
# --------------------------------------------------------------------------- #
def tokens(s: str) -> list[str]:
    if _razdel_tokenize is not None:
        return [t.text for t in _razdel_tokenize(s)]
    return re.findall(r"\w+|[^\w\s]", s, re.UNICODE)


def word_sequence(s: str) -> list[str]:
    """Только слова (для выравнивания предложений без учёта пунктуации)."""
    return [norm_word(t) for t in re.findall(r"[А-Яа-яЁёA-Za-z\-]+", s)]


def punctuation_after_words(s: str) -> dict[int, str]:
    """Возвращает {индекс_слова: знак}, где знак стоит ПОСЛЕ слова с этим индексом.

    Индексация по последовательности слов (0-based). Несколько знаков подряд
    склеиваются. Это позволяет сравнить расстановку знаков ученика и эталона по
    позициям, игнорируя сами слова.
    """
    result: dict[int, str] = {}
    word_idx = -1
    for tok in tokens(s):
        if re.match(r"[А-Яа-яЁёA-Za-z\-]+$", tok):
            word_idx += 1
        elif tok.strip() and any(ch in PUNCT for ch in tok):
            mark = "".join(ch for ch in tok if ch in PUNCT)
            if word_idx >= 0 and mark:
                result[word_idx] = result.get(word_idx, "") + mark
    return result


def _canon_mark(mark: str) -> str:
    """Канонизация знака: тире/дефис → '-', схлопывание повторов не делаем."""
    return re.sub(r"[–—-]", "-", mark)


def punctuation_score(user: str, reference_with_marks: str) -> tuple[float, list[str]]:
    """Сравнивает расстановку знаков ученика с эталоном по позициям слов.

    Возвращает (доля_верных, список_замечаний).
    """
    exp = {i: _canon_mark(m) for i, m in punctuation_after_words(reference_with_marks).items()}
    got = {i: _canon_mark(m) for i, m in punctuation_after_words(user).items()}
    if not exp:
        return (1.0 if not got else 0.5), []
    positions = set(exp) | set(got)
    correct = 0
    notes: list[str] = []
    for pos in sorted(positions):
        e = exp.get(pos, "")
        g = got.get(pos, "")
        if e == g:
            if e:
                correct += 1
        elif e and not g:
            notes.append(f"пропущен знак «{e}» после {pos + 1}-го слова")
        elif g and not e:
            notes.append(f"лишний знак «{g}» после {pos + 1}-го слова")
        else:
            notes.append(f"неверный знак: ожидался «{e}», стоит «{g}»")
    return correct / len(exp), notes


# --------------------------------------------------------------------------- #
# Грамматические основы (зад. 4)
# --------------------------------------------------------------------------- #
def grammatical_bases_score(user_words: Iterable[str], expected_bases: list[list[str]]) -> float:
    """Сверяет множество выделенных учеником слов с эталонными основами.

    expected_bases — список основ, каждая основа — список слов (подлежащее/сказуемое).
    Считаем долю слов-эталона, попавших в ответ ученика.
    """
    user_set = {morph.normal_form(norm_word(w)) for w in user_words if norm_word(w)}
    exp_words = [morph.normal_form(norm_word(w)) for base in expected_bases for w in base]
    exp_words = [w for w in exp_words if w]
    if not exp_words:
        return 1.0
    hits = sum(1 for w in exp_words if w in user_set)
    return hits / len(exp_words)


# --------------------------------------------------------------------------- #
# Использование заданных слов / фразеологизма (зад. 5, 12)
# --------------------------------------------------------------------------- #
def words_used(answer: str, required_words: Iterable[str], min_count: int) -> tuple[bool, list[str]]:
    """Использовано ли не менее min_count слов из списка (с учётом смены формы)."""
    used = [w for w in required_words if morph.contains_lemma(answer, w)]
    return len(used) >= min_count, used


def phraseme_present(answer: str, phraseme: str) -> bool:
    """Есть ли фразеологизм в ответе (нечётко: по леммам опорных слов).

    Фразеологизм считается использованным, если все его «содержательные» слова
    (длиннее 2 букв) присутствуют в ответе в любой форме.
    """
    keys = [w for w in re.findall(r"[А-Яа-яЁё\-]+", phraseme) if len(w) > 2]
    if not keys:
        return norm_text(phraseme) in norm_text(answer)
    answer_lemmas = morph.lemmas_set(answer)
    return all(morph.normal_form(k) in answer_lemmas for k in keys)


def find_matching_phraseme(answer: str, allowed: list[str]) -> Optional[str]:
    for ph in allowed:
        if phraseme_present(answer, ph):
            return ph
    return None


# --------------------------------------------------------------------------- #
# Структурные признаки предложения (зад. 5)
# --------------------------------------------------------------------------- #
def is_interrogative(sentence: str) -> bool:
    return sentence.strip().endswith("?")


def has_author_words_after_speech(sentence: str) -> bool:
    """Прямая речь со словами автора ПОСЛЕ неё: «"…" — автор» (грубый детектор).

    Требуем: закрывающую кавычку/реплику, затем тире, затем слово со строчной буквы.
    Окончательное решение — уровень C, это лишь предварительный признак.
    """
    s = sentence.strip()
    # вариант с кавычками: «…» — слова  или  "..." - слова
    pat = re.compile(r'[»"][\s]*[—–-]\s+[а-яё]', re.UNICODE)
    if pat.search(s):
        return True
    # вариант с тире-репликой: — Реплика, — сказал
    pat2 = re.compile(r'[а-яё][,.!?]?\s*[—–-]\s+[а-яё]', re.UNICODE)
    return bool(pat2.search(s)) and ("—" in s or "–" in s)


COORD_CONJ = {"и", "а", "но", "да", "или", "либо", "то", "ни", "зато", "однако"}
# Содержательные части речи, члены которых бывают однородными.
CONTENT_POS = {"NOUN", "ADJF", "ADJS", "VERB", "INFN", "ADVB", "PRTF", "PRTS", "GRND", "NUMR"}


def has_homogeneous_members(sentence: str) -> bool:
    """Детектор однородных членов: два+ слова одной части речи, связанных
    запятой и/или сочинительным союзом.

    Если pymorphy3 доступен — проверяем совпадение части речи у соединённых слов;
    иначе откатываемся на грубую эвристику (запятая+союз / перечисление).
    Окончательное решение по спорным случаям — уровень C.
    """
    s = sentence.lower()
    if not morph.available():
        if re.search(r",\s+(и|а|но|да|или|либо|то)\b", s):
            return True
        return len(re.findall(r"\w+\s*,\s*\w+", s)) >= 2

    # последовательность из слов и «связок» (запятая/союз) между ними
    toks = re.findall(r"[а-яё]+|,", s)
    i = 0
    n = len(toks)
    while i < n:
        if toks[i] == "," or toks[i] in COORD_CONJ:
            i += 1
            continue
        # начинаем потенциальный ряд с слова toks[i]
        first_pos = morph.pos(toks[i])
        if first_pos in CONTENT_POS:
            j = i + 1
            members = 1
            while j < n and (toks[j] == "," or toks[j] in COORD_CONJ):
                # пропускаем связки (может быть «, и»)
                while j < n and (toks[j] == "," or toks[j] in COORD_CONJ):
                    j += 1
                if j < n and morph.pos(toks[j]) == first_pos:
                    members += 1
                    j += 1
                else:
                    break
            if members >= 2:
                return True
        i += 1
    return False


def parse_morphemes(text: str) -> list[str]:
    """Выделяет морфемы из разбора ученика.

    Принимает записи вида «при-став-к-а», «при|став|к|а», «при став к а» и
    нормализует к списку морфем (нижний регистр, ё→е). Используется грейдером
    зад. 9 для сравнения с эталонной разметкой.
    """
    cleaned = text.strip().lower().replace("ё", "е")
    parts = re.split(r"[^а-я]+", cleaned)
    return [p for p in parts if p]


# --------------------------------------------------------------------------- #
# Синонимы: количество и различие корней (зад. 8)
# --------------------------------------------------------------------------- #
def split_synonyms(user: str) -> list[str]:
    parts = re.split(r"[,;\n]+", user)
    return [p.strip() for p in parts if p.strip()]


def approx_root(word: str) -> str:
    """Грубое выделение «корня» для проверки различия корней.

    Берём лемму, отбрасываем типовые приставки и окончания/суффиксы — это
    эвристика для случая, когда корень не размечен в банке. Точная разметка
    корня в банке (поле root) всегда приоритетнее.
    """
    lemma = morph.normal_form(word)
    s = lemma
    for pref in ("без", "бес", "пре", "при", "пере", "про", "под", "над", "раз",
                 "рас", "из", "ис", "воз", "вос", "за", "на", "по", "не", "о", "об"):
        if s.startswith(pref) and len(s) - len(pref) >= 3:
            s = s[len(pref):]
            break
    # отбросить хвост (окончание/суффикс) — оставить первые ~4 буквы корня
    return s[:4]


def distinct_roots(words: Iterable[str], roots_map: Optional[dict[str, str]] = None) -> tuple[bool, list[str]]:
    """Попарно ли различны корни. roots_map — разметка корней из банка (приоритет)."""
    roots: list[str] = []
    for w in words:
        wn = norm_word(w)
        if roots_map and wn in roots_map:
            roots.append(roots_map[wn])
        else:
            roots.append(approx_root(wn))
    return len(set(roots)) == len(roots), roots


# --------------------------------------------------------------------------- #
# Сверка лишнего слова (зад. 1, 10) и его написания
# --------------------------------------------------------------------------- #
def extra_word_matches(user: str, expected_word: str, expected_spelling: Optional[str] = None) -> tuple[bool, bool]:
    """Возвращает (совпало_слово, совпало_написание)."""
    user_n = norm_word(user)
    word_ok = user_n == norm_word(expected_word) or (
        expected_spelling is not None and user_n == norm_word(expected_spelling)
    )
    if expected_spelling is None:
        return word_ok, word_ok
    spelling_ok = user_n == norm_word(expected_spelling)
    return word_ok, spelling_ok

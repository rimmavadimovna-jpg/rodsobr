"""Тесты детекторов уровня A (без LLM)."""
from __future__ import annotations

from letovo_bot.core import detectors as D


def test_norm_text():
    assert D.norm_text("  Ёлка   зелёная ") == "елка зеленая"


def test_parse_number_set_joined():
    assert D.parse_number_set("35") == {3, 5}
    assert D.parse_number_set("3,5") == {3, 5}
    assert D.parse_number_set("3 5") == {3, 5}
    assert D.parse_number_set("2; 4") == {2, 4}


def test_number_set_partial():
    assert D.number_set_partial("2,4", [2, 4]) == 1.0
    assert D.number_set_partial("2", [2, 4]) == 0.5
    # лишний номер штрафует
    assert D.number_set_partial("2,4,5", [2, 4]) == 0.5


def test_exact_int():
    assert D.exact_int("Ответ: 1, потому что...", 1)
    assert not D.exact_int("2", 1)


def test_normalize_scheme():
    assert D.normalize_scheme("[ О и О ]") == D.normalize_scheme("[ОиО]")
    assert D.normalize_scheme("[ ], и [ ]") == D.normalize_scheme("[],и[]")


def test_punctuation_after_words():
    marks = D.punctuation_after_words("Солнце село, и стало темно.")
    # запятая после 2-го слова (индекс 1)
    assert marks.get(1) == ","


def test_punctuation_score_full():
    score, notes = D.punctuation_score("Солнце село, и стало темно.",
                                       "Солнце село, и стало темно.")
    assert score == 1.0
    assert notes == []


def test_punctuation_score_missing():
    score, notes = D.punctuation_score("Солнце село и стало темно.",
                                       "Солнце село, и стало темно.")
    assert score < 1.0
    assert any("пропущен" in n for n in notes)


def test_is_interrogative():
    assert D.is_interrogative("Ты придёшь?")
    assert not D.is_interrogative("Я приду.")


def test_author_words_after_speech():
    assert D.has_author_words_after_speech('«Привет!» — сказал он.')


def test_split_synonyms():
    assert D.split_synonyms("прелестный, дивный; чудесный") == \
        ["прелестный", "дивный", "чудесный"]


def test_distinct_roots():
    distinct, _ = D.distinct_roots(["прелестный", "дивный", "чудесный"])
    assert distinct
    same, _ = D.distinct_roots(["красивый", "красота"])
    assert not same


def test_phraseme_present():
    assert D.phraseme_present("Он работал спустя рукава весь день.", "спустя рукава")
    assert not D.phraseme_present("Он работал усердно.", "спустя рукава")


def test_extra_word_matches():
    word_ok, spell_ok = D.extra_word_matches("прекрасный", "пр_красный", "прекрасный")
    assert word_ok and spell_ok
    word_ok, spell_ok = D.extra_word_matches("прикрасный", "пр_красный", "прекрасный")
    assert not spell_ok


def test_grammatical_bases_score():
    score = D.grammatical_bases_score(["солнце", "село"], [["солнце", "село"]])
    assert score == 1.0


def test_homogeneous_members_detected():
    # однородные существительные через союз и запятые
    assert D.has_homogeneous_members("Я люблю книги, журналы и газеты.")
    # однородные сказуемые
    assert D.has_homogeneous_members("Он встал и ушёл.")


def test_homogeneous_members_absent():
    assert not D.has_homogeneous_members("Наступила тёплая весна.")


def test_parse_morphemes():
    assert D.parse_morphemes("при-став-к-а") == ["при", "став", "к", "а"]
    assert D.parse_morphemes("уч | и | тель | ниц | а") == ["уч", "и", "тель", "ниц", "а"]
    assert D.parse_morphemes("корень: уч, суффикс: тель") == \
        ["корень", "уч", "суффикс", "тель"]

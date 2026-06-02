"""Выверка задания 9 по Викисловарю через MediaWiki API (action=parse).

Используется ОФЛАЙН при наполнении банка, не в рантайме. Шаг цепочки A → B
включается только если статья B явно подтверждает производность от A
(формулировки «происходит от», «образовано от»). Иначе шаг бракуется.
"""
from __future__ import annotations

import re
from typing import Optional
from urllib.parse import quote

API = "https://ru.wiktionary.org/w/api.php"

# Маркеры явной производности в секции «Этимология».
DERIVATION_MARKERS = (
    "происходит от", "образовано от", "образовано путём", "уменьш. к",
    "уменьш.-ласк. к", "от гл.", "от сущ.", "от прил.",
)


def article_url(word: str) -> str:
    return f"https://ru.wiktionary.org/wiki/{quote(word)}"


def fetch_wikitext(word: str, session=None) -> Optional[str]:
    """Возвращает вики-текст статьи через action=parse&prop=wikitext.

    Требует сети; при отсутствии requests/сети возвращает None (вызывающий код
    отправляет задание на ручную проверку).
    """
    try:  # pragma: no cover - сеть/опциональная зависимость
        import requests
    except Exception:
        return None
    params = {
        "action": "parse", "page": word, "prop": "wikitext",
        "format": "json", "formatversion": "2",
    }
    try:  # pragma: no cover - сеть
        s = session or requests
        r = s.get(API, params=params, timeout=15,
                  headers={"User-Agent": "letovo-bot/1.0 (bank verification)"})
        r.raise_for_status()
        return r.json()["parse"]["wikitext"]
    except Exception:
        return None


def confirms_derivation(child_wikitext: str, parent: str) -> bool:
    """Подтверждает ли статья child, что слово образовано от parent.

    Грубая, но консервативная проверка: ищем маркер производности и упоминание
    родителя/его основы рядом в секции «Этимология».
    """
    if not child_wikitext:
        return False
    text = child_wikitext.lower()
    parent_stem = parent.lower()[:max(3, len(parent) - 2)]
    # ограничимся фрагментом около маркеров
    for marker in DERIVATION_MARKERS:
        for m in re.finditer(re.escape(marker), text):
            window = text[m.start(): m.start() + 200]
            if parent_stem in window:
                return True
    return False


def verify_chain(chain: list[str], session=None) -> tuple[bool, list[dict]]:
    """Проверяет цепочку A → B → C … по Викисловарю.

    Возвращает (всё_подтверждено, steps), где steps — список
    {from, to, source, confirmed}. Неподтверждённый шаг ⇒ задание бракуется.
    """
    steps: list[dict] = []
    all_ok = True
    for parent, child in zip(chain, chain[1:]):
        wikitext = fetch_wikitext(child, session=session)
        confirmed = confirms_derivation(wikitext or "", parent)
        all_ok = all_ok and confirmed
        steps.append({
            "from": parent, "to": child,
            "source": article_url(child),
            "confirmed": confirmed,
        })
    return all_ok, steps

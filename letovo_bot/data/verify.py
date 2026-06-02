"""Офлайн-выверка банка (§5.3–5.4). Запускается разово, не в рантайме.

  * verify_orthograms — сверка единиц words/зад.1 с Розенталем/Лопатиным через
    сильную модель Claude. verified=1 только при confident=true; иначе строка
    уходит в for_manual_review.csv.
  * verify_chains — выверка цепочек зад. 9 по Викисловарю (data/wiktionary.py).

LLM здесь НИЧЕГО не придумывает: она лишь подтверждает/опровергает уже
введённый человеком ответ и помечает уверенность.
"""
from __future__ import annotations

import csv
import json
import sqlite3
from pathlib import Path

from .. import config
from ..core import db
from ..core.llm import safe_parse_json
from . import wiktionary

try:  # pragma: no cover
    import anthropic
except Exception:  # pragma: no cover
    anthropic = None

VERIFY_SYSTEM = (
    "Ты — корректор по русской орфографии. Тебе дают слово с пропуском и "
    "предполагаемый ответ. Сверь с правилами Розенталя/Лопатина. НЕ придумывай "
    "новый ответ — только подтверди или опровергни данный. Верни строго JSON: "
    "{\"answer\": str, \"type\": str, \"confident\": bool, \"note\": str}."
)


def _client():
    if not config.ANTHROPIC_API_KEY or anthropic is None:
        return None
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)


def verify_orthograms(conn: sqlite3.Connection, review_csv: str | Path = "for_manual_review.csv") -> int:
    """Сверяет записи words. Возвращает число подтверждённых (verified=1)."""
    client = _client()
    rows = conn.execute("SELECT * FROM words").fetchall()
    confirmed = 0
    review: list[dict] = []
    for r in rows:
        if client is None:
            review.append({"id": r["id"], "word": r["word_gapped"], "note": "нет API-ключа"})
            continue
        prompt = (f"Слово: {r['word_gapped']}\nПредполагаемая буква: {r['answer_letter']}\n"
                  f"Проверочное/тип: {r['check_word']} / {r['orthogram_type']}")
        try:  # pragma: no cover - сеть
            msg = client.messages.create(
                model=config.ANTHROPIC_MODEL_VERIFY, max_tokens=300,
                system=VERIFY_SYSTEM, messages=[{"role": "user", "content": prompt}])
            text = "".join(b.text for b in msg.content if getattr(b, "type", None) == "text")
        except Exception as e:  # pragma: no cover
            review.append({"id": r["id"], "word": r["word_gapped"], "note": f"ошибка API: {e}"})
            continue
        data = safe_parse_json(text)
        if data and data.get("confident") and data.get("answer", "").lower() == (r["answer_letter"] or "").lower():
            conn.execute("UPDATE words SET verified=1 WHERE id=?", (r["id"],))
            confirmed += 1
        else:
            review.append({"id": r["id"], "word": r["word_gapped"],
                           "note": (data or {}).get("note", "не подтверждено")})
    conn.commit()
    if review:
        _write_review(review, review_csv)
    return confirmed


def verify_chains(conn: sqlite3.Connection, review_csv: str | Path = "for_manual_review_9.csv") -> int:
    """Перепроверяет цепочки зад. 9 по Викисловарю. Возвращает число подтверждённых."""
    import json as _json
    confirmed = 0
    review: list[dict] = []
    rows = conn.execute("SELECT id, answer_json FROM tasks WHERE task_type=9").fetchall()
    for r in rows:
        answer = _json.loads(r["answer_json"])
        ok, steps = wiktionary.verify_chain(answer["chain"])
        if ok:
            answer["steps"] = steps
            conn.execute("UPDATE tasks SET answer_json=? WHERE id=?",
                         (_json.dumps(answer, ensure_ascii=False), r["id"]))
            confirmed += 1
        else:
            unconfirmed = [s for s in steps if not s["confirmed"]]
            review.append({"id": r["id"], "chain": " → ".join(answer["chain"]),
                           "note": f"не подтверждены шаги: {unconfirmed}"})
    conn.commit()
    if review:
        _write_review(review, review_csv)
    return confirmed


def verify_phonetics(conn: sqlite3.Connection, review_csv: str | Path = "for_manual_review_7.csv") -> int:
    """Сверяет сохранённое число зад. 7 с приближённым расчётом (phonetics.py).

    НЕ меняет банк: лишь сигнализирует о расхождениях для ручной проверки —
    источник истины остаётся за человеком. Возвращает число совпавших заданий.
    """
    import json as _json

    from . import phonetics
    agreed = 0
    review: list[dict] = []
    rows = conn.execute("SELECT id, payload_json, answer_json FROM tasks WHERE task_type=7").fetchall()
    for r in rows:
        payload = _json.loads(r["payload_json"])
        answer = _json.loads(r["answer_json"])
        calc, steps = phonetics.count_sound(payload["sentence"], payload["sound"])
        if calc == answer.get("count"):
            agreed += 1
        else:
            review.append({"id": r["id"], "sentence": payload["sentence"],
                           "sound": payload["sound"], "stored": answer.get("count"),
                           "calculated": calc, "note": "; ".join(steps)})
    if review:
        _write_review(review, review_csv)
    return agreed


def _write_review(rows: list[dict], path: str | Path) -> None:
    path = Path(path)
    keys = sorted({k for row in rows for k in row})
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=keys)
        w.writeheader()
        w.writerows(rows)
    print(f"На ручную проверку: {len(rows)} строк → {path}")

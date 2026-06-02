import sqlite3
import pytest

from letovo_bot.core import db
from letovo_bot.data import build_bank


@pytest.fixture(scope="session")
def bank() -> sqlite3.Connection:
    """In-memory банк, собранный из тех же спецификаций, что и боевой."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    db.init_db(conn)
    body, lic, st, ph = build_bank.seed_text()
    text_id = db.insert_text(conn, body, lic, st, ph)
    body2, lic2, st2, ph2 = build_bank.seed_text2()
    text2_id = db.insert_text(conn, body2, lic2, st2, ph2)
    for (tt, p, a, r, topic, src) in build_bank.collect_task_specs(text_id, text2_id):
        db.insert_task(conn, tt, p, a, topic=topic, rubric=r, source=src, verified=True)
    return conn

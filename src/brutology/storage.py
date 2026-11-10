"""Ukladanie nahrávok do SQLite (jeden súbor, bez servera)."""
import sqlite3
import time
from pathlib import Path

DEFAULT_DB = Path(__file__).resolve().parents[2] / "data" / "logs" / "brutology.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id INTEGER PRIMARY KEY,
    started_at REAL NOT NULL,
    note TEXT
);
CREATE TABLE IF NOT EXISTS samples (
    session_id INTEGER NOT NULL REFERENCES sessions(id),
    t REAL NOT NULL,
    name TEXT NOT NULL,
    value REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_samples ON samples(session_id, name, t);
"""


class Storage:
    def __init__(self, path=DEFAULT_DB):
        path = Path(path)
        if str(path) != ":memory:":
            path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(path))
        self.db.executescript(SCHEMA)

    def start_session(self, note: str = "") -> int:
        cur = self.db.execute(
            "INSERT INTO sessions(started_at, note) VALUES (?, ?)", (time.time(), note)
        )
        self.db.commit()
        return cur.lastrowid

    def add_sample(self, session_id: int, t: float, values: dict) -> None:
        self.db.executemany(
            "INSERT INTO samples(session_id, t, name, value) VALUES (?, ?, ?, ?)",
            [(session_id, t, k, float(v)) for k, v in values.items()],
        )

    def commit(self) -> None:
        self.db.commit()

    def sessions(self):
        return self.db.execute("SELECT id, started_at, note FROM sessions ORDER BY id").fetchall()

    def series(self, session_id: int, name: str):
        """Vráti zoznam (t, hodnota) pre jednu veličinu."""
        return self.db.execute(
            "SELECT t, value FROM samples WHERE session_id=? AND name=? ORDER BY t",
            (session_id, name),
        ).fetchall()

    def close(self) -> None:
        self.db.commit()
        self.db.close()

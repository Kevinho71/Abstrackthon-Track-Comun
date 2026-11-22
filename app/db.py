import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import Optional

STATUSES = ("vendida", "cita_agendada", "pendiente_seguimiento", "resuelta", "perdida")
CLOSED_STATUSES = ("vendida", "resuelta", "perdida")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    telegram_id INTEGER PRIMARY KEY,
    name TEXT,
    wa_name TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS chats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_id INTEGER NOT NULL,
    customer TEXT,
    summary TEXT,
    status TEXT NOT NULL,
    next_action TEXT,
    amount REAL,
    follow_up_at TEXT,
    unanswered INTEGER NOT NULL DEFAULT 0,
    done INTEGER NOT NULL DEFAULT 0,
    last_reminded_at TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_chats_agent ON chats(agent_id, done);
"""


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds")


class Database:
    def __init__(self, path: str):
        self.path = path
        folder = os.path.dirname(os.path.abspath(path))
        os.makedirs(folder, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # --- agentes ---
    def upsert_agent(self, telegram_id: int, name: str) -> None:
        with self._conn() as c:
            c.execute(
                "INSERT INTO agents(telegram_id, name, created_at) VALUES(?,?,?) "
                "ON CONFLICT(telegram_id) DO UPDATE SET name=excluded.name",
                (telegram_id, name, iso(now_utc())),
            )

    def set_wa_name(self, telegram_id: int, wa_name: str) -> None:
        with self._conn() as c:
            c.execute("UPDATE agents SET wa_name=? WHERE telegram_id=?", (wa_name, telegram_id))

    def get_agent(self, telegram_id: int) -> Optional[sqlite3.Row]:
        with self._conn() as c:
            return c.execute("SELECT * FROM agents WHERE telegram_id=?", (telegram_id,)).fetchone()

    # --- chats ---
    def add_chat(
        self,
        agent_id: int,
        customer: str,
        summary: str,
        status: str,
        next_action: Optional[str],
        amount: Optional[float],
        follow_up_at: Optional[datetime],
        unanswered: bool,
    ) -> int:
        done = status in CLOSED_STATUSES and not unanswered
        ts = iso(now_utc())
        with self._conn() as c:
            cur = c.execute(
                "INSERT INTO chats(agent_id, customer, summary, status, next_action, amount, "
                "follow_up_at, unanswered, done, created_at, updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                (
                    agent_id, customer, summary, status, next_action, amount,
                    iso(follow_up_at) if follow_up_at else None,
                    int(unanswered), int(done), ts, ts,
                ),
            )
            return cur.lastrowid

    def get_chat(self, chat_id: int, agent_id: int) -> Optional[sqlite3.Row]:
        with self._conn() as c:
            return c.execute(
                "SELECT * FROM chats WHERE id=? AND agent_id=?", (chat_id, agent_id)
            ).fetchone()

    def set_status(self, chat_id: int, agent_id: int, status: str) -> bool:
        done = int(status in CLOSED_STATUSES)
        with self._conn() as c:
            cur = c.execute(
                "UPDATE chats SET status=?, done=?, unanswered=CASE WHEN ?=1 THEN 0 ELSE unanswered END, "
                "updated_at=? WHERE id=? AND agent_id=?",
                (status, done, done, iso(now_utc()), chat_id, agent_id),
            )
            return cur.rowcount > 0

    def mark_done(self, chat_id: int, agent_id: int) -> bool:
        with self._conn() as c:
            cur = c.execute(
                "UPDATE chats SET done=1, unanswered=0, updated_at=? WHERE id=? AND agent_id=?",
                (iso(now_utc()), chat_id, agent_id),
            )
            return cur.rowcount > 0

    def snooze(self, chat_id: int, agent_id: int, minutes: int) -> bool:
        when = iso(now_utc() + timedelta(minutes=minutes))
        with self._conn() as c:
            cur = c.execute(
                "UPDATE chats SET follow_up_at=?, unanswered=0, updated_at=? WHERE id=? AND agent_id=?",
                (when, iso(now_utc()), chat_id, agent_id),
            )
            return cur.rowcount > 0

    def pending(self, agent_id: int, limit: int = 20) -> list[sqlite3.Row]:
        with self._conn() as c:
            return c.execute(
                "SELECT * FROM chats WHERE agent_id=? AND done=0 "
                "ORDER BY unanswered DESC, COALESCE(follow_up_at, '9999') ASC LIMIT ?",
                (agent_id, limit),
            ).fetchall()

    def stats(self, agent_id: int) -> dict[str, int]:
        with self._conn() as c:
            rows = c.execute(
                "SELECT status, COUNT(*) n FROM chats WHERE agent_id=? GROUP BY status", (agent_id,)
            ).fetchall()
            unanswered = c.execute(
                "SELECT COUNT(*) FROM chats WHERE agent_id=? AND done=0 AND unanswered=1", (agent_id,)
            ).fetchone()[0]
        out = {r["status"]: r["n"] for r in rows}
        out["_sin_responder"] = unanswered
        return out

    # --- recordatorios ---
    def due_reminders(self, cooldown_min: int) -> list[sqlite3.Row]:
        now = now_utc()
        with self._conn() as c:
            return c.execute(
                "SELECT * FROM chats WHERE done=0 AND "
                "(unanswered=1 OR (follow_up_at IS NOT NULL AND follow_up_at<=?)) AND "
                "(last_reminded_at IS NULL OR last_reminded_at<=?)",
                (iso(now), iso(now - timedelta(minutes=cooldown_min))),
            ).fetchall()

    def mark_reminded(self, chat_id: int) -> None:
        with self._conn() as c:
            c.execute("UPDATE chats SET last_reminded_at=? WHERE id=?", (iso(now_utc()), chat_id))

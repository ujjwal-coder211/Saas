"""
src/storage/database.py

Shared aiosqlite connection used for:
  - `progress`  : dedupe ledger (query_hash primary key) so re-runs skip work
                  already done.
  - `usage`     : token/cost metrics, one row per successful API call.

A single connection is reused across the app (SQLite handles concurrent
access from one process fine as long as writes are serialized), guarded by
an asyncio.Lock so overlapping worker tasks don't race on writes.
"""

import asyncio
import aiosqlite


SCHEMA = """
CREATE TABLE IF NOT EXISTS progress (
    hash TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS usage (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model TEXT NOT NULL,
    prompt_tokens INTEGER NOT NULL,
    completion_tokens INTEGER NOT NULL,
    total_tokens INTEGER NOT NULL,
    estimated_cost_usd REAL NOT NULL,
    timestamp REAL NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_model ON usage(model);
"""


class Database:
    def __init__(self, db_path: str):
        self.db_path = db_path
        self._conn: aiosqlite.Connection | None = None
        self._lock = asyncio.Lock()

    async def connect(self):
        self._conn = await aiosqlite.connect(self.db_path)
        # WAL mode gives better concurrent read/write behavior for this
        # single-writer, many-readers-ish workload.
        await self._conn.execute("PRAGMA journal_mode=WAL;")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self):
        if self._conn:
            await self._conn.commit()
            await self._conn.close()

    async def is_done(self, query_hash: str) -> bool:
        async with self._conn.execute(
            "SELECT 1 FROM progress WHERE hash = ?", (query_hash,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None

    async def mark_done(self, query_hash: str, model: str, timestamp: float):
        async with self._lock:
            await self._conn.execute(
                "INSERT OR IGNORE INTO progress (hash, model, created_at) VALUES (?, ?, ?)",
                (query_hash, model, timestamp),
            )
            await self._conn.commit()

    async def record_usage(self, usage_record) -> None:
        async with self._lock:
            await self._conn.execute(
                """INSERT INTO usage
                   (model, prompt_tokens, completion_tokens, total_tokens,
                    estimated_cost_usd, timestamp)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (
                    usage_record.model,
                    usage_record.prompt_tokens,
                    usage_record.completion_tokens,
                    usage_record.total_tokens,
                    usage_record.estimated_cost_usd,
                    usage_record.timestamp,
                ),
            )
            await self._conn.commit()

    async def cost_summary(self) -> list[dict]:
        query = """
            SELECT model,
                   COUNT(*) as requests,
                   SUM(prompt_tokens) as prompt_tokens,
                   SUM(completion_tokens) as completion_tokens,
                   SUM(estimated_cost_usd) as estimated_cost_usd
            FROM usage
            GROUP BY model
        """
        async with self._conn.execute(query) as cursor:
            rows = await cursor.fetchall()
            cols = [d[0] for d in cursor.description]
            return [dict(zip(cols, row)) for row in rows]

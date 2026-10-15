"""SQLite-backed record of every album in a batch and what happened to it.
Survives restarts, so a long matching run can resume and nothing is forgotten."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path

PENDING, READY, REVIEW, MISSING = "pending", "ready", "review", "missing"
IN_PICARD, DONE, PROBLEM, SKIPPED = "in_picard", "done", "problem", "skipped"
PROCESSING = "processing"
STATUSES = (PENDING, READY, REVIEW, MISSING, IN_PICARD, PROCESSING, DONE, PROBLEM, SKIPPED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS albums (
    path TEXT PRIMARY KEY,
    root TEXT NOT NULL,
    status TEXT NOT NULL,
    artist TEXT, title TEXT, year TEXT,
    tracks INTEGER, duration_ms INTEGER,
    fingerprint TEXT,
    release_mbid TEXT,
    confidence REAL,
    verdict TEXT,
    message TEXT,
    updated REAL,
    processed REAL
);
CREATE INDEX IF NOT EXISTS albums_root_status ON albums(root, status);
"""


class BatchStore:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        with self._conn() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _conn(self):
        with self._lock:
            conn = sqlite3.connect(self.path, timeout=30)
            conn.row_factory = sqlite3.Row
            try:
                yield conn
                conn.commit()
            finally:
                conn.close()

    # -- writes -------------------------------------------------------------

    def add_found(self, root: str, paths: list[str]) -> tuple[int, int]:
        """Register discovered albums. Existing rows are kept untouched.
        Returns (new, already_known)."""
        new = 0
        now = time.time()
        with self._conn() as conn:
            for path in paths:
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO albums(path, root, status, updated) VALUES (?, ?, ?, ?)",
                    (path, root, PENDING, now),
                )
                new += cursor.rowcount
        return new, len(paths) - new

    def update(self, path: str, **fields) -> None:
        if "verdict" in fields and not isinstance(fields["verdict"], (str, type(None))):
            fields["verdict"] = json.dumps(fields["verdict"])
        fields["updated"] = time.time()
        columns = ", ".join(f"{k} = ?" for k in fields)
        with self._conn() as conn:
            conn.execute(f"UPDATE albums SET {columns} WHERE path = ?", (*fields.values(), path))

    def forget_missing(self, root: str, existing: set[str]) -> int:
        """Drop pending/triaged rows whose folder no longer exists under this root.
        Rows already sent to Picard or finished are kept as history."""
        removed = 0
        with self._conn() as conn:
            rows = conn.execute("SELECT path, status FROM albums WHERE root = ?", (root,)).fetchall()
            for row in rows:
                if row["path"] not in existing and row["status"] in (PENDING, READY, REVIEW, MISSING, SKIPPED):
                    conn.execute("DELETE FROM albums WHERE path = ?", (row["path"],))
                    removed += 1
        return removed

    # -- reads --------------------------------------------------------------

    @staticmethod
    def _row(row: sqlite3.Row) -> dict:
        data = dict(row)
        verdict = data.get("verdict")
        data["verdict"] = json.loads(verdict) if verdict else None
        return data

    def get(self, path: str) -> dict | None:
        with self._conn() as conn:
            row = conn.execute("SELECT * FROM albums WHERE path = ?", (path,)).fetchone()
        return self._row(row) if row else None

    def counts(self, root: str) -> dict[str, int]:
        with self._conn() as conn:
            rows = conn.execute(
                "SELECT status, COUNT(*) AS n FROM albums WHERE root = ? GROUP BY status", (root,)
            ).fetchall()
        counts = {status: 0 for status in STATUSES}
        counts.update({row["status"]: row["n"] for row in rows})
        counts["total"] = sum(counts[s] for s in STATUSES)
        return counts

    def list(self, root: str, status: str | None = None, query: str = "", offset: int = 0, limit: int = 100) -> list[dict]:
        sql, args = "SELECT * FROM albums WHERE root = ?", [root]
        if status:
            sql += " AND status = ?"
            args.append(status)
        if query:
            sql += " AND (path LIKE ? OR artist LIKE ? OR title LIKE ?)"
            args += [f"%{query}%"] * 3
        sql += " ORDER BY path COLLATE NOCASE LIMIT ? OFFSET ?"
        args += [limit, offset]
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [self._row(r) for r in rows]

    def paths_with_status(self, root: str, status: str, limit: int | None = None) -> list[str]:
        sql = "SELECT path FROM albums WHERE root = ? AND status = ? ORDER BY path COLLATE NOCASE"
        args: list = [root, status]
        if limit:
            sql += " LIMIT ?"
            args.append(limit)
        with self._conn() as conn:
            return [r["path"] for r in conn.execute(sql, args).fetchall()]

    def recover_interrupted(self) -> int:
        """A crash mid-processing leaves rows in 'processing'. Never assume what
        happened: flag them for a human to check."""
        with self._conn() as conn:
            cursor = conn.execute(
                "UPDATE albums SET status = ?, message = ?, updated = ? WHERE status = ?",
                (PROBLEM, "Processing was interrupted. Check this folder and Picard before retrying.", time.time(), PROCESSING),
            )
            return cursor.rowcount

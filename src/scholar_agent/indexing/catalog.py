"""SQLite catalog: note metadata, wikilink graph, embedding-model guard, ingestion diagnostics."""

from __future__ import annotations

import json
import sqlite3
import threading
from contextlib import contextmanager
from pathlib import Path

from scholar_agent.ingestion.models import Document
from scholar_agent.text import normalize

SCHEMA = """
CREATE TABLE IF NOT EXISTS notes (
  source TEXT NOT NULL, path TEXT NOT NULL, title TEXT NOT NULL, title_norm TEXT NOT NULL,
  kind TEXT, lang TEXT, hash TEXT, mtime REAL, n_chunks INTEGER DEFAULT 0,
  n_chars INTEGER DEFAULT 0, meta TEXT,
  PRIMARY KEY (source, path)
);
CREATE INDEX IF NOT EXISTS idx_notes_title ON notes(title_norm);
CREATE TABLE IF NOT EXISTS links (
  source TEXT NOT NULL, src_path TEXT NOT NULL, target TEXT NOT NULL, target_norm TEXT NOT NULL,
  label TEXT, line INTEGER, section TEXT
);
CREATE INDEX IF NOT EXISTS idx_links_src ON links(source, src_path);
CREATE INDEX IF NOT EXISTS idx_links_target ON links(source, target_norm);
CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT);
"""


class _Rows:
    """Fully fetched query result, so the connection lock is never held by a lazy cursor."""

    def __init__(self, rows: list[sqlite3.Row]):
        self._rows = rows

    def fetchall(self) -> list[sqlite3.Row]:
        return self._rows

    def fetchone(self) -> sqlite3.Row | None:
        return self._rows[0] if self._rows else None

    def __iter__(self):
        return iter(self._rows)


class Catalog:
    """Thread-safe: the agent seeds notes and papers in parallel threads."""

    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(SCHEMA)

    def _q(self, sql: str, args: tuple | list = ()) -> _Rows:
        with self._lock:
            return _Rows(self._conn.execute(sql, args).fetchall())

    @contextmanager
    def tx(self):
        with self._lock:
            try:
                yield self._conn
                self._conn.commit()
            except Exception:
                self._conn.rollback()
                raise

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # ---- meta -----------------------------------------------------------
    def get_meta(self, key: str) -> str | None:
        row = self._q("SELECT value FROM meta WHERE key=?", (key,)).fetchone()
        return row["value"] if row else None

    def set_meta(self, key: str, value: str) -> None:
        with self.tx() as c:
            c.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", (key, value))

    def reset(self) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM notes")
            c.execute("DELETE FROM links")

    # ---- notes ----------------------------------------------------------
    def hashes(self, source: str) -> dict[str, str]:
        rows = self._q("SELECT path, hash FROM notes WHERE source=?", (source,))
        return {r["path"]: r["hash"] for r in rows}

    def upsert_note(self, doc: Document, n_chunks: int) -> None:
        meta = json.dumps(
            {"tags": doc.tags, "urls": doc.urls[:50], "embeds": doc.embeds[:50]}, ensure_ascii=False
        )
        with self.tx() as c:
            c.execute(
                "INSERT OR REPLACE INTO notes(source,path,title,title_norm,kind,lang,hash,mtime,"
                "n_chunks,n_chars,meta) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (doc.source, doc.path, doc.title, normalize(doc.title), doc.kind, doc.lang,
                 doc.content_hash, doc.mtime, n_chunks, len(doc.body.strip()), meta),
            )
            c.execute("DELETE FROM links WHERE source=? AND src_path=?", (doc.source, doc.path))
            c.executemany(
                "INSERT INTO links(source,src_path,target,target_norm,label,line,section) "
                "VALUES (?,?,?,?,?,?,?)",
                [(doc.source, doc.path, lk.target, normalize(lk.target), lk.label, lk.line, lk.section)
                 for lk in doc.links],
            )

    def delete_note(self, source: str, path: str) -> None:
        with self.tx() as c:
            c.execute("DELETE FROM notes WHERE source=? AND path=?", (source, path))
            c.execute("DELETE FROM links WHERE source=? AND src_path=?", (source, path))

    def find_note(self, name: str, source: str | None = None) -> sqlite3.Row | None:
        """Resolve a title, wikilink target or relative path to a note row."""
        cleaned = name.removesuffix(".md")
        sql = "SELECT * FROM notes WHERE (title_norm=? OR path=? OR path=?)"
        args: list = [normalize(cleaned), name, name + ".md"]
        if source:
            sql += " AND source=?"
            args.append(source)
        return self._q(sql + " LIMIT 1", args).fetchone()

    def neighbours(self, source: str, path: str, limit: int = 10) -> list[dict]:
        """1-hop wikilink neighbours (outgoing + incoming) with their relation labels."""
        outgoing = self._q(
            "SELECT n.source, n.path, n.title, l.label, 'out' AS direction FROM links l "
            "JOIN notes n ON n.source=l.source AND n.title_norm=l.target_norm "
            "WHERE l.source=? AND l.src_path=? LIMIT ?",
            (source, path, limit),
        ).fetchall()
        row = self._q(
            "SELECT title_norm FROM notes WHERE source=? AND path=?", (source, path)
        ).fetchone()
        incoming: list[sqlite3.Row] = []
        if row:
            incoming = self._q(
                "SELECT n.source, n.path, n.title, l.label, 'in' AS direction FROM links l "
                "JOIN notes n ON n.source=l.source AND n.path=l.src_path "
                "WHERE l.source=? AND l.target_norm=? LIMIT ?",
                (source, row["title_norm"], limit),
            ).fetchall()
        seen: set[str] = set()
        result: list[dict] = []
        for r in [*outgoing, *incoming]:
            if r["path"] not in seen and r["path"] != path:
                seen.add(r["path"])
                result.append(dict(r))
        return result[:limit]

    def links_of(self, source: str, path: str) -> list[sqlite3.Row]:
        return self._q(
            "SELECT target, label, line FROM links WHERE source=? AND src_path=? ORDER BY line",
            (source, path),
        ).fetchall()

    # ---- diagnostics ----------------------------------------------------
    def _scalar(self, sql: str) -> int:
        row = self._q(sql).fetchone()
        return int(row[0]) if row else 0

    def stats(self) -> dict:
        q = self._q
        return {
            "notes": self._scalar("SELECT COUNT(*) FROM notes"),
            "chunks": self._scalar("SELECT COALESCE(SUM(n_chunks),0) FROM notes"),
            "links": self._scalar("SELECT COUNT(*) FROM links"),
            "by_kind": {r[0]: r[1] for r in q("SELECT kind, COUNT(*) FROM notes GROUP BY kind")},
            "by_lang": {r[0]: r[1] for r in q("SELECT lang, COUNT(*) FROM notes GROUP BY lang")},
        }

    def doctor(self) -> dict[str, list]:
        q = self._q
        sep = " | "
        return {
            "empty_notes": [
                r["path"] for r in q("SELECT path FROM notes WHERE n_chars < 20 ORDER BY path LIMIT 200")
            ],
            "broken_links": [
                dict(r) for r in q(
                    "SELECT l.src_path, l.target FROM links l LEFT JOIN notes n "
                    "ON n.source=l.source AND n.title_norm=l.target_norm WHERE n.path IS NULL "
                    "ORDER BY l.src_path LIMIT 200"
                )
            ],
            "duplicate_content": [
                dict(r) for r in q(
                    "SELECT hash, GROUP_CONCAT(path, ?) AS paths, COUNT(*) AS n FROM notes "
                    "WHERE n_chars >= 20 GROUP BY hash HAVING n > 1 LIMIT 100",
                    (sep,),
                )
            ],
            "duplicate_titles": [
                dict(r) for r in q(
                    "SELECT title_norm, GROUP_CONCAT(path, ?) AS paths, COUNT(*) AS n FROM notes "
                    "GROUP BY source, title_norm HAVING n > 1 LIMIT 100",
                    (sep,),
                )
            ],
            "orphans": [
                r["path"] for r in q(
                    "SELECT n.path FROM notes n WHERE n.kind != ? AND NOT EXISTS ("
                    "SELECT 1 FROM links l WHERE l.source=n.source AND l.target_norm=n.title_norm) "
                    "AND NOT EXISTS (SELECT 1 FROM links l2 WHERE l2.source=n.source AND "
                    "l2.src_path=n.path) LIMIT 200",
                    ("map",),
                )
            ],
        }

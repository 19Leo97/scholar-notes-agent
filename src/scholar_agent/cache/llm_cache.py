"""SQLite LLM response cache so re-running an evaluation costs nothing.

Cached generations keep their `usage_metadata`, so reports still show what a live run costs.
"""

from __future__ import annotations

import hashlib
import sqlite3
import threading
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from langchain_core.caches import BaseCache
from langchain_core.load import dumps, loads
from langchain_core.outputs import Generation


class SQLiteLLMCache(BaseCache):
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._lock = threading.Lock()
        self._db.execute("CREATE TABLE IF NOT EXISTS llm_cache (key TEXT PRIMARY KEY, value TEXT)")
        self.hits = 0
        self.misses = 0

    @staticmethod
    def _key(prompt: str, llm_string: str) -> str:
        return hashlib.sha256((llm_string + "\x00" + prompt).encode()).hexdigest()

    def lookup(self, prompt: str, llm_string: str) -> Sequence[Generation] | None:
        with self._lock:
            row = self._db.execute("SELECT value FROM llm_cache WHERE key=?", (self._key(prompt, llm_string),)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return loads(row[0])

    def update(self, prompt: str, llm_string: str, return_val: Sequence[Generation]) -> None:
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO llm_cache(key, value) VALUES (?, ?)",
                (self._key(prompt, llm_string), dumps(list(return_val))),
            )
            self._db.commit()

    def clear(self, **kwargs: Any) -> None:
        with self._lock:
            self._db.execute("DELETE FROM llm_cache")
            self._db.commit()

"""Loader for unstructured .txt notes (no frontmatter, no wikilinks)."""

from __future__ import annotations

import hashlib
from pathlib import Path

from scholar_agent.ingestion.loaders.base import read_text_robust, register
from scholar_agent.ingestion.loaders.obsidian import URL_PATTERN, clean_stem
from scholar_agent.ingestion.models import Document
from scholar_agent.text import detect_language


class PlainTextLoader:
    extensions = (".txt",)

    def load(self, source: str, root: Path, file: Path) -> Document:
        text, raw = read_text_robust(file)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        return Document(
            source=source,
            path=file.relative_to(root).as_posix(),
            title=clean_stem(file.stem),
            kind="note",
            lang=detect_language(text),
            frontmatter={},
            body=text,
            body_start_line=1,
            urls=sorted(set(URL_PATTERN.findall(text))),
            content_hash=hashlib.sha1(raw).hexdigest(),
            mtime=file.stat().st_mtime,
        )


register(PlainTextLoader())

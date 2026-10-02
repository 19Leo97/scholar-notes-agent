"""Data structures produced by ingestion."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Link:
    target: str            # note title as written in [[...]]
    label: str | None      # semantic label such as "Parte de" / "Relacionada con"
    line: int              # 1-based absolute line number
    section: str | None = None


@dataclass
class Document:
    source: str                      # logical name of the notes collection (vault)
    path: str                        # path relative to the collection root, posix separators
    title: str
    kind: str                        # concept | hypothesis | question | summary | synthesis | map | note
    lang: str                        # es | en | und
    frontmatter: dict[str, Any]
    body: str
    body_start_line: int             # 1-based line of the first body line in the file
    links: list[Link] = field(default_factory=list)
    embeds: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    content_hash: str = ""
    mtime: float = 0.0

    @property
    def is_own_idea(self) -> bool:
        return self.kind == "hypothesis"

    @property
    def tags(self) -> list[str]:
        raw = self.frontmatter.get("tags") or []
        return [str(t) for t in raw] if isinstance(raw, list) else [str(raw)]


@dataclass
class Chunk:
    source: str
    path: str
    index: int
    title: str
    heading: str                     # "Section > Subsection" or ""
    text: str                        # original markdown shown to the model
    embed_text: str                  # cleaned text + contextual header used for embeddings
    line_start: int
    line_end: int
    kind: str
    lang: str
    tags: list[str] = field(default_factory=list)
    images: list[str] = field(default_factory=list)
    urls: list[str] = field(default_factory=list)
    extra: dict[str, Any] = field(default_factory=dict)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.path}:{self.index}"

"""Obsidian / Markdown loader: frontmatter, wikilinks (with relation labels), embeds, URLs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

import yaml

from scholar_agent.ingestion.loaders.base import read_text_robust, register
from scholar_agent.ingestion.models import Document, Link
from scholar_agent.text import detect_language

# Link targets may contain single bracket pairs, e.g. [[RES — [1] Paper title]]
TARGET = r"((?:[^\[\]|#\n]|\[[^\[\]\n]*\])+)"
_WIKILINK = re.compile(r"(?<!!)\[\[" + TARGET + r"(?:#([^\]|\n]+))?(?:\|([^\]\n]+))?\]\]")
_EMBED = re.compile(r"!\[\[" + TARGET + r"(?:#[^\]|\n]+)?(?:\|[^\]\n]+)?\]\]")
_MD_IMAGE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)[^)]*\)")
URL_PATTERN = re.compile(r"https?://[^\s)>\]\x22\x27]+")
_RELATION = re.compile(r"^\s*[-*]?\s*\*\*(.+?)\*\*\s*(?:→|->|:)\s*(.*)$")
_NOTION_HASH = re.compile(r"\s+[0-9a-f]{32}$")
_COMMENT = re.compile(r"%%.*?%%", re.DOTALL)
_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
_PREFIX = re.compile(r"^([A-Z]{2,5})\s+[—–-]\s+")

PREFIX_KIND = {
    "HIP": "hypothesis", "CON": "concept", "PRG": "question",
    "RES": "summary", "SIN": "synthesis", "MAPA": "map",
}
TIPO_KIND = {
    "hipótesis": "hypothesis", "hipotesis": "hypothesis", "concepto": "concept",
    "pregunta": "question", "resumen": "summary", "síntesis": "synthesis",
    "sintesis": "synthesis", "mapa": "map",
}


def blank_comments(text: str) -> str:
    """Remove Obsidian %%comments%% while preserving line numbering."""
    return _COMMENT.sub(lambda m: "\n" * m.group(0).count("\n"), text)


def split_frontmatter(text: str) -> tuple[dict, str, int]:
    """Return (frontmatter, body, 1-based line where the body starts)."""
    lines = text.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, text, 1
    for i in range(1, min(len(lines), 200)):
        if lines[i].strip() in {"---", "..."}:
            try:
                meta = yaml.safe_load("\n".join(lines[1:i])) or {}
            except yaml.YAMLError:
                meta = {}
            if not isinstance(meta, dict):
                meta = {}
            return meta, "\n".join(lines[i + 1 :]), i + 2
    return {}, text, 1


def clean_stem(stem: str) -> str:
    """Drop Notion export hashes: 'Articulo 1 ... 3477ab3a...' -> 'Articulo 1 ...'."""
    return _NOTION_HASH.sub("", stem).strip()


def kind_from(stem: str, meta: dict) -> str:
    tipo = str(meta.get("tipo") or meta.get("type") or "").strip().lower()
    if tipo in TIPO_KIND:
        return TIPO_KIND[tipo]
    if tipo in set(PREFIX_KIND.values()):
        return tipo
    m = _PREFIX.match(stem)
    if m and m.group(1) in PREFIX_KIND:
        return PREFIX_KIND[m.group(1)]
    return "note"


def extract_links(body: str, first_line: int) -> list[Link]:
    """Wikilinks with their relation label (`- **Parte de** → [[X]]`) and enclosing section."""
    links: list[Link] = []
    section: str | None = None
    in_fence = False
    for offset, line in enumerate(body.split("\n")):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        heading = _HEADING.match(line)
        if heading:
            section = heading.group(1)
        relation = _RELATION.match(line)
        label = relation.group(1).strip() if relation else None
        for m in _WIKILINK.finditer(line):
            links.append(Link(m.group(1).strip(), label, first_line + offset, section))
    return links


class ObsidianLoader:
    extensions = (".md", ".markdown")

    def load(self, source: str, root: Path, file: Path) -> Document:
        text, raw = read_text_robust(file)
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        meta, body, start = split_frontmatter(text)
        body = blank_comments(body)
        stem = clean_stem(file.stem)  # wikilinks resolve by file name, so it is the canonical title
        embeds = {m.group(1).strip() for m in _EMBED.finditer(body)}
        embeds |= {m.group(1) for m in _MD_IMAGE.finditer(body) if not m.group(1).startswith("http")}
        return Document(
            source=source,
            path=file.relative_to(root).as_posix(),
            title=stem,
            kind=kind_from(stem, meta),
            lang=detect_language(body),
            frontmatter=meta,
            body=body,
            body_start_line=start,
            links=extract_links(body, start),
            embeds=sorted(embeds),
            urls=sorted(set(URL_PATTERN.findall(body))),
            content_hash=hashlib.sha1(raw).hexdigest(),
            mtime=file.stat().st_mtime,
        )


register(ObsidianLoader())

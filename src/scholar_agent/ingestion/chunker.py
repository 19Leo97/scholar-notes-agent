"""Heading-aware chunking that preserves exact line ranges for citations."""

from __future__ import annotations

import re
from dataclasses import dataclass

from scholar_agent.ingestion.loaders.obsidian import _EMBED, _MD_IMAGE, TARGET, URL_PATTERN
from scholar_agent.ingestion.models import Chunk, Document
from scholar_agent.text import approx_tokens

_HEADING = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_WIKI_ALIAS = re.compile(r"\[\[" + TARGET + r"(?:#[^\]|\n]+)?\|([^\]\n]+)\]\]")
_WIKI = re.compile(r"\[\[" + TARGET + r"(?:#[^\]|\n]+)?\]\]")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")


@dataclass
class _Block:
    heading: str
    lines: list[tuple[int, str]]  # (absolute line number, text)


def clean_for_embedding(text: str) -> str:
    """Simplify Obsidian syntax so embeddings see natural language."""
    text = _EMBED.sub("", text)
    text = _MD_IMAGE.sub("", text)
    text = _WIKI_ALIAS.sub(lambda m: m.group(2), text)
    text = _WIKI.sub(lambda m: m.group(1), text)
    text = URL_PATTERN.sub("", text)
    text = re.sub(r"\*\*|__|`", "", text)
    text = re.sub(r"^[>\-\*\s]+(?=\S)", "", text, flags=re.MULTILINE)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _sections(doc: Document) -> list[_Block]:
    blocks: list[_Block] = []
    stack: list[tuple[int, str]] = []
    current = _Block("", [])
    in_fence = False
    for offset, line in enumerate(doc.body.split("\n")):
        number = doc.body_start_line + offset
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
        heading = None if in_fence else _HEADING.match(line)
        if heading:
            if current.lines:
                blocks.append(current)
            level, title = len(heading.group(1)), heading.group(2)
            while stack and stack[-1][0] >= level:
                stack.pop()
            stack.append((level, title))
            # A lone H1 equal to the note title adds no information
            path = " > ".join(t for lv, t in stack if not (lv == 1 and t == doc.title))
            current = _Block(path, [(number, line)])
        else:
            current.lines.append((number, line))
    if current.lines:
        blocks.append(current)
    return blocks


def _split_block(block: _Block, max_tokens: int) -> list[list[tuple[int, str]]]:
    """Pack paragraphs into <= max_tokens windows; split oversized paragraphs by sentence."""
    paragraphs: list[list[tuple[int, str]]] = []
    buf: list[tuple[int, str]] = []
    for item in block.lines:
        if item[1].strip() == "":
            if buf:
                paragraphs.append(buf)
                buf = []
        else:
            buf.append(item)
    if buf:
        paragraphs.append(buf)

    pieces: list[list[tuple[int, str]]] = []
    for para in paragraphs:
        text = "\n".join(t for _, t in para)
        if approx_tokens(text) <= max_tokens:
            pieces.append(para)
            continue
        window: list[tuple[int, str]] = []
        size = 0
        for number, line in para:
            for sentence in _SENTENCE_END.split(line):
                cost = approx_tokens(sentence)
                if window and size + cost > max_tokens:
                    pieces.append(window)
                    window, size = [], 0
                window.append((number, sentence))
                size += cost
        if window:
            pieces.append(window)

    windows: list[list[tuple[int, str]]] = []
    current: list[tuple[int, str]] = []
    size = 0
    for piece in pieces:
        cost = approx_tokens("\n".join(t for _, t in piece))
        if current and size + cost > max_tokens:
            windows.append(current)
            current, size = [], 0
        current.extend(piece)
        size += cost
    if current:
        windows.append(current)
    return windows


def chunk_document(doc: Document, max_tokens: int = 450, min_tokens: int = 40) -> list[Chunk]:
    raw: list[tuple[str, int, int, str]] = []  # heading, start, end, text
    for block in _sections(doc):
        for window in _split_block(block, max_tokens):
            text = "\n".join(t for _, t in window).strip()
            if text:
                raw.append((block.heading, window[0][0], window[-1][0], text))

    # Merge tiny trailing fragments into the previous chunk of the same note
    merged: list[tuple[str, int, int, str]] = []
    for heading, start, end, text in raw:
        if merged and approx_tokens(text) < min_tokens:
            ph, ps, _pe, pt = merged[-1]
            if approx_tokens(pt) + approx_tokens(text) <= max_tokens:
                merged[-1] = (ph, ps, end, pt + "\n\n" + text)
                continue
        merged.append((heading, start, end, text))

    tags = doc.tags
    chunks: list[Chunk] = []
    for index, (heading, start, end, text) in enumerate(merged):
        header = doc.title + (f" > {heading}" if heading else "")
        if tags:
            header += f"\nTags: {', '.join(tags)}"
        chunks.append(
            Chunk(
                source=doc.source, path=doc.path, index=index, title=doc.title,
                heading=heading, text=text,
                embed_text=f"{header}\n{clean_for_embedding(text)}",
                line_start=start, line_end=end, kind=doc.kind, lang=doc.lang, tags=tags,
                images=sorted({m.group(1).strip() for m in _EMBED.finditer(text)}
                              | {m.group(1) for m in _MD_IMAGE.finditer(text)}),
                urls=sorted(set(URL_PATTERN.findall(text))),
                extra={k: doc.frontmatter[k] for k in ("doi", "año", "fuentes") if k in doc.frontmatter},
            )
        )
    return chunks

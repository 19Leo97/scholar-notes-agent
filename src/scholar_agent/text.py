"""Small, dependency-free text helpers shared across the package."""

from __future__ import annotations

import re
import unicodedata

_WORD = re.compile(r"[^\W_]+", re.UNICODE)

_STOP = {
    # English
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "is", "are", "was", "were",
    "be", "by", "with", "as", "at", "that", "this", "it", "from", "which", "not", "but", "can",
    # Spanish
    "el", "la", "los", "las", "un", "una", "unos", "unas", "y", "o", "de", "del", "al", "en",
    "por", "para", "con", "es", "son", "fue", "que", "se", "su", "sus", "lo", "como", "pero",
    "más", "mas", "este", "esta", "estos", "estas", "no", "si", "sí",
}
_ES_HINTS = {"el", "la", "los", "las", "de", "del", "que", "una", "por", "con", "para", "es", "se", "en"}
_EN_HINTS = {"the", "of", "and", "to", "in", "is", "that", "for", "with", "are", "this", "from"}


def strip_accents(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", text) if unicodedata.category(c) != "Mn")


def normalize(text: str) -> str:
    """Lowercase, accent-free, whitespace-collapsed form used for matching."""
    return " ".join(_WORD.findall(strip_accents(text).lower()))


def tokenize(text: str, drop_stop: bool = True) -> list[str]:
    tokens = _WORD.findall(strip_accents(text).lower())
    return [t for t in tokens if len(t) > 1 and not (drop_stop and t in _STOP)]


def approx_tokens(text: str) -> int:
    """Cheap token estimate (~3.6 chars/token for mixed ES/EN). Used only for budgeting."""
    return max(1, round(len(text) / 3.6))


def truncate_tokens(text: str, max_tokens: int) -> str:
    max_chars = int(max_tokens * 3.6)
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    boundary = max(cut.rfind(". "), cut.rfind("\n"))
    if boundary > max_chars * 0.6:
        cut = cut[: boundary + 1]
    return cut.rstrip() + " …"


def detect_language(text: str) -> str:
    """Return 'es', 'en' or 'und' using stop-word and accent heuristics."""
    words = [w.lower() for w in _WORD.findall(text)][:400]
    if not words:
        return "und"
    es = sum(w in _ES_HINTS for w in words) + sum(c in "ñáéíóúü¿¡" for c in text[:2000].lower()) * 0.5
    en = sum(w in _EN_HINTS for w in words)
    if es == en == 0:
        return "und"
    return "es" if es > en else "en"


def stable_hash(token: str, buckets: int = 1 << 20) -> int:
    import zlib

    return zlib.crc32(token.encode("utf-8")) % buckets

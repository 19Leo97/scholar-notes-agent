"""Loader protocol and extension registry. Add a format = add a module + register()."""

from __future__ import annotations

from pathlib import Path
from typing import Protocol

from scholar_agent.ingestion.models import Document


class Loader(Protocol):
    @property
    def extensions(self) -> tuple[str, ...]: ...

    def load(self, source: str, root: Path, file: Path) -> Document: ...


_REGISTRY: dict[str, Loader] = {}


def register(loader: Loader) -> None:
    for ext in loader.extensions:
        _REGISTRY[ext.lower()] = loader


def get_loader(path: Path) -> Loader | None:
    return _REGISTRY.get(path.suffix.lower())


def supported_extensions() -> set[str]:
    return set(_REGISTRY)


def read_text_robust(file: Path) -> tuple[str, bytes]:
    """Read text trying UTF-8 (with BOM) first, then Windows encodings common in old .txt notes."""
    raw = file.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return raw.decode(enc), raw
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace"), raw

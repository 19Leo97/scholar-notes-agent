"""Typed configuration: YAML defaults + environment overrides + privacy validation."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

Provider = Literal["groq", "gemini", "ollama"]
Role = Literal["router", "agent", "synthesizer", "judge"]
Mode = Literal["notes", "literature", "hybrid"]

PACKAGE_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = PACKAGE_ROOT / "config" / "default.yaml"
DEFAULT_PRICING = PACKAGE_ROOT / "config" / "pricing.yaml"


class PrivacyError(RuntimeError):
    """Raised when a configuration could expose private data to model training."""


class Paths(BaseModel):
    notes_dirs: list[str] = Field(default_factory=list)
    index_dir: str = ".index"
    cache_dir: str = ".cache"
    sqlite: str = ".index/catalog.sqlite"


class LLMSpec(BaseModel):
    provider: Provider
    model: str
    temperature: float = 0.0
    num_ctx: int | None = None  # Ollama only: context window (the server default may truncate long prompts)


class EmbeddingSpec(BaseModel):
    provider: Literal["ollama", "fastembed", "hash"] = "ollama"
    model: str = "bge-m3"
    batch_size: int = 32


class RerankerSpec(BaseModel):
    provider: Literal["none", "fastembed"] = "none"
    model: str = "jinaai/jina-reranker-v2-base-multilingual"


class ChunkingSpec(BaseModel):
    max_tokens: int = 450
    min_tokens: int = 40


class RetrievalSpec(BaseModel):
    candidates: int = 30
    top_k: int = 8
    mmr_lambda: float = 0.7
    graph_expand: bool = True
    graph_neighbours: int = 2


class ModeSpec(BaseModel):
    groups: list[Literal["notes", "literature", "web"]]


class BudgetSpec(BaseModel):
    max_cost_usd: float = 0.05
    max_input_tokens: int = 60000
    max_tool_calls: int = 8
    max_iterations: int = 5
    evidence_tokens_each: int = 350
    evidence_tokens_total: int = 6000


class PrivacySpec(BaseModel):
    gemini_paid_tier: bool = False
    outbound_ngram: int = 8


class LiteratureSpec(BaseModel):
    providers: list[Literal["openalex", "europepmc", "semantic_scholar", "arxiv"]] = [
        "openalex", "europepmc", "arxiv",
    ]
    per_provider: int = 8
    http_cache_days: float = 7.0
    verify_dois: bool = True


class WebSpec(BaseModel):
    provider: Literal["auto", "tavily", "ddgs"] = "auto"
    results: int = 5
    fetch_tokens: int = 1200


class Settings(BaseModel):
    paths: Paths = Field(default_factory=Paths)
    llm: dict[Role, LLMSpec]
    embeddings: EmbeddingSpec = Field(default_factory=EmbeddingSpec)
    reranker: RerankerSpec = Field(default_factory=RerankerSpec)
    chunking: ChunkingSpec = Field(default_factory=ChunkingSpec)
    retrieval: RetrievalSpec = Field(default_factory=RetrievalSpec)
    modes: dict[Mode, ModeSpec]
    budget: BudgetSpec = Field(default_factory=BudgetSpec)
    privacy: PrivacySpec = Field(default_factory=PrivacySpec)
    literature: LiteratureSpec = Field(default_factory=LiteratureSpec)
    web: WebSpec = Field(default_factory=WebSpec)
    pricing: dict[str, dict[str, float]] = Field(default_factory=dict)

    # ---- helpers -------------------------------------------------------
    def resolve(self, relative: str) -> Path:
        p = Path(relative)
        return p if p.is_absolute() else Path.cwd() / p

    @property
    def index_dir(self) -> Path:
        return self.resolve(self.paths.index_dir)

    @property
    def cache_dir(self) -> Path:
        return self.resolve(self.paths.cache_dir)

    @property
    def sqlite_path(self) -> Path:
        return self.resolve(self.paths.sqlite)

    def validate_privacy(self) -> None:
        """Refuse configurations that could send private data to training pipelines."""
        uses_gemini = any(spec.provider == "gemini" for spec in self.llm.values())
        if uses_gemini and not self.privacy.gemini_paid_tier:
            raise PrivacyError(
                "A role is configured to use Gemini but `gemini_paid_tier` is not confirmed. "
                "Free-tier Gemini may use your prompts to improve Google products. Set "
                "GEMINI_PAID_TIER=true only if your API key is on a paid (billing-enabled) plan, "
                "or switch the role to `groq` / `ollama`."
            )


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"1", "true", "yes", "on"}


def load_settings(config_path: str | Path | None = None, overrides: dict | None = None) -> Settings:
    """Load settings. Precedence (lowest to highest): defaults < user YAML < environment < explicit overrides."""
    load_dotenv(override=False)
    data = yaml.safe_load(DEFAULT_CONFIG.read_text(encoding="utf-8")) or {}
    if config_path:
        user = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
        data = _deep_merge(data, user)
    if "GEMINI_PAID_TIER" in os.environ:
        data.setdefault("privacy", {})["gemini_paid_tier"] = _truthy(os.environ["GEMINI_PAID_TIER"])
    if overrides:
        data = _deep_merge(data, overrides)
    pricing = yaml.safe_load(DEFAULT_PRICING.read_text(encoding="utf-8")) or {}
    data["pricing"] = pricing.get("models", {})
    return Settings.model_validate(data)

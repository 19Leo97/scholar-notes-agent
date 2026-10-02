"""Chat-model construction per role, usage-tracking config and robust structured output."""

from __future__ import annotations

import json
import os
import re
from typing import Any, TypeVar

from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from pydantic import BaseModel

from scholar_agent.budget.tracking import QueryTracker, UsageCallback
from scholar_agent.config import LLMSpec, Role, Settings

T = TypeVar("T", bound=BaseModel)


class MissingKeyError(RuntimeError):
    pass


def _require(var: str, provider: str) -> None:
    if not os.environ.get(var):
        raise MissingKeyError(f"{var} is not set (needed for provider '{provider}'). Copy .env.example to .env.")


def build_chat_model(spec: LLMSpec) -> BaseChatModel:
    if spec.provider == "groq":
        _require("GROQ_API_KEY", "groq")
        from langchain_groq import ChatGroq

        return ChatGroq(model=spec.model, temperature=spec.temperature, max_retries=2)
    if spec.provider == "gemini":
        _require("GOOGLE_API_KEY", "gemini")
        from langchain_google_genai import ChatGoogleGenerativeAI

        return ChatGoogleGenerativeAI(model=spec.model, temperature=spec.temperature, max_retries=2)
    from langchain_ollama import ChatOllama

    host = os.environ.get("OLLAMA_HOST")
    kwargs: dict[str, Any] = {"model": spec.model, "temperature": spec.temperature}
    if spec.num_ctx:
        kwargs["num_ctx"] = spec.num_ctx
    if host:
        kwargs["base_url"] = host if host.startswith("http") else f"http://{host}"
    return ChatOllama(**kwargs)


class ModelHub:
    """Lazily builds one model per role; tests inject fakes through `models`."""

    def __init__(self, settings: Settings, tracker: QueryTracker,
                 models: dict[Role, BaseChatModel] | None = None):
        self.settings = settings
        self.tracker = tracker
        self._models: dict[str, BaseChatModel] = {str(k): v for k, v in (models or {}).items()}
        self._callback = UsageCallback(tracker)

    def model(self, role: Role) -> BaseChatModel:
        if role not in self._models:
            self._models[role] = build_chat_model(self.settings.llm[role])
        return self._models[role]

    def config(self, role: Role) -> RunnableConfig:
        """RunnableConfig that attributes token usage to a role and model."""
        return RunnableConfig(
            callbacks=[self._callback],
            metadata={"role": role, "model": self.settings.llm[role].model},
        )


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.IGNORECASE)


def invoke_structured(hub: ModelHub, role: Role, schema: type[T], messages: list[BaseMessage]) -> T:
    """Structured output via native tool/JSON mode, with a plain-JSON fallback."""
    model, cfg = hub.model(role), hub.config(role)
    try:
        result = model.with_structured_output(schema).invoke(messages, config=cfg)
        if isinstance(result, schema):
            return result
        if isinstance(result, dict):
            return schema.model_validate(result)
    except Exception:
        pass
    instruction = (
        "Reply with ONLY a JSON object (no prose, no code fences) matching this JSON schema:\n"
        + json.dumps(schema.model_json_schema())
    )
    raw = model.invoke([*messages, HumanMessage(instruction)], config=cfg)
    text = raw.content if isinstance(raw.content, str) else "".join(
        part.get("text", "") if isinstance(part, dict) else str(part) for part in raw.content
    )
    text = _FENCE.sub("", text.strip())
    start, end = text.find("{"), text.rfind("}")
    return schema.model_validate_json(text[start : end + 1])

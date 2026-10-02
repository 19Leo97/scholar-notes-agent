"""Scripted chat model so the whole graph can be tested offline, without API keys."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import Any

from langchain_core.callbacks import CallbackManagerForLLMRun
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import RunnableLambda
from pydantic import BaseModel, Field


class ScriptedChatModel(BaseChatModel):
    """Plays back AIMessages (for tool-calling) and builders for structured outputs."""

    script: list[AIMessage] = Field(default_factory=list)
    structured: dict[str, list[Callable[[list[BaseMessage]], BaseModel]]] = Field(default_factory=dict)
    in_tokens: int = 200
    out_tokens: int = 40
    seen: list[list[BaseMessage]] = Field(default_factory=list)

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def _generate(self, messages: list[BaseMessage], stop: list[str] | None = None,
                  run_manager: CallbackManagerForLLMRun | None = None, **kwargs: Any) -> ChatResult:
        self.seen.append(messages)
        msg = self.script.pop(0) if self.script else AIMessage(content="DONE")
        msg = msg.model_copy(update={"usage_metadata": {
            "input_tokens": self.in_tokens, "output_tokens": self.out_tokens,
            "total_tokens": self.in_tokens + self.out_tokens}})
        return ChatResult(generations=[ChatGeneration(message=msg)])

    def bind_tools(self, tools, **kwargs):  # tool schemas are irrelevant to the script
        return self

    def with_structured_output(self, schema, **kwargs):
        def run(messages, config=None):
            self.invoke(messages, config=config)  # triggers callbacks so token usage is recorded
            queue = self.structured[schema.__name__]
            builder = queue.pop(0) if len(queue) > 1 else queue[0]
            return builder(messages)
        return RunnableLambda(run)


def evidence_lines(messages: list[BaseMessage]) -> list[tuple[str, str]]:
    """Parse the EVIDENCE block of the synthesizer prompt into (id, body) pairs."""
    text = str(messages[-1].content)
    block = text.split("EVIDENCE", 1)[-1]
    parts = re.split(r"\n\n(?=\[[NPW]\d+\] )", block.strip())
    out = []
    for part in parts:
        match = re.match(r"\[([NPW]\d+)\] [^\n]*\n(.*)", part, re.DOTALL)
        if match:
            out.append((match.group(1), match.group(2).strip()))
    return out


def first_words(text: str, n: int = 10, skip: int = 0) -> str:
    words = re.sub(r"[#*>\[\]-]", " ", text).split()
    return " ".join(words[skip : skip + n])

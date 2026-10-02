"""Structured outputs exchanged between graph nodes (validated with Pydantic)."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Intent = Literal["question", "verify_idea", "lookup"]
Verdict = Literal["SUPPORTED", "REFUTED", "MIXED", "INSUFFICIENT"]


class Plan(BaseModel):
    """Output of the planning step (router model)."""

    intent: Intent = Field(
        description="question = explain/answer; verify_idea = the user states an idea or hypothesis "
        "to be checked; lookup = find specific facts or references."
    )
    language: Literal["es", "en"] = Field(description="Language of the user's question.")
    sub_questions: list[str] = Field(default_factory=list, description="At most 3 focused sub-questions.")
    notes_queries: list[str] = Field(
        default_factory=list, description="1-2 keyword queries for the personal notes, in the notes' language."
    )
    literature_queries: list[str] = Field(
        default_factory=list, description="1-2 keyword queries in ENGLISH for scientific literature APIs."
    )


class Citation(BaseModel):
    id: str = Field(description="Evidence ID exactly as shown, e.g. N1, P2, W1.")
    quote: str = Field(
        description="Short VERBATIM excerpt (5-30 words) copied from that evidence that supports the claim."
    )


class Claim(BaseModel):
    text: str = Field(description="One factual statement supported by the cited evidence.")
    citations: list[Citation] = Field(description="At least one citation per claim.")


class Section(BaseModel):
    title: str
    claims: list[Claim]


class AIIdea(BaseModel):
    idea: str = Field(description="Your own hypothesis, connection or suggestion; NOT stated in the sources.")
    rationale: str = Field(description="Why you propose it, reasoning from the evidence.")
    based_on: list[str] = Field(
        default_factory=list, description="Evidence IDs that inspired it (may be empty if purely speculative)."
    )


class Synthesis(BaseModel):
    sections: list[Section] = Field(description="The answer, organised in short titled sections.")
    ai_ideas: list[AIIdea] = Field(default_factory=list, description="0-3 ideas clearly marked as yours.")
    verdict: Verdict | None = Field(
        default=None, description="Only when intent is verify_idea: how the evidence bears on the idea."
    )
    gaps: list[str] = Field(
        default_factory=list, description="What could not be found or remains uncertain (no citation needed)."
    )

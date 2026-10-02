"""LLM-as-judge helpers. Use a model from a different family than the generator when possible."""

from __future__ import annotations

from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel, Field

from scholar_agent.llm.factory import ModelHub, invoke_structured


class Decision(BaseModel):
    decision: Literal["yes", "no", "maybe"] = Field(
        description="The yes/no/maybe conclusion the answer gives to the question."
    )


class AnswerScore(BaseModel):
    faithfulness: int = Field(ge=1, le=5, description="5 = every statement is supported by the evidence.")
    relevance: int = Field(ge=1, le=5, description="5 = fully answers the question.")
    rationale: str = Field(description="One sentence.")


def extract_decision(hub: ModelHub, question: str, answer: str) -> str:
    system = (
        "You read a research answer and report which biomedical yes/no/maybe conclusion it reaches "
        "for the question. `maybe` means the answer is inconclusive, mixed or says there is not enough evidence."
    )
    out = invoke_structured(hub, "judge", Decision,
                            [SystemMessage(system), HumanMessage(f"Question: {question}\n\nAnswer:\n{answer[:3500]}")])
    return out.decision


def score_answer(hub: ModelHub, question: str, answer: str, evidence: str) -> AnswerScore:
    system = (
        "You grade a research answer. Faithfulness: are all claims supported by the EVIDENCE shown? "
        "Relevance: does it address the question? Be strict and base the grade only on the given text."
    )
    human = f"Question: {question}\n\nEVIDENCE:\n{evidence[:6000]}\n\nANSWER:\n{answer[:3500]}"
    return invoke_structured(hub, "judge", AnswerScore, [SystemMessage(system), HumanMessage(human)])

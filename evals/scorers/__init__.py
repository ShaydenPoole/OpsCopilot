"""Eval scorers for the Aviation Ops Copilot.

Four scorers, three rule-based / deterministic + one LLM-as-judge:

- :mod:`tool_call_correctness` : did the expected tools get called?
- :mod:`retrieval_quality`     : recall@k for RAG-flavored questions
- :mod:`llm_as_judge`          : Llama 3.3 70B grades against the rubric
- :mod:`security_redteam`      : deterministic leak / drift / introspect checks
"""

from evals.scorers.llm_as_judge import llm_as_judge_scorer
from evals.scorers.retrieval_quality import retrieval_quality_scorer
from evals.scorers.security_redteam import security_redteam_scorer
from evals.scorers.tool_call_correctness import tool_call_correctness_scorer

__all__ = [
    "llm_as_judge_scorer",
    "retrieval_quality_scorer",
    "security_redteam_scorer",
    "tool_call_correctness_scorer",
]

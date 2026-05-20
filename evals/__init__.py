"""Aviation Ops Copilot eval suite (Inspect AI).

Public surface:

- :mod:`run_eval`               : Inspect AI Task + runner entrypoint
- :mod:`scorers`                : 4 scorers (tool-call, retrieval, judge, redteam)
- :func:`load_question_bank`    : read every JSONL under questions/ as Samples
"""

from evals.dataset import load_question_bank, EvalQuestion

__all__ = ["EvalQuestion", "load_question_bank"]

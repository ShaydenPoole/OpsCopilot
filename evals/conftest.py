"""pytest discovery hook for the evals/ tests.

Adds ``backend/`` to ``sys.path`` so ``from aviation_copilot...`` resolves
when running ``pytest evals/`` from the repo root or from backend/.
"""

from __future__ import annotations

import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1] / "backend"
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

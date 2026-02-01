"""ThesisCheck - Local multi-agent debate runner for evaluating claims."""

from .config import Settings
from .runner import JudgeOut, run_duel
from .validators import AgentRole

__all__ = [
    "__version__",
    "Settings",
    "JudgeOut",
    "run_duel",
    "AgentRole",
]
__version__ = "2.3.0"
import os
from pathlib import Path

# Language models stay inside the project: without HF_HOME they go to runtime/hf (what TruthGuardian.bat setup fills),
# never to the user profile. Set before anything imports huggingface_hub, which reads it once.
os.environ.setdefault("HF_HOME", str(Path(__file__).resolve().parents[2] / "runtime" / "hf"))

from truth_guardian.schema import (  # noqa: E402
    AgentStep,
    Document,
    HallucinationType,
    Labels,
    Meta,
    Sample,
    Span,
    read_jsonl,
    write_jsonl,
)

__all__ = [
    "AgentStep",
    "Document",
    "HallucinationType",
    "Labels",
    "Meta",
    "Sample",
    "Span",
    "read_jsonl",
    "write_jsonl",
]

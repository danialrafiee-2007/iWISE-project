# Truth Guardian

Hallucination detection and reliability assessment for RAG and agentic AI answers.
Entry for iWISE 2026 AI & Web Programming Challenge, AI Challenge 4.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
uv run pytest
```

After the first `uv sync` and the first model downloads, run everything offline so no command depends on the network
(uv otherwise re-checks the spaCy model URL, and Hugging Face re-checks model files):

```bash
HF_HUB_OFFLINE=1 uv run --offline pytest
```

Optional, once: export HHEM to ONNX for a faster live pipeline (same scores, about 34% faster per answer):

```bash
HF_HUB_OFFLINE=1 uv run --offline python scripts/export_onnx.py
```

## Audit a RAG system

Run every answer in a log through the guardian and get the system's health summary (one JSON line per answer,
`{"id", "question", "sources", "answer"}` or the project's Sample format):

```bash
HF_HUB_OFFLINE=1 uv run --offline python scripts/audit.py --input answers.jsonl --out audit_out
```

`--profile` uses a domain profile fitted on a few dozen labelled answers of that domain (`truth_guardian.adapt`).

## Benchmark

`benchmark/` holds TG-Bench, the project's mini-benchmark of controlled edits and agent runs, with its own README.

## Data format

Every dataset is converted to one JSONL format defined in `src/truth_guardian/schema.py`.
Each line is a `Sample`: question, documents, answer, optional evidence and agent log, labels and meta.
`meta.group_id` ties samples that share a source; a group never crosses train/dev/test splits.

## Documentation

- `docs/AI_USAGE.md`: AI tools used, by whom, for what, and how outputs were verified
- `docs/CREDITS.md`: datasets, models and libraries with their licenses
- `docs/DECISIONS.md`: key technical decisions and why
- `benchmark/README.md`: TG-Bench data card

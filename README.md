# Truth Guardian

Hallucination detection and reliability assessment for RAG and agentic AI answers.
Entry for iWISE 2026 AI & Web Programming Challenge, AI Challenge 4.

## Setup

Requires [uv](https://docs.astral.sh/uv/) and Python 3.12+.

```bash
uv sync
uv run pytest
```

## Data format

Every dataset is converted to one JSONL format defined in `src/truth_guardian/schema.py`.
Each line is a `Sample`: question, documents, answer, optional evidence and agent log, labels and meta.
`meta.group_id` ties samples that share a source; a group never crosses train/dev/test splits.

## Documentation

- `docs/AI_USAGE.md`: AI tools used, by whom, for what, and how outputs were verified
- `docs/CREDITS.md`: datasets, models and libraries with their licenses
- `docs/DECISIONS.md`: key technical decisions and why

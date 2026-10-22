# Annotation Guide: judging the system's flagged claims

Two team members fill `eval/annotation/claims_A.csv` and `claims_B.csv` **independently** (no discussion until both are done).
Each row is one sentence of an AI answer that the system flagged. Read `claim`, `evidence` and, if needed, the full source in
`data/processed/ragtruth_dev.jsonl` (search by the part of `claim_id` before `#`). Judge only against the sources, not world knowledge.

| Column | Allowed answers | Meaning |
|---|---|---|
| `flag_correct` | `yes` / `no` / `unsure` | `yes` if the claim really is contradicted by, or not supported by, the sources |
| `type_correct` | `yes` / `no` / `na` | Does `status` / `type` match the problem? `na` when `flag_correct` is `no` |
| `explanation_helpful` | `1` to `5` | Would `explanation` + `evidence` (+ `fix`) let a user understand and fix the problem? 1 = useless, 5 = fully clear |
| `notes` | free text | Anything surprising; keep it short |

Status meanings: **contradicted**: the sources say otherwise (a wrong number, name or a reversed statement);
**unsupported**: the sources say nothing that backs it; **insufficient_evidence**: no source passage is even about it.

When done, run `uv run --offline python -I scripts/annotation_kit.py score` for Cohen's kappa and the human-judged precision.
Kappa above 0.6 is usually read as substantial agreement; below 0.4 means the questions or guide need tightening.

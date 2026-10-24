# TG-Bench

A small benchmark for hallucination detectors in RAG answers and agent runs, built by the Truth Guardian team
for iWISE 2026 (AI Challenge 4). It tests what aggregate benchmarks hide: whether a detector catches one specific
kind of lie, finds the exact words, and traces an agent's error to the step where it began.

## Parts

| Part | Samples | What it holds |
|---|---|---|
| Fool the Guardian | 432 | 60 grounded RAGTruth dev answers (20 QA, 20 summaries, 20 data-to-text) as controls, and copies with one controlled edit each: number (53), entity (51), negation (58), opposite word (49), added claim (60), swapped roles (41), stronger quantifier (30), dropped hedge (30). Kinds that apply to few bases are topped up from further dev answers, one per source group. Every edit has its exact character span and the original wording. |
| TG-Agent | 220 | Scripted agent runs (search, read, reason, answer) built from grounded RAGTruth dev QA answers: 60 clean, and 160 with one injected error and its exact step: fabricated fact (40), ignored tool error (60), answer addition (60). |

Both parts come from RAGTruth **dev**, never from train or test, so a detector trained on RAGTruth train can be
scored on them.

A third part, **Challenge cases** (`challenge_cases.json`, 160 samples), covers the five harder cases the Challenge 4
description names: 20 fictional topics, each with a faithful answer, a mixed answer (one wrong detail among correct
sentences), an added unsupported claim, an answer that uses only part of the evidence (10 leave out an asked-for fact,
10 drop a caveat), and the faithful answer over sources that miss the question with an honest answer as its control;
plus 20 agent runs (an invented fact, a revised value, an outdated value kept, a hand-off between agents), each with
a faithful twin. `[[...]]` marks the wrong words; `src/truth_guardian/data/challenge_cases.py` builds the samples
with exact spans and steps. All its text was written for this set, so it is released in full. It was written by the
project's AI assistant (see docs/AI_USAGE.md) and is to be reviewed by the team; a single author's style is a
limitation. Truth Guardian's results on it are in `eval/results/challenge_cases.json` (D-110).

## What is released

The source texts belong to RAGTruth's sources (MS MARCO passages, CNN/Daily Mail articles, Yelp business data),
each with its own terms. This folder therefore holds no source text, only:

- `fool_the_guardian.labels.jsonl` and `tg_agent.labels.jsonl`: per sample its id, source group, label, edit kind
  or error category, gold spans (with the edited words and the original wording) or responsible step;
- `checksums.json`: SHA-256 of the full files a rebuild must produce;
- `truth_guardian.*.jsonl` and `truth_guardian.scores.json`: this project's predictions and scores, as a baseline.

## Rebuild and score

With RAGTruth downloaded and processed as in the main README:

```bash
uv run --offline python scripts/build_benchmark.py
```

rebuilds both parts deterministically into `data/processed/` and checks them against `checksums.json`.

```bash
uv run --offline python scripts/score_benchmark.py --fool my_predictions.jsonl --agent my_agent_predictions.jsonl
```

scores any detector. Prediction lines are `{"id", "score", "spans": [[start, end], ...]}` for Fool the Guardian
(spans optional) and `{"id", "score", "step"}` for TG-Agent (step optional).

## Baseline: Truth Guardian

| Edit kind | AUROC vs controls | Edit located |
|---|---|---|
| Added claim | 0.891 | 98% |
| Number | 0.825 | 92% |
| Entity | 0.779 | 69% |
| Negation | 0.778 | 43% |
| Swapped roles | 0.743 | 34% |
| Opposite word | 0.647 | 22% |
| Stronger quantifier | 0.646 | 13% |
| Dropped hedge | 0.552 | 0% |

TG-Agent: detection AUROC 0.760, exact step 39%, within one step 83% (always-first-step 0%, random 25%).
Quantifier and hedge edits are mostly flagged as advisory cautions, not scored as hallucinations.

## Limitations

- Edits are synthetic and use closed word lists (quantifiers, hedges, a small antonym table); natural errors are
  more varied. Treat a high score as necessary, not sufficient.
- English only; three RAGTruth tasks; agent runs follow one simple script.
- Some swapped-role edits read awkwardly, since any noun subject and object may be exchanged.

## Licence

Labels and scripts: to be set by the team before publication. Users must also respect RAGTruth (MIT) and the terms
of its sources when rebuilding. Cite RAGTruth (Niu et al., 2024) alongside TG-Bench.

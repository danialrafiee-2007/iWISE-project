# AI Usage Disclosure

Required by the iWISE rules: every AI tool, how it was used, which components it influenced, and how the team verified the output.
Add a row every time an AI tool contributes to code, data, text or design. "Verified by" must be a team member who can explain the result.

| Date | Tool / model | Used by | Purpose | Components affected | Verification by the team | Verified by |
|---|---|---|---|---|---|---|
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Analysis of the 25 challenges and choice of Challenge 4 | Project direction | Team read the official challenge text and rules | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Project roadmap and phase plan | Planning | Team reviewed the timeline and scope | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Project scaffold, unified data schema and its unit tests | `src/truth_guardian/schema.py`, `tests/test_schema.py` | Ran `uv run pytest` (11 passed); team to walk through every validator | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Dataset download script, raw-data inspection, decisions D-009 to D-015 | `scripts/download_data.py`, `docs/DECISIONS.md` | Checksums re-verified on a second run; team to re-check the statistics behind each decision | |
| 2026-10-22 | Claude Code (Claude Opus 5.5) | | Polarity check with NLI confirmation and override, report contract, live analysis pipeline, tracer speed-up, learned tracer, decisions D-060 to D-064 | `polarity.py`, `overrides.py`, `report.py`, `pipeline.py`, `symbolic.py`, `tracer.py`, `explain.py`, `signals.py`, `scripts/train_tracer.py`, `scripts/evaluate_perturbations.py`, `scripts/download_data.py`, tests | Polarity thresholds chosen on train false alarms only; suite used for reporting, not tuning; tracer scores are out-of-fold by question; all tests pass | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Phase 2 analysis (NLI dropped, HHEM extension, ensemble option), Phase 3 groundwork: AgentHallu download, converter, split, provenance tracer v0 and its evaluation, decisions D-049 to D-057 | `fusion.py`, `scripts/analyze_fusion.py`, `scripts/download_data.py`, `data/agenthallu.py`, `symbolic.py`, `tracer.py`, `scripts/evaluate_tracer.py`, tests | Leakage test for reference answers; all 693 trajectories validate; tracer compared with simple baselines on dev only | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Fix-it suggestions, "Fool the Guardian" perturbation suite, data story, their evaluation scripts, decisions D-045 to D-048 | `correct.py`, `perturb.py`, `symbolic.py` (atoms), `scripts/evaluate_fixit.py`, `scripts/build_perturbations.py`, `scripts/evaluate_perturbations.py`, `scripts/data_story.py`, tests | Fix-it scored on train only against annotator notes; perturbation examples read by hand; 102 tests pass | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Explanations (type, word spans, reason), structure-feature switch, analysis script (ablation, learning curve, train error analysis, span/type report), shared helpers, first fusion results, decisions D-041 to D-044 | `explain.py`, `fusion.py`, `features.py`, `provenance.py`, `scripts/analyze_fusion.py`, tests | 87 tests pass; per-task and per-generator AUROC checked to rule out shortcut explanations | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Fusion model (stacking, calibration, save/load with checksum), feature extraction and training scripts, separate span threshold, license checks, decisions D-035 to D-040 | `fusion.py`, `evaluation.py`, `scripts/extract_features.py`, `scripts/train_fusion.py`, `docs/CREDITS.md`, tests | 80 tests pass, including synthetic learnability, tampered-file and stale-version checks; licenses read from package metadata and repo LICENSE files | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Phase 2 start: sentence labels, external dev, BM25 + RRF retrieval, symbolic checks, feature cache, signal extractors, signal-study script, decisions D-027 to D-033 | `labels.py`, `retrieval.py`, `symbolic.py`, `features.py`, `signals.py`, `scripts/signal_study.py`, tests | 71 tests pass; symbolic false positives inspected by hand and fixed; HHEM remote code read before use | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | B2 embedding and B3 NLI baselines, shared model and evidence modules, decisions D-024 to D-026 | `models.py`, `evidence.py`, `baselines/embedding.py`, `baselines/nli.py`, tests | 43 tests pass; NLI label order checked against the model config; sanity pairs (1945 vs 2022) checked by hand | |
| 2026-10-21 | Claude Code (Claude Opus 5.5) | | Phase 1: converters, splits, data card, evaluation harness, sentence splitter, B1 baseline, decisions D-016 to D-023 | `src/truth_guardian/data/`, `evaluation.py`, `text.py`, `baselines/lexical.py`, `scripts/`, tests | 37 tests pass; all 17,790 RAGTruth and 60,000 HaluEval samples validate; metrics checked against hand-computed values | |

## Work done directly by the team

Fill in per member as the project progresses.

## Known limitations and risks of AI-generated parts

Fill in as they are found.

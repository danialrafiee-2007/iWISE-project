# Technical Decisions

Each decision records what was chosen and why, so any team member can defend it in the judges' Q&A.

| ID | Date | Decision | Reason |
|---|---|---|---|
| D-001 | 2026-10-21 | Challenge 4: Truth Guardian | Highest innovation and practical-value ceiling; few strong competitors |
| D-002 | 2026-10-21 | Core pipeline runs offline with open models; no paid LLM API in the core | Cost, reproducibility, privacy, and a clear answer to "is it just GPT?" LLMs only as a comparison baseline |
| D-003 | 2026-10-21 | English first; Persian is a stretch goal | Labeled data exists only in English |
| D-004 | 2026-10-21 | One JSONL schema (`Sample`) for every dataset | Converters, models, evaluation and the API share one contract |
| D-005 | 2026-10-21 | Splits by `meta.group_id`; a source never crosses train/dev/test | RAGTruth has 6 responses per source; random splits would leak |
| D-006 | 2026-10-21 | Final test split is created in week 2 and locked until week 11 | Prevents tuning on the test set |
| D-007 | 2026-10-21 | Training on Kaggle/Colab GPUs; local machine for CPU inference and the web app | Local GPU is a GeForce MX110 with 2 GB |
| D-008 | 2026-10-21 | Python 3.13 managed by uv, versions locked in `uv.lock` | Installed locally; uv could not install a separate 3.12 on this machine |
| D-009 | 2026-10-21 | Raw data pinned to exact repo commits with SHA-256 checks (`scripts/download_data.py`) | Every member gets byte-identical data; results are reproducible |
| D-010 | 2026-10-21 | RAGTruth official test split (2,700 responses) is the locked test set; dev is carved from train by `source_id` | Official split already keeps all 6 responses of a source together (0 sources cross splits) |
| D-011 | 2026-10-21 | RAGTruth "Conflict" maps to `contradicted`, "Baseless Info" to `unsupported`; original label kept in `source_label` | Matches our taxonomy without losing the original annotation |
| D-012 | 2026-10-21 | `implicit_true` spans (1,928) stay hallucinated | We measure faithfulness to the sources, not world truth |
| D-013 | 2026-10-21 | 173 responses with quality `incorrect_refusal` or `truncated` are excluded from training and reported separately | They are not normal answers and would add label noise |
| D-014 | 2026-10-21 | Every metric is reported per task as well as overall | Hallucination rate differs by task (test: QA 18%, Summary 23%, Data2txt 64%); a model could exploit task type |
| D-015 | 2026-10-21 | HaluEval used only for cross-dataset testing | Its QA, dialogue and summary hallucinations were deliberately generated, a different distribution from natural ones |
| D-016 | 2026-10-21 | Yelp structured data rendered as "key: value" lines (null as "not specified"), one document per review | NLI models are trained on natural text, not JSON; null values cause 1,642 labeled hallucinations, so they must stay visible |
| D-017 | 2026-10-21 | HaluEval: 500 question groups per task (1,000 samples), "general" excluded, all files locked | Enough for a cross-dataset check at a fraction of the compute; "general" has no source documents |
| D-018 | 2026-10-21 | Sentences: split on line breaks first, then spaCy's rule-based sentencizer, keeping character offsets | Structured data is one fact per line; offsets let us highlight the exact text in the UI |
| D-019 | 2026-10-21 | Confidence intervals by bootstrap over source groups, not single responses | The 6 responses of one source are correlated; per-response resampling would give falsely narrow intervals |
| D-020 | 2026-10-21 | Decision thresholds are tuned on dev only and passed to test unchanged | Tuning on test inflates results |
| D-021 | 2026-10-21 | Every F1 is reported next to the "flag everything" F1 | With 44% hallucinated responses, flagging everything already scores F1 0.615 on dev; AUROC is the fairer headline metric |
| D-022 | 2026-10-21 | Thresholds must be checked for transfer to test, and calibration is a core Phase 2 goal | Hallucination rate drops from 44.6% (train) to 34.9% (test), QA from 30.6% to 17.8% |
| D-023 | 2026-10-21 | Length is reported as a shortcut risk for HaluEval | HaluEval QA grounded answers average 2.3 words vs 11.1 for hallucinated ones |
| D-024 | 2026-10-21 | B3 premise = the 5 source sentences most similar to the answer sentence (in source order); score = 1 - P(entailment) | Sources exceed the 512-token NLI limit; 1 - P(entailment) flags both contradicted and unsupported sentences |
| D-025 | 2026-10-21 | NLI outputs are reordered by the model's own `id2label` | Different NLI models use different label orders (e.g. the large DeBERTa model we plan to try); hard-coded indices would silently break |
| D-026 | 2026-10-21 | ~~NLI over the training set runs on a Kaggle/Colab GPU in Phase 2~~ Superseded by D-033 | On the local CPU B3 takes about 5 s per response: about 2 hours for dev, about 19 hours for train |
| D-027 | 2026-10-21 | Symbolic checks favour precision: skip passage citations, word-count statements and generic date phrases; normalise US states and street abbreviations | On dev, word-level precision rose from 0.261 to 0.475 and sentence precision from 0.301 to 0.498, while response AUROC fell from 0.730 to 0.672. This signal's job is exact, explainable word-level evidence; ranking responses is the fusion model's job |
| D-028 | 2026-10-21 | Sentence labels = overlap with any gold span; spans are kept for word-level evaluation | In train, a hallucinated sentence has a median of 17 words but the gold span only 5 (median 45% coverage), so sentence-level highlighting alone caps span precision near 0.5; 7.2% of spans cross sentence boundaries |
| D-029 | 2026-10-21 | External dev = the next 250 HaluEval groups per task after the locked 500 (same ranking, disjoint) | Lets us check cross-dataset generalisation during development without touching locked files |
| D-030 | 2026-10-21 | Evidence retrieval = our own BM25 fused with embedding similarity by Reciprocal Rank Fusion (k=60) | Lexical matching beat embeddings on dev (B1 vs B2), so both rankings are combined; RRF needs no score calibration |
| D-031 | 2026-10-21 | HHEM loaded with `trust_remote_code` only at revision de9a5e6, after reading its code | Remote code runs on our machine; the reviewed revision only builds a T5 classifier and a prompt |
| D-032 | 2026-10-21 | LettuceDetect lives in a separate `study` dependency group and is never trusted on RAGTruth train/dev | It was trained on RAGTruth train, which includes our dev, so its dev scores are inflated and its train scores in-sample |
| D-034 | 2026-10-21 | Response scores must not be the plain max over sentence NLI scores; the fusion model learns the aggregation | B3 (NLI-base, max of 1 - P(entailment)) is the weakest baseline on dev: AUROC 0.631 vs B1 0.674 and B2 0.649. Its scores saturate (tuned threshold 0.9992) because almost every answer has some sentence NLI cannot confirm; on data2text it is near random (0.534) |
| D-035 | 2026-10-21 | Fusion = two-stage stacking: sentence classifier, then response classifier on aggregates of out-of-fold sentence probabilities and raw signals; one group-based fold assignment shared by both stages | Stage 2 must never learn from in-sample (over-confident) stage-1 scores; grouping by source prevents leakage |
| D-036 | 2026-10-21 | Classifiers: logistic regression vs scikit-learn HistGradientBoosting (same family as LightGBM) | No extra dependency; a simple, explainable model and a strong one are always compared |
| D-037 | 2026-10-21 | Calibration: Platt scaling fitted on out-of-fold response scores | Rank-preserving, so AUROC is unchanged; isotonic would create ties |
| D-038 | 2026-10-21 | Separate response and span (sentence) thresholds, both tuned on dev; threshold grid uses observed scores only | Sentence probabilities and calibrated response probabilities are on different scales |
| D-039 | 2026-10-21 | Saved models: models/fusion/<version>/ with model.joblib, a manifest (signal versions, data, metrics, thresholds, SHA-256) and a LATEST pointer; loading refuses tampered files and stale signal versions | Fast reuse for the team and judges without silent mismatches; joblib files can run code, so integrity is checked |
| D-040 | 2026-10-21 | Results are marked "dirty" only when src, scripts or dependencies differ from HEAD | Result files changing during long runs should not mark reproducible code as dirty |
| D-041 | 2026-10-21 | NLI-large dropped | Measured about 600 s per sample on the laptop (memory pressure with other jobs), about 43 hours for the 306-sample study subset alone |
| D-042 | 2026-10-21 | Fusion candidates: lexical, symbolic, dense, NLI-base, HHEM. LettuceDetect stays out of the fusion and is reported only as an external reference on the locked test | Signal study (306 RAGTruth dev / 300 HaluEval xdev): HHEM is the best clean signal (0.795 / 0.684). LettuceDetect's 0.966 on RAGTruth dev against 0.661 on HaluEval confirms the contamination from D-032 |
| D-043 | 2026-10-21 | Structure features (position, sentence length, sentence count) are kept but always reported with an ablation | Cheap fusion (lexical + symbolic, HGB) reaches dev AUROC 0.835 against B1's 0.674, and 0.813 without structure. Gains hold within every task and every generator (e.g. llama-2-13b 0.541 to 0.851), so they are not task or generator identity |
| D-044 | 2026-10-21 | Heavy signals (NLI, HHEM) are first extracted on 170 train groups (~1,000 responses); more groups only if the learning curve and ablation show they pay off | About 8 s per response on the laptop; full train would take about 30 hours |
| D-033 | 2026-10-21 | All computation runs on the local laptop; heavy signals are cached per sentence and extraction resumes after interruption | User requirement; caching turns re-training and evaluation into seconds |

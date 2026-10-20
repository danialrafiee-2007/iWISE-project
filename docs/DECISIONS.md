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

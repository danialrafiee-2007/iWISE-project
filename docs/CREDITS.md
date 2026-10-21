# Third-party Resources and Licenses

Licenses marked "verified" were read on the official page on the given date. Re-check before submission.

## Datasets

| Resource | Link | License | Status | Planned use |
|---|---|---|---|---|
| RAGTruth | https://github.com/ParticleMedia/RAGTruth | MIT | verified 2026-10-21 | Main training and test data (span-level labels) |
| HaluEval | https://github.com/RUCAIBox/HaluEval | MIT | verified 2026-10-21 | Cross-dataset test |
| LLM-AggreFact | https://huggingface.co/datasets/lytang/LLM-AggreFact | | to check | Additional test |
| AgentHallu | https://arxiv.org/abs/2601.06818 | | release and license unconfirmed | External agent test, if released |

## Models

| Resource | Link | License | Status | Planned use |
|---|---|---|---|---|
| DeBERTa-v3-large NLI | https://huggingface.co/MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli | MIT | verified 2026-10-21 | NLI signal (accuracy) |
| nli-deberta-v3-base | https://huggingface.co/cross-encoder/nli-deberta-v3-base | Apache-2.0 | verified 2026-10-21 | NLI signal (fast demo) |
| HHEM-2.1-Open | https://huggingface.co/vectara/hallucination_evaluation_model | Apache-2.0 | verified 2026-10-21 | Consistency signal and baseline |
| MiniCheck | https://github.com/Liyan06/MiniCheck | Apache-2.0 | verified 2026-10-21 | Fact-check signal and baseline |
| LettuceDetect | https://github.com/KRLabsOrg/LettuceDetect | MIT | verified 2026-10-21 | Span-level baseline |
| all-MiniLM-L6-v2 | https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 | Apache-2.0 | verified 2026-10-21 | B2 embedding baseline, evidence retrieval |
| en_core_web_sm 3.8.0 | https://github.com/explosion/spacy-models | MIT | verified 2026-10-21 | Named entities for symbolic checks |
| LettuceDetect base (lettucedect-base-modernbert-en-v1) | https://huggingface.co/KRLabsOrg/lettucedect-base-modernbert-en-v1 | MIT | verified 2026-10-21 | Signal study only (trained on RAGTruth) |
| HHEM-2.1-Open @ de9a5e6 | https://huggingface.co/vectara/hallucination_evaluation_model | Apache-2.0 | verified 2026-10-21; remote code reviewed | Consistency signal; downloads the google/flan-t5-base tokenizer |

## Libraries

| Library | License | Status |
|---|---|---|
| pydantic | | to check |
| pytest | | to check |
| numpy | | to check |
| scikit-learn | | to check |
| spaCy | | to check |
| PyTorch | | to check |
| sentence-transformers | | to check |
| transformers | | to check |

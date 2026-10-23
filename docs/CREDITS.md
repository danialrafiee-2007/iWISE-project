# Third-party Resources and Licenses

Licenses marked "verified" were read on the official page on the given date. Re-check before submission.

## Datasets

| Resource | Link | License | Status | Planned use |
|---|---|---|---|---|
| RAGTruth | https://github.com/ParticleMedia/RAGTruth | MIT | verified 2026-10-21 | Main training and test data (span-level labels) |
| HaluEval | https://github.com/RUCAIBox/HaluEval | MIT | verified 2026-10-21 | Cross-dataset test |
| LLM-AggreFact | https://huggingface.co/datasets/lytang/LLM-AggreFact | CC-BY-ND-4.0, gated | verified 2026-10-21 | Optional extra test only. "No derivatives": never redistribute converted copies; access requires accepting terms on Hugging Face (team decision) |
| AgentHallu @ 9ffe8bc8 | https://github.com/liuxuannan/AgentHallu | CC BY 4.0 (repo LICENSE file) | verified 2026-10-21; downloaded with SHA-256 check | Agent-log provenance (Phase 3): one third dev, two thirds locked test; attribution required |

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

## Lexical resources

| Resource | Link | License | Status | Planned use |
|---|---|---|---|---|
| WordNet 3.0 (via nltk_data @ 550b6625) | https://wordnet.princeton.edu | WordNet 3.0 license (Princeton; free use with notice) | verified 2026-10-22; SHA-256 checked | Antonyms for the polarity check; the copyright notice must ship with any copy |

## Libraries

Read from the installed package metadata on 2026-10-21.

| Library | Version | License |
|---|---|---|
| pydantic | 2.14.1 | MIT |
| pytest | 9.1.1 | MIT |
| numpy | 2.5.4 | BSD-3-Clause AND 0BSD AND MIT AND Zlib AND CC0-1.0 |
| scikit-learn | 1.9.1 | BSD-3-Clause |
| joblib | 1.6.0 | BSD-3-Clause |
| spaCy | 3.8.16 | MIT |
| PyTorch | 2.14.1 | Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND MIT |
| sentence-transformers | 6.1.0 | Apache-2.0 |
| transformers | 5.20.2 | Apache-2.0 |
| huggingface-hub | 1.33.0 | Apache-2.0 |
| tokenizers | 0.23.3 | Apache-2.0 (classifier) |
| lettucedetect (study group only) | 0.2.3 | MIT |
| nltk | 3.10.4 | Apache-2.0 (PyPI metadata) |
| onnxruntime | 1.31.0 | MIT |
| onnx | 1.23.2 | Apache-2.0 |
| fastapi | 0.161.1 | MIT |
| starlette | 1.9.0 | BSD-3-Clause |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx (tests) | 0.28.1 | BSD-3-Clause |

## Web app (Phase 4)

Read from the installed package metadata on 2026-10-23.

| Library | Version | License |
|---|---|---|
| react, react-dom | 19.3.1 | MIT |
| three (app and Glass Halo, Signal Array) | 0.170.0 | MIT |
| three (Halftone Iris, Lumen Grid, as shipped) | 0.143.0 | MIT |
| @react-spring/web | 10.1.2 | MIT |
| spring-text-engine | 0.1.5 | MIT |
| orbloom | 0.1.0 | MIT |
| tailwindcss, @tailwindcss/vite | 4.3.3 | MIT |
| vite | 8.3.5 | MIT |
| @vitejs/plugin-react | 6.1.2 | MIT |
| typescript | 5.9.3 | Apache-2.0 |
| @fontsource/jetbrains-mono | 5.3.0 | OFL-1.1 |

| Resource | Source | License | Status | Use |
|---|---|---|---|---|
| GetLayers layers: Neural Monitor (template), Roadmap Ascent, Slider Spectra, Cards Cascade (sections), Glass Halo, Halftone Iris, Lumen Grid, Signal Array (scenes), Pharos, Loupe, Riffle (gradients), Orb Studio, Text Animations (tools) | https://www.getlayers.ai | GetLayers licence, purchased by the team | team to confirm the licence terms, including whether the sources may sit in a public repository | Visual layers of the web app; changes listed in web/scripts/vendor-layers.mjs and in each adapted component |
| General Sans (woff2 files shipped in the Neural Monitor template) | Fontshare (Indian Type Foundry) | ITF Free Font License, as published by Fontshare | not verified | Interface typeface |
| Brain model rotten-brain.glb (in the Neural Monitor template) | GetLayers template | as the template | team to confirm | Particle brain on the landing page |

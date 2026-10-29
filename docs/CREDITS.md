# Third-party Resources and Licenses

Licenses marked "verified" were read on the official page on the given date. Re-check before submission.

## Datasets

| Resource | Link | License | Status | Planned use |
|---|---|---|---|---|
| RAGTruth | https://github.com/ParticleMedia/RAGTruth | MIT | verified 2026-10-21 | Main training and test data (span-level labels) |
| HaluEval | https://github.com/RUCAIBox/HaluEval | MIT | verified 2026-10-21 | Cross-dataset test |
| LLM-AggreFact | https://huggingface.co/datasets/lytang/LLM-AggreFact | CC-BY-ND-4.0, gated | verified 2026-10-21 | Optional extra test only. "No derivatives": never redistribute converted copies; access requires accepting terms on Hugging Face (team decision) |
| AgentHallu @ 9ffe8bc8 | https://github.com/liuxuannan/AgentHallu | CC BY 4.0 (repo LICENSE file) | verified 2026-10-21; downloaded with SHA-256 check | Agent-log provenance (Phase 3): one third dev, two thirds locked test; attribution required |
| RAGTruth translated (es @ 39d88100, fr @ 95d0aa3e, zh @ 1f3db52b) | https://huggingface.co/datasets/KRLabsOrg/ragtruth-es-translated (and -fr-, -cn-) | MIT (dataset card) | verified 2026-10-28; train files only, downloaded with SHA-256 check | Multilingual check (D-137): RAGTruth's human labels carried over a machine translation (Gemma 3 27B). Their test files translate our locked RAGTruth test set and are never fetched |
| PsiloQA @ 375c3321 | https://huggingface.co/datasets/s-nlp/PsiloQA | CC BY 4.0 | verified 2026-10-28; downloaded with SHA-256 check | Multilingual check (D-137), Arabic, Chinese, French and Spanish only (no Persian): Wikipedia contexts, answers of several LLMs, spans labelled by GPT-4o, not by people. Its test split becomes a locked test set |
| FLEURS @ 70bb2e84 | https://huggingface.co/datasets/google/fleurs | CC BY 4.0 | verified 2026-10-28; dev split of six languages, downloaded with SHA-256 check (`scripts/download_media_eval.py`) | Stage 2 measurement (D-139): real read speech with human transcripts; Whisper's error rate and the media chain. Not used for training |
| TextVQA (lmms-lab copy @ 9c0699cd) | https://textvqa.org, https://huggingface.co/datasets/lmms-lab/textvqa | annotations CC BY 4.0, OpenImages photos CC BY 2.0 (the copy carries no licence tag; the original's applies) | verified 2026-10-28; one third of validation, downloaded with SHA-256 check | Stage 2 measurement (D-139): real photos with text and ten human answers per question. Not used for training |
| MTVQA @ 7cdca63e | https://huggingface.co/datasets/ByteDance/MTVQA | CC BY-NC 4.0, non-commercial only | verified 2026-10-28; test split, downloaded with SHA-256 check | Stage 2 measurement (D-139), Arabic, French and Russian: questions on text in images with expert answers. Non-commercial: fine for the challenge and research, not for sale |
| XQuAD @ 7d30520c | https://github.com/google-deepmind/xquad | CC BY-SA 4.0 (repo license file) | verified 2026-10-28; downloaded with SHA-256 check | Multilingual check (D-137): the same 1,190 questions in English, Arabic, Spanish, Russian and Chinese, translated by professionals; tuned the language detection; Russian has no labelled hallucination set, so it is checked with controlled edits of these answers. Share-alike: derived copies keep the license |

## Models

| Resource | Link | License | Status | Planned use |
|---|---|---|---|---|
| DeBERTa-v3-large NLI | https://huggingface.co/MoritzLaurer/DeBERTa-v3-large-mnli-fever-anli-ling-wanli | MIT | verified 2026-10-21 | NLI signal (accuracy) |
| nli-deberta-v3-base | https://huggingface.co/cross-encoder/nli-deberta-v3-base | Apache-2.0 | verified 2026-10-21 | NLI signal (fast demo) |
| HHEM-2.1-Open | https://huggingface.co/vectara/hallucination_evaluation_model | Apache-2.0 | verified 2026-10-21 | Consistency signal and baseline |
| Claude Opus 5.5 through the Anthropic API (official `anthropic` Python SDK, MIT) | https://docs.anthropic.com | Anthropic's commercial terms; paid per use | 2026-10-29; experimental, off until the team sets a key | The online check (D-141): a disclosed second opinion on doubtful claims, with web search; never the local verdict. Sends the question, the doubtful claims and the sources to Anthropic |
| MiniCheck | https://github.com/Liyan06/MiniCheck | Apache-2.0 | verified 2026-10-21 | Fact-check signal and baseline |
| LettuceDetect | https://github.com/KRLabsOrg/LettuceDetect | MIT | verified 2026-10-21 | Span-level baseline |
| all-MiniLM-L6-v2 | https://huggingface.co/sentence-transformers/all-MiniLM-L6-v2 | Apache-2.0 | verified 2026-10-21 | B2 embedding baseline, evidence retrieval |
| en_core_web_sm 3.8.0 | https://github.com/explosion/spacy-models | MIT | verified 2026-10-21 | Named entities for symbolic checks |
| LettuceDetect base (lettucedect-base-modernbert-en-v1) | https://huggingface.co/KRLabsOrg/lettucedect-base-modernbert-en-v1 | MIT | verified 2026-10-21 | Signal study only (trained on RAGTruth) |
| HHEM-2.1-Open @ de9a5e6 | https://huggingface.co/vectara/hallucination_evaluation_model | Apache-2.0 | verified 2026-10-21; remote code reviewed | Consistency signal; downloads the google/flan-t5-base tokenizer |
| faster-whisper-small @ 536b066 | https://huggingface.co/Systran/faster-whisper-small | MIT (Whisper: openai/whisper) | downloaded 2026-10-27, SHA-256 in runtime/multimodal/MODEL_MANIFEST.json | Speech to text (media readers, D-125) |
| Qwen3-VL-2B-Instruct-GGUF @ 52d6c8f | https://huggingface.co/Qwen/Qwen3-VL-2B-Instruct-GGUF | Apache-2.0 | downloaded 2026-10-27, SHA-256 in the manifest | What an image shows, through llama.cpp (D-125) |
| tessdata_fast @ 8741641 | https://github.com/tesseract-ocr/tessdata_fast | Apache-2.0 | downloaded 2026-10-27, SHA-256 in the manifest | Text in images, 163 language, script and orientation models (D-125) |
| multilingual-e5-small @ 614241f | https://huggingface.co/intfloat/multilingual-e5-small | MIT | downloaded 2026-10-27, SHA-256 in the manifest | Multilingual retrieval, not yet in the fusion model (D-125) |
| mDeBERTa-v3-base-mnli-xnli @ 8adb042 | https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli | MIT | downloaded 2026-10-27, SHA-256 in the manifest | Multilingual NLI, not yet in the fusion model (D-125) |
| llama.cpp b11923 (llama-server, Windows CPU x64) | https://github.com/ggml-org/llama.cpp/releases/tag/b11923 | MIT | downloaded 2026-10-27; zip SHA-256 matches the release's digest (runtime/tools/llama.cpp/VERSION.txt) | Runs the Qwen image model locally |

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
| pypdf | 6.21.2 | BSD-3-Clause |
| fastapi | 0.161.1 | MIT |
| starlette | 1.9.0 | BSD-3-Clause |
| uvicorn | 0.54.0 | BSD-3-Clause |
| httpx (tests) | 0.28.1 | BSD-3-Clause |
| faster-whisper (media group) | 1.2.1 | MIT |
| ctranslate2 (media group) | 4.8.4 | MIT |
| av / PyAV (media group; its wheel carries FFmpeg's libraries, LGPL-2.1-or-later) | 19.0.2 | BSD-3-Clause |
| tesserocr (media group; its wheel carries Tesseract 5.5.3, Apache-2.0, and Leptonica, BSD-2-Clause) | 2.12.0 | MIT |
| Pillow (media group) | 13.0.0 | MIT-CMU |

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
| @fontsource/vazirmatn (Vazirmatn by Saber Rastikerdar, Arabic-script subset: Persian and Arabic interface text) | 5.3.0 | OFL-1.1 |
| @fontsource/fraunces (Fraunces by Undercase Type: headings, after iridology.app) | 5.3.0 | OFL-1.1 |
| @fontsource/newsreader (Newsreader by Production Type: reading text) | 5.3.0 | OFL-1.1 |
| @fontsource/jost (Jost by indestructible type*: menus, buttons, labels, numbers) | 5.3.0 | OFL-1.1 |
| @fontsource/literata (Literata by TypeTogether, Cyrillic subset: Russian headings and text) | 5.3.0 | OFL-1.1 |

| Resource | Source | License | Status | Use |
|---|---|---|---|---|
| GetLayers layers: Neural Monitor (template), Roadmap Ascent, Slider Spectra, Cards Cascade (sections), Glass Halo, Halftone Iris, Lumen Grid, Signal Array (scenes), Pharos, Loupe, Riffle (gradients), Orb Studio, Text Animations (tools) | https://www.getlayers.ai | GetLayers licence, purchased by the team | team to confirm the licence terms, including whether the sources may sit in a public repository | Visual layers of the web app; changes listed in web/scripts/vendor-layers.mjs and in each adapted component |
| General Sans (woff2 files shipped in the Neural Monitor template) | Fontshare (Indian Type Foundry) | ITF Free Font License, as published by Fontshare | not verified | No longer used: the interface moved to Jost with the iridology.app look, and the build ships no General Sans file (the three files still sit unused in web/src/assets/fonts) |
| Brain model rotten-brain.glb (in the Neural Monitor template) | GetLayers template | as the template | team to confirm | Particle brain on the landing page |

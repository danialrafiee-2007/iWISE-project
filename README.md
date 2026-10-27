# Truth Guardian

Hallucination detection and reliability assessment for RAG and agentic AI answers.
Entry for iWISE 2026 AI & Web Programming Challenge, AI Challenge 4.

## Quick start (Windows)

Double-click `TruthGuardian.bat`. It checks that everything is in place, starts the web app offline and opens it in
the browser. To prepare the folder, install [uv](https://docs.astral.sh/uv/getting-started/installation/) and run
`TruthGuardian.bat setup` once with internet: it installs Python and the packages, downloads the datasets (checksums
verified) and the language models, builds the processed data and the fast HHEM export, warms up and caches the
examples, and skips whatever is already there.

Setup keeps everything the app needs inside the project folder, in `runtime/`: uv, Python 3.13, the package cache and
the language models (about 2 GB, not committed). After it, **the whole folder can be copied to another 64-bit Windows
computer and runs there offline, with nothing to install**. On the first start in a new folder the launcher rebuilds
`.venv` from `runtime/` without internet (about 20 seconds), so `.venv` itself need not be copied. Other systems use
the Docker image below. Code run directly (tests, scripts, `uv run`) keeps the language models in `runtime/hf` too
unless `HF_HOME` says otherwise, so nothing is downloaded into the user profile.

| Command | What it does |
|---|---|
| `TruthGuardian.bat` | start the web app (port 8765) and open the browser; if it is already running, just open it |
| `TruthGuardian.bat setup` | once, with internet: install and download everything into this folder |
| `TruthGuardian.bat check` | list what is present and what is missing |
| `TruthGuardian.bat test` | run the test suite |
| `TruthGuardian.bat smoke` | end-to-end check of the web app against the real models |

Options: `--port N`, `--no-browser`. On other systems the same steps are `uv sync` and
`uv run python -m truth_guardian.web --prepare` once, then `uv run --offline python -m truth_guardian.web`
(`--check` prints the checklist).

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

## Web app

One command starts it on http://127.0.0.1:8765 and opens the browser; the models load and warm up in the background
(about a minute on the project laptop), and the ready-made examples are checked once and kept on disk:

```bash
uv run --offline python -m truth_guardian.web
```

It runs fully offline (no CDN, no online fonts; Hugging Face is told not to reach the network, so the models must have
been downloaded once) and only answers on localhost. The top bar has Home, **AI engine**, About, Team and Contact us.
Resting the pointer on AI engine lists the challenge's four inputs, and on each the parts behind it (D-127): under
Text the tools (Analyze, Heal, Fool the Guardian, Agent guardian, Audit, Model card) and Examples, six written answers
each showing one check; under Audio, Image and Video a page that reads a file and one that names the models doing it
and what they have been shown to do. **Tour** lists one tour per input: the text tour walks through every tool in about
three minutes (`?tour=play` runs it hands-free); the others come once their pages are settled. Sources can be added
from PDF, Word, HTML, Markdown or text files.
The interface speaks English, Arabic, Chinese, French, Russian, Spanish and Persian (the globe at the end of the top bar,
or `?lang=fa`); Persian and Arabic pages read right to left. The checks themselves work on English answers and sources.
The built front end is committed in `src/truth_guardian/web/static`, so Node is not needed to run it.

The Contact page is the one part that uses the internet: its server sends each message by SMTP to the team's mailbox
(majidrafiee1404@gmail.com, fixed in `contact.py`). Copy `smtp.example.env` to `smtp.local.env` (ignored by git and
Docker) and fill in the sending account, for Gmail an app password; or set `TG_SMTP_USER` and `TG_SMTP_PASSWORD` in the
environment. Without them the page says that sending is not set up, and everything else stays offline.

### Images, sound and video (media readers, D-125)

The challenge's other inputs have local readers in `src/truth_guardian/media`, offline like the rest. Each turns a file
into text segments that say where they came from (a box in the image, a time range in the sound), which language and
script, and how sure the reader is; an unknown or uncertain language, silence or a weak reading goes to review instead
of being guessed.

| Input | Reader | Model (in `runtime/multimodal`, checked against `MODEL_MANIFEST.json`) |
|---|---|---|
| Sound | `speech.py` | Whisper Small through faster-whisper (CTranslate2 int8), language per segment |
| Text in images | `ocr.py` | Tesseract 5.5 (inside the `tesserocr` package) with tessdata_fast: the script first, then a few likely languages |
| What an image shows | `vision.py` | Qwen3-VL-2B (GGUF) through llama.cpp's `llama-server` in `runtime/tools`, an opinion, never proof |
| Video | `video.py` | PyAV: the soundtrack to Whisper, a few timed frames to Tesseract |
| Other languages' text | `multilingual.py` | multilingual E5 (retrieval) and mDeBERTa NLI, not yet part of the fusion model |

They come with the default `media` dependency group (`uv sync`), not with the Docker image. `GET /api/media/status`
shows, per reader, whether its files are present, its runtime is installed, it has run on known samples and its quality
has been evaluated, four separate things; `POST /api/media/read` reads one file. `uv run python scripts/media_pilot.py`
draws samples with known content, runs every reader on them with the network cut off and records what it read, its time
and its peak memory in `eval/results/media_pilot.json`. Those samples are synthetic: they show the readers work, not how
well they do on real media, which still needs labelled data.

On the landing page each of the four challenge inputs opens a panel where it is given to the models (D-126): write or
paste an answer with its sources, choose or paste an image, choose a video, or press the microphone and speak, in any
language; what was read or found comes back in the same panel, with where it was found and how sure the reader is. The
browser asks for the microphone once; it allows it on `localhost` and `127.0.0.1`, not on a plain `http://` address of
another computer.

To change the front end (Node 20 or later):

```bash
cd web
npm install
npm run layers   # only when the GetLayers scenes in web/layers-src change
npm run dev      # http://localhost:5173, API proxied to the Python server on port 8765
npm run build    # writes src/truth_guardian/web/static
```

## Results

The final model was evaluated once on each locked test set, with the thresholds chosen on RAGTruth dev; every run is
logged in `eval/locked_runs.log` and the reports are in `eval/results`. The web app's Model card reads them directly.

| Locked test set | Answers | Truth Guardian AUROC | Best baseline AUROC |
|---|---|---|---|
| RAGTruth test | 2,700 | 0.859 [0.843, 0.874] | 0.687 (B1 lexical overlap) |
| HaluEval QA (never trained on) | 1,000 | 0.933 | 0.845 (B1) |
| HaluEval dialogue | 1,000 | 0.670 | 0.514 (B1) |
| HaluEval summary | 1,000 | 0.694 | 0.642 (B1) |

On RAGTruth test: F1 0.721 (flagging every answer gives 0.518), character-level span F1 0.302, calibration error 0.061.
On AgentHallu (462 natural agent runs) the learned tracer finds the exact faulty step in 32% of hallucinating runs
against 18% for a random step, but tells faithful from hallucinating runs barely better than chance (AUROC 0.53).

External reference: LettuceDetect, a published detector fine-tuned on RAGTruth train itself (so RAGTruth test is its
home ground), scored on the same answers. On RAGTruth test it ranks answers less well (AUROC 0.827 against 0.859) but
finds the wrong words better (span F1 0.395 against 0.302); on HaluEval it scores 0.779 / 0.717 / 0.541 for QA /
dialogue / summary against our 0.933 / 0.670 / 0.694. See D-109

Calibration: a risk reads as a probability on RAGTruth (calibration error 0.034 on dev, 0.061 on the locked test;
the Model card shows the reliability diagram). On HaluEval, a domain the model never saw, it is 0.188 until a domain
profile recalibrates it (D-111).

The five harder cases the challenge description names were measured on 100 answers and agent runs written for them,
each paired with a faithful version (`benchmark/challenge_cases.json`, run once, D-110):

| Case | Answer flagged | What the case needs | Faithful twins flagged |
|---|---|---|---|
| Correct and incorrect information mixed | 20% | wrong part marked 55%, correct parts kept 100% | 0% |
| Only part of the evidence used | 20% (dropped caveats) | left-out fact named 100%, dropped caveat noticed 70% | 0% (a gap wrongly named 5%) |
| Claims no document supports | 70% | claim found 85% | 0% |
| Documents with low relevance or too little evidence | 100% | retriever blamed 45%, else the generator | honest answers 20% |
| Multi-step agents that generate or revise information | 45% | step where it began 45%, run stopped 55% | 0% (5% stopped) |

The risk still ranks the wrong answers above their faithful twins (AUROC 0.94, 1.00, 1.00 and 0.87 for mixed,
unsupported, weak sources and agents); the misses are answers just under the line, and an agent that keeps an
outdated value after a newer tool result is not caught (0 of 5). See D-110 in `docs/DECISIONS.md` for the full record.

### After the locked test (measured on development data only)

The locked sets were opened once (D-109) and not again; these later changes are measured on development and external
development data:

- **Domain profiles** (D-113): from 50 labelled answers of a new domain, a profile re-weights the model's evidence and
  recalibrates its risk. On HaluEval answers the profiles did not see: dialogue AUROC 0.683 to 0.723, summary 0.699 to
  0.789, calibration error about 0.24 to 0.07, verdict accuracy 60% to 68% and 58% to 72%. QA ranking was already high
  (0.916). Profiles never use answer length, which on HaluEval alone separates the labels (QA 0.98 AUROC).
- **Exact words** (D-115): a token-level detector trained on all of RAGTruth train narrows each flagged sentence to
  its marked words. RAGTruth dev span F1 0.371 to 0.406 (threshold chosen on one half of dev, measured on the other).
- **Overclaims** (D-114): stronger quantifiers and dropped hedges now count as hallucinations when confirmed, with
  settings chosen on train. Fool the Guardian: quantifier edits caught 37% to 57%, hedge edits 20% to 37%; opposite
  words unchanged at 45%.
- **Agents** (D-116): three fixes tried out of fold on AgentHallu dev made no difference; detection stays near chance.

The exact-word detector (90 MB) is not in the repository; without it the app marks whole sentences. Train it with
`uv run python scripts/train_detector.py --full` (about 7 hours on a laptop CPU) or copy `models/detector/full`.

## Online demo and Docker

The `Dockerfile` builds the whole app into one CPU-only Linux image (locked packages with the CPU build of PyTorch,
datasets with checksums, the two language models at pinned revisions, the ONNX export and the example cache; internet
needed for the build only) that runs offline on Docker Engine or Docker Desktop. `compose.yaml` runs it on this
computer only, with a health check that waits for the models:

```bash
docker compose up -d --build     # then http://127.0.0.1:7860; "docker compose ps" shows healthy when ready
```

`docs/DOCKER.md` has every command, the measured requirements (2 GB of memory for the container), what the image holds,
the security settings and the tested setups. `TG_ACCESS_CODE` asks every visitor for that code (any user name); without
it the app is open. `TG_ALLOWED_HOSTS` adds host names the server accepts. To give the judges a link, put it on a Hugging Face Space with your own account:

```bash
hf auth login
uv run python scripts/deploy_space.py --space your-name/truth-guardian --access-code choose-a-code
```

A public Space shows its files, including the built front end with the GetLayers layers, and lets anyone pull the
image; settle those licences first (`docs/CREDITS.md`) or pass `--private`.

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
- `docs/DOCKER.md`: running the app in Docker, its requirements and what was tested
- `benchmark/README.md`: TG-Bench data card

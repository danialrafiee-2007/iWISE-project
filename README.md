# Truth Guardian

Hallucination detection and reliability assessment for RAG and agentic AI answers.
Entry for iWISE 2026 AI & Web Programming Challenge, AI Challenge 4.

## For judges: the ready-made package

**One file does everything:** download `Get-Truth-Guardian.bat` from the latest
[Release](https://github.com/danialrafiee-2007/iWISE-project/releases/latest) and double-click it. Its questions all
come first: which drive to use (it makes the folder `iWISE_Truth Guardian` there), whether to delete the downloaded
parts once they are unpacked (about 5 GB back) and whether to put a shortcut on the desktop. Then it runs on its own:
it downloads the latest ready-made package (the whole source code with its tests and documents, Python with every
package, and every model) with the whole download's progress and the time left, checks each part against its SHA-256,
unpacks it and opens the app in the browser, offline from then on. A broken download resumes where it stopped; run
again, the file skips what is done and starts the app, and without internet it starts the copy already there. It
installs nothing in Windows and needs no administrator (D-213, D-217). Windows may warn about a file from the
internet: choose **More info**, then **Run anyway**; the release page gives the file's SHA-256 to check it first.

`scripts/build_portable.py` turns a finished install into one folder with everything the setup steps produce, so whoever
receives it has nothing to download or wait for beyond the first unpacking: they copy the folder, double-click
`Start-Truth-Guardian.bat`, and the app opens in the browser, offline. `README-FIRST.txt` in the folder says this in
English and Persian. To make it, after `TruthGuardian.bat setup`:

```bash
.venv/Scripts/python.exe scripts/build_portable.py --out D:/dist/TruthGuardian-Portable
```

The app is split into zip parts under 2 GB, for GitHub Releases and FAT32 drives. It carries the Visual C++ runtime beside
Python for a clean Windows, and the same data as the Docker image: no raw datasets, training data or locked test sets, so
`scripts/build_data.py` and the evaluation scripts need `TruthGuardian.bat setup` first. No key file or log goes in, and
nothing bought from elsewhere (the first site and its purchased layers left the project in D-214), so the package can be
published in a public Release.

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

Setup also fetches the models for sound, images and other languages, and the large weights of the language models, from
their official sources, checking each against `scripts/media_models.json`; a download that breaks resumes where it
stopped. If some could not be fetched, setup says so instead of reporting success, `TruthGuardian.bat check` lists them,
and running setup again fetches only what is missing. Two models do not come from setup: the exact-word detector
(`models/detector/full`; training it takes about 7 hours with `scripts/train_detector.py --full`, and without it flagged
claims mark the whole sentence) and the fast HHEM export behind the published numbers (`models/onnx`; without it setup
downloads HHEM's models and rebuilds it). Both are in the ready-made package: copy them from its unpacked `TruthGuardian`
folder into this one, keeping their paths, before setup.

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

`TruthGuardian.bat` starts it on http://127.0.0.1:8765 and opens the browser; the models load and warm up in the
background (about a minute on the project laptop):

```bash
uv run --offline python -m truth_guardian.web
```

The site is plain HTML5, CSS3 and JavaScript in `src/truth_guardian/web/static_html`: no framework, no build step, no
CDN or online font, nothing that needs Node. It is one page whose parts change softly, with a rail on the left: **Home**
(a chat that answers from the person's files and the project's documents and checks every answer before it is shown,
with three lamps for the local models, the free online models and the Guardian), **Model performance** (check an
answer, reliability with the calibration diagram, check an agent, fool the Guardian), **Architecture** (the engine's
real code as a live map, every node opening its code), **Team**, **About** and **Contact**. A 26-step tour walks the
judges through the site and its brain, and the activity log (bottom corner) shows what the page and the engine do,
live, with the project's history, downloadable as CSV or JSON. The first site, in React with bought visual layers, was
removed for the final project (D-214); its strings live on in `src/truth_guardian/web/i18n`.

The interface speaks English, Arabic, Chinese, French, Russian, Spanish and Persian (the globe in the rail); Persian and
Arabic pages read right to left. English answers over English sources go to the English engine; Arabic, Chinese, French,
Russian and Spanish (also across languages) go to a separate, experimental multilingual check (multilingual E5 and
mDeBERTa NLI, D-137, D-138), which on its dev set ranks answers at 0.77 to 0.85 AUROC by language but sees fewer kinds of
error than the English engine; Persian answers get a lighter check of numbers, dates and names, and the page says so.
The language comes from the texts, never from the interface.
On real media (D-139, `scripts/evaluate_media.py`): Whisper hears read speech with 5.5 to 13% word errors in Spanish,
English, Russian and French (33% Arabic, 22% of Chinese characters) and names the language every time, and the chain
then tells a transcript from one with a changed fact at 0.74 to 0.78 AUROC (0.65 Chinese). Photos of scenes are another
matter: Tesseract, built for documents, reads the answer's words in only 4 to 26% of them, so the check finds little
evidence there and calls most answers unsupported; documents and screenshots read well.

The Contact page is the other part that uses the internet: its server sends each message by SMTP to the team's mailbox
(majidrafiee1404@gmail.com, fixed in `contact.py`). Copy `smtp.example.env` to `smtp.local.env` (ignored by git and
Docker) and fill in the sending account, for Gmail an app password; or set `TG_SMTP_USER` and `TG_SMTP_PASSWORD` in the
environment. Without them the page says that sending is not set up, and everything else stays offline.

### Document library (the RAG's first part, D-163)

Files the person adds and the project's own documents are cut into passages of about 120 words that keep their page,
embedded once with multilingual E5 and kept in `data/web/library/library.sqlite`, offline. Search fuses meaning with word
search, in any checked language and across them. `GET /api/library` lists, `POST /api/library/documents` adds a file with its
progress streamed, `DELETE /api/library/documents/{id}` removes one of the person's own, and `POST /api/library/search`
returns the closest passages and `enough`, whether they are close enough to hold an answer. On XQuAD
(`scripts/evaluate_retrieval.py`, half its articles held out) the right paragraph is in the top five 98.8 to 100% of the time in
the same language and 89.2 to 99.0% over English; encyclopaedia paragraphs are an easy case, so real documents will do
less well. `enough` is weaker: it refuses 57 to 90% of questions the library cannot answer in the same language, and across
languages only the clearly unrelated.

A recording or an image goes in as text (D-165): what was said with its time, the words read in the image, and the image
model's description, marked as its opinion. `POST /api/library/read` shows what was extracted without adding it, and
`POST /api/library/reviewed` adds it as a person corrected it, marked as reviewed (D-167).
Readers make mistakes: speech has 5.5 to 32.7% word errors and text in photographs reads poorly, and Persian is unmeasured.

### Asking the documents (the RAG, D-164, D-168, D-169)

The page `/ask` is where text, sound and images meet. A document, a recording or an image is added from the conversation or the
library's tab; what was read in a recording or an image is shown for review first, beside the file. A question then searches all
of it, the model writes from the closest passages and looks at their images, and every answer carries how it was checked and its
sources. Its other tabs check an answer about a recording or an image (D-135). This is one system of several models, not one
model: the readers turn files into text, which is what the Guardian can check. On made-up files, answers needing two or three
files of different kinds had every part right in 8 of 8 questions (`scripts/evaluate_mixed.py`); real photographs and noisy
recordings are untested.

`POST /api/ask` answers a question from the library and streams its stages, its text and the result. The closest passages go
to the local model (Qwen3-VL-2B), which cites them as [n]. When nothing
is close enough, the answer says the documents do not say, without calling a model. The Guardian checks every answer against
the passages it was given and its verdict is shown beside it; Persian gets a lighter check, labelled as such, and an answer
resting on the image model's description is marked as an opinion and not checked.

Measured on the local model (`scripts/evaluate_answers.py`, final run of D-172). On held-out XQuAD articles, 90 of 100
questions whose article is left out say the documents do not say and none ends as a grounded answer, and the right article is
shown 95 to 100% of the time. On 28 real documents in seven languages (`eval/rag_documents`, questions written by us), no
answerable question of 56 was stopped, the expected words are in 51, and 19 of 21 without an answer say so. What it does not do:
a verdict says an answer rests on its sources, not that it answers the question; outside English the check calls many right
answers uncertain (of 44 right answers in six languages, 22 were grounded), and neither check can judge a bare short answer
such as "308", so the model is asked for whole sentences (D-172).

When the documents hold no answer, `POST /api/ask/free` (D-191, `rag/free.py`) asks online instead, with no Claude and
nothing paid: a free model answers (Groq or OpenRouter when their keys are in `free.local.env`, see `free.example.env`;
otherwise Pollinations, which needs no key and gives one answer every 45 seconds) and names the pages it relied on. The
Guardian then reads those pages (Wikipedia's API for Wikipedia articles, Jina Reader for the rest, cleaned of markup) and
finds its own sources on Wikipedia in the question's language and in English, never from the model's choice. The local
engine checks every claim against all of them, and each source is labelled: supports, contradicts, unrelated, could not
be opened (a page the model named that does not open may not exist), or read but not judged (the light check of a
language no full check reads, such as Persian). The verdict is the local engine's, not another model's opinion; a
grounded verdict means the answer agrees with what was found, and Wikipedia does not hold everything. The HTML chat calls
it by itself, and its "Truth Guardian check" button shows the last answer's full report under the chat.
`scripts/free_trial.py` runs ten mixed questions through it and keeps every answer with its sources and labels.

### The agent (D-170)

On the same page, "Agent, step by step" lets the model decide in several steps what to search for and work out, with the live
Guardian reading each step as it happens. Its tools only read: searching the library, listing the documents, and arithmetic. An
answer stating what no tool returned goes back once, and a second time ends the run with no answer shown; the finished answer is
then checked with the agent's log. `POST /api/agent/run` streams its steps. On made-up files with the local model
(`scripts/evaluate_agent.py`), 7 of 8 English tasks were right, sums among them, and all 3 without an answer said so, in about 30 s
each. In Persian it is much weaker: 3 of 4 held the right words, one with a wrong weekday, which the light check now marks, and
one with a misspelled name, which it cannot see. A name the task writes in Persian no longer draws the live guardian's objection
when the agent thinks in English: 1 of 4 Persian runs drew one, against 3 before (D-172).

### Sound and images (media readers, D-125)

The challenge announced text only; sound and images are the project's own additions, with local readers in
`src/truth_guardian/media`, offline like the rest. Video was dropped (D-140). Each turns a file
into text segments that say where they came from (a box in the image, a time range in the sound), which language and
script, and how sure the reader is; an unknown or uncertain language, silence or a weak reading goes to review instead
of being guessed.

| Input | Reader | Model (in `runtime/multimodal`, checked against `MODEL_MANIFEST.json`) |
|---|---|---|
| Sound | `speech.py` | Whisper Small through faster-whisper (CTranslate2 int8), language per segment |
| Text in images | `ocr.py` | Tesseract 5.5 (inside the `tesserocr` package) with tessdata_fast: the script first, then a few likely languages |
| What an image shows | `vision.py` | Qwen3-VL-2B (GGUF) through llama.cpp's `llama-server` in `runtime/tools`, an opinion, never proof |
| Other languages' text | `multilingual.py` | multilingual E5 (retrieval) and mDeBERTa NLI, read by the multilingual check (D-138) |

Their Python packages come with the default `media` dependency group (`uv sync`), not with the Docker image; setup
fetches the model files (`scripts/fetch_media_models.py`). `GET /api/media/status`
shows, per reader, whether its files are present, its runtime is installed, it has run on known samples and its quality
has been evaluated, four separate things; `POST /api/media/read` reads one file. `uv run python scripts/media_pilot.py`
draws samples with known content, runs every reader on them with the network cut off and records what it read, its time
and its peak memory in `eval/results/media_pilot.json`. Those samples are synthetic: they show the readers work, not how
well they do on real media, which still needs labelled data.

In the chat a recording or an image is added like a document: what was read in it becomes text the Guardian can
check, and an answer about an image is checked against what the OCR reader read in it (D-199). A free online model gives
a second, independent reading of the same image or recording, and the Guardian marks each sentence agreed, disputed or
unclear (D-200). The browser asks for the microphone once; it allows it on `localhost` and `127.0.0.1`, not on a plain
`http://` address of another computer.

To change the site, edit the files in `src/truth_guardian/web/static_html` and reload the page; after changing a Python
file the Architecture page shows, run `uv run python scripts/build_arch_source.py` so its code map shows the code as it
is (a test fails until then).

## Results

The locked test sets were opened twice, each time with the system as the app runs it and the thresholds chosen on RAGTruth
dev: at the end of the Guardian's build (D-109), and after the RAG and the checks of phase 5 were added (D-172). The table
gives the second; the fusion model is the same, only the rules around it grew. Every run is logged in `eval/locked_runs.log`
and the reports are in `eval/results`. The web app's Reliability page reads them directly.

| Locked test set | Answers | Truth Guardian AUROC | Best baseline AUROC |
|---|---|---|---|
| RAGTruth test | 2,700 | 0.856 [0.840, 0.871] (first: 0.859) | 0.687 (B1 lexical overlap) |
| HaluEval QA (never trained on) | 1,000 | 0.933 | 0.845 (B1) |
| HaluEval dialogue | 1,000 | 0.670 | 0.514 (B1) |
| HaluEval summary | 1,000 | 0.691 (first: 0.694) | 0.642 (B1) |

On RAGTruth test: F1 0.717 (first: 0.721; flagging every answer gives 0.518), character-level span F1 0.325 (0.302),
calibration error 0.069 (0.061).
On AgentHallu (462 natural agent runs) the learned tracer finds the exact faulty step in 32% of hallucinating runs
against 18% for a random step, but tells faithful from hallucinating runs barely better than chance (AUROC 0.53).

External reference: LettuceDetect, a published detector fine-tuned on RAGTruth train itself (so RAGTruth test is its
home ground), scored on the same answers. On RAGTruth test it ranks answers less well (AUROC 0.827 against 0.856) but
finds the wrong words better (span F1 0.395 against 0.325); on HaluEval it scores 0.779 / 0.717 / 0.541 for QA /
dialogue / summary against our 0.933 / 0.670 / 0.691. See D-109 and D-172

Calibration: a risk reads as a probability on RAGTruth (calibration error 0.034 on dev, 0.069 on the locked test;
the Reliability page shows the reliability diagram). On HaluEval, a domain the model never saw, it is 0.188 until a domain
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

### After the first locked test (measured on development data only)

The locked sets were opened twice: first at the end of the Guardian's build (D-109), then once more after phase 5 (D-172),
as the Results above say. The changes below came between the two openings. Each was chosen and measured on development
and external development data only; the second opening then measured the whole system with them. A second opening makes
the locked numbers somewhat less clean than a single one would be, which is why the table above shows both runs:

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

A public Space shows its files, including the built front end with the purchased layers, and lets anyone pull the
image; settle those licences first (`docs/CREDITS.md`) or pass `--private`.

## Benchmark

`benchmark/` holds TG-Bench, the project's mini-benchmark of controlled edits and agent runs, with its own README.

## Data format

Every dataset is converted to one JSONL format defined in `src/truth_guardian/schema.py`.
Each line is a `Sample`: question, documents, answer, optional evidence and agent log, labels and meta.
`meta.group_id` ties samples that share a source; a group never crosses train/dev/test splits.

## Project layout

One folder holds everything, and nothing that belongs to the project lies beside it (D-171).

| Path | What it holds | In git |
|---|---|---|
| `src/truth_guardian/` | the Guardian, the RAG (`rag/`), the readers (`media/`), the web app (`web/`) | yes |
| `tests/`, `scripts/`, `eval/`, `benchmark/`, `docs/`, `deploy/` | tests, tools, measures and their results, TG-Bench, documents, the package's starter | yes |
| `models/` | the trained fusion models and profiles; the exact-word detector and the fast HHEM come from the ready-made package (see Quick start) | partly |
| `data/` | datasets, cached examples, the document library | no |
| `runtime/` | uv, Python, the package cache, the language models, the readers; `rag-eval/` and `npm-cache/` are working files that stay out of the package | no |
| `.venv/` | built by the launcher from `runtime/`, for this folder only | no |
| `dist/` | the judges' package, written by `scripts/build_portable.py` | no |

To keep it this way: use a branch, not a second clone or copy; keep lasting working files under `runtime/` and add any new
folder there to `LEFT_OUT` in `scripts/build_portable.py`; test a package in a temporary folder and remove it afterwards.

## Documentation

- `docs/AI_USAGE.md`: AI tools used, by whom, for what, and how outputs were verified
- `docs/CREDITS.md`: datasets, models and libraries with their licenses
- `docs/DECISIONS.md`: key technical decisions and why
- `docs/DOCKER.md`: running the app in Docker, its requirements and what was tested
- `benchmark/README.md`: TG-Bench data card

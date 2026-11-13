# Architecture (as implemented at commit c5e4ac81 / package 20261111-1615-e88d666b)

> Verified from source on 2026-11-13. Paths are relative to the working copy `Edit_IWISE_Project\TruthGuardian`.

## 1. Runtime picture

```
Browser ── same origin ──► FastAPI / uvicorn  127.0.0.1:8765   (src/truth_guardian/web/__main__.py, app.py)
  static_html/ (HTML, CSS, JS)     ├─ GET /{path}   → static_html files, SPA fallback to index.html (no-cache)
  fetch /api/* (JSON)              ├─ /api/*        → Engine (one lock; checks queue) + RAG + media + free online
  NDJSON streams for long work     └─ background thread at start: load + warm up models, cache examples
```

- **Start:** `TruthGuardian.bat`
  - checks the environment and rebuilds `.venv` offline from `runtime/` when the folder moved (`:env_check`, `:env_build`)
  - then runs `uv run --offline python -m truth_guardian.web --port 8765`
  - modes: `setup`, `check`, `test`, `smoke`
- **Offline by default:** `HF_HUB_OFFLINE=1`, and models load from `runtime/hf` (the package sets `HF_HOME`, D-119).
- **Hosts:** only localhost host names are accepted (TrustedHostMiddleware). `TG_ALLOWED_HOSTS` adds hosts and
  `TG_ACCESS_CODE` adds HTTP Basic access (for a hosted demo).

## 2. Directory map

| Path | Role |
|---|---|
| `src/truth_guardian/` | Engine: signals, fusion, rules, report contract, tracer and guardian, heal, multilingual |
| `src/truth_guardian/rag/` | Library (SQLite + E5 + BM25), answer, generators (local only), agent, media ingest, `free.py` (online), `second.py`, `seen.py`, `learned.py`, `words.py`, `chunks.py` |
| `src/truth_guardian/media/` | Readers: `speech.py` (Whisper), `ocr.py` (Tesseract), `vision.py` (Qwen3-VL via llama-server) |
| `src/truth_guardian/web/` | `app.py` (all endpoints), `engine.py`, `examples.py`, `metrics.py` (model card), `activity.py` (log), `contact.py`, `documents.py`, `doctor.py`, `i18n/*.ts` (strings source), `static_html/` (**the site**) |
| `models/` | Fusion ensemble `20261022-082833-ensemble`, multilingual fusion, tracer, domain profiles, detector, HHEM ONNX |
| `runtime/` | `python/` (CPython 3.13.17), `uv/`, `uv-cache/` (offline wheels), `hf/` (HF models), `multimodal/` (Whisper, Qwen3-VL GGUF, tessdata, E5, mDeBERTa), `tools/llama.cpp`, `logs/` (activity) |
| `data/` | `processed/` (dev sets for examples and Fool), `raw/nltk_data` (WordNet), `web/examples/` (cached example reports), `web/library/library.sqlite` (document library), `web/learned_seed.json` |
| `eval/results/` | Evaluation JSON files read live by the Reliability tab (`metrics.py`) |
| `scripts/` | 69 scripts: build data, train, evaluate, `build_arch_source.py`, `build_portable.py`, `build_icon.py`, ... |
| `tests/` | 62 files, 565 test functions (pytest); `test_html_ui.py` covers the site statically |
| `docs/` | `DECISIONS.md` (224 decisions), `AI_USAGE.md`, `CREDITS.md`, `DEMO.md`, `DOCKER.md`, data cards |
| `Get-Truth-Guardian.bat`, `TruthGuardian.bat`, `deploy/portable/` | Judges' downloader, app launcher, package starter |

## 3. API (src/truth_guardian/web/app.py) and who calls it

Streams are newline-delimited JSON, one event per line: `stage`, `check`, `queued`, `text`, `step`, then a final
`result` or `error`.

| Endpoint | Kind | Called by (static_html/js) |
|---|---|---|
| `GET /api/health` | JSON | `app.js` (Guardian lamp, every 2 s until ready), `check.js`, `fool.js` |
| `GET /api/examples`, `GET /api/examples/{id}` | JSON | `check.js`, `agent.js` |
| `POST /api/analyze` | stream | `check.js` |
| `POST /api/heal` | stream | `check.js` |
| `POST /api/agent` | stream | `agent.js` |
| `GET /api/fool/answers`, `POST /api/fool/edit`, `GET /api/fool/tricks/{id}`, `POST /api/fool/check` (stream) | | `fool.js` |
| `GET/POST /api/documents` | JSON | `check.js` (read PDF, DOCX, HTML, MD, TXT into sources) |
| `GET /api/model-card` | JSON | `models.js`, `check.js`, `agent.js`, `fool.js` |
| `GET /api/media/status` | JSON | `app.js` (local lamp), `models.js` |
| `POST /api/media/read` | JSON | `chat.js` (microphone → transcript) |
| `GET /api/library`, `POST /api/library/documents` (stream), `POST /api/library/read`, `POST /api/library/reviewed`, `GET .../{id}/picture`, `GET .../{id}/passages`, `DELETE .../{id}`, `POST /api/library/search` | | `chat.js` uses `documents` and `passages`; the rest have no caller in the site (left from the React site) |
| `GET /api/ask/generators` | JSON | `app.js` |
| `POST /api/ask` | stream | `chat.js` |
| `POST /api/agent/run` | stream | no caller in the site (React-era agent mode) |
| `GET /api/online/status` | JSON | `app.js` (online lamp, every 60 s) |
| `POST /api/ask/free` | stream | `chat.js` (when the documents hold no answer, or the local answer is untrusted) |
| `GET /api/learned`, `POST /api/learned/settings`, `DELETE /api/learned/{id}` | JSON | `chat.js` |
| `GET/POST /api/contact` | JSON | `contact.js` (falls back to `mailto:`) |
| `GET /api/activity`, `/api/activity/download`, `/api/activity/history` | JSON | `activity.js` |

## 4. Main data flows

**Chat (home page, `chat.js`):**

1. The question goes to `POST /api/ask` (`rag/answer.py`).
   - The library finds the closest passages (E5 + BM25, RRF).
   - The local Qwen3-VL-2B writes an answer with `[n]` citations.
   - The Guardian checks it, and heals it if flagged.
   - A non-English answer gets the "light" check, and Persian has no full verdict.
2. If the answer is `not_in_documents`, **or** the site judges it untrusted (`hallucinated`, or half or more of its
   sentences doubtful in the light check), it goes to `POST /api/ask/free` (`rag/free.py`):
   - a free model answers
   - Jina Reader opens the pages the model named
   - the Guardian finds its own sources (Wikipedia, Wikidata, Tavily, World Bank, OpenAlex)
   - the local engine checks every claim, and each source is labelled supports, contradicts, unrelated or could not open
3. A verified online answer may be kept in the "learned" collection (`rag/learned.py`).
4. The bubble shows the answer only. **"Truth Guardian check"** opens the last answer's full report in a dialog
   (`report.js`).

**Files in the chat:** each file goes to `POST /api/library/documents` with `describe: true`. It is read (OCR, speech,
or vision description) and embedded straight into the person's library. There is **no review step** in the HTML site.

**Check an answer (`check.js`):**
- pick an example (cached report) or enter your own question, sources and answer
- `POST /api/analyze` streams the stages; the report renders through `TGReport.render`
- optionally `POST /api/heal` runs the healing rounds

**Check an agent (`agent.js`):** `POST /api/agent` returns the report and the agent timeline. The steps are replayed
client-side as the "Guardian's path".

**Fool the Guardian (`fool.js`):** `/api/fool/*` (apply a trick, then stream the check of the edited answer).

## 5. Models

- **Local:**
  - all-MiniLM-L6-v2, nli-deberta-v3-base, HHEM (ONNX), the fusion ensemble (own), the token detector (own) and the
    learned tracer (own)
  - multilingual E5 + mDeBERTa
  - Whisper Small (faster-whisper int8), Tesseract 5.5, Qwen3-VL-2B (GGUF, llama.cpp)
- **Online (free, optional):**
  - Pollinations (no key); Groq `openai/gpt-oss-120b`, Groq Whisper large-v3 and Groq Qwen vision; OpenRouter
    Nemotron (keys in `free.local.env`)
  - Tavily (key optional), Wikipedia, Wikidata, World Bank, OpenAlex, Jina Reader
- **No Claude/Anthropic code remains** (D-216).

## 6. State and storage

| Store | Content | Notes |
|---|---|---|
| `data/web/library/library.sqlite` | The document library: project documents plus everything a person adds, and learned answers | Persistent; one shared store per installation |
| `data/web/examples/*.json` | Cached reports of the ready-made examples | Rebuilt when the model version changes |
| `runtime/logs/activity-YYYY-MM-DD.jsonl` | Engine activity log | Only the first words of a question are kept, never file content |
| Browser `localStorage` | `tg-lang` (language), plus the activity log's page-side rows | Per browser |
| `free.local.env`, `smtp.local.env` | Optional keys | Not present in the source; git-ignored. **Never commit them** |

## 7. Security baseline (verified in app.py)

- TrustedHost localhost only; strict Pydantic bodies (`extra="forbid"`) with length caps; a path-traversal guard on
  static files; contact headers folded to one line with a fixed recipient and rate limiting; joblib models checked by
  SHA-256 against their manifests.
- Front end: every `innerHTML` template escapes data with an `esc()` helper; external links get
  `rel="noopener noreferrer"`.
- Risks to remember (verified in code; severity is my assessment):
  - **The library is shared** by everyone who can reach the server (one SQLite file). This matters only on a hosted
    demo.
  - **Questions leave the computer automatically** when the documents hold no answer, or the local answer is judged
    untrusted. Where they go:
    - the question → a free model (Pollinations, Groq or OpenRouter)
    - search words → Wikipedia, Wikidata, Tavily, World Bank and OpenAlex
    - pages the model named → Jina Reader (`r.jina.ai`)
    - images and recordings → Groq or OpenRouter, only if a key is set
    The UI asks no per-question consent; the online lamp is the only indication.
  - **Blind server-side request** (`rag/free.py` `probe()`): when Jina cannot read a page the model named, the server
    sends a GET to that URL itself to tell "not found" from "blocked". A URL chosen by an online model, possibly
    steered by the question, can therefore make the server contact any address, including localhost or the LAN.
    Only the status is used, never the content, so the impact is low on a single-user local install.
  - **No rate limit on heavy endpoints** (`/api/analyze`, `/api/ask`, `/api/ask/free`, media). Checks queue on one lock.
  - **Page-side activity log:** `localStorage["tg-activity-site"]` keeps up to 1,000 rows, with up to 300 characters of
    each question. The comment says "only the first words".
  - **The contact recipient** (a personal Gmail address) is hard-coded in `web/contact.py`, `js/contact.js` and an
    `index.html` comment, so it is visible to anyone who views the source.

### External hosts the server may contact (from `rag/free.py`, `rag/second.py`)

`text.pollinations.ai`, `api.groq.com`, `openrouter.ai`, `api.tavily.com`, `{lang}.wikipedia.org`, `www.wikidata.org`,
`api.worldbank.org`, `api.openalex.org`, `r.jina.ai`, plus any URL named by the online model (see `probe()`), and
SMTP (`smtp.gmail.com` by default) for Contact when it is configured. Its User-Agent names the project and its GitHub
URL.

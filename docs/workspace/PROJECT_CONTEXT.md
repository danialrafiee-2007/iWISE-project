# Project context: Truth Guardian (IWISE_London)

> Workspace knowledge file. Written 2026-11-13 from direct inspection of the code, not from memory.
> Before relying on any statement here, check the file it names. Update this file when the facts change.

## What the project is

Truth Guardian is the team's entry to **iWISE 2026 AI & Web Programming Challenge, AI Challenge 4** (hallucination
detection and reliability assessment for RAG and agentic AI answers). Official repository:
`https://github.com/danialrafiee-2007/iWISE-project`.

The challenge text, as the team recorded it in `docs/DECISIONS.md` D-143 (read on iwise.org on 2026-11-02):

- Inputs per sample: Question, Retrieved Documents, AI Answer, Evidence, Agent Logs.
- Outputs, at least: a Grounded/Hallucinated label, a risk score or probability, the suspicious or unsupported parts
  when possible, and evidence or an explanation.
- Five harder cases: mixed correct/incorrect information, partial use of evidence, unsupported claims, low-relevance or
  insufficient documents, and multi-step agents that generate or revise information.
- The challenge announced **text only**. Audio and images are the team's own additions.
- The full official brief is **not** in the repository.

## Locations

| What | Path | Rule |
|---|---|---|
| Source project (read-only) | `A:\Apps\IWISI_London\iWISE_Truth Guardian\TruthGuardian` | Never modify, install into, move or delete |
| Workspace root | `A:\Apps\IWISI_London\Edit_IWISE_Project` | Holds unrelated material too (`video/`): never touch it |
| Working copy (develop here) | `A:\Apps\IWISI_London\Edit_IWISE_Project\TruthGuardian` | All application work happens here |
| These docs | `Edit_IWISE_Project\TruthGuardian\docs\workspace\` | Keep in sync with the code |
| Session pointer | `Edit_IWISE_Project\CLAUDE.md` (outside the repo, so it is never committed) | Tells every new Claude session to read these docs first |
| Git (working copy) | Repository at `c5e4ac81`; `origin` = official repo; `main` tracks `origin/main` | Attached 2026-11-13 without changing files; see `GIT_WORKFLOW.md` §7 |
| Personal Git branch | `sepehr/ui-ux-development` (local, checked out, **not pushed**; its first commit holds these docs) | All UI/UX commits go here. **Never push to `main`** (a pre-push hook blocks it). Commit messages name no AI tool (D-152) |

## What the source and the working copy are (verified 2026-11-13)

- The source is the team's **ready-made package**, build `20261111-1615-e88d666b` (`..\packages\package.txt`).
- **It is not a Git repository**: there is no `.git` anywhere in it.
- All 433 files that Git tracks at commit **`c5e4ac81`** (tag `package-20261111-1611`, which is `main` on GitHub as of
  2026-11-13) are byte-identical in the package. I compared each file's Git blob hash with GitHub's tree.
- On top of that commit, the package adds untracked runtime assets:
  - `runtime/` (Python 3.13, uv, the uv cache, Hugging Face models, media models, llama.cpp, logs)
  - `.venv/`
  - `data/` (processed dev data, example cache, document library, NLTK WordNet)
  - model weights (detector, HHEM ONNX)
  - eval logs and `__pycache__`
- The working copy is a full copy of the source **except `.venv/`**. See `DEVELOPMENT_LOG.md` for the exclusion and its
  verification.

## The product today (code at c5e4ac81)

- **One front end:** plain HTML5, CSS3 and JavaScript in `src/truth_guardian/web/static_html/`. There is no framework and no
  build step.
  - The React/Vite site (`web/`) was **removed** in D-214. Do not look for it.
  - Its strings survive in `src/truth_guardian/web/i18n/*.ts`.
- **Back end:** a FastAPI server, `python -m truth_guardian.web`, on `127.0.0.1:8765`. It serves the site and `/api/*`.
  Launched by `TruthGuardian.bat`.
- **Engine:** fully offline English text check (signals, fusion ensemble, rules, report), plus:
  - an experimental multilingual check
  - a RAG chat over a local document library (local Qwen3-VL-2B through llama.cpp)
  - an agent mode
  - audio and image readers (Whisper Small, Tesseract, Qwen3-VL)
- **Online (free services only; Claude removed in D-216):** when the documents hold no answer, the question goes to a
  free model (Pollinations with no key; Groq or OpenRouter with a key). The local Guardian then checks that answer
  against sources it fetches itself (Wikipedia, Wikidata, Tavily, World Bank, OpenAlex, Jina Reader).
- **"What it learned online" (D-222):** verified online answers are kept in the library and answered offline next time.

## Facts that matter for UI/UX work

1. **There is no build step.** Edit the files in `static_html/` and reload the page.
2. **Cache busting:** `index.html` loads every CSS and JS file with `?v=71`. Static files are served without cache
   headers, and only `index.html` is sent with `no-cache`. **Bump `v=` in `index.html` whenever a CSS or JS file
   changes**, or browsers may keep the old file.
3. **`js/i18n.js` is generated** (7 languages, 1,039 keys in English). Its generator script is **not** in the
   repository; it says it is built from `src/truth_guardian/web/i18n/*.ts` plus the `html.*` strings. Until the
   generator is found, edits go into `i18n.js` directly, and the `.ts` sources may drift from it.
4. **`js/arch-src.js` is generated** by `scripts/build_arch_source.py`. Never hand-edit it.
5. **The front-end tests are static.** `tests/test_html_ui.py` (24 tests) asserts the contents of `index.html`, CSS
   and JS: element IDs, class names, endpoints, "no http(s) URL in front-end files". A UI change can break them;
   run and update them together.
6. **No internet in the front end.** No CDN, no web fonts, no `http(s)://` in HTML, CSS or JS (a test enforces this).
7. **Server text arrives in English.** Claim explanations, triage reasons, diagnosis messages and warnings come from
   the Python report in English and are shown untranslated on non-English pages.

## Working rules (from the user, Phase 1 brief)

- Read the relevant docs here first, then the actual source files, before any change.
- Understand dependencies and side effects; never assume an old explanation is still true.
- Record every meaningful change in `DEVELOPMENT_LOG.md`: files, reasons, details, verification.
- Until implementation is explicitly authorized: no redesign, no functional change, no refactor, no dependency
  install or upgrade, no Git branch changes, no push.
- Never modify the source project.
- Never commit or publish secrets (`*.local.env`, keys, tokens).

## Related docs

- `ARCHITECTURE.md`: system, API, data flow
- `UI_UX_GUIDE.md`: visual identity and UX patterns
- `COMPONENT_MAP.md`: pages, scripts, CSS and endpoints
- `GIT_WORKFLOW.md`: Git state and the proposed branch workflow
- `DEVELOPMENT_LOG.md`: what changed and how it was verified
- Team docs: `docs/DECISIONS.md` (D-001…D-224), `docs/AI_USAGE.md`, `docs/CREDITS.md`, `README.md`

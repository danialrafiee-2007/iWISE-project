# Component map: the site (`src/truth_guardian/web/static_html/`)

> Verified 2026-11-13 at commit c5e4ac81. Line counts: `index.html` 622, `css/style.css` 2,284, `css/intro.css` 267.
> Scripts: `ui` 409, `check` 523, `chat` 515, `arch-graph` 412, `fool` 395, `deck` 378, `pages` 261, `agent` 259,
> `activity` 226, `models` 220, `report` 163, `arch-data` 144, `app` 106, `contact` 75, `intro` 65.
> Generated: `i18n.js` (7,281 lines), `arch-src.js` (171 KB).

## 1. Script loading and shared globals

Classic `<script>` tags at the end of `<body>`, in this order (they depend on it):

`i18n.js → ui.js → activity.js → intro.js → pages.js → arch-data.js → arch-src.js → arch-graph.js → contact.js →
report.js → models.js → deck.js → check.js → agent.js → fool.js → chat.js → app.js`

Each file is an IIFE or a top-level script and talks to the others through globals:

| Global | Defined in | Purpose |
|---|---|---|
| `window.TG_MESSAGES` | i18n.js | All strings, by language |
| `window.TG` (`t`, `setLang`, `lang`, `onLang`, `closeMenus`, `go`, `openTab`) | ui.js (+ pages.js adds `go` and `openTab`) | i18n, menus, navigation |
| `window.TGLog` | activity.js | `log(category, action, detail, level)`: page-side activity rows |
| `window.TGReport` (`render`, `progress`) | report.js | Draws a Guardian report and the stage progress list |
| `window.TGDeck` (`examples`, `tricks`) | deck.js | 3D card decks |
| `window.TGCheck` | check.js | Lets other parts bring an answer into Check an answer |
| `window.TG_ARCH`, `window.TG_SRC` | arch-data.js, arch-src.js | Code-map graphs and the real source text |
| DOM event `tg:entering` | intro.js → pages.js | The intro tells the page to play its entrance |

**Duplicated helpers (technical debt):** `esc()`, `num()`, `pct()`, `label()`, the NDJSON `stream()` reader and
`base64` are re-implemented in several files (`chat.js`, `check.js`, `report.js`, `fool.js`, `agent.js`, `models.js`).

## 2. Shell (every page)

| Part | Markup | CSS | JS |
|---|---|---|---|
| Intro overlay | `section#intro` (16 path pieces + solid shield + name) | `intro.css`, `.site` clip-path circle | `intro.js` |
| Panel + rail | `.site > .panel > nav.rail` | `.panel`, `.rail`, `.rail-btn`, `.rail-line`, `.rail-gap`, `::after` tags, `::before` bead tab | `ui.js` (pointer light `--ly`, magnification `--mag`) |
| Language menu | `.rail-menu[data-menu=lang] > .pop.pop-lang#lang-menu` | `.pop`, `.pop-item` | `ui.js` `renderLanguages`, `open`, `close` |
| Site tour | `button[data-tour=site]` → `.tour-layer`, `.tour-dim`, `.tour-spot`, `.tour-card` | §tour | `ui.js` `STEPS` (26) |
| Status lamps | `#rail-lamp`, `#rail-online-lamp`, `#rail-guard-lamp` + home chips `#state`, `#online-state`, `#guard-state` | `.lamp`, `.lamp.ready`, `.lamp.bad`, `.status-chip`, `.status-stack` | `app.js` |
| Activity log | `.log-fab` (made by JS) → `dialog.log-dialog` | §activity log | `activity.js` |
| Page switcher | `main#main > .page[data-page]` | `.page`, `.leaving`, `.entering-page .layer` | `pages.js` |
| Banner (per page) | `section.banner` → `h1.banner-title > .title-glow + .title-text` | `.banner`, `.title-*`, `.banner-text` | n/a |

## 3. Pages

### `/` Home: "Ask Truth Guardian" chat
- **Purpose:** ask a question (typed or spoken), add files, get a locally written answer checked by the Guardian;
  online fallback.
- **Markup:**
  - `section.home-banner` (lead text box plus three lamp chips)
  - `section.card.chat#chat`: `button.learn-btn#chat-learned`, `ol.chat-log#chat-log`, `form.composer#composer` (file
    chips, a textarea that grows to 180px, attach label, mic button, note, `button.check-btn#chat-check`, `button.send-btn`)
  - `dialog#chat-full.report-dialog`, `dialog#learn-dialog`
- **JS:** `chat.js`, plus `report.js` for the full report.
- **API:** `/api/ask` (stream), `/api/ask/free` (stream), `/api/library/documents` (stream), `/api/media/read`,
  `/api/learned*`, `/api/library/documents/{id}/passages`.
- **States:**
  - "Thinking…" while the local answer is written and checked; its streamed text is held back until checked
  - online: "asking provider · model", a "waiting Ns" countdown, "sources", "checking"
  - errors in the bubble

### `/models` Model performance (4 tabs)

| Tab | Container | JS | API | Content |
|---|---|---|---|---|
| Check an answer | `#panel-report > #check-tab` | `check.js`, `deck.js`, `report.js` | `/api/examples*`, `/api/analyze`, `/api/heal`, `/api/documents`, `/api/health`, `/api/model-card` | Examples deck (`#ck-deck`) beside a form: question, 1–10 sources (typed or files), answer, task `select#ck-task`, domain profile `select#ck-profile`; streamed stages; full report; JSON download; "Heal this answer" with rounds |
| Reliability | `#panel-reliability` (`#models-body`, `#media-models`, `#media-quality`) | `models.js` | `/api/model-card`, `/api/media/status` | Stat row, "candles" against baselines per locked set, tables, reliability diagram (SVG with tooltip and data table), media model status cards, media quality |
| Check an agent | `#panel-agent > #agent-tab` | `agent.js` | `/api/examples*`, `/api/agent`, `/api/model-card` | Pick a ready-made run or paste JSON steps (`textarea#agent-json`); policy strict or lenient; the "Guardian's path" replay (`.gp-*`); tracer suspicion; report |
| Fool the Guardian | `#panel-fool > #fool-tab`, `#fool-score` | `fool.js`, `deck.js`, `report.js` | `/api/fool/*`, `/api/health`, `/api/model-card` | Trick pile deck (`#fool-deck`), editable answer `textarea#fool-answer`, sources list, Apply row, outcome shield (green / amber / red), score for this visit |

### `/architecture` Architecture
- **Code map:** `section.ag-section` with three chips (`data-graph`: guardian, answers, readers) and `#arch-graphs`.
  Force-directed SVG graphs (`arch-graph.js`): zoom, pan, drag; hover names a node, click opens `dialog#code-dialog`
  with its description, inputs and outputs, and real code. A double-click shows the "graph that explains the graph".
- **Six stage cards** in `ol.arch-flow` (`.arch-step` with icon, number, title, text, model chips `.arch-chip.local`,
  `.online` or `.score`, and function buttons `.arch-fn[data-src]` that open the code dialog).
- **Data:** static (`arch-data.js`, `arch-src.js`, i18n). No API.

### `/team` Team
- `button.card.person-feature` (supervisor) and `ul.people` with 4 `button.card.person-card`. A click opens
  `dialog#person-dialog` (photo or placeholder, rank, name, role, bio on a parchment texture).
- **Data:** hard-coded in `index.html` and `pages.js` `PEOPLE`. Photos exist for 2 of 5 people. No API.

### `/about` About
- Sections: the challenge, how the engine works (5 `.stage` items), the data table, the models table, the measured
  results table (`table.facts`, numbers hard-coded in HTML), and where processing happens.
- **Static content** (strings from i18n; numbers typed into HTML). No API.

### `/contact` Contact us
- `form.card.contact-form#contact-form`: name, email, subject, message; `.btn-accent#contact-send`; `#contact-status`.
- **JS:** `contact.js` → `POST /api/contact`. If the server has no SMTP account or fails, it opens `mailto:` with the
  message.

## 4. Reusable UI pieces (CSS classes; 399 top-level class selectors in total)

| Family | Classes | Notes |
|---|---|---|
| Surfaces | `.panel`, `.card`, `.section`, `.banner`, `.rp-card`, `.stat`, `.chart-box`, `.media-card` | `#panel-reliability` and `#panel-agent` restyle children into "warm panels" via ID-scoped overrides |
| Buttons | `.btn-accent` (peach primary), `.btn-primary`, `.btn-ghost`, `.btn-small`, `.chip` (`aria-pressed`), `.tab`, `.tool-btn`, `.send-btn`, `.check-btn`, `.rail-btn`, `.dialog-x`, `.file-btn`, `.arch-fn`, `.learn-btn` | Several button families with no shared base class |
| Status | `.lamp`, `.status-chip`, `.pill.<status>`, `.pill.lane-<lane>`, `.stance.<supports\|contradicts\|unrelated\|…>`, `.grade.g<A–F>`, `.legend-*` | |
| Report | `.rp-grid`, `.rp-main`, `.rp-side`, `.rp-claim`, `.rp-verdict`, `.gauge*`, `.claim-mark`, `.share`, `.bar`, `.rp-well`, `.rp-warn`, `.stage-row`, `.stage-chip` | Built by `report.js` |
| Forms | `.field`, `.field-row`, `.form-foot`, `.form-status`, `.composer*`, `.ck-form*`, `.file-chip` | |
| Data viz | `.candles`/`.candle*` (bar "candles"), `.calib-*` (reliability diagram, SVG), `.meter*`, `table.facts`, `.table-wrap` | Hand-made SVG and CSS, no chart library |
| Decks | `.ex-*` (example ring), `.tk-*` (trick pile) | `deck.js` |
| Agent path | `.gp-*` | `agent.js` |
| Dialogs | `dialog.person-dialog` (+ `.report-dialog`, `.learn-dialog`, `.code-dialog`), `.log-dialog` | Native `<dialog>`, soft close |
| Tour | `.tour-*` | `ui.js` |
| Code map | `.ag-*`, `.arch-*` | `arch-graph.js` |
| Utility | `.mono`, `.sr-only`, `.rp-small`, `.section-note`, `.section-text` | |

## 5. Assets

| File | Size | Use |
|---|---|---|
| `fonts/fraunces-500.woff2` | 18 KB | The only web font (display) |
| `people/hamed-khalilavi.jpg`, `people/danial-rafiee.jpg` | 93 KB, 73 KB (900×1125 per markup) | Team photos |
| `textures/parchment.jpg` | 266 KB | Bio dialog background |
| Inline SVG | n/a | All icons and the shield |
| `deploy/portable/truth-guardian.ico` | n/a | Desktop shortcut icon (`scripts/build_icon.py`) |

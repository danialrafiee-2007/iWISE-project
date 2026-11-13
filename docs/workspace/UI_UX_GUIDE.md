# UI/UX guide: the Truth Guardian site as it is

> Describes the shipped design in `src/truth_guardian/web/static_html/` (`css/style.css` 2,284 lines,
> `css/intro.css` 267 lines, `index.html` 622 lines, 17 scripts). Verified 2026-11-13. This is a description of
> what exists, not a redesign. When the code and this file disagree, the code wins: fix this file.

## 1. Visual identity

**Origin.** The stylesheet says its colours were "measured from the reference video's dashboard (frame at 2.6 s)".
The shield logo and the name treatment come from the retired React site.

**Composition (desktop):**
- a near-white page
- one large rounded **panel** (radius 28px) whose ground runs mint → sage → peach-cream → near-white
- a deep green pill-shaped **rail** (58px wide) on the inline start
- the **main column** beside it, holding a dark green **banner** on top and frosted white **cards** below

**Mood:** calm, scientific, "emerald and peach". Depth everywhere: nothing is flat.

### Colour tokens (`:root` in `style.css`)

| Token | Value | Use |
|---|---|---|
| `--page` | `#f4f4f4` | page behind the panel |
| `--mint` / `--sage` / `--peach` / `--peach-warm` / `--cream` | `#b7d9cf` / `#cde0d9` / `#e0dcd1` / `#f1dccb` / `#eef2f1` | the panel's gradient ground |
| `--rail-top` / `--rail-bottom` | `#12342d` / `#061817` | rail |
| `--banner-from` / `--banner-to` | `#11352b` / `#06211e` | banner |
| `--accent` | `#e6986d` | peach-orange accent: primary button, "Guardian" in the title, "Truth Guardian check" when active |
| `--active` / `--active-light` | `#76baa8` / `#9fe0c9` | the lit rail bead (the current page) |
| `--ink` / `--ink-soft` | `#173f2b` / `#557063` | text on light surfaces |
| `--on-dark` / `--on-dark-soft` | `#eef7f2` / 68% | text on dark surfaces |
| `--ok` / `--wait` / `--bad` | `#39ff88` / `#f3c34f` / `#ff6b6b` | status lamps |
| `--emerald` | `11 92 60` (RGB triplet) | every shadow tint: `rgb(var(--emerald) / α)` |

**Secondary palette.** These colours are hard-coded, not tokens:
- the "warm panel" hairline `#e4ddca` (29 uses) and the warm card gradient `#e7f0e8 → #f7f3e9 → #efe6d3`
- the claim status colours, for example contradicted reds `#d23c3c`, `#8f1f1f`, `#a02424`, and greens `#17603b`, `#2f9a72`
- the online/local chips: green `rgb(47 179 106)` and blue `rgb(64 132 214)`
- the example stripes in `check.js`: 12 bright hues (`#fb7185` …)

### Depth system

- `--lift`, `--lift-high`: layered emerald drop shadows (3 layers).
- `--bevel-light`, `--bevel-dark`: an inset top highlight plus an inner bottom shade.
- Cards: a white 86→74% gradient, a 1px white border, `backdrop-filter: blur(6px)` (6 uses in the file).

### Typography

| Role | Font | Notes |
|---|---|---|
| Display: titles, section titles, numbers | `"Fraunces TG"` (self-hosted `fonts/fraunces-500.woff2`, weight 500 only, Latin) with Georgia fallback | The banner title has stacked drop shadows (a 3D effect), a moving sheen, and a breathing green glow; the *Guardian* word is italic peach |
| Body / UI | `system-ui, "Segoe UI", Tahoma, sans-serif` | From `:root` |
| RTL text (fa, ar) | `Tahoma, "Segoe UI", system-ui` | Only on `.banner-text`, `.pop-item`, `.tour-card` |
| Code / figures | `ui-monospace, Consolas` (+ `Cascadia Mono` in one place) | |

- **Observed sizes:** about 30 distinct rem values. Most text sits between 0.70 and 0.98rem; section titles are 1.35rem;
  banner titles use `clamp(1.6–2.6rem)`. **There is no defined type scale.**
- **Line-height:** 1.6 on the body; 1.65 to 1.7 in reading text.

### Shape, spacing, layout

- **Radii:** panel 28px, card 22px (tokens); pills 999px (28 uses); also 8, 10, 12, 14, 16, 18 and 24px. No scale.
- **Spacing:** the main grid gap is 14px. Section padding is `22px 26px` (`18px 16px` on phones); the banner is
  `26px 30px` (home `18px 26px`).
- **Layout:**
  - `.panel` is a 2-column grid (`auto 1fr`) whose column gap is a "channel" of 84px, where the rail's hover tags appear
  - the rail is `position: sticky`
  - the home page fills exactly one screen at ≥901×620px: the banner takes its natural height, the chat the rest, and
    only the chat log scrolls (D-203)

### Iconography

Inline SVG, 24×24 viewBox, stroke `currentColor`, stroke-width 1.8 (2 to 2.2 for small actions), round caps and joins.
The **shield** (path `M12 3l7 3v5c0 4.5-3 8.3-7 10-4-1.7-7-5.5-7-10V6l7-3z`) is the logo. It recurs in the rail, the
intro, the "Truth Guardian check" button, Fool's outcome and the agent path.

### Motion (a single standard, `style.css` §"The change between pages")

| Token | Value |
|---|---|
| `--fade-out` | 520ms |
| `--layer-in` | 700ms |
| `--stagger` | 110ms |
| `--content-delay` | 240ms |
| `--ease-soft` | `cubic-bezier(0.22, 0.61, 0.36, 1)` |

- **Page change** (`pages.js`): the current page fades out, then the next page's "layers" (each top-level box) rise in
  one after another. Each box's content fades in after the box, and the page title is "written in" by a clip-path wipe
  (mirrored on RTL pages).
- **Intro** (`intro.css` / `intro.js`):
  - the shield is drawn from 16 outline pieces, then shown solid with the name
  - the first click, scroll, touch or key flies the shield to the rail
  - the site opens as a growing circle from that point (1.1s) while the rail draws downward
- **Ambient:** the lamp pulse (2.4s), the title sheen (7s), the title glow (4.2s), card sheen bands, and the decks'
  auto-turn. There are 15 infinite animations in total.
- **Rail:** a dock-like magnification of the icons near the pointer (`--mag`) and a light that follows the pointer
  (`--ly`).
- **Dialogs, menus and the tour** use the same soft-in / page-out keyframes.
- **Reduced motion:** 5 `prefers-reduced-motion` blocks switch off the intro circle, rail grow, lamp pulse, title
  effects, page and layer transitions, dialogs, flash, menus, the tour, the deck glow and the agent path animations.
  JS reads the same media query (`pages.js`, `chat.js`, `deck.js`).

## 2. Information architecture and navigation

- **One HTML document**, six "pages" shown and hidden by `pages.js`, with history routing:
  - `/` home (chat)
  - `/models` "Model performance" (tabs: Check an answer · Reliability · Check an agent · Fool the Guardian)
  - `/architecture`
  - `/team`
  - `/about`
  - `/contact`
- Unknown paths show home.
- **A reload anywhere goes back to `/`** and replays the intro (D-205).
- **The rail, top to bottom:**
  - shield (home link)
  - Home
  - — Model performance, Architecture
  - — Team, About, Contact
  - (gap)
  - Site tour, Language menu
  - — three status lamps: local models, online models, Guardian
- **Rail tags:** each icon shows its name in a small dark tag on hover or focus (hidden on phones).
- **Current page:** marked by a lit mint "bead" plus a tab joining it to the panel; `aria-current="page"`.
- **Floating activity-log button**, bottom inline-end corner (`activity.js`, D-210): three tabs (this page, the engine
  live, the project's history) with CSV/JSON download.
- **Site tour** (`ui.js`, D-211): 26 steps across all pages. It dims the page around the explained element, auto-plays
  on a timer (8 to 14 s per step), and moves with the arrow keys; Esc closes it.

## 3. Interaction patterns

| Pattern | Where | Notes |
|---|---|---|
| Status lamps (green / amber / red + tooltip) | rail, home banner chips | polled: local every 60 s, online every 60 s, Guardian every 2 s until ready |
| NDJSON streaming with stage progress | Check an answer, Fool, Agent; the chat's online path | `ck-stages` list: ticked with seconds, the current one blinking |
| Native `<dialog>` with a soft close | full report, learned list, team bios, code window | backdrop click and Esc close; the page behind is locked |
| Tabs (`role=tablist`), arrow keys, RTL-aware | Model performance | the page height animates so the window never jumps |
| 3D card decks (`deck.js`) | examples (a ring), Fool tricks (a pile) | drag, wheel, keys, click; auto-turn paused on hover, focus, busy, or reduced motion |
| Chips with `aria-pressed` | graph tabs, agent policy | |
| Claim marks (buttons inside the answer text) | report | colour by status; a click selects the claim and shows its detail |
| Gauge (`role=meter`) with threshold marks | verdict card | |

## 4. States

- **Loading:**
  - lamps amber with "connecting…" / "loading…"
  - "Thinking…" in the chat bubble
  - the stage list during checks
  - the queued notice ("waiting for the check before…")
  - file chips show `…` then the embedding percentage
- **Errors:**
  - lamps red ("unreachable", "failed")
  - chat bubble `.msg-off` with the server's message (often English)
  - a file chip turns red `!` with a chat note
  - a red alert box in Check an answer
  - Contact shows a status line, with a `mailto:` fallback
- **Empty:**
  - the chat log is empty at start, with a lead sentence above
  - the learned list shows "Nothing kept yet."
  - the "Truth Guardian check" button stays **disabled** until a checked answer exists
- **Models not ready:** Check, Fool and Agent buttons are disabled until `/api/health` says ready. The chat does not
  block, and the server answers 503 until ready.

## 5. Multilingual and RTL

- **Seven languages:** en, ar, zh, fr, ru, es, fa.
  - Language comes from `?lang=`, then `localStorage` key `tg-lang`, then the browser language, then English.
  - Persian and Arabic set `dir="rtl"` on `<html>`.
- **Strings:** `window.TG_MESSAGES` in `js/i18n.js` (generated); `window.TG.t(key, vars)`. Elements carry
  `data-i18n`, `data-i18n-label`, `data-i18n-aria` and `data-i18n-placeholder`. Coverage: fr, ru and es have all
  1,039 keys; ar, zh and fa lack only 4 singular `.one` plural forms (they fall back to `.other`).
- **RTL handling:**
  - 13 `[dir="rtl"]` rules and 38 logical properties (`inset-inline-*`, `margin-inline`, `padding-inline`)
  - the rail moves to the right and the hover tags flip
  - the language list stays LTR on purpose
  - user text gets `dir="auto"`
  - numbers use the locale (Persian digits in fa; Latin digits in ar via `ar-u-nu-latn`)
- **Gap:** text generated by the server (claim explanations, triage reasons, diagnosis messages, warnings, source
  notes not matched by `chat.js`'s regex table) is shown in English on every page.

## 6. Responsive behaviour

- Breakpoints in use: 720, 900/901, 1000, 1100px (hover-capable checks too). **They are not unified.**
- **≤720px:**
  - the rail stays a column but narrows (50px) and loses its tags
  - the banner stacks
  - Team shows 2 columns and hides roles
  - the Contact form fields stack
  - section padding shrinks
- **≤900px:** the home banner's lamps drop under the text.
- **≤1100px / ≤720px:** the architecture grid goes 3 → 2 → 1 columns.
- **Home "fits one screen"** only applies at ≥901×620px; below that the page scrolls normally.

## 7. Accessibility, current state

- **Present:**
  - landmark `nav` and `main`, `aria-label`s on the rail buttons
  - `aria-current`, `aria-live` on the lamps, chat log and stages
  - `role=meter` on the gauge
  - tabs with roles and keyboard support
  - native dialogs
  - 17 `:focus-visible` styles
  - reduced-motion support
  - `.sr-only` exists
- **Weak or missing (verified by reading):**
  - no skip link
  - after a page change, focus is not moved to the new page heading
  - the chat bubble holds the answer only; the verdict is not announced
  - several colours on the gradient panel (`--ink-soft` `#557063` on mint/peach, 0.7–0.76rem labels) need contrast checks
  - status relies partly on colour (lamps, claim marks), with text available mostly via tooltips
  - the intro needs a key press or click to dismiss, and it replays on every reload

## 8. Content voice

- Plain, explanatory sentences, a bit long. UI labels are full phrases ("Truth Guardian check", "What it learned
  online").
- Code comments narrate the design history with decision IDs (D-xxx). Keep that habit: cite decisions in comments.
- Factual inconsistency: About → "Where the processing happens" says *"No answer or source leaves the computer"*, while
  the home lead and the chat send questions online when the documents hold no answer.

## 9. Page-by-page assessment

**Fact or opinion:** the "what it does" parts are verified in the code. Strengths and weaknesses are my assessment from
reading the code, **not** from watching the page run: the app has not been run from the working copy yet.

| Page | Strengths | Weaknesses (UX) | Possible improvements (not started) |
|---|---|---|---|
| **Intro** (overlay) | Strong brand moment; any gesture enters; reduced-motion path; the shield "lands" on the rail | Replays on **every reload** (a reload always goes to `/`); dismissing it takes a gesture; no skip on revisit | Show it once per session; let a deep link skip it |
| **Home / chat** | Clear one-task screen; the file, mic and send tools are familiar; the answer is held back until checked; online fallback with step-by-step status; "learned" transparency | **The verdict is not in the bubble**: the user must press "Truth Guardian check", which shows only the *last* answer; no stage progress for the local path ("Thinking…" only); no cancel; files enter the library with **no review step**; no notice that the question is about to go online; server notes and errors often in English | Verdict chip and risk in each bubble; a per-message report link; stage progress; a cancel button; a consent or notice before going online |
| **Model performance › Check an answer** | Full feature set (examples deck, files, sources, task, profile); streamed stages; a rich report; heal rounds with a diff; JSON download; keeps focus while redrawing | Dense: four sub-tools sit under "Model performance", which is a confusing label for an *interactive check*; the form is long; English explanations inside the report on other languages | Rename the section or IA (tools vs. results); progressive disclosure in the form |
| **› Reliability** | Live from `eval/results`; reliability diagram with tooltip, legend and data table; honest limits | Many numbers at small sizes (0.7–0.8rem); hard for non-experts | Plain-language summary first, details below |
| **› Check an agent** | Distinctive "Guardian's path" visual; strict/lenient policy; paste-your-own JSON | The JSON textarea is expert-only; replay timing is fixed | A step builder or examples first; play, pause and step controls |
| **› Fool the Guardian** | Playful, teaches the system; tricks deck; outcome shield in three colours; the sources stay in view | The score is per visit only; the deck relies on wheel and drag (keys exist) | Keep the score; clearer "what happened" copy |
| **Architecture** | Interactive code map with the real code; local/online chips; keyboard-focusable nodes | Developer-oriented; force graphs are heavy on small screens; a hidden double-click feature | A guided reading order; a mobile fallback list |
| **Team** | Warm cards; dialog bios on a parchment texture | 3 of 5 people have no photo (placeholder icon); names hard-coded in two places | Photos or initials; one data source |
| **About** | Complete content (challenge, engine, data, models, results) | Numbers typed into HTML (they can go stale); **says "No answer or source leaves the computer"**, which contradicts the online fallback | Read the numbers from the model card; correct the privacy sentence |
| **Contact** | Works without SMTP (`mailto:` fallback); rate-limit message | One generic invalid message (not per field); `novalidate` with no inline errors; the recipient address is visible in the page source | Per-field messages with `aria-describedby` |

## 10. Rules of thumb for future UI work (derived from the codebase's own conventions)

1. Use the existing tokens. Add a token before adding a new hard-coded colour or radius.
2. Keep the depth language (`--lift`, `--bevel-*`) and the motion tokens. Respect `prefers-reduced-motion` for every
   new animation.
3. Use logical properties and test in fa or ar for every change.
4. Never load anything from the internet in the front end (enforced by a test).
5. Bump `?v=` in `index.html` after editing CSS or JS.
6. Add new strings to `js/i18n.js` in all seven languages; note that the generator is missing (see PROJECT_CONTEXT).
7. Update `tests/test_html_ui.py` when you deliberately change asserted IDs, classes or files.

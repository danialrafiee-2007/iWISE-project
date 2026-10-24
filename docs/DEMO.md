# Demo script (8 to 10 minutes)

Before judging: double-click `TruthGuardian.bat` at least two minutes early, wait for
"offline · models ready" in the top bar, and switch Wi-Fi off. Every example below opens instantly from the cache.

| Time | Page | What to do | What to say |
|---|---|---|---|
| 0:00 | Landing | Scroll once through "How it works" | AI answers sound right even when they are not. Truth Guardian checks every claim against the sources, on this laptop, offline. Five stages: evidence, four signals, a calibrated fusion model, rules for what models miss, and a report. |
| 1:00 | Analyze | "A wrong year and a wrong citation" | The year is marked on the exact word, with the source sentence and the fix 2022 → 1945. The citation [2] is flagged: source 1 is the one that supports the claim. Blame goes to the language model, because the sources do answer the question. The grade, the risk and the conformal guarantee sit on the right. |
| 2:30 | Analyze | "Sources that disagree", then "The retriever fetched the wrong page" | When the sources contradict each other the answer is marked contested, not hallucinated. When the sources miss the question, the fault is retrieval, not the model. |
| 3:30 | Heal | "Heal this answer" from the first example | Round by round: the wrong year is replaced from the source, then the answer is checked again; the risk falls and every change says why. |
| 4:30 | Fool the Guardian | Hand the laptop to a judge: pick a trick, apply it, check | The signal light shows whether the edit was caught and found. The cards show how often each trick is caught on the 372 edited answers of the suite, weak ones included. |
| 6:00 | Agent guardian | "An agent that fills a gap from memory", strict | Step by step: at step 3 the agent names troops no tool returned, and the guardian stops the run before the answer reaches anyone. Switch to lenient to show the trade-off. |
| 7:30 | Model card | Scroll | The locked test, opened once at the end with the final model: AUROC 0.859 on 2,700 RAGTruth test answers against 0.687 for the best baseline on the same answers, 0.933 on HaluEval QA it never saw, guarantees that held on held-out splits, and the limits we measured: opposite words, other domains (HaluEval dialogue 0.67), natural agent runs, span F1 lower on test than on dev. |
| 8:30 | Audit (optional) | "Use the sample log", run | One click checks a whole system's log: estimated hallucination rate, lanes, blame and the riskiest answers. |

Questions likely to come up: why fusion instead of one big model (each signal sees a different error; ablations in
docs/DECISIONS.md), why the risk can be trusted as a probability (calibration error 0.03 on RAGTruth dev and 0.06 on the locked test; about
0.23 on HaluEval, whose thresholds come from RAGTruth), why the test number is trustworthy (opened once at the end with
the final model, every run logged in eval/locked_runs.log), what happens on a new domain (domain profiles), and what the team built versus AI tools (docs/AI_USAGE.md).

## Tour, presentation size and the demo video

- **Tour** (top bar, or "Take the 3-minute tour" on the first page): eleven steps through every tool on ready-made
  examples. Hand it to a judge who wants to explore alone; arrow keys move, Esc leaves.
- **Size** button (100, 125, 150%): use 125% on a projector.
- **Demo video**: open `http://127.0.0.1:8765/?tour=play` (or press Autoplay in the tour) and record the screen, for
  example with the Windows Game Bar (Win + Alt + R) or OBS. The tour advances by itself, about two minutes in all;
  record at 125% so the text is readable in the video, then add the voice-over from the table above.


# Demo script (8 to 10 minutes)

Before judging: double-click `TruthGuardian.bat` at least two minutes early, wait for the
dot in the top bar to turn green (its tooltip reads "models ready"), and switch Wi-Fi off. Every example below opens instantly from the cache.
The tools are under **AI engine** in the top bar (rest the pointer on it, then on Text), one flat list (D-144): **Check an answer**, **Check an agent**, **Fool the Guardian** and **Reliability**. The examples are the card deck on the Check an answer page, and Heal runs on that same page from a flagged report. Home goes back to the first page.

| Time | Page | What to do | What to say |
|---|---|---|---|
| 0:00 | Landing | Scroll once through the challenge inputs | AI answers sound right even when they are not. The challenge is about text, and that is what we show first: checked claim by claim against the sources, on this laptop, offline: evidence for every sentence, four signals, a calibrated fusion model, rules for what models miss, and a report. |
| 1:00 | Check an answer | Card "A wrong year and a wrong citation" | The year is marked on the exact word, with the source sentence and the fix 2022 → 1945. The citation [2] is flagged: source 1 is the one that supports the claim. Blame goes to the language model, because the sources do answer the question. The grade, the risk and the conformal guarantee sit on the right. |
| 2:30 | Check an answer | Cards "Sources that disagree", then "The retriever fetched the wrong page" | When the sources contradict each other the answer is marked contested, not hallucinated. When the sources miss the question, the fault is retrieval, not the model. |
| 3:30 | Check an answer | "Heal this answer" on the first example's report; it runs on the same page | The project's own addition, not something the challenge asks for. Round by round: the wrong year is replaced from the source, then the answer is checked again; the risk falls and every change says why. |
| 4:30 | Fool the Guardian | Hand the laptop to a judge: pick a trick, apply it, check | The signal light shows whether the edit was caught and found. The cards show how often each trick is caught on the 372 edited answers of the suite, weak ones included. |
| 6:00 | Check an agent | "An agent that fills a gap from memory", strict | Step by step: at step 3 the agent names troops no tool returned, and the guardian stops the run before the answer reaches anyone. Switch to lenient to show the trade-off. |
| 7:30 | Reliability | Scroll | The locked test, opened once at the end with the final model: AUROC 0.859 on 2,700 RAGTruth test answers against 0.687 for the best baseline and 0.827 for LettuceDetect, a published detector trained on RAGTruth itself, on the same answers; 0.933 on HaluEval QA it never saw, guarantees that held on held-out splits, and the limits we measured: opposite words, other domains (HaluEval dialogue 0.67), natural agent runs, span F1 lower on test than on dev. Then the reliability diagram (a risk of 0.8 means about 80%) and the table of the challenge's five harder cases. |
Questions likely to come up: why fusion instead of one big model (each signal sees a different error; ablations in
docs/DECISIONS.md), why the risk can be trusted as a probability (calibration error 0.03 on RAGTruth dev and 0.06 on the locked test; about
0.23 on HaluEval, whose thresholds come from RAGTruth), why the test number is trustworthy (opened once at the end with
the final model, every run logged in eval/locked_runs.log), what happens on a new domain (domain profiles), and what the team built versus AI tools (docs/AI_USAGE.md).

## Tour and the demo video

- **Tour** in the top bar (rest the pointer on it), then **Text tour**: eleven steps through every tool on ready-made
  examples. Hand it to a judge who wants to explore alone; arrow keys move, Esc leaves. The audio and image
  tours are listed as coming.
- **On a projector**: enlarge with the browser's own zoom (Ctrl and +); the app's size button was removed (D-127).
- **Demo video**: open `http://127.0.0.1:8765/?tour=play` (or press Autoplay in the tour) and record the screen, for
  example with the Windows Game Bar (Win + Alt + R) or OBS. The tour advances by itself, about two minutes in all;
  record with the browser zoomed to 125% so the text is readable in the video, then add the voice-over from the table
  above.


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
| 7:30 | Model card | Scroll | AUROC 0.844 against 0.674 for the best baseline, 0.914 on HaluEval QA it never saw, guarantees that held on held-out splits, and the limits we measured: opposite words, other domains, natural agent runs. |
| 8:30 | Audit (optional) | "Use the sample log", run | One click checks a whole system's log: estimated hallucination rate, lanes, blame and the riskiest answers. |

Questions likely to come up: why fusion instead of one big model (each signal sees a different error; ablations in
docs/DECISIONS.md), why the risk can be trusted as a probability (calibration error about 0.04 on RAGTruth dev), what happens on a new domain
(domain profiles), and what the team built versus AI tools (docs/AI_USAGE.md).

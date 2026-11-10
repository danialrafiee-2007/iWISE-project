"""A first trial of the free online answer (D-191): ten questions through the running server's /api/ask/free, each
answer kept with its claims, sources and labels in runtime/online/free_trial_<date>_<time>.jsonl, and a short table printed.

    uv run python scripts/free_trial.py [--port 8766]

The questions mix numbers and dates, less-known places, and Persian (the light check). Pollinations allows one answer
every 45 seconds, so ten take about eight minutes; the server waits by itself. Nothing is labelled by hand here: this
shows what the pipeline does on live answers, not how often it is right (that needs the team's labels, the plan's step 6).
"""

import argparse
import json
import time
import urllib.request
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUESTIONS = [
    "When was the Eiffel Tower completed and how tall is it?",
    "What is the population of Bam, Iran, and when did its major earthquake happen?",
    "Who wrote the novel The Blind Owl and in what year was it first published?",
    "How long is the Karun River and where does it flow into?",
    "When did the James Webb Space Telescope launch, and what is the diameter of its primary mirror?",
    "What is the capital of Bhutan and roughly how many people live there?",
    "Who was the first woman to win the Fields Medal, and in what year?",
    "How many moons does Mars have, and what are their names?",
    "برج میلاد در چه سالی افتتاح شد و ارتفاع آن چقدر است؟",
    "حافظ شیرازی در کدام شهر به دنیا آمد و در چه قرنی می‌زیست؟",
]


def ask(question: str, port: int) -> dict:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/ask/free", data=json.dumps({"question": question}).encode(), headers={"Content-Type": "application/json"})
    lines = urllib.request.urlopen(request, timeout=400).read().decode("utf-8").strip().splitlines()
    last = json.loads(lines[-1])
    return {"error": last.get("message")} if last.get("type") == "error" else last["answer"]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=8766)
    parser.add_argument("--gap", type=float, default=0, help="seconds to rest between questions (46 lets Pollinations answer without a wait, so each time is the pipeline's own)")
    args = parser.parse_args()
    out = ROOT / "runtime" / "online" / f"free_trial_{datetime.now():%Y%m%d_%H%M}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    print(f"{'#':>2}  {'status':9} {'verdict':12} {'risk':>5}  {'claims':>6}  sources (S supports, C contradicts, U unrelated, M could not be read, X does not exist, J unjudged)")
    with out.open("a", encoding="utf-8", newline="\n") as f:
        for n, question in enumerate(QUESTIONS, 1):
            if n > 1 and args.gap:
                time.sleep(args.gap)
            started = time.perf_counter()
            try:
                answer = ask(question, args.port)
            except Exception as e:  # a failed question is kept as such and the trial goes on
                answer = {"error": f"{type(e).__name__}: {e}"}
            f.write(json.dumps({"question": question, "seconds": round(time.perf_counter() - started, 1), "answer": answer}, ensure_ascii=False) + "\n")
            f.flush()
            if "error" in answer:
                print(f"{n:>2}  error     {answer['error'][:90]}")
                continue
            report = answer.get("report") or {}
            letters = "".join({"supports": "S", "contradicts": "C", "unrelated": "U", "missing": "M", "not_found": "X", "unjudged": "J"}[c["stance"]] for c in answer["citations"])
            doubtful = sum(1 for claim in answer.get("light", []) if claim["status"] == "doubtful")
            claims = len(report.get("claims", [])) or len(answer.get("light", []))
            print(f"{n:>2}  {answer.get('seconds', 0):5.1f}s {answer['status']:9} {report.get('verdict') or ('doubtful ' + str(doubtful) if answer.get('light') else '-'):12} {report.get('risk') or 0:5.2f}  {claims:>6}  {letters}")
    print(f"kept in {out}")


if __name__ == "__main__":
    main()

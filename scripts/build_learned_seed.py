"""The project's own examples of what the Guardian learned online (D-222): data/web/learned_seed.json.

Asks the running app questions of general knowledge that the project's documents do not hold. Each goes online
(/api/ask/free): a free model answers and the Guardian checks the answer against the sources it finds. Only the answers
the Guardian keeps (grounded, with a source that supports them and none against them) are written, exactly as they were
kept; nothing is edited by hand. The ready-made package carries the file, so a judge's copy starts with these examples.

    TruthGuardian.bat --no-browser                                 (in one window; the models must be ready)
    .venv/Scripts/python.exe scripts/build_learned_seed.py --port 8765
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "web" / "learned_seed.json"
QUESTIONS = [
    "When was the Eiffel Tower completed, and how tall is it?",
    "Who wrote the novel One Hundred Years of Solitude, and when was it first published?",
    "When did Apollo 11 land on the Moon, and who were the first two people to walk on it?",
    "Who discovered penicillin, and in what year?",
    "What is the capital of Australia?",
    "When did the Berlin Wall fall?",
    "Who painted the Mona Lisa?",
    "What is the speed of light in a vacuum?",
    "Who developed the theory of general relativity, and when was it published?",
    "When was the University of Tehran founded?",
    "What is the tallest mountain on Earth above sea level, and how high is it?",
    "Who was the first woman to win a Nobel Prize?",
]


def ask(port: int, question: str) -> dict:
    request = urllib.request.Request(f"http://127.0.0.1:{port}/api/ask/free", data=json.dumps({"question": question}).encode(),
                                     headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(request, timeout=300) as reply:
        events = [json.loads(line) for line in reply.read().decode("utf-8").splitlines() if line.strip()]
    for event in events:
        if event.get("type") == "error":
            raise RuntimeError(event.get("message", "error"))
    return next(e for e in reversed(events) if e.get("type") == "result")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    kept = []
    for question in QUESTIONS:
        try:
            result = ask(args.port, question)
        except Exception as e:  # one question that fails does not stop the others
            print(f"  failed  {question}  ({str(e)[:120]})")
            continue
        answer = result["answer"]
        verdict = (answer.get("report") or {}).get("verdict", answer.get("status"))
        if result.get("learned"):
            kept.append(result["learned"]["record"])
            print(f"  kept    {question}  ({verdict}, risk {result['learned']['record']['risk']:.2f})")
        else:
            print(f"  not     {question}  ({verdict})")
    if not kept:
        sys.exit("nothing was kept; is the app running, and is keeping switched on?")
    OUT.write_text(json.dumps(kept, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{OUT.relative_to(ROOT)}: {len(kept)} of {len(QUESTIONS)} answers kept")


if __name__ == "__main__":
    main()

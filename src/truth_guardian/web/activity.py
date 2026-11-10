"""The activity log (D-210): what the engine did, step by step, for the judges to watch, and the project's history.

Every request the site makes and every stage of a check, an answer, an online answer, an agent run or a file being
read is one row: when, what kind of work, what happened, how long it took and whether it failed. Rows are kept in
memory for the page to follow live and appended to runtime/logs/activity-<date>.jsonl (on the project's drive, never
in git), from which they can be downloaded whole as CSV or JSON.

What is never written: keys, passwords, the content of files, or a whole question (only its first words).

The project's history is read, not logged: the decisions in docs/DECISIONS.md and the commits git knows.
"""

import csv
import io
import json
import os
import re
import subprocess
import threading
import time
from collections import deque
from datetime import datetime
from pathlib import Path

KEEP = 3000
SHORT = 120
COLUMNS = ["id", "time", "category", "action", "detail", "status", "ms"]


def short(text: str | None, size: int = SHORT) -> str:
    """The first words of a text, on one line."""
    text = " ".join(str(text or "").split())
    return text if len(text) <= size else text[: size - 1].rstrip() + "…"


class ActivityLog:
    """Rows in memory (the newest KEEP) and, when given a folder, in one JSON-lines file per day."""

    def __init__(self, folder: Path | None = None):
        self.folder = folder
        self.rows: deque = deque(maxlen=KEEP)
        self.next_id = 1
        self.lock = threading.Lock()
        self.states: dict[str, str] = {}

    def record(self, category: str, action: str, detail: str = "", status: str = "ok", ms: float | None = None) -> dict:
        with self.lock:
            row = {"id": self.next_id, "time": datetime.now().astimezone().isoformat(timespec="seconds"), "category": category,
                   "action": action, "detail": short(detail, 400), "status": status, "ms": None if ms is None else round(ms)}
            self.next_id += 1
            self.rows.append(row)
            if self.folder is not None:
                try:
                    self.folder.mkdir(parents=True, exist_ok=True)
                    with (self.folder / f"activity-{row['time'][:10]}.jsonl").open("a", encoding="utf-8", newline="\n") as f:
                        f.write(json.dumps(row, ensure_ascii=False) + "\n")
                except OSError:
                    pass  # the log never stops the work it describes
        return row

    def changed(self, what: str, state: str, detail: str = "") -> None:
        """A row only when a state (the engine's, the online services') differs from the last one seen."""
        if self.states.get(what) != state:
            self.states[what] = state
            self.record("status", f"{what}: {state}", detail, "error" if state in {"failed", "error", "offline"} else "ok")

    def since(self, after: int = 0, limit: int = 500) -> list[dict]:
        with self.lock:
            return [row for row in self.rows if row["id"] > after][-limit:]

    def everything(self) -> list[dict]:
        """Every row the log holds: the day files when it writes them (earlier runs included), else memory."""
        if self.folder is None or not self.folder.exists():
            return list(self.rows)
        rows = []
        for path in sorted(self.folder.glob("activity-*.jsonl")):
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        return rows


def to_csv(rows: list[dict]) -> str:
    out = io.StringIO()
    writer = csv.DictWriter(out, COLUMNS, extrasaction="ignore", lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(rows)
    return "﻿" + out.getvalue()


def summary(result: dict) -> str:
    """One line on a finished piece of work: who answered, the verdict and risk, the sources and their labels, the image
    check and the second opinion, as far as the result holds them."""
    found = result.get("answer") or result.get("report") or result
    if not isinstance(found, dict):
        return ""
    report = found.get("report") if isinstance(found.get("report"), dict) else found
    parts = []
    if found.get("generator"):
        parts.append(f"model {found['generator']}")
    if found.get("status"):
        parts.append(f"status {found['status']}")
    if isinstance(report, dict) and report.get("verdict"):
        parts.append(f"verdict {report['verdict']}")
        if isinstance(report.get("risk"), int | float):
            parts.append(f"risk {report['risk']:.2f}")
    citations = found.get("citations") or []
    if citations:
        labels: dict[str, int] = {}
        for c in citations:
            labels[c.get("stance") or "unlabelled"] = labels.get(c.get("stance") or "unlabelled", 0) + 1
        parts.append(f"{len(citations)} sources (" + ", ".join(f"{k} {v}" for k, v in sorted(labels.items())) + ")")
    if isinstance(found.get("seen"), dict):
        parts.append(f"image check {found['seen'].get('verdict')}")
    if isinstance(found.get("second"), dict):
        parts.append(f"second opinion {found['second'].get('model')}: {found['second'].get('verdict')}")
    if found.get("seconds"):
        parts.append(f"{found['seconds']:.1f} s")
    return " · ".join(parts)


def stage_line(event: dict) -> str | None:
    """A stage event as a row's detail; None for the many progress events in between (only their last is kept)."""
    if event.get("type") != "stage":
        return None
    if "done" in event and event.get("done") != event.get("total"):
        return None
    extra = {k: v for k, v in event.items() if k not in {"type", "stage", "t"} and isinstance(v, str | int | float)}
    return " ".join([str(event.get("stage", ""))] + [f"{k}={short(str(v), 60)}" for k, v in extra.items()])


# ---- The project's history: the decisions and the commits, read when asked ----

_ROW = re.compile(r"^\| (D-\d{3}) \| (\d{4}-\d{2}-\d{2}) \| (.+?) \| (.+?) \|\s*$")


def decisions(root: Path) -> list[dict]:
    path = root / "docs" / "DECISIONS.md"
    if not path.exists():
        return []
    found = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if m := _ROW.match(line):
            found.append({"id": m[1], "date": m[2], "decision": short(m[3], 600), "why": short(m[4], 400)})
    return found


def commits(root: Path, limit: int = 400) -> list[dict]:
    """The commits of the folder's repository, newest first; none when git or the repository is missing."""
    try:
        out = subprocess.run(["git", "-C", str(root), "log", f"-n{limit}", "--date=short", "--pretty=format:%h%x09%ad%x09%s"],
                             capture_output=True, text=True, encoding="utf-8", timeout=10, check=True,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    rows = []
    for line in out.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3:
            rows.append({"hash": parts[0], "date": parts[1], "subject": parts[2]})
    return rows


def folder(root: Path) -> Path | None:
    """runtime/logs under the project; None (memory only) when TG_ACTIVITY_FILES=0, as in the tests."""
    return None if os.environ.get("TG_ACTIVITY_FILES") == "0" else root / "runtime" / "logs"


def timer() -> float:
    return time.perf_counter()

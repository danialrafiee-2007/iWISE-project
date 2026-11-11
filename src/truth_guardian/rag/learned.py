"""What the Guardian learned online (D-222): an online answer the Guardian found grounded is kept, so the same question is
answered the next time on this computer, offline.

When the documents hold no answer, a free model answers online and the Guardian checks it against sources (rag/free.py).
When that check finds the answer grounded, with at least one source supporting it and none contradicting it, the
question, the answer and the supporting sources' own words are kept in the library's own collection, "learned". The next
time the question (or one close to it) is asked, the library finds it there: the local model answers from those words,
offline, and the Guardian checks that answer again before it is shown.

Nothing is trained. The models stay exactly as measured on the locked test sets; only the library grows, and only with
answers that passed the full check. A person sees what is kept, switches the keeping off, and removes any of it, in the
chat ("What it learned online"). What a person asked stays on this computer: the ready-made package carries none of it,
only the project's own examples in data/web/learned_seed.json, each one an online answer the Guardian checked, kept as
it was and loaded when the library first opens.
"""

import hashlib
import json
import re
import time
from pathlib import Path

from truth_guardian.rag.library import LEARNED

SETTINGS = Path("data") / "web" / "library" / "learned.json"
SEED = Path("data") / "web" / "learned_seed.json"
MAX_KEPT = 100
MAX_SOURCES = 3
SOURCE_CHARS = 900
PREFIX = "Learned online - "
_SPACE = re.compile(r"\s+")
_UNSAFE = re.compile(r"[\x00-\x1f]")  # a name in the library, not a file on disk: only control characters go


def settings(root: Path) -> dict:
    """{"on": whether answers are kept, "dismissed": the project's examples a person removed, so they stay removed}."""
    try:
        values = json.loads((root / SETTINGS).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        values = {}
    return {"on": bool(values.get("on", True)), "dismissed": [str(d) for d in values.get("dismissed", [])]}


def save_settings(root: Path, values: dict) -> dict:
    path = root / SETTINGS
    path.parent.mkdir(parents=True, exist_ok=True)
    kept = {"on": bool(values.get("on", True)), "dismissed": sorted(set(values.get("dismissed", [])))}
    path.write_text(json.dumps(kept, indent=1), encoding="utf-8")
    return kept


def _excerpt(text: str, limit: int = SOURCE_CHARS) -> str:
    """The source's words, cut at a sentence end before the limit when there is one."""
    text = _SPACE.sub(" ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    end = max(cut.rfind(". "), cut.rfind("。"), cut.rfind("؟ "), cut.rfind("! "))
    return (cut[: end + 1] if end > limit // 2 else cut.rstrip()) + " …"


def record_of(answer) -> dict | None:
    """What is kept of an online answer (rag/answer.py's Answer), or None when it is not worth keeping: only an answer
    the full check found grounded, with a source that supports it and none that contradicts it."""
    report = answer.report
    if answer.status != "checked" or report is None or report.verdict != "grounded" or not answer.text.strip() or not answer.question.strip():
        return None
    stances = [c.stance for c in answer.citations]
    if "contradicts" in stances or "supports" not in stances:
        return None
    supporting = [c for c in answer.citations if c.stance == "supports"][:MAX_SOURCES]
    return {
        "question": _SPACE.sub(" ", answer.question).strip(),
        "answer": answer.text.strip(),
        "date": time.strftime("%Y-%m-%d"),
        "generator": answer.generator or "",
        "risk": round(float(report.risk), 3),
        "sources": [{"title": c.document, "url": c.place or "", "text": _excerpt(c.text)} for c in supporting],
    }


def name_of(record: dict) -> str:
    question = _UNSAFE.sub(" ", record["question"])
    question = _SPACE.sub(" ", question).strip().rstrip(".")
    return f"{PREFIX}{question[:90].rstrip()}.txt"


def text_of(record: dict) -> str:
    """The document kept in the library: the question and the answer first, so a question close to it finds them, then
    the sources' own words, so the next check reads the sources and not only the answer."""
    lines = [
        f"Question: {record['question']}",
        f"Answer: {record['answer']}",
        f"Checked by Truth Guardian on {record['date']}: grounded (risk {record['risk']:.2f}); answered online by {record['generator']}.",
        "Sources that support it:",
    ]
    for n, source in enumerate(record["sources"], 1):
        lines.append(f"[{n}] {source['title']}" + (f" ({source['url']})" if source["url"] and source["url"] != source["title"] else ""))
        lines.append(source["text"])
    return "\n".join(lines) + "\n"


def digest(record: dict) -> str:
    return hashlib.sha256(text_of(record).encode("utf-8")).hexdigest()


def keep(library, record: dict | None, root: Path):
    """Keeps an answer's record in the library, in place of an earlier one for the same question; the oldest go past
    MAX_KEPT. Returns the library's entry, or None when keeping is off or there is nothing to keep."""
    if record is None or not settings(root)["on"]:
        return None
    name = name_of(record)
    for entry in library.documents(LEARNED):
        if entry.name == name:
            library.remove(entry.id, LEARNED)
    entry = library.add(name, text_of(record).encode("utf-8"), LEARNED)
    kept = library.documents(LEARNED)
    for old in kept[: max(0, len(kept) - MAX_KEPT)]:
        library.remove(old.id, LEARNED)
    return entry


def seeds(root: Path) -> list[dict]:
    try:
        return json.loads((root / SEED).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def ensure_seed(library, root: Path) -> int:
    """Adds the project's own learned examples the library does not hold yet, except those a person removed."""
    dismissed = set(settings(root)["dismissed"])
    have = {entry.name for entry in library.documents(LEARNED)}
    added = 0
    for record in seeds(root):
        if digest(record) in dismissed or name_of(record) in have:
            continue
        library.add(name_of(record), text_of(record).encode("utf-8"), LEARNED)
        added += 1
    return added


def items(library, root: Path) -> list[dict]:
    """What is kept, newest first, with whether each is one of the project's own examples."""
    shipped = {name_of(record) for record in seeds(root)}
    out = []
    for entry in reversed(library.documents(LEARNED)):
        question = entry.name.removeprefix(PREFIX).removesuffix(".txt")
        out.append({"id": entry.id, "question": question, "added_at": entry.added_at, "language": entry.language, "seed": entry.name in shipped})
    return out


def forget(library, root: Path, document_id: int) -> bool:
    """Removes one kept answer; one of the project's examples is also noted, so it is not loaded again."""
    entry = next((e for e in library.documents(LEARNED) if e.id == document_id), None)
    if entry is None:
        return False
    record = next((r for r in seeds(root) if name_of(r) == entry.name), None)
    if record is not None:
        values = settings(root)
        save_settings(root, {**values, "dismissed": [*values["dismissed"], digest(record)]})
    return library.remove(document_id, LEARNED)

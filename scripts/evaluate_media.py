"""Stage 2 (D-139): the media chain on real media, what the readers read and how the claim check then judges answers.

Speech, FLEURS dev (read speech with human transcripts) in English, Arabic, Spanish, French, Russian and Chinese:
Whisper's word error rate (character error rate for Chinese) and how often it names the language; then the chain, through
the engine's own routing: the human transcript as a grounded answer and the same transcript with one controlled edit
(its first number plus one, else one of its words swapped for another recording's) as a hallucinated one, both checked
against what Whisper heard.

Text in images, TextVQA (English photos) and MTVQA (Arabic, French, Russian): how often Tesseract reads the human
answer (every word of it found in the reading); then the chain: the human answer as grounded and another question's
answer as hallucinated, checked against the words read. On TextVQA the image model (Qwen) also answers: its answers that
contain a human answer count as right, the others as its real errors, and the chain's AUROC between the two is the one
number here on real model errors.

Answers of known language are routed as the app routes them; one the engine will not check counts as not checked, and
AUROC is over the checked ones. Nothing is tuned on these files and every number is measured once. Each item's result is
kept in eval/predictions/media_eval_items.jsonl, so a stopped run resumes; the summary goes to eval/results/media_eval.json.
"""

import argparse
import ast
import hashlib
import io
import json
import re
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
ITEMS = ROOT / "eval" / "predictions" / "media_eval_items.jsonl"
OUT = ROOT / "eval" / "results" / "media_eval.json"
SEED = "tg-media-v1"
SPEECH_LANGUAGES = ("en", "ar", "es", "fr", "ru", "zh")
MTVQA_LANGUAGES = {"AR": "ar", "FR": "fr", "RU": "ru"}
MAX_SOURCE, MAX_SOURCES = 20_000, 10  # what /api/analyze accepts


def ranked(keys, n):
    return sorted(keys, key=lambda k: hashlib.sha256(f"{SEED}:{k}".encode()).hexdigest())[:n]


def norm_words(text: str, chars: bool = False) -> list[str]:
    text = "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in unicodedata.normalize("NFKC", text).lower())
    return [c for c in text if not c.isspace()] if chars else text.split()


def edit_distance(a: list[str], b: list[str]) -> int:
    row = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, y in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (x != y))
    return row[-1]


def edited(text: str, other: str, chinese: bool) -> str | None:
    """One controlled change: the first number plus one, else a word (Chinese: two characters) from another transcript."""
    number = re.search(r"\d+", text)
    if number:
        return text[: number.start()] + str(int(number.group()) + 1) + text[number.end() :]
    if chinese:
        mine, theirs = re.findall(r"[一-鿿]{2}", text), re.findall(r"[一-鿿]{2}", other)
        pick = next((t for t in theirs if t not in text), None)
        return text.replace(mine[len(mine) // 2], pick, 1) if mine and pick else None
    mine = sorted({w for w in re.findall(r"[^\W\d_]{4,}", text)}, key=len, reverse=True)
    theirs = [w for w in sorted(set(re.findall(r"[^\W\d_]{4,}", other)), key=len, reverse=True) if w.lower() not in text.lower()]
    return re.sub(rf"\b{re.escape(mine[0])}\b", theirs[0], text, count=1) if mine and theirs else None


class Chain:
    """The engine as the app runs it, with each answer's result kept."""

    def __init__(self):
        self._engine = None
        self.done = {}
        if ITEMS.exists():
            self.done = {r["key"]: r for r in map(json.loads, ITEMS.open(encoding="utf-8")) if r}

    @property
    def engine(self):
        """Loaded on the first answer to check, so a run that finds every answer kept only writes the summary."""
        if self._engine is None:
            from truth_guardian.web.engine import Engine

            self._engine = Engine()
            self._engine.load()
        return self._engine

    def keep(self, row: dict) -> dict:
        ITEMS.parent.mkdir(parents=True, exist_ok=True)
        with ITEMS.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
        self.done[row["key"]] = row
        return row

    def check(self, key: str, answer: str, parts: list[str], question: str | None, hint: str | None, label: int, extra: dict) -> dict:
        if key in self.done:
            return self.done[key]
        from truth_guardian.pipeline import make_sample
        from truth_guardian.web.engine import NotChecked

        row = {"key": key, "label": label, **extra}
        try:
            report = self.engine.analyze(make_sample(answer, parts, question, sample_id=key), hint=hint)
            row |= {"risk": report.risk, "verdict": report.verdict, "check": report.language.check if report.language else None}
        except NotChecked as e:
            row |= {"risk": None, "not_checked": e.reason}
        return self.keep(row)


def evidence_of(reading, raw: bytes):
    from truth_guardian.media.evidence import evidence

    return evidence(reading, raw, MAX_SOURCE, MAX_SOURCES)


def speech(chain: Chain, per_language: int) -> None:
    from truth_guardian.media.speech import transcribe

    for code in SPEECH_LANGUAGES:
        folder = RAW / "fleurs" / code
        rows = {}
        for line in (folder / "dev.tsv").open(encoding="utf-8"):
            cols = line.rstrip("\n").split("\t")
            rows.setdefault(cols[1], cols)  # one recording per file name
        names = ranked(rows, per_language)
        for i, name in enumerate(names):
            key = f"fleurs-{code}-{name}"
            raw_text, normalized = rows[name][2], rows[name][3]
            if f"{key}-heard" not in chain.done:
                path = folder / "audio" / "dev" / name
                reading = transcribe(path)
                chinese = code == "zh"
                errors = edit_distance(norm_words(normalized, chinese), norm_words(reading.text, chinese))
                found = evidence_of(reading, path.read_bytes())
                chain.keep({"key": f"{key}-heard", "kind": "speech", "language": code, "heard_language": reading.language,
                            "errors": errors, "words": len(norm_words(normalized, chinese)), "parts": found.parts, "hint": reading.language})
            heard = chain.done[f"{key}-heard"]
            other = rows[names[(i + 1) % len(names)]][2]
            extra = {"kind": "speech-check", "language": code}
            chain.check(f"{key}-grounded", raw_text, heard["parts"], None, heard["hint"], 0, extra)
            change = edited(raw_text, other, code == "zh")
            if change:
                chain.check(f"{key}-edited", change, heard["parts"], None, heard["hint"], 1, extra)
        print(f"speech {code}: {len(names)} recordings", flush=True)


def images(chain: Chain, textvqa: int, mtvqa: int, qwen: int) -> None:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.parquet as pq
    from PIL import Image

    from truth_guardian.media.ocr import read_text

    items = []
    table = pq.read_table(RAW / "textvqa" / "validation-00000-of-00003.parquet", columns=["question_id", "question", "answers", "image"]).to_pylist()
    usable = {str(r["question_id"]): r for r in table if Counter(r["answers"]).most_common(1)[0][0] not in ("unanswerable", "yes", "no")}
    for qid in ranked(usable, textvqa):
        r = usable[qid]
        items.append(("textvqa", "en", qid, r["question"], Counter(r["answers"]).most_common(1)[0][0], set(r["answers"]), r["image"]["bytes"]))
    for shard in sorted((RAW / "mtvqa").glob("test-*.parquet")):
        part = pq.read_table(shard)
        for r in part.filter(pc.is_in(part["lang"], value_set=pa.array(list(MTVQA_LANGUAGES)))).to_pylist():
            pair = ast.literal_eval(r["qa_pairs"])[0]
            items.append(("mtvqa", MTVQA_LANGUAGES[r["lang"]], r["id"], pair["question"], str(pair["answer"]), {str(pair["answer"])}, r["image"]["bytes"]))
    chosen = []
    for source, code in [("textvqa", "en"), *(("mtvqa", c) for c in MTVQA_LANGUAGES.values())]:
        mine = {i[2]: i for i in items if i[0] == source and i[1] == code}
        chosen += [mine[k] for k in ranked(mine, textvqa if source == "textvqa" else mtvqa)]
    for n, (source, code, qid, question, gold, golds, data) in enumerate(chosen):
        key = f"{source}-{code}-{qid}"
        if f"{key}-read" not in chain.done:
            image = Image.open(io.BytesIO(data))
            reading = read_text(image)
            words = set(norm_words(reading.text))
            found = evidence_of(reading, data)
            chain.keep({"key": f"{key}-read", "kind": "image", "source": source, "language": code, "read_language": reading.language,
                        "answer_read": all(w in words for w in norm_words(gold)), "parts": found.parts, "hint": reading.language})
        read = chain.done[f"{key}-read"]
        if not read["parts"]:
            continue
        others = [c for c in chosen if c[0] == source and c[1] == code and set(norm_words(c[4])) != set(norm_words(gold))]
        extra = {"kind": "image-check", "source": source, "language": code}
        chain.check(f"{key}-grounded", gold, read["parts"], question, read["hint"], 0, extra)
        if others:
            chain.check(f"{key}-swapped", others[n % len(others)][4], read["parts"], question, read["hint"], 1, extra)
    print(f"images: {len(chosen)} questions", flush=True)

    from truth_guardian.media import vision

    for source, code, qid, question, gold, golds, data in [c for c in chosen if c[0] == "textvqa"][:qwen]:
        key = f"qwen-{qid}"
        read = chain.done[f"textvqa-en-{qid}-read"]
        if f"{key}-answer" not in chain.done:
            said = vision.describe(Image.open(io.BytesIO(data)), question).text.strip()
            right = any(" ".join(norm_words(g)) in " ".join(norm_words(said)) for g in golds if norm_words(g))
            chain.keep({"key": f"{key}-answer", "kind": "qwen", "answer": said, "right": right})
        said = chain.done[f"{key}-answer"]
        if read["parts"] and said["answer"]:
            chain.check(f"{key}-check", said["answer"], read["parts"], question, read["hint"], int(not said["right"]), {"kind": "qwen-check", "language": "en"})
    vision.stop()
    print(f"qwen: {qwen} answers", flush=True)


def auroc(rows: list[dict]) -> dict:
    from sklearn.metrics import roc_auc_score

    checked = [r for r in rows if r.get("risk") is not None]
    labels = [r["label"] for r in checked]
    out = {"answers": len(rows), "checked": len(checked), "hallucinated": sum(labels)}
    if 0 < sum(labels) < len(labels):
        out["auroc"] = round(float(roc_auc_score(labels, [r["risk"] for r in checked])), 3)
        out["flagged_grounded"] = round(sum(r["verdict"] != "grounded" for r in checked if r["label"] == 0) / max(1, len(labels) - sum(labels)), 3)
        out["caught_hallucinated"] = round(sum(r["verdict"] != "grounded" for r in checked if r["label"] == 1) / max(1, sum(labels)), 3)
    out["not_checked"] = dict(Counter(r["not_checked"] for r in rows if r.get("risk") is None))
    return out


def summary(chain: Chain) -> dict:
    rows = list(chain.done.values())
    by = defaultdict(list)
    for r in rows:
        by[(r["kind"], r.get("source", ""), r.get("language", ""))].append(r)
    result = {"speech": {}, "images": {}, "qwen": {}}
    for code in SPEECH_LANGUAGES:
        heard = by[("speech", "", code)]
        if heard:
            result["speech"][code] = {
                "recordings": len(heard),
                "error_rate": round(sum(r["errors"] for r in heard) / max(1, sum(r["words"] for r in heard)), 3),
                "unit": "characters" if code == "zh" else "words",
                "language_right": round(sum((r["heard_language"] or "").split("-")[0] == code for r in heard) / len(heard), 3),
                "chain": auroc(by[("speech-check", "", code)]),
            }
    for source, code in [("textvqa", "en"), *(("mtvqa", c) for c in MTVQA_LANGUAGES.values())]:
        read = by[("image", source, code)]
        if read:
            result["images"][f"{source}_{code}"] = {
                "questions": len(read),
                "text_found": round(sum(bool(r["parts"]) for r in read) / len(read), 3),
                "answer_read": round(sum(r["answer_read"] for r in read) / len(read), 3),
                "language_right": round(sum((r["read_language"] or "").split("-")[0] == code for r in read) / len(read), 3),
                "chain": auroc(by[("image-check", source, code)]),
            }
    answers = by[("qwen", "", "")]
    if answers:
        result["qwen"] = {"answers": len(answers), "right": round(sum(r["right"] for r in answers) / len(answers), 3), "chain": auroc(by[("qwen-check", "", "en")])}
    # What media/status.py reads to mark a reader's quality as evaluated, with the headline number of each.
    result["components"] = {
        "speech": {"data": "FLEURS dev", "error_rate": {c: r["error_rate"] for c, r in result["speech"].items()}},
        "ocr": {"data": "TextVQA, MTVQA", "answer_read": {k: r["answer_read"] for k, r in result["images"].items()}},
        "vision": {"data": "TextVQA", "right": result["qwen"].get("right")},
    }
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--speech", type=int, default=100, help="recordings per language")
    parser.add_argument("--textvqa", type=int, default=150)
    parser.add_argument("--mtvqa", type=int, default=100, help="questions per language")
    parser.add_argument("--qwen", type=int, default=60, help="TextVQA questions the image model answers")
    args = parser.parse_args()
    chain = Chain()
    speech(chain, args.speech)
    images(chain, args.textvqa, args.mtvqa, args.qwen)
    result = summary(chain)
    OUT.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8", newline="\n")
    print(json.dumps(result, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""On-disk cache of per-sentence signal values; extraction can stop at any point and resume later.

One JSONL file per (signal, dataset). A sidecar .meta.json records the signal version, so a cache built
with different settings is never silently mixed with a new one.
"""

import json
import time
from collections.abc import Callable, Iterable
from pathlib import Path

from truth_guardian.schema import Sample
from truth_guardian.text import Sentence, split_sentences

SignalFn = Callable[[Sample, list[Sentence]], list[dict]]


class FeatureStore:
    def __init__(self, path: str | Path, signal: str, version: str):
        self.path = Path(path)
        self.meta_path = self.path.with_suffix(".meta.json")
        meta = {"signal": signal, "version": version}
        if self.meta_path.exists():
            existing = json.loads(self.meta_path.read_text(encoding="utf-8"))
            if existing != meta:
                raise ValueError(f"{self.path} was built with {existing}, not {meta}; delete it to rebuild")
        else:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.meta_path.write_text(json.dumps(meta), encoding="utf-8")
        self._drop_partial_line()

    def _drop_partial_line(self) -> None:
        """A run killed mid-write can leave half a line; cut it so appends stay valid JSONL."""
        if not self.path.exists():
            return
        data = self.path.read_bytes()
        if data and not data.endswith(b"\n"):
            self.path.write_bytes(data[: data.rfind(b"\n") + 1])

    def load(self) -> dict[str, list[dict]]:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as f:
            rows = (json.loads(line) for line in f if line.strip())
            return {row["id"]: row["sentences"] for row in rows}

    def append(self, sample_id: str, sentences: list[dict]) -> None:
        with self.path.open("a", encoding="utf-8", newline="\n") as f:
            f.write(json.dumps({"id": sample_id, "sentences": sentences}) + "\n")


def load_rows(signals: Iterable[str], dataset: Path, features_dir: Path) -> dict[str, dict[str, list[dict]]]:
    """Cached rows per signal for one dataset file; rows[signal][sample_id] -> per-sentence dicts."""
    from truth_guardian.signals import SIGNALS

    rows = {}
    for signal in signals:
        path = features_dir / signal / f"{dataset.stem}.jsonl"
        if not path.exists():
            raise FileNotFoundError(f"no cached {signal} features for {dataset.name}; run scripts/extract_features.py first")
        rows[signal] = FeatureStore(path, signal, SIGNALS[signal][0]).load()
    return rows


def usable(samples: Iterable[Sample], rows: dict[str, dict]) -> list[Sample]:
    """Samples that have every requested signal cached."""
    return [s for s in samples if all(s.id in r for r in rows.values())]


def extract(samples: Iterable[Sample], store: FeatureStore, signal: SignalFn, report_every: int = 50) -> int:
    """Compute the signal for samples not yet in the store; returns how many were computed."""
    done = set(store.load())
    todo = [s for s in samples if s.id not in done]
    started = time.perf_counter()
    for i, sample in enumerate(todo, 1):
        sentences = split_sentences(sample.answer)
        rows = signal(sample, sentences)
        store.append(sample.id, [{"start": s.start, "end": s.end, **row} for s, row in zip(sentences, rows)])
        if i % report_every == 0 or i == len(todo):
            rate = (time.perf_counter() - started) / i
            print(f"  {store.path.name}: {i}/{len(todo)} new ({len(done)} cached), {rate:.2f} s/sample, ~{rate * (len(todo) - i) / 60:.0f} min left", flush=True)
    return len(todo)

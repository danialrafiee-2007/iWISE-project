"""The brain behind the web app: loads the saved models once, warms them up, and runs one check at a time.

The models are not thread-safe and the laptop CPU is the bottleneck, so every check takes one lock: requests queue
instead of competing. A check whose client has gone away (its `cancelled` event is set) is dropped when its turn comes,
so quick clicks never leave a backlog. `FakeEngine`-style test doubles only need the same methods.
"""

import random
import threading
import time
from collections.abc import Callable
from pathlib import Path

from truth_guardian import adapt, conformal, fusion, triage
from truth_guardian.heal import Healing
from truth_guardian.heal import heal as heal_answer
from truth_guardian.perturb import KINDS, entity_pool, perturb
from truth_guardian.pipeline import analyze, make_sample
from truth_guardian.report import Report
from truth_guardian.schema import Sample, read_jsonl

ROOT = Path(__file__).resolve().parents[3]
WARM_UP = make_sample(
    "Anne Frank died in 1945 at Bergen-Belsen.",
    ["Anne Frank died of typhus in February 1945 at the Bergen-Belsen concentration camp."],
    "When did Anne Frank die?",
    sample_id="warm-up",
)


class Cancelled(Exception):
    """The client went away before its check started."""


def _proceed(cancelled: threading.Event | None) -> None:
    if cancelled is not None and cancelled.is_set():
        raise Cancelled


class Engine:
    def __init__(self, root: Path = ROOT):
        self.root = root
        self.state = "loading"
        self.error: str | None = None
        self.warm_seconds: float | None = None
        self._lock = threading.Lock()
        self._pool: dict[str, list[str]] | None = None

    def load(self) -> None:
        """Load every saved model and calibration, then run one check so later checks are warm."""
        try:
            started = time.perf_counter()
            self.model, self.manifest = fusion.load(self.root / "models" / "fusion")
            self.version = self.manifest["version"]
            folder = self.root / "models" / "fusion" / self.version
            self.calibration = conformal.load(folder, self.version)
            self.triage = triage.load(folder, self.version)
            self.tracer, self.tracer_manifest = fusion.load(self.root / "models" / "tracer")
            self.profiles = {
                p.name: p for p in (adapt.load(path, self.version) for path in sorted((self.root / "models" / "profiles").glob("*.json"))) if p is not None
            }
            self.state = "warming"
            self.analyze(WARM_UP)
            self.warm_seconds = time.perf_counter() - started
            self.state = "ready"
        except Exception as e:
            self.state, self.error = "failed", f"{type(e).__name__}: {e}"
            raise

    def busy(self) -> bool:
        return self._lock.locked()

    def info(self) -> dict:
        ready = self.state == "ready"
        return {
            "state": self.state,
            "error": self.error,
            "warm_seconds": self.warm_seconds,
            "model_version": self.version if ready else None,
            "tracer_version": self.tracer_manifest["version"] if ready else None,
            "profiles": sorted(self.profiles) if ready else [],
        }

    def _options(self, profile: str | None, policy: str) -> dict:
        options = {"model_version": self.version, "tracer": self.tracer, "guardian_policy": policy}
        if profile:
            if profile not in self.profiles:
                raise KeyError(f"unknown domain profile {profile!r}")
            return {**options, "profile": self.profiles[profile]}
        return {**options, "calibration": self.calibration, "triage_policy": self.triage}

    def analyze(
        self, sample: Sample, profile: str | None = None, policy: str = "strict", progress: Callable[[str], None] | None = None,
        cancelled: threading.Event | None = None,
    ) -> Report:
        with self._lock:
            _proceed(cancelled)
            return analyze(sample, self.model, progress=progress, **self._options(profile, policy))

    def heal(
        self, sample: Sample, profile: str | None = None, on_check: Callable[[int], None] | None = None, cancelled: threading.Event | None = None,
    ) -> Healing:
        """on_check(i) is called before the i-th check (0 = the original answer)."""
        checks = iter(range(1_000))

        def check(s: Sample) -> Report:
            _proceed(cancelled)
            if on_check:
                on_check(next(checks))
            return analyze(s, self.model, **options)

        with self._lock:
            _proceed(cancelled)
            options = self._options(profile, "strict")
            return heal_answer(sample, check)

    def edit(self, sample: Sample, kind: str, seed: int, pool_from: list[Sample]) -> Sample | None:
        """One Fool-the-Guardian edit of a grounded answer; entity swaps draw names from the other answers."""
        if kind not in KINDS:
            raise KeyError(f"unknown edit kind {kind!r}")
        with self._lock:
            if self._pool is None:
                self._pool = entity_pool(pool_from)
            return perturb(sample, kind, random.Random(f"{sample.id}:{kind}:{seed}"), self._pool)


def read_samples(path: Path) -> list[Sample]:
    return list(read_jsonl(path)) if path.exists() else []

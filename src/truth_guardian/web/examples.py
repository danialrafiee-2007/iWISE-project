"""Ready-made inputs for the web app, with their reports computed once and kept on disk so the demo never waits.

Two kinds: short showcase answers written for this project (each slips in one kind of error the guardian checks),
and answers drawn from development data only (RAGTruth dev, TG-Agent dev, the Fool-the-Guardian controls) with
their gold labels. The locked test set is never used here. A cached report is recomputed when the model changes.
"""

import hashlib
import json
from pathlib import Path

from pydantic import BaseModel, Field

from truth_guardian.adapt import labelled_choice
from truth_guardian.pipeline import make_sample
from truth_guardian.report import Report
from truth_guardian.schema import Sample, read_jsonl

MIN_ANSWER, MAX_ANSWER = 200, 900
DIALOGUE_PROFILE = "HaluEval dialogue"
AGENT_CATEGORIES = ("synthetic: fabricated fact", "synthetic: ignored tool error", "synthetic: answer addition")


class GoldSpan(BaseModel):
    start: int
    end: int
    type: str | None = None


class Example(BaseModel):
    id: str
    title: str
    about: str
    origin: str
    task: str
    question: str | None = None
    sources: list[str]
    answer: str
    agent_steps: list[dict] = Field(default_factory=list)
    gold: str | None = None
    gold_spans: list[GoldSpan] = Field(default_factory=list)
    profile: str | None = None

    def sample(self) -> Sample:
        sample = make_sample(self.answer, self.sources, self.question, self.agent_steps or None, sample_id=self.id)
        return sample.model_copy(update={"meta": sample.meta.model_copy(update={"task": self.task})})


SHOWCASE = [
    Example(
        id="anne-frank", title="A wrong year and a wrong citation", origin="written for this demo", task="qa",
        about="A wrong year and a citation that points to the wrong source, slipped into a short answer.",
        question="When and where did Anne Frank die, and what happened at the camp afterwards?",
        sources=[
            "Anne Frank died of typhus in February 1945 at the Bergen-Belsen concentration camp, where she had been moved from Auschwitz in late 1944.",
            "British troops liberated Bergen-Belsen on 15 April 1945. They found about 60,000 prisoners inside, many of them seriously ill, and thousands more died in the weeks after liberation.",
        ],
        answer="Anne Frank died in 2022 at Bergen-Belsen. The camp was liberated by British troops in April 1945. She had been moved there from Auschwitz in late 1944 [2].",
    ),
    Example(
        id="semi-final", title="Who beat whom", origin="written for this demo", task="qa",
        about="Every word of the answer appears in the source; only the roles are swapped.",
        question="Who won the 2014 World Cup semi-final in Belo Horizonte?",
        sources=["In the 2014 World Cup semi-final in Belo Horizonte, Germany defeated Brazil 7-1. It was the heaviest defeat in Brazil's World Cup history."],
        answer="In the 2014 World Cup semi-final in Belo Horizonte, Brazil defeated Germany 7-1.",
    ),
    Example(
        id="library", title="Sources that disagree", origin="written for this demo (fictional library)", task="qa",
        about="Two sources give different opening years; the answer silently takes one side.",
        question="When did the Marlow Public Library open?",
        sources=[
            "The Marlow Public Library opened in 1932 and holds about 40,000 books.",
            "The Marlow Public Library opened in 1934 and holds about 40,000 books.",
        ],
        answer="The Marlow Public Library opened in 1932 and holds about 40,000 books.",
    ),
    Example(
        id="sleep-trial", title="Stronger than the evidence", origin="written for this demo (fictional trial)", task="qa",
        about="The source says some participants slept better; the answer says most did.",
        question="What did the trial find about the supplement?",
        sources=["In a small 2021 trial of 40 adults, some participants reported better sleep. The supplement may reduce anxiety, the authors said. Larger studies are needed."],
        answer="Most participants reported better sleep. Larger studies are needed.",
    ),
    Example(
        id="photosynthesis", title="A faithful answer", origin="written for this demo", task="summary",
        about="Every claim restates the source; the guardian should let it through.",
        question="Summarise how photosynthesis works.",
        sources=["Photosynthesis is the process by which plants use sunlight, water and carbon dioxide to make glucose. It takes place mainly in the chloroplasts of leaf cells, and it releases oxygen as a by-product."],
        answer="Plants use sunlight, water and carbon dioxide to make glucose. This happens mainly in the chloroplasts of leaf cells, and oxygen is released as a by-product.",
    ),
    Example(
        id="egg", title="The retriever fetched the wrong page", origin="written for this demo", task="qa",
        about="The source is about egg prices, not cooking, so the fault lies before the language model.",
        question="How long should a soft-boiled egg cook?",
        sources=["Global egg prices rose sharply in 2023 after outbreaks of bird flu reduced the number of laying hens in several countries."],
        answer="A soft-boiled egg should cook for about six minutes.",
    ),
]

AGENT_SHOWCASE = [
    Example(
        id="agent-liberation", title="An agent that fills a gap from memory", origin="written for this demo", task="agent",
        about="The search returns the date but not the troops; the agent names them anyway.",
        question="Which troops liberated Bergen-Belsen, and on what date?",
        sources=[],
        agent_steps=[
            {"step": 1, "kind": "action", "content": "call search('Bergen-Belsen liberation date')", "observation": "Bergen-Belsen concentration camp was liberated on 15 April 1945. About 60,000 prisoners were found inside."},
            {"step": 2, "kind": "thought", "content": "The camp was liberated on 15 April 1945. I still need to know which troops liberated it."},
            {"step": 3, "kind": "thought", "content": "It was liberated by the American 3rd Armored Division."},
            {"step": 4, "kind": "answer", "content": "Bergen-Belsen was liberated on 15 April 1945 by the American 3rd Armored Division."},
        ],
        answer="Bergen-Belsen was liberated on 15 April 1945 by the American 3rd Armored Division.",
    ),
]


def _select(samples: list[Sample], n: int, key) -> list[Sample]:
    """A fixed, content-independent choice: the n samples whose hashed id sorts first."""
    return sorted(samples, key=lambda s: hashlib.sha256(f"tg-web-v1:{key}:{s.id}".encode()).hexdigest())[:n]


def _gold(sample: Sample) -> tuple[str, list[GoldSpan]]:
    labels = sample.labels
    return labels.response, [GoldSpan(start=s.start, end=s.end, type=s.type) for s in labels.spans]


def from_sample(sample: Sample, title: str, about: str, origin: str, profile: str | None = None) -> Example:
    gold, spans = _gold(sample) if sample.labels else (None, [])
    sources = [d.text for d in sample.documents if not d.id.startswith("step") and d.source != "question"]
    steps = [s.model_dump(exclude_none=True) for s in sample.agent_log or []]
    return Example(
        id=sample.id, title=title, about=about, origin=origin, task=sample.meta.task, question=sample.question,
        sources=sources, answer=sample.answer, agent_steps=steps, gold=gold, gold_spans=spans, profile=profile,
    )


def dev_examples(root: Path) -> list[Example]:
    path = root / "data" / "processed" / "ragtruth_dev.jsonl"
    if not path.exists():
        return []
    samples = [s for s in read_jsonl(path) if s.meta.quality == "good" and MIN_ANSWER <= len(s.answer) <= MAX_ANSWER]
    names = {"qa": "Question answering", "summary": "News summary", "data2text": "Business data to text"}
    out = []
    for task, name in names.items():
        for response in ("hallucinated", "grounded"):
            pool = [s for s in samples if s.meta.task == task and s.labels.response == response and (response == "grounded" or s.labels.spans)]
            for s in _select(pool, 1, f"{task}:{response}"):
                out.append(from_sample(s, f"{name}, {response} by the annotators", "Drawn at random from RAGTruth dev; compare the guardian with the annotators' marks.", "RAGTruth dev"))
    return out


def domain_examples(root: Path) -> list[Example]:
    """HaluEval dialogue answers checked with the shipped dialogue profile, drawn from the external dev answers the
    profile was not fitted on."""
    path = root / "data" / "processed" / "xdev_halueval_dialogue.jsonl"
    if not path.exists():
        return []
    samples = list(read_jsonl(path))
    fitted = set(labelled_choice(len(samples), "dialogue"))
    pool = [s for i, s in enumerate(samples) if i not in fitted]
    out = []
    for response in ("hallucinated", "grounded"):
        for s in _select([s for s in pool if s.labels.response == response], 1, f"dialogue:{response}"):
            out.append(from_sample(
                s, f"A chatbot reply, {response} by the annotators",
                "Drawn at random from HaluEval dialogue (external dev), a domain unlike RAGTruth, and checked with the HaluEval dialogue profile fitted on 50 other labelled replies.",
                "HaluEval dialogue dev", DIALOGUE_PROFILE,
            ))
    return out


def agent_examples(root: Path) -> list[Example]:
    path = root / "data" / "processed" / "tg_agent_dev.jsonl"
    if not path.exists():
        return list(AGENT_SHOWCASE)
    samples = list(read_jsonl(path))
    out = list(AGENT_SHOWCASE)
    titles = {
        "synthetic: fabricated fact": "A thought invents a fact",
        "synthetic: ignored tool error": "The tool fails, the agent carries on",
        "synthetic: answer addition": "The final answer adds a claim",
    }
    for category in AGENT_CATEGORIES:
        pool = [s for s in samples if s.labels.category == category]
        for s in _select(pool, 1, category):
            out.append(from_sample(s, titles[category], f"Drawn at random from TG-Agent dev; the error was planted at step {s.labels.responsible_step}.", "TG-Agent dev"))
    for s in _select([s for s in samples if s.labels.response == "grounded"], 1, "grounded"):
        out.append(from_sample(s, "A faithful agent", "Drawn at random from TG-Agent dev; no error was planted.", "TG-Agent dev"))
    return out


def fool_answers(root: Path) -> list[Sample]:
    """The unedited, grounded controls of the Fool-the-Guardian suite: starting points for the game."""
    path = root / "data" / "processed" / "perturb_dev.jsonl"
    return [s for s in read_jsonl(path) if s.id.startswith("perturb-control-")] if path.exists() else []


def brain_fingerprint() -> str:
    """Hash of the brain's source (the package without the web app and the RAG on top of it): a cached report is stale when
    it changes."""
    package = Path(__file__).resolve().parents[1]
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        if not {"web", "rag"} & set(path.relative_to(package).parts):
            digest.update(path.read_bytes())
    return digest.hexdigest()[:16]


class ExampleStore:
    """All examples by id, with each report cached under data/web/examples/ for one model version and brain source."""

    def __init__(self, root: Path):
        self.folder = root / "data" / "web" / "examples"
        self.code = brain_fingerprint()
        self.examples = {e.id: e for e in [*SHOWCASE, *dev_examples(root), *domain_examples(root)]}
        self.agents = {e.id: e for e in agent_examples(root)}

    def find(self, example_id: str) -> Example | None:
        return self.examples.get(example_id) or self.agents.get(example_id)

    def _path(self, example_id: str) -> Path:
        return self.folder / f"{hashlib.sha256(example_id.encode()).hexdigest()[:16]}.json"

    def cached(self, example_id: str, model_version: str) -> Report | None:
        """The kept report; a damaged file counts as absent, so the example is checked again and the file replaced."""
        path = self._path(example_id)
        if not path.exists():
            return None
        try:
            stored = json.loads(path.read_text(encoding="utf-8"))
            fresh = stored.get("model_version") == model_version and stored.get("code") == self.code
            return Report.model_validate(stored["report"]) if fresh else None
        except (OSError, ValueError, KeyError, AttributeError):
            return None

    def store(self, example_id: str, model_version: str, report: Report) -> None:
        """Through a temporary file, so a run stopped midway never leaves a half-written report."""
        self.folder.mkdir(parents=True, exist_ok=True)
        payload = {"model_version": model_version, "code": self.code, "report": report.model_dump(mode="json")}
        path = self._path(example_id)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload), encoding="utf-8", newline="\n")
        temporary.replace(path)

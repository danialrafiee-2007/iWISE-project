"""HTTP API and static file server for the Truth Guardian web app (FastAPI).

Long checks stream newline-delimited JSON events ({"type": "stage" | "check" | "progress" | "queued" | "result" |
"error", ...}) so the page shows live progress instead of a blank wait. Every answer goes through the same report
contract as the Python API (report.py). Inputs are capped, nothing is fetched from the internet, no path is taken
from the user, and only localhost host names are accepted (against DNS rebinding). The one exception to staying offline
is the Contact page, whose messages the server sends by SMTP when the owner has set up a mail account (contact.py). For a hosted demo,
TG_ALLOWED_HOSTS adds host names (comma-separated, "*.hf.space" style) and TG_ACCESS_CODE asks every visitor for
that code (HTTP basic authentication, any user name).
"""

import asyncio
import base64
import binascii
import json
import os
import queue
import secrets
import smtplib
import sys
import tempfile
import threading
import time
from collections.abc import Callable
from email.message import EmailMessage
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from truth_guardian import models
from truth_guardian.audit import summarize
from truth_guardian.heal import apply as apply_changes
from truth_guardian.media.evidence import evidence
from truth_guardian.pipeline import make_sample
from truth_guardian.schema import Sample
from truth_guardian.web import contact
from truth_guardian.web.engine import ROOT, Cancelled, Engine, NotChecked
from truth_guardian.web.documents import MAX_BYTES, SUPPORTED, extract, split
from truth_guardian.web.examples import Example, ExampleStore, fool_answers
from truth_guardian.web.metrics import model_card

STATIC = Path(__file__).with_name("static")
MAX_QUESTION, MAX_ANSWER, MAX_SOURCE, MAX_SOURCES = 1_000, 5_000, 20_000, 10
MAX_STEPS, MAX_STEP = 30, 5_000
MAX_AUDIT_ANSWERS, MAX_AUDIT_CHARS = 100, 2_000_000
MAX_MEDIA_BYTES = 25_000_000
MEDIA_KINDS = {
    "image": {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff", ".gif"},
    # .webm is what the browser's recorder makes; it is read for its sound only.
    "audio": {".wav", ".mp3", ".m4a", ".ogg", ".opus", ".flac", ".aac", ".wma", ".weba", ".webm"},
}
HOSTS = ["127.0.0.1", "localhost", "testserver"]
ACCESS_PROMPT = 'Basic realm="Truth Guardian", charset="UTF-8"'
Task = Literal["qa", "summary", "data2text", "other"]


def allowed_hosts() -> list[str]:
    return HOSTS + [h.strip() for h in os.environ.get("TG_ALLOWED_HOSTS", "").split(",") if h.strip()]


def has_access(authorization: str | None, code: str) -> bool:
    if not authorization or not authorization.startswith("Basic "):
        return False
    try:
        password = base64.b64decode(authorization[6:], validate=True).decode().partition(":")[2]
    except (binascii.Error, UnicodeDecodeError):
        return False
    return secrets.compare_digest(password.encode(), code.encode())


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CheckIn(_Strict):
    example_id: str | None = None
    question: str | None = Field(default=None, max_length=MAX_QUESTION)
    sources: Annotated[list[Annotated[str, Field(max_length=MAX_SOURCE)]], Field(max_length=MAX_SOURCES)] = []
    source_names: Annotated[list[Annotated[str, Field(max_length=255)] | None], Field(max_length=MAX_SOURCES)] = []
    answer: str | None = Field(default=None, max_length=MAX_ANSWER)
    task: Task = "other"
    profile: str | None = None
    language: str | None = Field(default=None, pattern=r"^[A-Za-z]{2,3}([_-][A-Za-z]{2,8})?$", description="the language a media reader found in the sources, used when the texts are too short to tell")


class StepIn(_Strict):
    step: int = Field(ge=0, le=1_000)
    kind: Literal["thought", "action", "observation", "answer"]
    content: str = Field(max_length=MAX_STEP)
    observation: str | None = Field(default=None, max_length=MAX_STEP)


class AgentIn(_Strict):
    example_id: str | None = None
    question: str | None = Field(default=None, max_length=MAX_QUESTION)
    steps: Annotated[list[StepIn], Field(max_length=MAX_STEPS)] = []
    answer: str | None = Field(default=None, max_length=MAX_ANSWER)
    policy: Literal["strict", "lenient"] = "strict"


class EditIn(_Strict):
    answer_id: str
    kind: str
    seed: int = Field(default=0, ge=0, le=1_000_000)


class FoolIn(_Strict):
    answer_id: str
    answer: str = Field(min_length=1, max_length=MAX_ANSWER)


class FileIn(_Strict):
    name: str = Field(min_length=1, max_length=255)
    data: str = Field(max_length=(MAX_BYTES // 3 + 1) * 4, description="the file's bytes, base64")


class AuditIn(_Strict):
    jsonl: str = Field(max_length=MAX_AUDIT_CHARS)
    profile: str | None = None


class MediaIn(_Strict):
    name: str = Field(min_length=1, max_length=255)
    data: str = Field(max_length=(MAX_MEDIA_BYTES // 3 + 1) * 4, description="the file's bytes, base64")
    languages: Annotated[list[Annotated[str, Field(pattern=r"^[A-Za-z]{2,3}([_-][A-Za-z]{2,8})?$")]], Field(max_length=3)] = []
    describe: bool = Field(default=False, description="also ask the image model what the image shows")
    question: str | None = Field(default=None, max_length=500, description="what the person asks about the image; implies describe")
    kind: Literal["image", "audio"] | None = Field(default=None, description="overrides the type the file name suggests")


class ContactIn(_Strict):
    name: str = Field(min_length=1, max_length=100)
    email: str = Field(min_length=3, max_length=254, pattern=r"^[^@\s<>,;]+@[^@\s<>,;]+\.[^@\s<>,;]+$")
    subject: str = Field(min_length=1, max_length=150)
    message: str = Field(min_length=1, max_length=5_000)
    lang: str = Field(default="en", max_length=10)


def _stream(work: Callable[[Callable[[dict], None], threading.Event], dict]) -> StreamingResponse:
    """Run work in a thread; it reports events through its first argument and returns the final result. The second
    argument is set when the client disconnects, so the checks it queued are dropped."""
    events: queue.Queue = queue.Queue()
    cancelled = threading.Event()

    def run() -> None:
        try:
            events.put({"type": "result", **work(events.put, cancelled)})
        except Cancelled:
            pass
        except (KeyError, ValueError) as e:
            events.put({"type": "error", "message": str(e).strip("'\"")})
        except Exception as e:
            events.put({"type": "error", "message": f"the check failed: {type(e).__name__}"})
        finally:
            events.put(None)

    threading.Thread(target=run, daemon=True).start()

    async def body():
        try:
            while (event := await asyncio.to_thread(events.get)) is not None:
                yield json.dumps(event) + "\n"
        finally:
            cancelled.set()

    return StreamingResponse(body(), media_type="application/x-ndjson")


def _changed_range(before: str, after: str) -> tuple[int, int] | None:
    """The span of `after` that differs from `before` (common prefix and suffix removed)."""
    if before == after:
        return None
    start = next((i for i, (a, b) in enumerate(zip(before, after)) if a != b), min(len(before), len(after)))
    end_before, end_after = len(before), len(after)
    while end_before > start and end_after > start and before[end_before - 1] == after[end_after - 1]:
        end_before, end_after = end_before - 1, end_after - 1
    return start, max(end_after, start + 1)


def _parse_log(text: str) -> list[Sample]:
    samples = []
    for i, line in enumerate(line for line in text.splitlines() if line.strip()):
        if len(samples) == MAX_AUDIT_ANSWERS:
            raise ValueError(f"at most {MAX_AUDIT_ANSWERS} answers per audit")
        try:
            row = json.loads(line)
            if "documents" in row:
                samples.append(Sample.model_validate(row))
            else:
                samples.append(make_sample(str(row["answer"]), [str(s) for s in row.get("sources", [])], row.get("question"), sample_id=str(row.get("id", i + 1))))
        except (json.JSONDecodeError, KeyError, TypeError, ValidationError) as e:
            raise ValueError(f"line {i + 1} is not a valid answer: {type(e).__name__}") from None
    if not samples:
        raise ValueError("the log is empty")
    return samples


def prepare(engine, store: ExampleStore, every_model: bool = False) -> None:
    """Load and warm up the models, then check every ready-made example once and keep its report on disk.

    every_model (the setup step) also runs the NLI model once: only rule-proposed sentence pairs reach it, so the
    warm-up never calls it and, with every example report already cached, setup would not download it.
    """
    engine.load()
    if every_model:
        models.nli_probabilities([("The sky is blue.", "The sky is not blue.")])
    for example in [*store.examples.values(), *store.agents.values()]:
        if store.cached(example.id, engine.version) is None:
            profile = example.profile if example.profile in getattr(engine, "profiles", {}) else None
            store.store(example.id, engine.version, engine.analyze(example.sample(), profile))


def create_app(
    engine=None, store: ExampleStore | None = None, root: Path = ROOT, load: bool = True, mailer: Callable[[contact.Settings, EmailMessage], None] = contact.send
) -> FastAPI:
    engine = engine or Engine(root)
    limit = contact.RateLimit()
    media_lock = threading.Lock()
    store = store or ExampleStore(root)
    fool = {s.id: s for s in fool_answers(root)}

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if load and engine.state != "ready":
            threading.Thread(target=prepare, args=(engine, store), daemon=True).start()
        yield
        if "truth_guardian.media.vision" in sys.modules:
            sys.modules["truth_guardian.media.vision"].stop()

    app = FastAPI(title="Truth Guardian", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=allowed_hosts())
    if code := os.environ.get("TG_ACCESS_CODE"):

        @app.middleware("http")
        async def access(request: Request, call_next):
            if request.url.path == "/api/health" or has_access(request.headers.get("authorization"), code):
                return await call_next(request)
            return Response("Truth Guardian needs the access code you were given.", status_code=401, headers={"WWW-Authenticate": ACCESS_PROMPT})

    def ready() -> None:
        if engine.state != "ready":
            raise HTTPException(503, "the models are still loading" if engine.state != "failed" else f"the models failed to load: {engine.error}")

    def example(example_id: str) -> Example:
        found = store.find(example_id)
        if found is None:
            raise HTTPException(404, f"no example {example_id!r}")
        return found

    def routed(sample: Sample, hint: str | None = None) -> None:
        """Refuses, before any stream starts, an answer no check reads, so the page can say why in its own language."""
        try:
            engine.route(sample, hint)
        except NotChecked as e:
            raise HTTPException(422, {"code": e.reason, "language": e.route.answer, "sources": e.route.sources}) from None

    def check(sample: Sample, profile: str | None = None, policy: str = "strict", example_id: str | None = None, hint: str | None = None) -> StreamingResponse:
        ready()
        routed(sample, hint)

        def work(emit, cancelled) -> dict:
            started = time.perf_counter()
            own = example_id is not None and profile == (store.find(example_id).profile if store.find(example_id) else None)
            cached = store.cached(example_id, engine.version) if own and policy == "strict" else None
            if cached is not None:
                return {"report": cached.model_dump(mode="json"), "seconds": 0.0, "cached": True}
            if engine.busy():
                emit({"type": "queued"})
            stage = lambda name: emit({"type": "stage", "stage": name, "t": round(time.perf_counter() - started, 2)})
            report = engine.analyze(sample, profile, policy, stage, cancelled, hint)
            report = engine.consult(sample, report, stage)  # the experimental online check, when set up (D-141)
            if own and policy == "strict":
                store.store(example_id, engine.version, report)
            return {"report": report.model_dump(mode="json"), "seconds": round(time.perf_counter() - started, 2), "cached": False}

        return _stream(work)

    def sample_from(body: CheckIn) -> tuple[Sample, str | None]:
        if body.example_id:
            return example(body.example_id).sample(), body.example_id
        if not body.answer or not body.answer.strip():
            raise HTTPException(422, "the answer is empty")
        if not any(s.strip() for s in body.sources) and not (body.question or "").strip():
            raise HTTPException(422, "give at least one source (or a question) to check the answer against")
        sample = make_sample(body.answer, body.sources, body.question or None, origins=body.source_names)
        return sample.model_copy(update={"meta": sample.meta.model_copy(update={"task": body.task})}), None

    @app.get("/api/health")
    def health() -> dict:
        return {**engine.info(), "examples": len(store.examples), "agent_examples": len(store.agents), "fool_answers": len(fool)}

    @app.get("/api/examples")
    def examples() -> dict:
        brief = lambda e: {k: getattr(e, k) for k in ("id", "title", "about", "origin", "task")}
        return {"answers": [brief(e) for e in store.examples.values()], "agents": [brief(e) for e in store.agents.values()]}

    @app.get("/api/examples/{example_id}")
    def get_example(example_id: str) -> dict:
        found = example(example_id)
        report = store.cached(example_id, engine.version) if engine.state == "ready" else None
        return {"example": found.model_dump(), "report": report.model_dump(mode="json") if report else None}

    @app.post("/api/analyze")
    def analyze(body: CheckIn) -> StreamingResponse:
        sample, example_id = sample_from(body)
        return check(sample, body.profile, example_id=example_id, hint=body.language)

    @app.post("/api/heal")
    def heal(body: CheckIn) -> StreamingResponse:
        sample, _ = sample_from(body)
        ready()
        routed(sample, body.language)

        def work(emit, cancelled) -> dict:
            started = time.perf_counter()
            if engine.busy():
                emit({"type": "queued"})
            healing = engine.heal(sample, body.profile, lambda i: emit({"type": "check", "round": i, "t": round(time.perf_counter() - started, 2)}), cancelled)
            answers = [sample.answer]
            for changes in healing.changes:
                answers.append(apply_changes(answers[-1], changes))
            rounds = [
                {"answer": answer, "changes": [c._asdict() for c in changes], "report": report.model_dump(mode="json")}
                for answer, changes, report in zip(answers, [[], *healing.changes], healing.reports)
            ]
            return {"original": sample.answer, "answer": healing.answer, "rounds": rounds, "seconds": round(time.perf_counter() - started, 2)}

        return _stream(work)

    @app.post("/api/agent")
    def agent(body: AgentIn) -> StreamingResponse:
        if body.example_id:
            found = example(body.example_id)
            return check(found.sample(), policy=body.policy, example_id=body.example_id)
        if not body.steps:
            raise HTTPException(422, "the trajectory has no steps")
        answer = body.answer or next((s.content for s in reversed(body.steps) if s.kind == "answer"), "")
        if not answer.strip():
            raise HTTPException(422, "the trajectory has no final answer")
        steps = [s.model_dump(exclude_none=True) for s in body.steps]
        return check(make_sample(answer, [], body.question or None, steps, sample_id="agent-input"), policy=body.policy)

    @app.get("/api/fool/answers")
    def fool_list() -> list[dict]:
        return [{"id": s.id, "question": s.question, "answer": s.answer, "sources": [d.text for d in s.documents], "task": s.meta.task} for s in fool.values()]

    @app.post("/api/fool/edit")
    def fool_edit(body: EditIn) -> dict:
        ready()
        if body.answer_id not in fool:
            raise HTTPException(404, f"no answer {body.answer_id!r}")
        try:
            edited = engine.edit(fool[body.answer_id], body.kind, body.seed, list(fool.values()))
        except KeyError as e:
            raise HTTPException(422, str(e).strip("'\"")) from None
        if edited is None:
            raise HTTPException(422, "this trick does not apply to this answer; pick another trick or another answer")
        span = edited.labels.spans[0]
        return {"answer": edited.answer, "edit": {"start": span.start, "end": span.end, "new": span.text, "original": (span.note or "").removeprefix("Original: ")}}

    @app.post("/api/fool/check")
    def fool_check(body: FoolIn) -> StreamingResponse:
        ready()
        if body.answer_id not in fool:
            raise HTTPException(404, f"no answer {body.answer_id!r}")
        original = fool[body.answer_id]
        edited = original.model_copy(update={"id": "fool-input", "answer": body.answer, "labels": None})
        changed = _changed_range(original.answer, body.answer)

        def work(emit, cancelled) -> dict:
            started = time.perf_counter()
            if engine.busy():
                emit({"type": "queued"})
            report = engine.analyze(edited, progress=lambda stage: emit({"type": "stage", "stage": stage, "t": round(time.perf_counter() - started, 2)}), cancelled=cancelled)
            hit = lambda c: changed is not None and c.start < changed[1] and changed[0] < c.end
            located = any(hit(c) and c.status != "supported" for c in report.claims)
            cautioned = any(hit(c) and c.cautions for c in report.claims)
            return {
                "report": report.model_dump(mode="json"), "edit": changed, "caught": report.risk >= report.response_threshold,
                "located": located, "cautioned": cautioned, "seconds": round(time.perf_counter() - started, 2),
            }

        return _stream(work)

    @app.get("/api/audit/sample")
    def audit_sample() -> dict:
        lines = [json.dumps({"id": e.id, "question": e.question, "sources": e.sources, "answer": e.answer}) for e in store.examples.values()]
        return {"jsonl": "\n".join(lines), "answers": len(lines)}

    @app.post("/api/audit")
    def audit(body: AuditIn) -> StreamingResponse:
        ready()
        try:
            samples = _parse_log(body.jsonl)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None

        def work(emit, cancelled) -> dict:
            started, reports = time.perf_counter(), []
            for i, s in enumerate(samples):
                emit({"type": "progress", "done": i, "total": len(samples), "t": round(time.perf_counter() - started, 2)})
                reports.append(engine.analyze(s, body.profile, cancelled=cancelled))
            summary = summarize(samples, reports)
            rows = [
                {"id": r.id, "verdict": r.verdict, "risk": r.domain.calibrated_risk if r.domain else r.risk, "grade": r.card.grade if r.card else None,
                 "lane": r.triage.lane if r.triage else None, "blame": r.diagnosis.blame if r.diagnosis else None,
                 "flagged": sum(c.status != "supported" for c in r.claims), "answer": s.answer[:200]}
                for s, r in zip(samples, reports)
            ]
            return {"summary": summary.model_dump(mode="json"), "answers": rows, "seconds": round(time.perf_counter() - started, 2)}

        return _stream(work)

    @app.get("/api/documents")
    def document_types() -> dict:
        return {"types": SUPPORTED, "max_bytes": MAX_BYTES, "max_source_chars": MAX_SOURCE, "max_sources": MAX_SOURCES}

    @app.post("/api/documents")
    def read_document(body: FileIn) -> dict:
        """Text of an uploaded document, split into parts that each fit one source."""
        try:
            raw = base64.b64decode(body.data, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "the file could not be read") from None
        try:
            found = extract(body.name, raw)
        except ValueError as e:
            raise HTTPException(422, str(e)) from None
        return {"name": body.name, "kind": found.kind, "pages": found.pages, "chars": len(found.text), "parts": split(found.text, MAX_SOURCE)}

    @app.get("/api/model-card")
    def card() -> dict:
        return {**model_card(root), "engine": engine.info()}

    @app.get("/api/media/status")
    def media_status() -> dict:
        """What each media reader can do here: files present, runtime installed, run on known samples, quality evaluated."""
        from truth_guardian.media import status

        return {"components": status.status()}

    @app.post("/api/media/read")
    def media_read(body: MediaIn) -> dict:
        """The text in an image or a recording, with where each piece came from (truth_guardian.media). One media job
        runs at a time: the readers are large and the image model alone takes about 2 GB."""
        suffix = Path(body.name).suffix.lower()
        known = suffix in set().union(*MEDIA_KINDS.values())
        kind = body.kind if body.kind and known else next((k for k, suffixes in MEDIA_KINDS.items() if suffix in suffixes), None)
        if kind is None:
            raise HTTPException(422, f"unsupported file type {suffix or '(none)'}; images and sound are read")
        question = (body.question or "").strip() or None
        describe = body.describe or question is not None
        try:
            raw = base64.b64decode(body.data, validate=True)
        except (binascii.Error, ValueError):
            raise HTTPException(422, "the file could not be read") from None
        if len(raw) > MAX_MEDIA_BYTES:
            raise HTTPException(413, f"the file is larger than {MAX_MEDIA_BYTES // 1_000_000} MB")
        try:
            from truth_guardian.media import ocr, speech, vision
        except ImportError:
            raise HTTPException(503, "the media readers are not installed on this computer") from None
        if not media_lock.acquire(timeout=1):
            raise HTTPException(429, "another media file is being read; try again in a moment")
        try:
            with tempfile.TemporaryDirectory(prefix="tg-media-") as folder:
                path = Path(folder) / f"input{suffix}"
                path.write_bytes(raw)
                if kind == "image":
                    reading = ocr.read_text(path, body.languages)
                    if describe:
                        seen = vision.describe(path, question)
                        reading.segments += seen.segments
                        reading.seconds = round(reading.seconds + seen.seconds, 2)
                        for reason in seen.reasons:
                            reading.review(reason)
                else:
                    hint = body.languages[0].replace("_", "-").split("-")[0].lower() if body.languages else None
                    reading = speech.transcribe(path, language=hint)
        except (OSError, RuntimeError, ValueError) as e:
            raise HTTPException(422, f"the file could not be read: {type(e).__name__}") from None
        finally:
            media_lock.release()
        # What the file gives a claim check as sources: the words read, one per line, with their places (D-135).
        found = evidence(reading, raw, MAX_SOURCE, MAX_SOURCES)
        return {"name": body.name, "kind": kind, "reading": reading.model_dump(mode="json"), "evidence": found.model_dump(mode="json")}

    @app.get("/api/contact")
    def contact_status() -> dict:
        return {"configured": contact.settings(root) is not None}

    @app.post("/api/contact")
    def send_message(body: ContactIn, request: Request) -> dict:
        config = contact.settings(root)
        if config is None:
            raise HTTPException(503, "sending email is not set up on this computer")
        if not contact.one_line(body.name) or not contact.one_line(body.subject) or not body.message.strip():
            raise HTTPException(422, "a name, a subject and a message are needed")
        if not limit.allow(request.client.host if request.client else "unknown"):
            raise HTTPException(429, "too many messages; try again later")
        try:
            mailer(config, contact.compose(config.user, body.name, body.email, body.subject, body.message, body.lang))
        except smtplib.SMTPAuthenticationError:
            raise HTTPException(502, "the mail server refused the account; check TG_SMTP_USER and the app password") from None
        except (OSError, smtplib.SMTPException) as e:
            raise HTTPException(502, f"the mail server could not be reached ({type(e).__name__})") from None
        return {"sent": True}

    @app.get("/{path:path}", include_in_schema=False)
    def static(path: str) -> FileResponse:
        if path.startswith("api/"):
            raise HTTPException(404, "no such endpoint")
        file = (STATIC / path).resolve()
        if path and file.is_file() and STATIC.resolve() in file.parents:
            return FileResponse(file)
        if "." in path.rsplit("/", 1)[-1]:
            raise HTTPException(404, f"no file {path!r}; reload the page if the app was rebuilt")
        index = STATIC / "index.html"
        if not index.exists():
            raise HTTPException(404, "the web app is not built; run `npm run build` in web/")
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    return app

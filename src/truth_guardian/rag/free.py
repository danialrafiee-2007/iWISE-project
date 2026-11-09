"""Answers from a free online model, checked by the local Guardian against sources it finds itself (D-191).

The owner's decision (2026-11-10): Claude has no part in the online answer; only free services. The order is the same as
before: a question is first answered from the documents (rag/answer.py), and only when they hold no answer does it go
online. Then:

    question -> a free model answers, naming the pages it says it relied on
             -> the Guardian reads those pages (Jina Reader) and finds its own on Wikipedia, in the question's language and
                in English, never from the model's choice
             -> the local engine checks every claim of the answer against all of them
             -> each source is labelled: supports, contradicts, unrelated, could not be opened (a page the model named that
                does not open may not exist), or read but not judged (the light check of a language no check reads)

The verdict is the local engine's, not another model's opinion. A grounded verdict means the answer agrees with what was
found; a source that is wrong itself is not caught, and Wikipedia does not hold everything, which the notes say.

Free services, tried in this order: Groq and OpenRouter when their keys are set (free.local.env, which git and Docker
ignore; free.example.env shows the lines; the owner fills it in, never the code), else Pollinations, which needs no key
and allows one answer every 45 seconds from one address: a wait it asks for is waited once and told. Sources: the
Wikipedia API (no key) and Jina Reader (r.jina.ai, no key). Sent: the question to the model; search words and page
addresses to Wikipedia and Jina. Nothing found on a page is acted on: page text is only read and checked.
"""

import json
import os
import re
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

from truth_guardian.language import detect
from truth_guardian.pipeline import make_sample
from truth_guardian.rag.answer import Answer, Citation, light_check
from truth_guardian.rag.generators import NotAvailable
from truth_guardian.rag.words import terms
from truth_guardian.report import Report
from truth_guardian.web.engine import NotChecked, _proceed

ROOT = Path(__file__).resolve().parents[3]
SETTINGS_FILE = "free.local.env"
KEYS = ("GROQ_API_KEY", "GROQ_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "TG_FREE_PROVIDER")
# Wikimedia asks every program to name itself and a way to reach its makers (its User-Agent policy).
AGENT = "TruthGuardian/1.0 (iWISE 2026 hallucination research; https://github.com/danialrafiee-2007/iWISE-project)"
# The free services, each OpenAI-compatible. key: the setting that holds its key (None: it needs none).
PROVIDERS = {
    "groq": {"url": "https://api.groq.com/openai/v1/chat/completions", "key": "GROQ_API_KEY", "model": "GROQ_MODEL", "default": "openai/gpt-oss-120b"},
    "openrouter": {"url": "https://openrouter.ai/api/v1/chat/completions", "key": "OPENROUTER_API_KEY", "model": "OPENROUTER_MODEL", "default": "nvidia/nemotron-3.5-lightning:free"},
    "pollinations": {"url": "https://text.pollinations.ai/openai", "key": None, "model": None, "default": "openai-fast"},
}
ORDER = ("groq", "openrouter", "pollinations")
WIKI = "https://{lang}.wikipedia.org/w/api.php"
READER = "https://r.jina.ai/"
WIKI_LANGS = {"en", "fa", "ar", "fr", "ru", "es", "zh"}
MAX_MODEL_PAGES = 3
WIKI_ARTICLES = 2
WIKI_HITS = 5  # search hits looked at; only those whose title concerns the question are read
PASSAGE_CHARS = 3_000
PARAGRAPHS = 6
LONGEST_WAIT = 60  # seconds: a longer wait asked for by a free service is not waited
TIMEOUT = 25  # the free model's answer
PAGE_TIMEOUT = 8  # one page or one Wikipedia call: a slow or dead page never holds the answer up
GENERATOR = "free-online"
SYSTEM = (
    "Answer the question in at most five whole sentences, in the language of the question, each naming what it is about. "
    "Then, on a new line, write SOURCES: followed by the full addresses (URLs) of up to three web pages that support your "
    "answer, separated by spaces, or SOURCES: none if you cannot name any."
)
_SOURCES = re.compile(r"^\s*\**\s*(SOURCES|Sources|sources)\s*\**\s*:(.*)$", re.M | re.S)
_URL = re.compile(r"https?://[^\s<>\"'\]]+")
_WAIT = re.compile(r"[Rr]etry after (\d+)\s*s")
NOTE = (
    "answered online by a free model, because the documents held no answer; the Guardian checked it here against the pages "
    "the model named and against Wikipedia articles it found itself, so a grounded verdict means the answer agrees with "
    "what was found, not that every page is right"
)
STANCES = ("supports", "contradicts", "unrelated", "missing", "unjudged")


class Busy(Exception):
    """The free service asked to wait (seconds)."""

    def __init__(self, seconds: int):
        super().__init__(f"the free service asks to wait {seconds} s")
        self.seconds = seconds


def settings(root: Path = ROOT) -> dict[str, str]:
    """The keys and model names, from the environment first, then free.local.env."""
    values: dict[str, str] = {}
    path = root / SETTINGS_FILE
    if path.is_file():
        for line in path.read_text(encoding="utf-8").splitlines():
            name, _, value = line.partition("=")
            if name.strip() in KEYS and value.strip():
                values[name.strip()] = value.strip().strip('"').strip("'")
    for name in KEYS:
        if os.environ.get(name):
            values[name] = os.environ[name]
    return values


def providers(values: dict[str, str]) -> list[tuple[str, str, str | None]]:
    """The services that may answer, in the order they are tried: the one named in TG_FREE_PROVIDER alone, else every
    one in ORDER whose key is set, ending with Pollinations, which needs none. Each: its name, its model, its key."""
    wanted = values.get("TG_FREE_PROVIDER", "").strip().lower()
    found = []
    for name in [wanted] if wanted in PROVIDERS else list(ORDER):
        spec = PROVIDERS[name]
        key = values.get(spec["key"]) if spec["key"] else None
        if spec["key"] and not key:
            continue
        found.append((name, (values.get(spec["model"]) if spec["model"] else None) or spec["default"], key))
    return found or [("pollinations", PROVIDERS["pollinations"]["default"], None)]


def provider(values: dict[str, str]) -> tuple[str, str, str | None]:
    """The service tried first."""
    return providers(values)[0]


def _request(url: str, data: dict | None = None, headers: dict | None = None, timeout: float = TIMEOUT) -> tuple[int, str]:
    body = json.dumps(data).encode() if data is not None else None
    request = urllib.request.Request(url, data=body, headers={"User-Agent": AGENT, **({"Content-Type": "application/json"} if body else {}), **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", errors="replace")
    except (urllib.error.URLError, TimeoutError, OSError) as e:  # no answer in time, or no connection: that page is skipped
        return 0, f"{type(e).__name__}: {e}"


def generate(question: str, name: str, model: str, key: str | None, fetch=_request) -> str:
    """The free model's reply as it wrote it. Busy when it asks to wait; ValueError on any other failure."""
    spec = PROVIDERS[name]
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    payload = {"model": model, "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}], "temperature": 0.7}
    status, text = fetch(spec["url"], payload, headers)
    if status in (402, 429):
        wait = _WAIT.search(text)
        raise Busy(int(wait.group(1)) + 1 if wait else 46)
    if status != 200:
        raise ValueError(f"{name} answered {status}: {text[:200]}")
    try:
        reply = json.loads(text)["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:
        raise ValueError(f"{name} sent an answer that could not be read") from e
    if not isinstance(reply, str) or not reply.strip():
        raise ValueError(f"{name} wrote no answer")
    return reply


def _balanced(url: str) -> str:
    """An address without the punctuation after it: a closing bracket stays only when the address opened one, so
    "wiki/Phobos_(moon)" keeps its bracket and "(see https://a.org/x)" loses the one that closed the aside."""
    url = url.rstrip(".,;:")
    while url.endswith(")") and url.count(")") > url.count("("):
        url = url[:-1].rstrip(".,;:")
    return url


def split_reply(reply: str) -> tuple[str, list[str]]:
    """The answer without its SOURCES line, and the addresses it named (up to MAX_MODEL_PAGES, each once)."""
    reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
    found = _SOURCES.search(reply)
    text = reply[: found.start()].strip() if found else reply
    named = _URL.findall(found.group(2)) if found else []
    named += [url for url in _URL.findall(text) if url not in named]
    text = _URL.sub("", text) if not found else text
    urls = [_balanced(url) for url in dict.fromkeys(named)][:MAX_MODEL_PAGES]
    return " ".join(text.replace("**", "").split()), urls


def clean(page: str) -> str:
    """A page as Jina Reader gives it, made into plain prose: no images, links reduced to their words, no table rows,
    footnote marks or lines made only of symbols, so the check reads what the page says and not its markup."""
    page = re.sub(r"!\[[^\]]*\]\([^)]*\)", "", page)
    page = re.sub(r"\[\[?(\d+)\]?\]\([^)]*\)", "", page)
    page = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", page)
    page = re.sub(r"\[\s*\]\([^)]*\)", "", page)  # a link with no words ("Review[](https://…)") leaves nothing
    page = re.sub(r"\[\d+\]|\[citation needed\]", "", page)
    lines = []
    for line in page.splitlines():
        stripped = line.strip()
        if stripped.startswith("|") or not re.search(r"\w{3}", stripped):
            lines.append("")
            continue
        lines.append(re.sub(r"^[#>*\-\s]+", "", stripped).replace("**", "").replace("__", ""))
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def relevant(page: str, words: set[str], limit: int = PASSAGE_CHARS) -> str:
    """The paragraphs of a page that share most words with the answer and the question, in the page's order. A paragraph
    sharing none is never kept, so a page about something else gives nothing."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", page) if len(p.strip()) > 40]
    shared = [len(words & set(terms(p))) for p in paragraphs]
    scored = [i for i in sorted(range(len(paragraphs)), key=lambda i: -shared[i]) if shared[i] > 0][:PARAGRAPHS]
    kept, size = [], 0
    for i in sorted(scored):
        if size + len(paragraphs[i]) > limit and kept:
            break
        kept.append(paragraphs[i][:limit])
        size += len(paragraphs[i])
    return "\n\n".join(kept)


_WIKI_PAGE = re.compile(r"^https?://([a-z]{2,3})(?:\.m)?\.wikipedia\.org/wiki/([^#?]+)")


# Wikipedia asks for few requests at a time: at most two go at once, one it refuses as too many (429) is asked again
# once after a short pause, and what it answered is kept for the session, so an article is never fetched twice.
WIKI_SLOTS = threading.Semaphore(2)
WIKI_PAUSE = 1.5
WIKI_KEPT = 256
_wiki_kept: dict[str, tuple[int, str]] = {}


def _wiki_get(url: str, fetch=_request, sleep=time.sleep) -> tuple[int, str]:
    if url in _wiki_kept:
        return _wiki_kept[url]
    with WIKI_SLOTS:
        status, text = fetch(url, None, None, PAGE_TIMEOUT)
        if status == 429:
            sleep(WIKI_PAUSE)
            status, text = fetch(url, None, None, PAGE_TIMEOUT)
    if status == 200:
        if len(_wiki_kept) >= WIKI_KEPT:
            _wiki_kept.pop(next(iter(_wiki_kept)))
        _wiki_kept[url] = (status, text)
    return status, text


def wiki_article(lang: str, title: str, fetch=_request) -> str | None:
    """A Wikipedia article's plain text, from the API (cleaner than the page)."""
    query = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "format": "json", "redirects": 1})
    status, text = _wiki_get(f"{WIKI.format(lang=lang)}?{query}", fetch)
    if status != 200:
        return None
    try:
        page = next(iter(json.loads(text)["query"]["pages"].values()))
    except (ValueError, KeyError, TypeError, StopIteration):
        return None
    return None if "missing" in page else page.get("extract") or None


def read_page(url: str, words: set[str], fetch=_request) -> str | None:
    """What a page the model named says about the answer; None when it does not open (it may not exist). A Wikipedia
    article is read from Wikipedia's API, any other page through Jina Reader, and cleaned of its markup."""
    wiki = _WIKI_PAGE.match(url)
    if wiki:
        article = wiki_article(wiki.group(1), urllib.parse.unquote(wiki.group(2)).replace("_", " "), fetch)
        return relevant(article, words) or None if article else None
    status, text = fetch(READER + url, None, {"Accept": "text/plain"}, PAGE_TIMEOUT)
    if status != 200 or len(text.strip()) < 200 or "Warning: Target URL returned error" in text[:600]:
        return None
    return relevant(clean(text.split("Markdown Content:", 1)[-1]), words) or None


def concerns(title: str, words: set[str]) -> bool:
    """A search hit concerns the question when every word of its title is in the question or the answer: "Fields Medal"
    or "Maryam Mirzakhani" for a question about the first woman to win the Fields Medal, never "Simone Biles"."""
    title_words = set(terms(re.sub(r"\([^)]*\)", "", title)))  # "Hafez (poet)": the words before the bracket
    return bool(title_words) and title_words <= words


def wikipedia(question: str, words: set[str], lang: str, fetch=_request) -> list[tuple[str, str, str]]:
    """Articles found for the question on Wikipedia in one language: (title, address, the paragraphs that concern it).
    It searches by the question's own words (no "when", "who" or "how"), and reads only the hits whose title concerns the
    question or the answer (concerns), at most WIKI_ARTICLES, at once."""
    query = urllib.parse.urlencode({"action": "query", "list": "search", "srsearch": " ".join(terms(question)) or question, "format": "json", "srlimit": WIKI_HITS})
    status, text = _wiki_get(f"{WIKI.format(lang=lang)}?{query}", fetch)
    if status != 200:
        return []
    try:
        titles = [hit["title"] for hit in json.loads(text)["query"]["search"]]
    except (ValueError, KeyError, TypeError):
        return []
    titles = [title for title in titles if concerns(title, words)][:WIKI_ARTICLES]
    with ThreadPoolExecutor(max_workers=max(1, len(titles))) as pool:
        articles = list(pool.map(lambda title: wiki_article(lang, title, fetch), titles))
    found = []
    for title, article in zip(titles, articles):
        passage = relevant(article, words) if article else ""
        if passage:
            found.append((title, f"https://{lang}.wikipedia.org/wiki/{urllib.parse.quote(title.replace(' ', '_'))}", passage))
    return found


def _same(evidence: str, source: str) -> bool:
    flat = lambda text: " ".join(text.split())
    return bool(evidence.strip()) and flat(evidence) in flat(source)


def stances(report: Report | None, texts: list[str]) -> list[str]:
    """Each source's label from the claims' evidence (by its source id, or else by its words found in the source):
    contradicts when a contradicted claim's evidence is in it, supports when a supported one's is, else unrelated;
    unjudged under the light check, which has no evidence."""
    labels = []
    for i, source in enumerate(texts):
        if report is None:
            labels.append("unjudged")
            continue
        here = [
            claim for claim in report.claims
            if claim.evidence and (claim.evidence.document_id == f"source{i + 1}" or (claim.evidence.document_id is None and _same(claim.evidence.text, source)))
        ]
        if any(claim.status == "contradicted" for claim in here):
            labels.append("contradicts")
        elif any(claim.status == "supported" for claim in here):
            labels.append("supports")
        else:
            labels.append("unrelated")
    return labels


def answer_free(
    question: str,
    engine,
    emit: Callable[[dict], None] | None = None,
    cancelled: threading.Event | None = None,
    root: Path = ROOT,
    fetch=_request,
    sleep=time.sleep,
) -> Answer:
    """A free model's answer, checked by the local Guardian against the pages it named and the Wikipedia articles found
    for it. `fetch` and `sleep` stand in for the network and the clock in tests. NotAvailable when no free service answers."""
    started = time.perf_counter()
    emit = emit or (lambda event: None)
    stage = lambda name, **more: emit({"type": "stage", "stage": name, "t": round(time.perf_counter() - started, 2), **more})
    done = lambda **fields: Answer(question=question, searched_for=question, seconds=round(time.perf_counter() - started, 2), **fields)
    # Each free service in turn: a busy or failing one hands the question to the next at once; only the last one is
    # waited for, when it asks for a short wait.
    chain = providers(settings(root))
    reply, failures = None, []
    for at, (name, model, key) in enumerate(chain):
        last = at == len(chain) - 1
        stage("online", provider=name, model=model)
        try:
            try:
                reply = generate(question, name, model, key, fetch)
            except Busy as busy:
                if not last:
                    raise
                if busy.seconds > LONGEST_WAIT:
                    raise NotAvailable(f"the free service {name} is busy; try again in {busy.seconds} s") from busy
                stage("waiting", seconds=busy.seconds)
                for _ in range(busy.seconds):
                    _proceed(cancelled)
                    sleep(1)
                stage("online", provider=name, model=model)
                reply = generate(question, name, model, key, fetch)
            break
        except NotAvailable:
            raise
        except Busy as busy:
            if last:
                raise NotAvailable(f"the free service {name} is still busy; try again in {busy.seconds} s") from busy
            failures.append(f"{name}: busy")
        except (OSError, ValueError) as e:
            if last:
                raise NotAvailable(f"the free service {name} did not answer: {str(e)[:200]}") from e
            failures.append(f"{name}: {str(e)[:80]}")
    generator = f"{GENERATOR}:{name}/{model}"
    _proceed(cancelled)
    text, urls = split_reply(reply)
    if not text:
        return done(status="unchecked", text="", generator=generator, notes=["the free model wrote no answer"])
    emit({"type": "text", "text": text})

    stage("sources")
    words = set(terms(f"{question} {text}"))
    code = (detect(f"{question} {text}").code or "en").split("-")[0].lower()
    langs = list(dict.fromkeys([code if code in WIKI_LANGS else "en", "en"]))
    # Every page the model named and every Wikipedia search are read at once, not one after another.
    with ThreadPoolExecutor(max_workers=len(urls) + len(langs)) as pool:
        pages = [pool.submit(read_page, url, words, fetch) for url in urls]
        searches = [pool.submit(wikipedia, question, words, lang, fetch) for lang in langs]
        read = [page.result() for page in pages]
        found = [search.result() for search in searches]
    _proceed(cancelled)
    sources: list[dict] = [{"title": url, "url": url, "text": passage or "", "opened": passage is not None, "found_by": "model"} for url, passage in zip(urls, read)]
    for lang, hits in zip(langs, found):
        for title, url, passage in hits:
            same = [s for s in sources if urllib.parse.unquote(s["url"]).replace(" ", "_") == urllib.parse.unquote(url)]
            if same:  # the model named the very article the Guardian found: one source, brought by both
                same[0]["found_by"] = "both"
                if not same[0]["opened"]:
                    same[0].update(text=passage, opened=True)
            else:
                sources.append({"title": f"Wikipedia ({lang}): {title}", "url": url, "text": passage, "opened": True, "found_by": "guardian"})

    opened = [s for s in sources if s["opened"]]
    notes = [NOTE]
    missing = [s["url"] for s in sources if not s["opened"]]
    if missing:
        notes.append(f"{len(missing)} page(s) the model named could not be opened; they may not exist: " + ", ".join(missing))
    if not urls:
        notes.append("the model named no page for its answer")
    if not opened:
        return done(status="unchecked", text=text, generator=generator, citations=_citations(sources, ["missing"] * len(sources)), notes=[*notes, "no source was found to check it against"])

    stage("check")
    sample = make_sample(text, [s["text"] for s in opened], question, sample_id="free", origins=[s["title"] for s in opened])
    report, light = None, []
    try:
        report = engine.analyze(sample, cancelled=cancelled)
        status = "checked"
    except NotChecked as refused:
        if refused.reason != "language":
            return done(status="unchecked", text=text, generator=generator, citations=_citations(sources, ["unjudged" if s["opened"] else "missing" for s in sources]), notes=[*notes, str(refused)])
        light = light_check(text, [SimpleNamespace(text=s["text"]) for s in opened])
        status = "light"
    labels = iter(stances(report, [s["text"] for s in opened]))
    found = [next(labels) if s["opened"] else "missing" for s in sources]
    return done(status=status, text=text, generator=generator, report=report, light=light, citations=_citations(sources, found), notes=notes)


def _citations(sources: list[dict], labels: list[str]) -> list[Citation]:
    return [
        Citation(n=n, document=s["title"], collection="web", page=None, text=s["text"], place=s["url"], role={"model": "cited by the model", "guardian": "found by the Guardian", "both": "cited by the model and found by the Guardian"}[s["found_by"]], stance=label, found_by=s["found_by"])
        for n, (s, label) in enumerate(zip(sources, labels), 1)
    ]

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
KEYS = ("GROQ_API_KEY", "GROQ_MODEL", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "TG_FREE_PROVIDER", "TAVILY_API_KEY")
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
# Tavily: a web search made for checking answers; without a key it runs in its free "keyless" mode (rate-limited), with
# TAVILY_API_KEY (free, 1,000 searches a month) on the account's own limit.
TAVILY = "https://api.tavily.com/search"
TAVILY_RESULTS = 4
# For a question or answer in Persian, a second web search kept to reliable Persian sites (D-196): encyclopaedias (the
# Great Islamic Encyclopaedia, the Encyclopaedia of the World of Islam, Encyclopaedia Iranica), the Persian poetry
# corpus Ganjoor, the Statistical Centre of Iran, the national news agencies IRNA and ISNA, and the journal and
# conference indexes Noormags and Civilica. Each was checked to answer for Persian questions on 2026-11-10.
FA_SITES = ("cgie.org.ir", "rch.ac.ir", "iranicaonline.org", "ganjoor.net", "amar.org.ir", "irna.ir", "isna.ir", "noormags.ir", "civilica.com")
FA_RESULTS = 5
MIN_SCORE = 0.3  # Tavily's relevance score (0 to 1) below which a hit is left out
# Specialised sources, asked only when the question is of their kind (D-197), both free without a key.
# The World Bank's figures for countries: a country named in the question and a figure it asks about.
WORLD_BANK = "https://api.worldbank.org/v2"
INDICATORS = {  # what the question asks about: its words in English and Persian, the World Bank's indicator
    "population": (("population", "people live", "inhabitants", "جمعیت"), "SP.POP.TOTL", "{:,.0f} people"),
    "GDP": (("gdp", "gross domestic product", "economy size", "تولید ناخالص"), "NY.GDP.MKTP.CD", "{:,.0f} US dollars"),
    "GDP per person": (("per capita", "سرانه"), "NY.GDP.PCAP.CD", "{:,.0f} US dollars"),
    "life expectancy at birth": (("life expectancy", "امید به زندگی"), "SP.DYN.LE00.IN", "{:.1f} years"),
    "land area": (("area", "square kilomet", "مساحت"), "AG.LND.TOTL.K2", "{:,.0f} square kilometres"),
    "unemployment rate": (("unemployment", "بیکاری"), "SL.UEM.TOTL.ZS", "{:.1f} percent"),
    "inflation rate": (("inflation", "تورم"), "FP.CPI.TOTL.ZG", "{:.1f} percent"),
    "adult literacy rate": (("literacy", "باسوادی", "سواد"), "SE.ADT.LITR.ZS", "{:.1f} percent"),
}
# Country names the World Bank writes otherwise, and Persian names, to its three-letter codes.
COUNTRY_ALIASES = {
    "iran": "IRN", "ایران": "IRN", "russia": "RUS", "روسیه": "RUS", "south korea": "KOR", "north korea": "PRK",
    "egypt": "EGY", "مصر": "EGY", "turkey": "TUR", "türkiye": "TUR", "ترکیه": "TUR", "united states": "USA", "usa": "USA",
    "america": "USA", "آمریکا": "USA", "امریکا": "USA", "united kingdom": "GBR", "britain": "GBR", "uk": "GBR",
    "انگلستان": "GBR", "بریتانیا": "GBR", "syria": "SYR", "سوریه": "SYR", "venezuela": "VEN", "yemen": "YEM", "یمن": "YEM",
    "laos": "LAO", "vietnam": "VNM", "ویتنام": "VNM", "عراق": "IRQ", "افغانستان": "AFG", "پاکستان": "PAK",
    "عربستان": "SAU", "امارات": "ARE", "قطر": "QAT", "کویت": "KWT", "عمان": "OMN", "بحرین": "BHR", "آذربایجان": "AZE",
    "ارمنستان": "ARM", "ترکمنستان": "TKM", "تاجیکستان": "TJK", "ازبکستان": "UZB", "قزاقستان": "KAZ", "چین": "CHN",
    "هند": "IND", "ژاپن": "JPN", "آلمان": "DEU", "فرانسه": "FRA", "ایتالیا": "ITA", "اسپانیا": "ESP", "کانادا": "CAN",
    "برزیل": "BRA", "استرالیا": "AUS", "بوتان": "BTN", "نپال": "NPL", "اندونزی": "IDN", "مالزی": "MYS", "لبنان": "LBN",
    "اردن": "JOR", "مکزیک": "MEX", "آرژانتین": "ARG", "نیجریه": "NGA", "سوئد": "SWE", "نروژ": "NOR", "هلند": "NLD",
}
_countries: dict[str, str] = {}
PLACE_WORDS = (" city", " town", " village", " province", " county", " state of ", " capital", "شهر", "روستا", "استان", "شهرستان", "پایتخت")
# OpenAlex: scholarly works (papers, theses, some books) for a question about research, with authors, year, venue, DOI.
OPENALEX = "https://api.openalex.org/works"
RESEARCH = ("paper", "study", "studies", "journal", "article", "published", "research", "researcher", "scientist", "theorem",
            "thesis", "doi", "مقاله", "پژوهش", "تحقیق", "مجله", "دانشمند", "پایان‌نامه", "قضیه")
SCHOLARLY_RESULTS = 3
# Wikidata: the structured facts behind Wikipedia (a population with its year, a height, a date of birth), read for
# the articles found, as plain sentences the check can compare numbers and dates with.
WIKIDATA = "https://www.wikidata.org/w/api.php"
FACTS = {
    "P1082": "population", "P2048": "height", "P2043": "length", "P2046": "area", "P2044": "elevation above sea level",
    "P2386": "diameter", "P2067": "mass", "P571": "date of founding or construction", "P1619": "date of official opening",
    "P577": "date of publication", "P569": "date of birth", "P570": "date of death", "P19": "place of birth",
    "P20": "place of death", "P36": "capital", "P17": "country", "P50": "author", "P1120": "number of deaths",
    "P166": "award received", "P585": "date",
}
UNITS = {
    "Q11573": "metres", "Q828224": "kilometres", "Q712226": "square kilometres", "Q25343": "square metres",
    "Q174728": "centimetres", "Q3710": "feet", "Q11570": "kilograms", "Q191118": "tonnes", "Q11574": "seconds",
    "Q7727": "minutes", "Q25235": "hours", "Q573": "days", "Q577": "years", "Q11229": "percent", "Q81454": "ångström",
}
MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"]
WIKI_LANGS = {"en", "fa", "ar", "fr", "ru", "es", "zh"}
CHECKED = {"en", "ar", "fr", "ru", "es", "zh"}  # the languages the full check reads (language.py); Persian gets the light one
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
STANCES = ("supports", "contradicts", "unrelated", "missing", "not_found", "unjudged")


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


def ascii_url(url: str) -> str:
    """An address as the network sends it: letters outside ASCII (a Persian article's title) percent-encoded, and a
    non-ASCII site name in its IDNA form, so such an address is read and never breaks the request."""
    parts = urllib.parse.urlsplit(url)
    try:
        host = parts.hostname.encode("idna").decode("ascii") if parts.hostname else ""
    except UnicodeError:
        host = parts.hostname or ""
    netloc = host + (f":{parts.port}" if parts.port else "")
    keep = "/:@!$&'()*+,;=%-._~"
    return urllib.parse.urlunsplit((parts.scheme, netloc, urllib.parse.quote(parts.path, safe=keep), urllib.parse.quote(parts.query, safe=keep + "?/"), urllib.parse.quote(parts.fragment, safe=keep)))


def _request(url: str, data: dict | None = None, headers: dict | None = None, timeout: float = TIMEOUT) -> tuple[int, str]:
    body = json.dumps(data).encode() if data is not None else None
    try:
        request = urllib.request.Request(ascii_url(url), data=body, headers={"User-Agent": AGENT, **({"Content-Type": "application/json"} if body else {}), **(headers or {})})
    except ValueError as e:  # an address that cannot be sent at all
        return 0, f"{type(e).__name__}: {e}"
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


_GONE = ("getaddrinfo failed", "Name or service not known", "nodename nor servname", "No address associated", "Errno 11001")


def probe(url: str, fetch=_request) -> str:
    """Whether a page that could not be read exists: asked directly, "not_found" when the site answers 404 or 410 or
    its name does not exist (the model may have made the address up), else "blocked" (it exists but keeps programs out,
    or did not answer in time)."""
    status, text = fetch(url, None, {"Accept": "text/html"}, PAGE_TIMEOUT)
    if status in (404, 410) or (status == 0 and any(sign in text for sign in _GONE)):
        return "not_found"
    return "blocked"


def read_page(url: str, words: set[str], fetch=_request) -> tuple[str, str]:
    """What a page the model named says about the answer, and its state: ("passage", "ok"), where the passage is empty
    when nothing on the page concerns the answer, or ("", "not_found") or ("", "blocked"). A Wikipedia article is read
    from Wikipedia's API, any other page through Jina Reader, cleaned of its markup."""
    wiki = _WIKI_PAGE.match(url)
    if wiki:
        lang, title = wiki.group(1), urllib.parse.unquote(wiki.group(2)).replace("_", " ")
        query = urllib.parse.urlencode({"action": "query", "prop": "extracts", "explaintext": 1, "titles": title, "format": "json", "redirects": 1})
        status, text = _wiki_get(f"{WIKI.format(lang=lang)}?{query}", fetch)
        if status != 200:
            return "", "blocked"
        try:
            page = next(iter(json.loads(text)["query"]["pages"].values()))
        except (ValueError, KeyError, TypeError, StopIteration):
            return "", "blocked"
        return ("", "not_found") if "missing" in page or "invalid" in page else (relevant(page.get("extract") or "", words), "ok")
    status, text = fetch(READER + url, None, {"Accept": "text/plain"}, PAGE_TIMEOUT)
    head = text[:600]
    if status == 200 and len(text.strip()) >= 200 and "Warning: Target URL returned error" not in head:
        return relevant(clean(text.split("Markdown Content:", 1)[-1]), words), "ok"
    if re.search(r"Target URL returned error (404|410)", head):
        return "", "not_found"
    return "", probe(url, fetch)


def concerns(title: str, words: set[str]) -> bool:
    """A search hit concerns the question when every word of its title is in the question or the answer: "Fields Medal"
    or "Maryam Mirzakhani" for a question about the first woman to win the Fields Medal, never "Simone Biles"."""
    # "Hafez (poet)": a bracket of one describing word is set aside; "Eiffel Tower (Paris, Texas)", a bracket naming
    # another place, is not, so the replica's article is not read for a question about the tower in Paris.
    title_words = set(terms(re.sub(r"\(\s*[^),\s]+\s*\)", "", title)))
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


def tavily(question: str, words: set[str], key: str | None = None, fetch=_request, sites: tuple[str, ...] = (), results: int = TAVILY_RESULTS, shared: int = 2) -> list[tuple[str, str, str]]:
    """Web pages found for the question by Tavily: (title, address, the passage it found), keeping only passages that
    share at least `shared` words with the question or the answer and that Tavily itself scores at least MIN_SCORE (its
    low-scored hits were noise: prices, unrelated news, profile pages). sites: only these sites (the Persian search)."""
    headers = {"Authorization": f"Bearer {key}"} if key else {"X-Tavily-Access-Mode": "keyless"}
    body = {"query": question[:400], "max_results": results, "search_depth": "basic", **({"include_domains": list(sites)} if sites else {})}
    status, text = fetch(TAVILY, body, headers, PAGE_TIMEOUT)
    if status != 200:
        return []
    try:
        results = json.loads(text).get("results", [])
    except ValueError:
        return []
    found = []
    for result in results:
        content = clean(str(result.get("content") or ""))
        if result.get("url") and float(result.get("score") or 0) >= MIN_SCORE and len(words & set(terms(content))) >= shared:
            found.append((str(result.get("title") or result["url"]), str(result["url"]), content[:PASSAGE_CHARS]))
    return found


def _when(value: dict) -> str | None:
    """A Wikidata time as words: "31 March 1889", "March 1889" or "1889", by its precision."""
    match = re.match(r"^([+-])(\d+)-(\d\d)-(\d\d)", value.get("time", ""))
    if not match:
        return None
    year, month, day = int(match.group(2)), int(match.group(3)), int(match.group(4))
    year_text = f"{year}" + (" BC" if match.group(1) == "-" else "")
    precision = value.get("precision", 9)
    if precision >= 11 and month and day:
        return f"{day} {MONTHS[month - 1]} {year_text}"
    if precision == 10 and month:
        return f"{MONTHS[month - 1]} {year_text}"
    if precision == 7:
        return f"the {year // 100 + 1}th century"
    return year_text


def _amount(value: dict) -> str | None:
    try:
        number = float(value["amount"])
    except (KeyError, ValueError):
        return None
    shown = f"{int(number):,}" if number.is_integer() else f"{number:,.2f}".rstrip("0").rstrip(".")
    unit = UNITS.get(str(value.get("unit", "")).rsplit("/", 1)[-1], "")
    return f"{shown} {unit}".strip()


def wikidata(articles: list[tuple[str, str]], fetch=_request) -> list[tuple[str, str, str]]:
    """The facts Wikidata holds for Wikipedia articles [(language, title)], one passage of plain sentences per article:
    (title, address, sentences). Each property's preferred statement is taken, else its latest; a population or similar
    number carries its year."""
    found, seen = [], set()
    for lang, title in articles:
        query = urllib.parse.urlencode({"action": "wbgetentities", "sites": f"{lang}wiki", "titles": title, "props": "claims|labels", "languages": f"en|{lang}", "format": "json"})
        status, text = _wiki_get(f"{WIKIDATA}?{query}", fetch)
        if status != 200:
            continue
        try:
            entity = next(iter(json.loads(text)["entities"].values()))
        except (ValueError, KeyError, StopIteration):
            continue
        if "missing" in entity or "claims" not in entity or entity.get("id") in seen:
            continue  # one entity once, though its Persian and English articles were both found
        seen.add(entity.get("id"))
        name = (entity.get("labels", {}).get("en") or entity.get("labels", {}).get(lang) or {}).get("value", title)
        facts, items = [], set()
        for prop, label in FACTS.items():
            statements = [c for c in entity["claims"].get(prop, []) if c.get("mainsnak", {}).get("snaktype") == "value"]
            if not statements:
                continue
            preferred = [c for c in statements if c.get("rank") == "preferred"]
            claim = (preferred or statements)[-1]
            data = claim["mainsnak"]["datavalue"]
            kind, value = data.get("type"), data.get("value")
            if kind == "time":
                shown = _when(value)
            elif kind == "quantity":
                shown = _amount(value)
                when = (claim.get("qualifiers", {}).get("P585") or [{}])[0].get("datavalue", {}).get("value")
                if shown and isinstance(when, dict):
                    shown = f"{shown} (in {_when(when)})"
            elif kind == "wikibase-entityid":
                shown = f"@{value.get('id')}"
                items.add(value.get("id"))
            else:
                shown = None
            if shown:
                facts.append((label, shown))
        if not facts:
            continue
        if items:  # the names of the places, people and countries the facts point to
            query = urllib.parse.urlencode({"action": "wbgetentities", "ids": "|".join(sorted(items)[:50]), "props": "labels", "languages": f"en|{lang}", "format": "json"})
            status, text = _wiki_get(f"{WIKIDATA}?{query}", fetch)
            names = {}
            if status == 200:
                try:
                    for qid, item in json.loads(text)["entities"].items():
                        names[qid] = (item.get("labels", {}).get("en") or item.get("labels", {}).get(lang) or {}).get("value", qid)
                except (ValueError, KeyError):
                    pass
            facts = [(label, names.get(shown[1:], shown[1:]) if shown.startswith("@") else shown) for label, shown in facts]
        sentences = " ".join(f"The {label} of {name} is {shown}." for label, shown in facts)
        found.append((name, f"https://www.wikidata.org/wiki/{entity.get('id', '')}", sentences))
    return found


def _country_names(fetch=_request) -> dict[str, str]:
    """The World Bank's countries by lower-cased name (and the part before a comma: "Iran, Islamic Rep." gives
    "iran"), with COUNTRY_ALIASES; asked once a session. Regions and income groups are left out."""
    if not _countries:
        status, text = fetch(f"{WORLD_BANK}/country?format=json&per_page=400", None, None, PAGE_TIMEOUT)
        if status == 200:
            try:
                for country in json.loads(text)[1]:
                    if (country.get("region") or {}).get("value") == "Aggregates":
                        continue
                    name = country["name"].lower()
                    _countries[name] = _countries.get(name) or country["id"]
                    _countries[name.split(",")[0].strip()] = country["id"]
            except (ValueError, KeyError, IndexError, TypeError):
                pass
        _countries.update({name: code for name, code in COUNTRY_ALIASES.items() if name not in _countries})
    return _countries


def world_bank(question: str, fetch=_request) -> list[tuple[str, str, str]]:
    """The World Bank's latest figure for each figure the question asks about (population, GDP, life expectancy...)
    in each country it names: (title, address, a sentence with the figure and its year). Nothing when it names no
    country or asks about no such figure."""
    lowered = f" {question.lower()} "
    asked = [(label, code, shown) for label, (cues, code, shown) in INDICATORS.items() if any(cue in lowered for cue in cues)]
    if not asked:
        return []
    # A question about a place inside a country ("the city of Bam", "Bam, Iran") must not get the whole country's figure,
    # which the check could read as contradicting the place's own.
    if any(word in lowered for word in PLACE_WORDS):
        return []
    names = _country_names(fetch)
    found_codes = list(dict.fromkeys(
        code for name, code in sorted(names.items(), key=lambda kv: -len(kv[0]))
        if re.search(rf"(?<!\w){re.escape(name)}(?!\w)", lowered) and not re.search(rf",\s*{re.escape(name)}(?!\w)", lowered)
    ))[:2]
    found = []
    for country in found_codes:
        for label, code, shown in asked[:3]:
            status, text = fetch(f"{WORLD_BANK}/country/{country}/indicator/{code}?format=json&mrnev=1", None, None, PAGE_TIMEOUT)
            if status != 200:
                continue
            try:
                row = json.loads(text)[1][0]
                value, year, name = float(row["value"]), row["date"], row["country"]["value"]
            except (ValueError, KeyError, IndexError, TypeError):
                continue
            found.append((f"{name}: {label}", f"https://data.worldbank.org/indicator/{code}?locations={row.get('country', {}).get('id', '')}",
                          f"According to the World Bank, the {label} of {name.split(',')[0]} was {shown.format(value)} in {year}."))
    return found


def scholarly(question: str, words: set[str], fetch=_request) -> list[tuple[str, str, str]]:
    """Scholarly works found by OpenAlex for a question about research: (title, address, a sentence with their
    authors, year, venue and DOI), keeping works whose title shares two words with the question or the answer."""
    if not any(cue in question.lower() for cue in RESEARCH):
        return []
    query = urllib.parse.urlencode({"search": " ".join(terms(question))[:300] or question[:300], "per_page": SCHOLARLY_RESULTS,
                                    "select": "id,title,publication_year,authorships,primary_location,doi,cited_by_count"})
    status, text = fetch(f"{OPENALEX}?{query}", None, None, PAGE_TIMEOUT)
    if status != 200:
        return []
    try:
        works = json.loads(text).get("results", [])
    except ValueError:
        return []
    found = []
    for work in works:
        title = str(work.get("title") or "")
        if not title or len(words & set(terms(title))) < 2:
            continue
        authors = [a["author"]["display_name"] for a in work.get("authorships", []) if a.get("author", {}).get("display_name")]
        venue = ((work.get("primary_location") or {}).get("source") or {}).get("display_name")
        sentence = f'The work "{title}" by {", ".join(authors[:4]) or "unknown authors"}{" et al." if len(authors) > 4 else ""} was published in {work.get("publication_year")}'
        sentence += f" in {venue}" if venue else ""
        sentence += f" (DOI {work['doi'].removeprefix('https://doi.org/')})." if work.get("doi") else "."
        found.append((title, work.get("doi") or work.get("id") or OPENALEX, sentence))
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


ALONE = 6  # at most this many sources are judged again on their own


def judge_each(text: str, question: str, texts: list[str], labels: list[str], engine, cancelled=None, report: Report | None = None) -> list[str]:
    """The check names one evidence for each claim, so a second source saying the same thing was left "unrelated".
    Each source left so (up to ALONE) is judged again on its own against the whole answer, and becomes "supports" when a
    claim is supported by it. It becomes "contradicts" only when a claim it contradicts alone is one the check against
    all the sources (report) found contradicted too: alone, a source that simply lacks the answer's number but holds
    other numbers reads as a contradiction (a trial marked five sources of a right answer so), while the World Bank's
    figure against a wrong population is a real one (D-197)."""
    wrong = {claim.text for claim in (report.claims if report else []) if claim.status == "contradicted"}
    labels = list(labels)
    for i in [i for i, label in enumerate(labels) if label == "unrelated"][:ALONE]:
        _proceed(cancelled)
        try:
            alone = engine.analyze(make_sample(text, [texts[i]], question, sample_id=f"free-source{i + 1}"), cancelled=cancelled)
        except NotChecked:
            continue
        said = stances(alone, [texts[i]])[0]
        if said == "supports":
            labels[i] = "supports"
        elif said == "contradicts" and any(claim.status == "contradicted" and claim.text in wrong and _about_same(claim) for claim in alone.claims):
            labels[i] = "contradicts"
    return labels


def _about_same(claim) -> bool:
    """A contradiction's evidence speaks of what the claim speaks of: two words other than numbers in common ("population"
    and "Iran"), so a source on Iran's life expectancy does not count against a claim on its population."""
    words = lambda text: {word for word in terms(text) if not any(ch.isdigit() for ch in word)}
    return bool(claim.evidence) and len(words(claim.text) & words(claim.evidence.text)) >= 2


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
    # Every page the model named, every Wikipedia search and the web search are read at once, not one after another;
    # then Wikidata's facts for the articles found.
    persian = "fa" in {code, (detect(question).code or "").split("-")[0].lower()}
    tavily_key = settings(root).get("TAVILY_API_KEY")
    with ThreadPoolExecutor(max_workers=len(urls) + len(langs) + 4) as pool:
        pages = [pool.submit(read_page, url, words, fetch) for url in urls]
        searches = [pool.submit(wikipedia, question, words, lang, fetch) for lang in langs]
        # For a Persian question the general search is a second voice beside the Persian sites, so it must share more.
        web = pool.submit(tavily, question, words, tavily_key, fetch, (), TAVILY_RESULTS, 3 if persian else 2)
        # A Persian question also searches the reliable Persian sites, where Persian facts are best found.
        fa_web = pool.submit(tavily, question, words, tavily_key, fetch, FA_SITES, FA_RESULTS) if persian else None
        # A country's figure from the World Bank, a research question's works from OpenAlex: only when asked of their kind.
        figures = pool.submit(world_bank, question, fetch)
        works = pool.submit(scholarly, question, words, fetch)
        read = [page.result() for page in pages]
        found = [search.result() for search in searches]
        on_web = web.result()
        on_fa_web = fa_web.result() if fa_web else []
        on_figures = figures.result()
        on_works = works.result()
    articles = [(lang, title) for lang, hits in zip(langs, found) for title, _, _ in hits]
    articles += [(m.group(1), urllib.parse.unquote(m.group(2)).replace("_", " ")) for url in urls if (m := _WIKI_PAGE.match(url))]
    facts = wikidata(list(dict.fromkeys(articles))[:4], fetch)
    _proceed(cancelled)
    sources: list[dict] = [{"title": url, "url": url, "text": passage, "opened": state == "ok", "state": state, "found_by": "model"} for url, (passage, state) in zip(urls, read)]
    for lang, hits in zip(langs, found):
        for title, url, passage in hits:
            same = [s for s in sources if urllib.parse.unquote(s["url"]).replace(" ", "_") == urllib.parse.unquote(url)]
            if same:  # the model named the very article the Guardian found: one source, brought by both
                same[0]["found_by"] = "both"
                if not same[0]["text"]:
                    same[0].update(text=passage, opened=True, state="ok")
            else:
                sources.append({"title": f"Wikipedia ({lang}): {title}", "url": url, "text": passage, "opened": True, "state": "ok", "found_by": "guardian"})
    for title, url, passage in [*[(f"(fa) {t}", u, p) for t, u, p in on_fa_web], *on_web]:
        same = [s for s in sources if s["url"].rstrip("/") == url.rstrip("/")]
        if same:
            if same[0]["found_by"] == "model":
                same[0]["found_by"] = "both"
            if not same[0]["text"]:
                same[0].update(text=passage, opened=True, state="ok")
        elif "wikipedia.org/wiki/" not in url:  # Wikipedia is read whole above; a search snippet of it adds nothing
            sources.append({"title": f"Web: {title}", "url": url, "text": passage, "opened": True, "state": "ok", "found_by": "guardian"})
    for name, url, sentences in facts:
        sources.append({"title": f"Wikidata: {name}", "url": url, "text": sentences, "opened": True, "state": "ok", "found_by": "guardian"})
    for name, url, sentence in on_figures:
        sources.append({"title": f"World Bank: {name}", "url": url, "text": sentence, "opened": True, "state": "ok", "found_by": "guardian"})
    for name, url, sentence in on_works:
        sources.append({"title": f"OpenAlex: {name}", "url": url, "text": sentence, "opened": True, "state": "ok", "found_by": "guardian"})

    # What each source is before any check: a page that does not exist, one that could not be read, one with nothing on
    # the answer, or one to check against.
    first = {"not_found": "not_found", "blocked": "missing"}
    opened = [s for s in sources if s["state"] == "ok" and s["text"].strip()]
    # A source in a language the full check does not read (a Persian page beside an English answer) would turn the whole
    # check into the light one; it is listed and left out of the check, read but not judged.
    said = (detect(text).code or "").split("-")[0].lower()
    if said in CHECKED:
        apart = [s for s in opened if (detect(s["text"]).code or said).split("-")[0].lower() not in CHECKED]
        opened = [s for s in opened if s not in apart]
        for s in apart:
            s["state"] = "apart"
        first["apart"] = "unjudged"
    notes = [NOTE]
    gone = [s["url"] for s in sources if s["state"] == "not_found"]
    shut = [s["url"] for s in sources if s["state"] == "blocked"]
    if gone:
        notes.append(f"{len(gone)} page(s) the model named do not exist (the address answers not found): " + ", ".join(gone))
    if shut:
        notes.append(f"{len(shut)} page(s) the model named could not be read; the site may keep programs out: " + ", ".join(shut))
    if not urls:
        notes.append("the model named no page for its answer")
    before = lambda s, judged: first.get(s["state"]) or ("unrelated" if not s["text"].strip() else judged)
    if not opened:
        return done(status="unchecked", text=text, generator=generator, citations=_citations(sources, [before(s, "unrelated") for s in sources]), notes=[*notes, "no source was found to check it against"])

    stage("check")
    sample = make_sample(text, [s["text"] for s in opened], question, sample_id="free", origins=[s["title"] for s in opened])
    report, light = None, []
    try:
        report = engine.analyze(sample, cancelled=cancelled)
        status = "checked"
    except NotChecked as refused:
        if refused.reason != "language":
            return done(status="unchecked", text=text, generator=generator, citations=_citations(sources, [before(s, "unjudged") for s in sources]), notes=[*notes, str(refused)])
        light = light_check(text, [SimpleNamespace(text=s["text"]) for s in opened])
        status = "light"
    texts = [s["text"] for s in opened]
    judged = stances(report, texts)
    if report is not None:
        judged = judge_each(text, question, texts, judged, engine, cancelled, report)
    labels = iter(judged)
    found = [next(labels) if s in opened else before(s, "unrelated") for s in sources]
    return done(status=status, text=text, generator=generator, report=report, light=light, citations=_citations(sources, found), notes=notes)


def _citations(sources: list[dict], labels: list[str]) -> list[Citation]:
    return [
        Citation(n=n, document=s["title"], collection="web", page=None, text=s["text"], place=s["url"], role={"model": "cited by the model", "guardian": "found by the Guardian", "both": "cited by the model and found by the Guardian"}[s["found_by"]], stance=label, found_by=s["found_by"])
        for n, (s, label) in enumerate(zip(sources, labels), 1)
    ]


# ---- Whether the free online services can be reached now (D-202), for the second lamp on the home page ----
# Each is asked something that costs nothing: a model list, a key's own page, a site's info. Tavily is not asked (a
# search would spend a credit), only whether its key is set. The result is kept a minute, so the page's polling never
# adds up to many requests.
PROBES = {
    "groq": ("https://api.groq.com/openai/v1/models", "GROQ_API_KEY"),
    "openrouter": ("https://openrouter.ai/api/v1/key", "OPENROUTER_API_KEY"),
    "pollinations": ("https://text.pollinations.ai/models", None),
    "wikipedia": ("https://en.wikipedia.org/w/api.php?action=query&meta=siteinfo&format=json", None),
}
STATUS_KEPT = 60.0
_status: dict = {}


def online_status(root: Path = ROOT, fetch=_request, now=time.monotonic) -> dict:
    """{"state": "online" | "partly" | "offline", "answer": [services that answer], "search": [sources that answer],
    "keys": [keys set]}: online when a model and Wikipedia answer, partly when only one of them does."""
    if _status and now() - _status["at"] < STATUS_KEPT:
        return _status["value"]
    values = settings(root)

    def ask(name: str) -> bool:
        url, key_name = PROBES[name]
        if key_name and not values.get(key_name):
            return False
        status, _ = fetch(url, None, {"Authorization": f"Bearer {values[key_name]}"} if key_name else None, PAGE_TIMEOUT)
        return status == 200

    with ThreadPoolExecutor(max_workers=len(PROBES)) as pool:
        answered = dict(zip(PROBES, pool.map(ask, PROBES)))
    answer = [name for name in ("groq", "openrouter", "pollinations") if answered[name]]
    search = ["wikipedia"] * answered["wikipedia"] + ["tavily"] * bool(values.get("TAVILY_API_KEY"))
    state = "online" if answer and answered["wikipedia"] else "partly" if answer or answered["wikipedia"] else "offline"
    value = {"state": state, "answer": answer, "search": search, "keys": [k for k in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "TAVILY_API_KEY") if values.get(k)]}
    _status.update(at=now(), value=value)
    return value

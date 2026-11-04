"""Fetch the documents the RAG is measured on into eval/rag_documents, in every language of the project (D-166).

    python scripts/fetch_rag_documents.py

Three Wikipedia articles and the Universal Declaration of Human Rights in each language: one article on the challenge's own
subject, one rich in numbers, one that each language wrote about its own part of the world, and a legal text of another
kind altogether. Wikipedia names the revision it gave, kept in SOURCES.json with the licence. The texts are kept in git, so a
measurement never depends on what these pages say later; this script only shows where they came from.
"""

import hashlib
import json
import re
import time
import urllib.parse
import urllib.request
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "eval" / "rag_documents"
AGENT = "TruthGuardian/0.1 (iWISE 2026 AI Challenge 4; https://github.com/danialrafiee-2007/iWISE-project)"
MAX_CHARS = 20_000
LANGUAGES = ("en", "ar", "es", "fa", "fr", "ru", "zh")
SAME_SUBJECT = {"hallucination": "Hallucination (artificial intelligence)", "everest": "Mount Everest"}
THEIR_OWN = {"en": "London", "ar": "القاهرة", "es": "Madrid", "fa": "تهران", "fr": "Paris", "ru": "Москва", "zh": "北京市"}
DECLARATION = {
    "en": "Universal Declaration of Human Rights", "ar": "الإعلان العالمي لحقوق الإنسان", "es": "Declaración Universal de los Derechos Humanos",
    "fa": "اعلامیه جهانی حقوق بشر", "fr": "Déclaration universelle des droits de l'homme", "ru": "Всеобщая декларация прав человека", "zh": "世界人权宣言",
}
WIKIPEDIA_LICENCE = "CC BY-SA 4.0"
WIKISOURCE_LICENCE = "a United Nations text kept by Wikisource, whose own contributions are CC BY-SA 4.0"
_EMPTY_SECTION = re.compile(r"\n=+ [^\n]+ =+\n+(?==)")
_HEADING = re.compile(r"^=+ *(.+?) *=+$", re.MULTILINE)


def get(url: str, attempts: int = 5) -> bytes:
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": AGENT}), timeout=60) as response:
                return response.read()
        except OSError:
            if attempt == attempts - 1:
                raise
            time.sleep(5 * (attempt + 1))
    raise AssertionError


def wiki(code: str, **query) -> dict:
    url = f"https://{code}.wikipedia.org/w/api.php?" + urllib.parse.urlencode({"action": "query", "format": "json", "formatversion": 2, **query})
    return json.loads(get(url))["query"]


def title_in(code: str, english: str) -> str | None:
    if code == "en":
        return english
    links = wiki("en", titles=english, prop="langlinks", lllang=code, redirects=1)["pages"][0].get("langlinks", [])
    return links[0]["title"] if links else None


def article(code: str, title: str) -> tuple[str, dict]:
    page = wiki(code, titles=title, prop="extracts|revisions", explaintext=1, rvprop="ids", redirects=1)["pages"][0]
    text = _HEADING.sub(r"\1", _EMPTY_SECTION.sub("\n", page["extract"]))
    revision = page["revisions"][0]["revid"]
    return text, {"title": page["title"], "url": f"https://{code}.wikipedia.org/w/index.php?oldid={revision}", "revision": revision, "licence": WIKIPEDIA_LICENCE}


class _Words(HTMLParser):
    """The text of a Wikisource page, whose headers and notes sit in tables and whose API gives no plain text."""

    SKIP = {"style", "script", "table", "sup", "figure"}
    BREAK = {"p", "div", "li", "h1", "h2", "h3", "h4", "h5", "br", "dd", "dt"}

    def __init__(self):
        super().__init__()
        self.parts, self.skipping = [], 0

    def handle_starttag(self, tag, attrs):
        self.skipping += tag in self.SKIP
        if tag in self.BREAK:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        self.skipping -= tag in self.SKIP and self.skipping > 0
        if tag in self.BREAK:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skipping:
            self.parts.append(data)

    def text(self) -> str:
        lines = [" ".join(line.split()) for line in "".join(self.parts).splitlines()]
        return "\n".join(line for line in lines if line)


def wikisource(code: str, title: str) -> tuple[str, dict]:
    url = f"https://{code}.wikisource.org/w/api.php?" + urllib.parse.urlencode({"action": "parse", "page": title, "prop": "text|revid", "format": "json", "formatversion": 2, "redirects": 1})
    page = json.loads(get(url))["parse"]
    words = _Words()
    words.feed(page["text"])
    return words.text(), {"title": page["title"], "url": f"https://{code}.wikisource.org/w/index.php?oldid={page['revid']}", "revision": page["revid"], "licence": WIKISOURCE_LICENCE}


def keep(code: str, name: str, text: str, source: dict, sources: list[dict]) -> None:
    cut = text[:MAX_CHARS].rsplit("\n", 1)[0] if len(text) > MAX_CHARS else text
    path = OUT / code / f"{name}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(cut.strip() + "\n", encoding="utf-8", newline="\n")
    sources.append({"language": code, "file": f"{code}/{name}.txt", **source, "cut_to_chars": MAX_CHARS, "sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "retrieved": time.strftime("%Y-%m-%d")})
    print(f"{code} {name:14} {len(cut):6} chars  {source['title']}", flush=True)


def main() -> None:
    sources: list[dict] = []
    for code in LANGUAGES:
        for name, english in SAME_SUBJECT.items():
            title = title_in(code, english)
            if title is None:
                print(f"{code} {name}: no article in this language", flush=True)
                continue
            keep(code, name, *article(code, title), sources)
        keep(code, "their_own", *article(code, THEIR_OWN[code]), sources)
        keep(code, "declaration", *wikisource(code, DECLARATION[code]), sources)
    (OUT / "SOURCES.json").write_text(json.dumps(sources, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(sources)} documents in {OUT}")


if __name__ == "__main__":
    main()

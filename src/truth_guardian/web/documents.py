"""Text from a document the user drops in as a source: PDF, Word (.docx), HTML, Markdown or plain text.

Everything is read in memory, offline, with caps on size and pages. A long document is split at paragraph or
sentence boundaries into parts no longer than one source may be, so it can be checked as several sources.
"""

import io
import re
import zipfile
from html.parser import HTMLParser
from typing import NamedTuple
from xml.etree import ElementTree

MAX_BYTES = 10_000_000
MAX_PAGES = 300
MAX_WORD_XML_BYTES = 50_000_000
TEXT_TYPES = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}
HTML_TYPES = {".html", ".htm"}
SUPPORTED = sorted({".pdf", ".docx", *TEXT_TYPES, *HTML_TYPES})
_WORD = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"


class Extracted(NamedTuple):
    kind: str
    text: str
    pages: int | None


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


class _HtmlText(HTMLParser):
    BLOCKS = {"p", "div", "br", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6", "section", "article", "blockquote"}

    def __init__(self):
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "noscript"):
            self.skip += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in ("script", "style", "noscript"):
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def _pdf(data: bytes) -> Extracted:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted:
            raise ValueError("the PDF is password-protected")
        pages = reader.pages[:MAX_PAGES]
        text = "\n\n".join((page.extract_text() or "") for page in pages)
    except PdfReadError as e:
        raise ValueError(f"the PDF could not be read ({e})") from None
    if not text.strip():
        raise ValueError("the PDF has no text layer (a scanned image); text recognition is not available offline")
    return Extracted("pdf", text, len(reader.pages))


def _docx(data: bytes) -> Extracted:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            if z.getinfo("word/document.xml").file_size > MAX_WORD_XML_BYTES:
                raise ValueError(f"the Word document unpacks to more than {MAX_WORD_XML_BYTES // 1_000_000} MB of text and markup")
            root = ElementTree.fromstring(z.read("word/document.xml"))
    except (zipfile.BadZipFile, KeyError, ElementTree.ParseError):
        raise ValueError("the file is not a valid Word document (.docx)") from None
    paragraphs = []
    for p in root.iter(f"{_WORD}p"):
        pieces = []
        for node in p.iter():
            if node.tag == f"{_WORD}t" and node.text:
                pieces.append(node.text)
            elif node.tag in (f"{_WORD}tab",):
                pieces.append("\t")
            elif node.tag in (f"{_WORD}br", f"{_WORD}cr"):
                pieces.append("\n")
        paragraphs.append("".join(pieces))
    return Extracted("docx", "\n".join(paragraphs), None)


def clean(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace(" ", " ")
    text = re.sub(r"[ \t\f\v]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def extract(name: str, data: bytes) -> Extracted:
    """Raises ValueError with a message meant for the user when the file cannot be used."""
    if len(data) > MAX_BYTES:
        raise ValueError(f"the file is {len(data) / 1e6:.1f} MB; the limit is {MAX_BYTES / 1e6:.0f} MB")
    suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
    if suffix == ".pdf":
        found = _pdf(data)
    elif suffix == ".docx":
        found = _docx(data)
    elif suffix in HTML_TYPES:
        parser = _HtmlText()
        parser.feed(_decode(data))
        found = Extracted("html", "".join(parser.parts), None)
    elif suffix in TEXT_TYPES:
        found = Extracted("text", _decode(data), None)
    else:
        raise ValueError(f"{suffix or 'this'} files are not supported; use {', '.join(SUPPORTED)}")
    text = clean(found.text)
    if not text:
        raise ValueError("no text was found in the file")
    return found._replace(text=text)


def split(text: str, limit: int) -> list[str]:
    """Parts of at most `limit` characters, cut at a paragraph break, else a sentence end, else a space."""
    parts = []
    while len(text) > limit:
        window = text[:limit]
        cut = max(window.rfind("\n\n"), -1)
        if cut < limit // 2:
            cut = max(window.rfind(". "), window.rfind("? "), window.rfind("! "))
            cut = cut + 1 if cut >= limit // 2 else window.rfind(" ")
        if cut <= 0:
            cut = limit
        parts.append(text[:cut].strip())
        text = text[cut:].strip()
    if text:
        parts.append(text)
    return parts

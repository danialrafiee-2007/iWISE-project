"""What writes an answer from the passages: the local model through llama-server, offline on this computer (D-164).
A model online once wrote too, when a key was set; it was removed with the rest of that layer (D-216), and when the
documents hold no answer the free online model of rag/free.py answers instead.

The small local model can fall into saying one sentence over and over until its tokens run out, which takes minutes and which
the check cannot object to, since each repeat is as grounded as the first. So its writing stops at the first sentence said twice.
"""

import base64
import http.client
import json
import re
import threading
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import NamedTuple, Protocol

from truth_guardian.text import split_sentences

LOCAL_MAX_TOKENS = 400
MIN_REPEAT_CHARS = 15
_CITATION = re.compile(r"\[[\d\s,]+\]")
_SENTENCE_ENDS = (".", "!", "?", "]", "。", "！", "？", "؟")
OnText = Callable[[str], None]


class Written(NamedTuple):
    text: str
    model: str
    cost_usd: float = 0.0
    refused: bool = False


class NotAvailable(ValueError):
    """Its message is meant for the person; a ValueError, so a stream reports it as its error."""


def repeat_starts(text: str) -> int | None:
    """Where the first sentence said for the second time begins; citations and case do not make it a new one."""
    seen = set()
    for sentence in split_sentences(text):
        said = _CITATION.sub("", sentence.text).strip().casefold()
        if len(said) >= MIN_REPEAT_CHARS and said in seen:
            return sentence.start
        seen.add(said)
    return None


def whole_sentences(text: str) -> str:
    """A reply cut off by its token limit, up to the end of its last whole sentence; all of it if it has none."""
    sentences = split_sentences(text)
    while len(sentences) > 1 and not sentences[-1].text.rstrip().endswith(_SENTENCE_ENDS):
        sentences.pop()
    return text[: sentences[-1].end] if sentences else text


class Generator(Protocol):
    name: str

    def available(self) -> bool: ...

    def write(self, system: str, messages: list[dict], on_text: OnText | None = None, images: Sequence[bytes] = (), schema: dict | None = None) -> Written:
        """images: PNG pictures the model may look at along with the last message. schema: the JSON the reply must be, held to
        by the local model's grammar; the system prompt should ask for it too."""
        ...


def _with_images(messages: list[dict], parts: list[dict], first: bool = False) -> list[dict]:
    """The messages with the last one's text joined by image parts, in the form each API asks for."""
    if not parts:
        return messages
    text = {"type": "text", "text": messages[-1]["content"]}
    return [*messages[:-1], {**messages[-1], "content": [*parts, text] if first else [text, *parts]}]


class LocalGenerator:
    name = "local"

    def __init__(self):
        self._lock = threading.Lock()

    def available(self) -> bool:
        from truth_guardian.media import vision

        return vision.files_present()

    def write(self, system: str, messages: list[dict], on_text: OnText | None = None, images: Sequence[bytes] = (), schema: dict | None = None) -> Written:
        """One at a time: llama-server is started with one slot, and a second request would only wait for it."""
        from truth_guardian.media import vision

        if not self.available():
            raise NotAvailable("the local model is not on this computer; run TruthGuardian.bat setup once with internet")
        parts = [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image).decode()}} for image in images]
        body = {"model": vision.ALIAS, "temperature": 0, "max_tokens": LOCAL_MAX_TOKENS, "stream": True, "messages": [{"role": "system", "content": system}, *_with_images(messages, parts)]}
        if schema:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": "reply", "schema": schema}}
        written, cut_off = "", False
        try:
            with self._lock:
                server = vision.server()
                server.start()
                request = urllib.request.Request(f"{server.url}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
                with urllib.request.urlopen(request, timeout=vision.ASK_TIMEOUT) as response:
                    for raw in response:
                        line = raw.decode("utf-8").strip()
                        if not line.startswith("data:"):
                            continue
                        payload = line.removeprefix("data:").strip()
                        if payload == "[DONE]":
                            break
                        choice = (json.loads(payload).get("choices") or [{}])[0]
                        cut_off = cut_off or choice.get("finish_reason") == "length"
                        text = (choice.get("delta") or {}).get("content") or ""
                        if not text:
                            continue
                        written += text
                        if on_text:
                            on_text(text)
                        if not schema and written.rstrip().endswith(_SENTENCE_ENDS) and (repeat := repeat_starts(written)) is not None:
                            written = written[:repeat]
                            break
        except (OSError, RuntimeError, http.client.HTTPException) as e:
            raise NotAvailable(f"the local model did not answer: {e}") from e
        return Written((whole_sentences(written) if cut_off and not schema else written).strip(), vision.ALIAS)

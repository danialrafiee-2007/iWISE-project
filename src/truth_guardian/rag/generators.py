"""What writes an answer from the passages: the local model through llama-server, or Claude when a key is set (D-164).

Both take the same request and tell their text as it comes, so the rest of the RAG does not know which one ran. The local
model runs offline on this computer. Claude is better and costs money: it counts against the online check's daily budget
(online.py) and needs a key, so it is used only when the person chooses it. A stream cut off midway reports no usage, so
what it cost cannot be counted.

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

from truth_guardian import online
from truth_guardian.text import split_sentences

LOCAL_MAX_TOKENS = 400
ONLINE_MAX_TOKENS = 8_000
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
        by the local model's grammar; the system prompt must ask for it too, as Claude reads it from there."""
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


class ClaudeGenerator:
    name = "online"

    def __init__(self, root: Path = online.ROOT, client=None, store: Path = online.STORE):
        self.root, self.client, self.store = root, client, store

    def available(self) -> bool:
        return self.client is not None or online.configured(self.root)

    def write(self, system: str, messages: list[dict], on_text: OnText | None = None, images: Sequence[bytes] = (), schema: dict | None = None) -> Written:
        import anthropic

        values = online.settings(self.root)
        limit = online.budget(values)
        if online.spent_today(self.store) >= limit:
            raise NotAvailable(f"today's online budget of ${limit:.2f} is spent")
        if not self.available():
            raise NotAvailable("the online model has no key; put it in anthropic.local.env (see anthropic.example.env)")
        client = self.client or online._client(values["ANTHROPIC_API_KEY"])
        parts = [{"type": "image", "source": {"type": "base64", "media_type": "image/png", "data": base64.b64encode(image).decode()}} for image in images]
        try:
            with client.beta.messages.stream(
                model=online.MODEL, max_tokens=ONLINE_MAX_TOKENS, system=system, messages=_with_images(messages, parts, first=True), output_config={"effort": online.EFFORT},
                betas=["server-side-fallback-2026-07-01"], fallbacks="default",
            ) as stream:
                for text in stream.text_stream:
                    if on_text:
                        on_text(text)
                final = stream.get_final_message()
        except anthropic.APIError as e:
            raise NotAvailable(f"the online model did not answer: {type(e).__name__}") from e
        cost = online._cost(final.usage)
        with online._lock:
            online._add_spend(cost, self.store)
        text = "".join(block.text for block in final.content if block.type == "text").strip()
        return Written(text, online.MODEL, cost, final.stop_reason == "refusal")

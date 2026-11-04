"""What writes an answer from the passages: the local model through llama-server, or Claude when a key is set (D-164).

Both take the same request and tell their text as it comes, so the rest of the RAG does not know which one ran. The local
model runs offline on this computer. Claude is better and costs money: it counts against the online check's daily budget
(online.py) and needs a key, so it is used only when the person chooses it. A stream cut off midway reports no usage, so
what it cost cannot be counted.
"""

import http.client
import json
import threading
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple, Protocol

from truth_guardian import online

LOCAL_MAX_TOKENS = 400
ONLINE_MAX_TOKENS = 8_000
OnText = Callable[[str], None]


class Written(NamedTuple):
    text: str
    model: str
    cost_usd: float = 0.0
    refused: bool = False


class NotAvailable(ValueError):
    """Its message is meant for the person; a ValueError, so a stream reports it as its error."""


class Generator(Protocol):
    name: str

    def available(self) -> bool: ...

    def write(self, system: str, messages: list[dict], on_text: OnText | None = None) -> Written: ...


class LocalGenerator:
    name = "local"

    def __init__(self):
        self._lock = threading.Lock()

    def available(self) -> bool:
        from truth_guardian.media import vision

        return vision.files_present()

    def write(self, system: str, messages: list[dict], on_text: OnText | None = None) -> Written:
        """One at a time: llama-server is started with one slot, and a second request would only wait for it."""
        from truth_guardian.media import vision

        if not self.available():
            raise NotAvailable("the local model is not on this computer; run TruthGuardian.bat setup once with internet")
        body = {"model": vision.ALIAS, "temperature": 0, "max_tokens": LOCAL_MAX_TOKENS, "stream": True, "messages": [{"role": "system", "content": system}, *messages]}
        parts = []
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
                        choices = json.loads(payload).get("choices") or [{}]
                        text = (choices[0].get("delta") or {}).get("content") or ""
                        if text:
                            parts.append(text)
                            if on_text:
                                on_text(text)
        except (OSError, RuntimeError, http.client.HTTPException) as e:
            raise NotAvailable(f"the local model did not answer: {e}") from e
        return Written("".join(parts).strip(), vision.ALIAS)


class ClaudeGenerator:
    name = "online"

    def __init__(self, root: Path = online.ROOT, client=None, store: Path = online.STORE):
        self.root, self.client, self.store = root, client, store

    def available(self) -> bool:
        return self.client is not None or online.configured(self.root)

    def write(self, system: str, messages: list[dict], on_text: OnText | None = None) -> Written:
        import anthropic

        values = online.settings(self.root)
        limit = online.budget(values)
        if online.spent_today(self.store) >= limit:
            raise NotAvailable(f"today's online budget of ${limit:.2f} is spent")
        if not self.available():
            raise NotAvailable("the online model has no key; put it in anthropic.local.env (see anthropic.example.env)")
        client = self.client or online._client(values["ANTHROPIC_API_KEY"])
        try:
            with client.beta.messages.stream(
                model=online.MODEL, max_tokens=ONLINE_MAX_TOKENS, system=system, messages=messages, output_config={"effort": online.EFFORT},
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

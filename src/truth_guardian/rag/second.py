"""A second, independent opinion on an image or a recording, from a free online model (D-200).

The local models read an image (Qwen3-VL-2B) and hear a recording (Whisper Small). Their reading cannot be checked against
itself, so the owner asked that a second model look and listen too, and the Guardian judge between them:

- an image: Groq's vision model (qwen3.8-27b, else OpenRouter's free Nemotron VL) answers the same question about the same
  picture and writes out the words it sees in it;
- a recording: Groq's Whisper large writes its own transcript when the recording is added to the library, kept beside the
  local one.

Then each sentence of the local answer is checked against the second opinion by the local engine, as against any source:
agreed when the second opinion supports it, disputed when it contradicts it, unclear otherwise. Two models agreeing is
not proof, and the report says so; two models disagreeing is the sign of a hallucination worth showing. Sent: the picture
or the recording and the question, to Groq (or OpenRouter), only when a key is set in free.local.env.
"""

import base64
import json
import os
import re
import urllib.request
import uuid
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

from truth_guardian.pipeline import make_sample
from truth_guardian.rag import free
from truth_guardian.rag.seen import found_in
from truth_guardian.text import split_sentences
from truth_guardian.web.engine import NotChecked

VISION = [("groq", "https://api.groq.com/openai/v1/chat/completions", "GROQ_API_KEY", "GROQ_VISION_MODEL", "qwen/qwen3.8-27b", 30),
          ("openrouter", "https://openrouter.ai/api/v1/chat/completions", "OPENROUTER_API_KEY", "OPENROUTER_VISION_MODEL", "nvidia/nemotron-3.5-super-vl:free", 90)]
HEARING = ("https://api.groq.com/openai/v1/audio/transcriptions", "GROQ_API_KEY", "whisper-large-v3")
LOOK = (
    "Look at the image and answer the question in at most five whole sentences, in the language of the question. Then, on a "
    "new line, write TEXT IN IMAGE: followed by every word written in the image, exactly as written and in its own script, "
    "or TEXT IN IMAGE: none."
)
_READ = re.compile(r"^\s*\**\s*TEXT IN IMAGE\s*\**\s*:(.*)$", re.I | re.M | re.S)
_MARK = re.compile(r"\s*\[\d{1,2}(?:\s*,\s*\d{1,2})*\]")


def enabled() -> bool:
    """Off when TG_SECOND_OPINION=0 (the tests set it, so they never reach the internet)."""
    return os.environ.get("TG_SECOND_OPINION", "1") != "0"


class Agreement(BaseModel):
    text: str
    status: Literal["agreed", "disputed", "unclear"]


class SecondOpinion(BaseModel):
    kind: Literal["image", "recording"]
    model: str
    text: str = Field(description="The second model's answer (an image) or transcript (a recording)")
    read: str = Field(default="", description="The words the second model saw in the image")
    claims: list[Agreement] = Field(default_factory=list)
    verdict: Literal["agreed", "disputed", "unclear"] = "unclear"


def look(question: str, picture: bytes, root: Path = free.ROOT, fetch=free._request) -> tuple[str, str, str] | None:
    """A second model's answer about the picture and the words it read in it: (model, answer, read), or None when no
    vision service has a key or none answered."""
    if not enabled():
        return None
    values = free.settings(root)
    image = base64.b64encode(picture).decode()
    kind = "image/png" if picture[:8] == b"\x89PNG\r\n\x1a\n" else "image/jpeg"
    for name, url, key_name, model_name, default, timeout in VISION:
        key = values.get(key_name)
        if not key:
            continue
        model = values.get(model_name) or default
        body = {"model": model, "messages": [{"role": "system", "content": LOOK}, {"role": "user", "content": [
            {"type": "text", "text": question}, {"type": "image_url", "image_url": {"url": f"data:{kind};base64,{image}"}}]}]}
        status, text = fetch(url, body, {"Authorization": f"Bearer {key}"}, timeout)
        if status != 200:
            continue
        try:
            reply = str(json.loads(text)["choices"][0]["message"]["content"] or "")
        except (ValueError, KeyError, IndexError, TypeError):
            continue
        reply = re.sub(r"<think>.*?</think>", "", reply, flags=re.S).strip()
        found = _READ.search(reply)
        answer = reply[: found.start()].strip() if found else reply
        read = found.group(1).strip() if found else ""
        read = "" if read.lower().strip(" .") in ("none", "") else read
        if answer:
            return f"{name}/{model}", " ".join(answer.replace("**", "").split()), " ".join(read.split())
    return None


def hear(name: str, data: bytes, root: Path = free.ROOT, send=None) -> tuple[str, str] | None:
    """A second transcript of a recording by Groq's Whisper large: (model, text), or None without a key or an answer."""
    if not enabled():
        return None
    url, key_name, model = HEARING
    key = free.settings(root).get(key_name)
    if not key:
        return None
    boundary = uuid.uuid4().hex.encode()
    body = b"".join([
        b"--%s\r\nContent-Disposition: form-data; name=\"model\"\r\n\r\n%s\r\n" % (boundary, model.encode()),
        b"--%s\r\nContent-Disposition: form-data; name=\"file\"; filename=\"%s\"\r\nContent-Type: application/octet-stream\r\n\r\n" % (boundary, Path(name).name.encode("utf-8", "replace")),
        data, b"\r\n--%s--\r\n" % boundary,
    ])
    request = urllib.request.Request(url, data=body, headers={"Authorization": f"Bearer {key}", "Content-Type": f"multipart/form-data; boundary={boundary.decode()}", "User-Agent": free.AGENT})
    try:
        if send is not None:
            reply = send(request)
        else:
            with urllib.request.urlopen(request, timeout=120) as response:
                reply = response.read().decode("utf-8")
        text = str(json.loads(reply).get("text") or "").strip()
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return (f"groq/{model}", " ".join(text.split())) if text else None


def agree(answer: str, other: str, question: str | None, engine, cancelled=None) -> list[Agreement]:
    """Each sentence of an answer against a second opinion, by the local engine: agreed when supported, disputed when
    contradicted. In a language the engine does not read, a sentence's numbers and quoted words found in the second
    opinion make it agreed, and else it stays unclear."""
    sentences = [_MARK.sub("", s.text).strip() for s in split_sentences(answer)]
    sentences = [s for s in sentences if re.search(r"\w", s)]
    if not sentences or not other.strip():
        return [Agreement(text=s, status="unclear") for s in sentences]
    try:
        report = engine.analyze(make_sample(answer, [other], question, sample_id="second"), cancelled=cancelled)
    except NotChecked:
        marks = lambda s: re.findall(r"\d[\d,.]*|«[^»]+»|\"[^\"]+\"|“[^”]+”", s)
        return [Agreement(text=s, status="agreed" if marks(s) and all(found_in(m.strip('«»"“”'), other) for m in marks(s)) else "unclear") for s in sentences]
    found = []
    for claim in report.claims:
        text = _MARK.sub("", claim.text).strip()
        if not re.search(r"\w", text):
            continue
        found.append(Agreement(text=text, status="agreed" if claim.status == "supported" else "disputed" if claim.status == "contradicted" else "unclear"))
    return found


def opinion(kind: str, model: str, other: str, answer: str, question: str | None, engine, read: str = "", cancelled=None) -> SecondOpinion:
    claims = agree(answer, other, question, engine, cancelled)
    verdict = "disputed" if any(c.status == "disputed" for c in claims) else "agreed" if any(c.status == "agreed" for c in claims) else "unclear"
    return SecondOpinion(kind=kind, model=model, text=other, read=read, claims=claims, verdict=verdict)

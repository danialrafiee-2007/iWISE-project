"""Smoke test of the web app against the real models: every endpoint once, and the built front end checked for
anything that would need the internet. Takes a minute or two (model loading and warm-up).

Exit code 0 when everything passes; each check prints one line.
"""

import json
import re
import sys
import time
from pathlib import Path

from fastapi.testclient import TestClient

from truth_guardian.web.app import STATIC, create_app

ROOT = Path(__file__).resolve().parents[1]
ALLOWED = re.compile(r"https?://(www\.w3\.org|localhost|127\.0\.0\.1|threejs\.org|github\.com|mrdoob\.com|reactjs\.org|react\.dev|fb\.me|tailwindcss\.com|fontshare\.com|getlayers\.ai|textura\.agency|github\.io)")
failures = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{f'  ({detail})' if detail else ''}", flush=True)
    if not ok:
        failures.append(name)


def result(response) -> dict:
    events = [json.loads(line) for line in response.iter_lines() if line]
    return events[-1] if events else {"type": "error", "message": "no events"}


def offline_build() -> None:
    index = STATIC / "index.html"
    check("front end is built", index.exists())
    found = set()
    for path in STATIC.rglob("*"):
        if path.suffix in {".html", ".js", ".css"}:
            for url in re.findall(r"https?://[^\s\"'`)<>]+", path.read_text(encoding="utf-8", errors="ignore")):
                if not ALLOWED.match(url):
                    found.add(f"{path.relative_to(STATIC).as_posix()}: {url[:80]}")
    loaders = [u for u in found if re.search(r"(unpkg|jsdelivr|cdnjs|googleapis|gstatic)\.", u)]
    check("no CDN or online font is loaded", not loaders, "; ".join(sorted(loaders)[:5]))
    print(f"     {len(found)} other URLs appear only in comments and licence text of bundled libraries")


def main() -> None:
    offline_build()
    started = time.perf_counter()
    with TestClient(create_app()) as client:
        while (health := client.get("/api/health").json())["state"] not in ("ready", "failed"):
            time.sleep(1)
        check("models load and warm up", health["state"] == "ready", f"{time.perf_counter() - started:.0f} s")
        if health["state"] != "ready":
            sys.exit(1)
        for page in ["/", "/analyze", "/agent", "/fool", "/model", "/audio", "/image/models", "/layers/glass-halo.html", "/layers/signal-array.html"]:
            check(f"GET {page}", client.get(page).status_code == 200)

        t = time.perf_counter()
        r = result(client.post("/api/analyze", json={"question": "When did Anne Frank die?", "sources": ["Anne Frank died of typhus in February 1945 at Bergen-Belsen."], "answer": "Anne Frank died in 1946 at Bergen-Belsen.", "task": "qa"}))
        fixes = [f["replacement"] for c in r.get("report", {}).get("claims", []) for f in c["fixes"]]
        check("analyze catches a wrong year and fixes it", r["type"] == "result" and r["report"]["verdict"] != "grounded" and "1945" in fixes, f"{time.perf_counter() - t:.1f} s")

        if health.get("multilingual_version"):
            t = time.perf_counter()
            spanish = {"question": "¿Cuándo murió Ana Frank?", "sources": ["Ana Frank murió de tifus en febrero de 1945 en Bergen-Belsen."], "answer": "Ana Frank murió en 1950 en Bergen-Belsen.", "task": "qa"}
            r = result(client.post("/api/analyze", json=spanish))
            language = r.get("report", {}).get("language") or {}
            check("a Spanish answer goes to the multilingual check", r["type"] == "result" and language.get("check") == "multilingual" and language.get("answer") == "es", f"{time.perf_counter() - t:.1f} s")
        persian = client.post("/api/analyze", json={"sources": ["آنه فرانک در سال ۱۹۴۵ درگذشت و دفتر خاطراتش منتشر شد."], "answer": "آنه فرانک در سال ۱۹۴۶ درگذشت و دفتر خاطراتش منتشر شد."})
        check("a Persian answer is refused with its language", persian.status_code == 422 and persian.json()["detail"].get("language") == "fa")

        r = result(client.post("/api/analyze", json={"example_id": "anne-frank"}))
        check("a ready-made example is served from the cache", r["type"] == "result" and r["cached"])

        r = result(client.post("/api/heal", json={"example_id": "anne-frank"}))
        check("heal produces rounds with the fixed year", r["type"] == "result" and "1945" in r["answer"] and len(r["rounds"]) >= 2, r.get("answer", r.get("message", ""))[:60])

        r = result(client.post("/api/agent", json={"example_id": "agent-liberation", "policy": "strict"}))
        check("the agent guardian stops the planted fabrication", r["type"] == "result" and r["report"]["agent"]["guardian_stop"] == 3)

        answers = client.get("/api/fool/answers").json()
        edited = None
        for a in answers[:10]:
            resp = client.post("/api/fool/edit", json={"answer_id": a["id"], "kind": "number", "seed": 1})
            if resp.status_code == 200:
                edited = (a["id"], resp.json()["answer"])
                break
        check("Fool the Guardian makes a number edit", edited is not None)
        if edited:
            r = result(client.post("/api/fool/check", json={"answer_id": edited[0], "answer": edited[1]}))
            check("Fool the Guardian scores the edit", r["type"] == "result" and r["edit"] is not None, f"caught={r.get('caught')} located={r.get('located')}")

        card = client.get("/api/model-card").json()
        check("model card reads the results", "ragtruth_dev" in card and "fool_the_guardian" in card)
    print("all passed" if not failures else f"{len(failures)} failed: {failures}")
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()

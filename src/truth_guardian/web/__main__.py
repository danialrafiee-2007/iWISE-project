"""Start the web app on localhost and open it in the browser; the models load and warm up in the background.

Runs offline: Hugging Face is told not to reach the network, so the models must already be downloaded.
--check prints what is present and missing and exits; --prepare (needs internet once) downloads the models, warms
them up and builds the example cache, then exits. --host 0.0.0.0 serves other machines (a hosted demo; see
TG_ALLOWED_HOSTS and TG_ACCESS_CODE in app.py).
"""

import argparse
import os
import sys
import threading
import webbrowser

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to serve other machines, e.g. in a container")
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--check", action="store_true", help="print the readiness checklist and exit")
    parser.add_argument("--prepare", action="store_true", help="download and warm up the models, cache the examples, exit")
    args = parser.parse_args()
    if not args.prepare:
        os.environ.setdefault("HF_HUB_OFFLINE", "1")

    from truth_guardian.web.engine import ROOT

    if args.check:
        from truth_guardian.web.doctor import report

        sys.exit(0 if report(ROOT) else 1)
    if args.prepare:
        from truth_guardian.web.app import prepare
        from truth_guardian.web.engine import Engine
        from truth_guardian.web.examples import ExampleStore

        from truth_guardian.media import models_dir, multilingual
        from truth_guardian.rag.library import open_library

        engine = Engine(ROOT)
        try:
            prepare(engine, ExampleStore(ROOT), every_model=True)
            added = open_library(ROOT).ensure_project(ROOT) if (models_dir() / multilingual.E5).is_dir() else 0
        except Exception as e:
            sys.exit(f"preparation failed: {engine.error or f'{type(e).__name__}: {e}'}")
        print(f"models ready (warm-up {engine.warm_seconds:.0f} s); examples cached in data/web/examples; {added} project documents added to the library")
        return

    import uvicorn

    from truth_guardian.web.app import create_app

    if args.host not in ("127.0.0.1", "localhost", "::1") and not os.environ.get("TG_ACCESS_CODE"):
        print(
            "Warning: listening beyond this computer without TG_ACCESS_CODE, so anyone who reaches the port can use the app. "
            "Fine in a container published on 127.0.0.1 only (compose.yaml); set TG_ACCESS_CODE before exposing it.",
            flush=True,
        )
    url = f"http://{'127.0.0.1' if args.host == '0.0.0.0' else args.host}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    print(f"Truth Guardian: {url}  (Ctrl+C to stop)", flush=True)
    uvicorn.run(create_app(), host=args.host, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

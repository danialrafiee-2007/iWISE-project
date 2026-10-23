"""Start the web app on localhost and open it in the browser; the models load and warm up in the background.

Runs offline: Hugging Face is told not to reach the network (the models must already be downloaded, see README).
"""

import argparse
import os
import threading
import webbrowser

os.environ.setdefault("HF_HUB_OFFLINE", "1")

import uvicorn  # noqa: E402

from truth_guardian.web.app import create_app  # noqa: E402

HOST = "127.0.0.1"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    url = f"http://{HOST}:{args.port}"
    if not args.no_browser:
        threading.Timer(1.5, webbrowser.open, [url]).start()
    print(f"Truth Guardian: {url}  (Ctrl+C to stop)", flush=True)
    uvicorn.run(create_app(), host=HOST, port=args.port, log_level="warning")


if __name__ == "__main__":
    main()

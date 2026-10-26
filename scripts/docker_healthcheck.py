"""Container health check: healthy only when the models are loaded and warm.

/api/health answers from the first second, while the models still load, so the HTTP status alone says nothing; this
reads its JSON and passes only on state "ready". Standard library only (the slim image has no curl), and it never
loads a model itself. Exit code 0 when ready, 1 otherwise; prints the state for `docker inspect`.
"""

import json
import os
import sys
import urllib.request

URL = f"http://127.0.0.1:{os.environ.get('TG_CONTAINER_PORT', '7860')}/api/health"

try:
    with urllib.request.urlopen(URL, timeout=4) as response:
        state = json.load(response).get("state")
except Exception as e:
    print(f"no answer: {type(e).__name__}")
    sys.exit(1)
print(state)
sys.exit(0 if state == "ready" else 1)

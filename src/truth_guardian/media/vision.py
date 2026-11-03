"""What an image shows, from Qwen3-VL-2B (GGUF, Q4_K_M with its Q8_0 vision part) run by llama.cpp's llama-server.

The server is started on demand on 127.0.0.1 only, with the model files from runtime/multimodal and no GPU layers, and is
stopped by stop() (the web app calls it when it shuts down); on Windows it also ends with this process, however that
ends, such as when its window is closed. Images go in the request itself as base64, never as a
public URL. The model is asked to state only what is visible, to keep any text in the image in its own language and to
call unreadable details unclear; its description is an opinion, so a reading from here always goes to review and is
never treated as proof of a claim on its own.
"""

import base64
import io
import json
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from truth_guardian.media import ROOT, llama_server, models_dir
from truth_guardian.media.contract import Place, Reading, Segment

MODEL = "qwen3-vl-2b-gguf/Qwen3VL-2B-Instruct-Q4_K_M.gguf"
PROJECTOR = "qwen3-vl-2b-gguf/mmproj-Qwen3VL-2B-Instruct-Q8_0.gguf"
HOST, PORT, ALIAS = "127.0.0.1", 8081, "tg-vision"
THREADS = 4
START_TIMEOUT = 180
ASK_TIMEOUT = 300
PROMPT = (
    "Describe only what is visible in this image: objects, people, actions, numbers and any written text. "
    "Copy written text exactly, in its original language and script; do not translate it. "
    "If a detail cannot be read or seen clearly, say it is unclear instead of guessing. Do not add anything that is not shown."
)


KILL_ON_JOB_CLOSE = 0x2000
EXTENDED_LIMIT_INFORMATION = 9
_job = None


def tie_to_this_process(process: subprocess.Popen) -> None:
    """On Windows, puts the process in a job object that ends it when the last handle closes, which is when this process
    ends. Without this, closing the app's window leaves the server running, the model in memory and its port taken."""
    global _job
    if sys.platform != "win32":
        return
    import ctypes
    from ctypes import wintypes

    class Limits(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64), ("LimitFlags", wintypes.DWORD),
            ("MinimumWorkingSetSize", ctypes.c_size_t), ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
            ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD),
        ]

    class ExtendedLimits(ctypes.Structure):
        _fields_ = [
            ("BasicLimitInformation", Limits), ("IoInfo", ctypes.c_uint64 * 6), ("ProcessMemoryLimit", ctypes.c_size_t),
            ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t), ("PeakJobMemoryUsed", ctypes.c_size_t),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.CreateJobObjectW.argtypes = (ctypes.c_void_p, wintypes.LPCWSTR)
    kernel32.SetInformationJobObject.argtypes = (wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)
    kernel32.AssignProcessToJobObject.argtypes = (wintypes.HANDLE, wintypes.HANDLE)
    if _job is None:
        job = kernel32.CreateJobObjectW(None, None)
        limits = ExtendedLimits()
        limits.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE
        if job and kernel32.SetInformationJobObject(job, EXTENDED_LIMIT_INFORMATION, ctypes.byref(limits), ctypes.sizeof(limits)):
            _job = job
    if _job:
        kernel32.AssignProcessToJobObject(_job, int(process._handle))


class VisionServer:
    def __init__(self, port: int = PORT):
        self.port = port
        self.process: subprocess.Popen | None = None
        self.output = None
        self.lock = threading.Lock()
        self.log = ROOT / "runtime" / "logs" / "llama-server.log"

    @property
    def url(self) -> str:
        return f"http://{HOST}:{self.port}"

    def command(self) -> list[str]:
        models = models_dir()
        return [
            str(llama_server()), "-m", str(models / MODEL), "--mmproj", str(models / PROJECTOR), "--host", HOST, "--port", str(self.port),
            "--alias", ALIAS, "--ctx-size", "4096", "--threads", str(THREADS), "--n-gpu-layers", "0", "--no-mmproj-offload", "--parallel", "1",
        ]

    def healthy(self) -> bool:
        try:
            with urllib.request.urlopen(f"{self.url}/health", timeout=2) as r:
                return r.status == 200 and json.load(r).get("status") == "ok"
        except (OSError, ValueError):
            return False

    def start(self) -> None:
        with self.lock:
            if self.process and self.process.poll() is None and self.healthy():
                return
            self.stop()
            self.log.parent.mkdir(parents=True, exist_ok=True)
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            self.output = open(self.log, "ab")
            self.process = subprocess.Popen(self.command(), stdout=self.output, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, creationflags=flags)
            tie_to_this_process(self.process)
            deadline = time.monotonic() + START_TIMEOUT
            while time.monotonic() < deadline:
                if self.process.poll() is not None:
                    raise RuntimeError(f"llama-server stopped while starting (code {self.process.returncode}); see {self.log}")
                if self.healthy():
                    return
                time.sleep(0.5)
            self.stop()
            raise TimeoutError(f"llama-server was not ready after {START_TIMEOUT} s; see {self.log}")

    def stop(self) -> None:
        process, self.process = self.process, None
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        if self.output:
            self.output.close()
            self.output = None

    def ask(self, image_png: bytes, prompt: str = PROMPT, max_tokens: int = 256) -> str:
        self.start()
        body = {
            "model": ALIAS, "temperature": 0, "max_tokens": max_tokens, "stream": False,
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": prompt},
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(image_png).decode()}},
            ]}],
        }
        request = urllib.request.Request(f"{self.url}/v1/chat/completions", data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(request, timeout=ASK_TIMEOUT) as r:
            return json.load(r)["choices"][0]["message"]["content"].strip()


_server = VisionServer()


def server() -> VisionServer:
    return _server


def reader_name() -> str:
    build = version_file().read_text(encoding="utf-8").split()[0] if version_file().is_file() else "build unknown"
    return f"Qwen3-VL-2B-Instruct Q4_K_M + mmproj Q8_0, llama.cpp {build}"


def describe(image_or_path, question: str | None = None) -> Reading:
    """What the image shows, as one description segment. `question` narrows it (it is added to the standing prompt)."""
    from PIL import Image

    started = time.perf_counter()
    image = image_or_path if isinstance(image_or_path, Image.Image) else Image.open(image_or_path)
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="PNG")
    prompt = PROMPT if not question else f"{PROMPT}\nQuestion: {question}"
    text = server().ask(buffer.getvalue(), prompt)
    reading = Reading(kind="image", reader=reader_name(), segments=[Segment(text=text, role="description", place=Place(box=(0, 0, image.width, image.height)))])
    reading.review("an image description is the model's opinion, not proof on its own")
    reading.seconds = round(time.perf_counter() - started, 2)
    return reading


def stop() -> None:
    _server.stop()


def files_present() -> bool:
    models = models_dir()
    return llama_server().is_file() and (models / MODEL).is_file() and (models / PROJECTOR).is_file()


def version_file() -> Path:
    """Written when llama.cpp is unpacked: the release tag and the zip's SHA-256."""
    return llama_server().parent / "VERSION.txt"

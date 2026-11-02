"""Media pilot: makes samples with known content, runs every media reader on them with the network cut off, each reader
in its own process, and records what it read, how long it took and the process's peak memory, in
eval/results/media_pilot.json (a copy goes to --report-dir when given).

    uv run python scripts/media_pilot.py [--only ocr,speech,vision,retrieval,nli] [--report-dir DIR]

Samples go to runtime/media-smoke. Images are drawn by the local Edge browser from HTML, so Arabic-script and Ethiopic
text is shaped as a reader would see it; speech comes from Windows' own voices (System.Speech); silence is
made here. They are synthetic and few: they show that each reader loads offline, runs and reads what it
should, not how well it does on real recordings and photos, which needs labelled data (eval/results/media_eval.json).
The checks follow from the samples' known content.
"""

import argparse
import json
import os
import platform
import shutil
import struct
import subprocess
import sys
import time
import wave
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
SAMPLES = ROOT / "runtime" / "media-smoke"
RESULT = ROOT / "eval" / "results" / "media_pilot.json"
DEAD_PROXY = "http://127.0.0.1:9"
EDGE = [Path(r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"), Path(r"C:\Program Files\Microsoft\Edge\Application\msedge.exe")]
EDGE_PROFILE = Path(os.environ.get("TG_EDGE_PROFILE", ROOT / "runtime" / "edge-headless"))
COMPONENTS = ["ocr", "speech", "vision", "retrieval", "nli"]

IMAGES = {
    "ocr-ja": ("Yu Gothic", "会議は午前十時に始まります。<br>資料は受付で配ります。", "ltr"),
    "ocr-am": ("Ebrima", "የኢትዮጵያ ዋና ከተማ አዲስ አበባ ናት።", "ltr"),
    "ocr-fa": ("Tahoma", "پایتخت ایران تهران است.<br>جلسه ساعت ده صبح شروع می‌شود.", "rtl"),
    "ocr-ar": ("Tahoma", "عاصمة مصر هي القاهرة.", "rtl"),
    "ocr-sw": ("Segoe UI", "Mji mkuu wa Kenya ni Nairobi na ni mji mkubwa wa Afrika Mashariki.", "ltr"),
    "ocr-en": ("Segoe UI", "The meeting starts at ten o'clock in room 214.", "ltr"),
}
# Expected words per image, and the BCP 47 language the reader should report (or flag for review).
EXPECT = {
    "ocr-ja": (["会議", "十時"], "ja"),
    "ocr-am": (["አዲስ", "አበባ"], "am"),
    "ocr-fa": (["تهران", "ایران"], "fa"),
    "ocr-ar": (["القاهرة", "مصر"], "ar"),
    "ocr-sw": (["Nairobi", "Kenya"], "sw"),
    "ocr-en": (["meeting", "214"], "en"),
    "ocr-en-rotated": (["meeting", "214"], "en"),
}
ENGLISH_SPEECH = "The capital of France is Paris, and the meeting starts at ten o'clock."
OTHER_SPEECH = {
    "de": "Die Hauptstadt von Deutschland ist Berlin.", "fr": "La capitale de l'Espagne est Madrid.", "es": "La capital de Italia es Roma.",
    "it": "La capitale della Germania è Berlino.", "pt": "A capital do Brasil é Brasília.", "ja": "日本の首都は東京です。",
    "zh": "中国的首都是北京。", "ru": "Столица России — Москва.", "ko": "한국의 수도는 서울입니다.", "nl": "De hoofdstad van Nederland is Amsterdam.",
}
RETRIEVAL = [
    ("会議は何時に始まりますか。", ["The library closes at six.", "会議は午前十時に始まります。", "Le musée est fermé le lundi."], 1),
    ("پایتخت ایران کجاست؟", ["The capital of Iran is Tehran.", "La capital de Francia es París.", "Der Zug fährt um acht Uhr."], 0),
    ("Where does the train leave from?", ["El tren sale del andén cuatro.", "پایتخت ایران تهران است.", "東京は日本の首都です。"], 0),
    ("¿Cuándo cierra la biblioteca?", ["La biblioteca cierra a las seis.", "The meeting is on Monday.", "Москва — столица России."], 0),
]
# premise, hypothesis, expected label; the labels follow from the words.
NLI_PAIRS = [
    ("会議は午前十時に始まります。", "会議は朝に始まります。", "entailment"),
    ("会議は午前十時に始まります。", "会議は正午に始まります。", "contradiction"),
    ("会議は午前十時に始まります。", "会議には三十人が参加します。", "neutral"),
    ("پایتخت ایران تهران است.", "تهران پایتخت ایران است.", "entailment"),
    ("پایتخت ایران تهران است.", "پایتخت ایران اصفهان است.", "contradiction"),
    ("پایتخت ایران تهران است.", "تهران شهری پرجمعیت است.", "neutral"),
    ("The museum is closed on Mondays.", "The museum does not open on Mondays.", "entailment"),
    ("The museum is closed on Mondays.", "The museum is open every day of the week.", "contradiction"),
    ("The museum is closed on Mondays.", "The museum has a large collection of paintings.", "neutral"),
    ("La biblioteca cierra a las seis de la tarde.", "La biblioteca abre por la noche hasta medianoche.", "contradiction"),
    ("La biblioteca cierra a las seis de la tarde.", "La biblioteca cierra por la tarde.", "entailment"),
    ("Столица России — Москва.", "Москва является столицей России.", "entailment"),
]


# --- measurement --------------------------------------------------------------------------------------------------

def peak_mb(pid: int | None = None) -> float | None:
    """Peak working set of this process (or of `pid`), from Windows; None elsewhere."""
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD)] + [(n, ctypes.c_size_t) for n in (
            "PeakWorkingSetSize", "WorkingSetSize", "QuotaPeakPagedPoolUsage", "QuotaPagedPoolUsage", "QuotaPeakNonPagedPoolUsage",
            "QuotaNonPagedPoolUsage", "PagefileUsage", "PeakPagefileUsage")]

    kernel, psapi = ctypes.WinDLL("kernel32"), ctypes.WinDLL("psapi")
    kernel.GetCurrentProcess.restype = wintypes.HANDLE
    kernel.OpenProcess.restype = wintypes.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
    handle = kernel.GetCurrentProcess() if pid is None else kernel.OpenProcess(0x0400 | 0x0010, False, pid)
    counters = Counters()
    counters.cb = ctypes.sizeof(Counters)
    if not psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb):
        return None
    return round(counters.PeakWorkingSetSize / 2**20, 1)


def ram_gb() -> float | None:
    if os.name != "nt":
        return None
    import ctypes

    class Status(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong), ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong), ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong), ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

    status = Status()
    status.dwLength = ctypes.sizeof(Status)
    ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status))
    return round(status.ullTotalPhys / 2**30, 1)


def check(name: str, ok: bool, detail: str = "") -> dict:
    return {"check": name, "passed": bool(ok), "detail": detail}


# --- samples -------------------------------------------------------------------------------------------------------

def edge() -> Path:
    found = next((p for p in EDGE if p.is_file()), None)
    if not found:
        raise SystemExit("Microsoft Edge is needed to draw the image samples")
    return found


def draw_html(name: str, html: str, size: tuple[int, int]) -> Path:
    page, png = SAMPLES / f"{name}.html", SAMPLES / f"{name}.png"
    page.write_text(html, encoding="utf-8")
    subprocess.run([str(edge()), "--headless=new", f"--user-data-dir={EDGE_PROFILE}", f"--window-size={size[0]},{size[1]}", "--hide-scrollbars",
                    "--virtual-time-budget=3000", f"--screenshot={png}", page.as_uri()], check=True, capture_output=True, timeout=120)
    return png


def text_page(font: str, text: str, direction: str) -> str:
    return (f'<!doctype html><html dir="{direction}"><meta charset="utf-8"><body style="margin:0;background:#fff">'
            f'<p style="margin:40px 48px;font:46px/1.5 \'{font}\';color:#111">{text}</p></body></html>')


def voices() -> list[tuple[str, str]]:
    script = "Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices() | Where-Object Enabled | ForEach-Object { $_.VoiceInfo.Name + '|' + $_.VoiceInfo.Culture.Name }"
    out = subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], capture_output=True, text=True, timeout=120).stdout
    return [tuple(line.strip().split("|", 1)) for line in out.splitlines() if "|" in line]


def speak(voice: str, text: str, path: Path) -> None:
    quoted = text.replace("'", "''")
    script = (
        "Add-Type -AssemblyName System.Speech; $s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
        f"$s.SelectVoice('{voice}'); $f = New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000, "
        "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen, [System.Speech.AudioFormat.AudioChannel]::Mono); "
        f"$s.SetOutputToWaveFile('{path}', $f); $s.Speak('{quoted}'); $s.Dispose()"
    )
    subprocess.run(["powershell.exe", "-NoProfile", "-Command", script], check=True, capture_output=True, timeout=120)


def read_wav(path: Path) -> bytes:
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())


def write_wav(path: Path, frames: bytes) -> None:
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(16_000)
        w.writeframes(frames)


def silence(seconds: float, noise: int = 6) -> bytes:
    """Quiet room tone: tiny noise rather than digital zero, closer to a real silent recording."""
    import random

    rng = random.Random(7)
    return b"".join(struct.pack("<h", rng.randint(-noise, noise)) for _ in range(int(seconds * 16_000)))


def make_samples() -> dict:
    from PIL import Image, ImageDraw, ImageFont

    SAMPLES.mkdir(parents=True, exist_ok=True)
    made = {}
    for name, (font, text, direction) in IMAGES.items():
        made[name] = str(draw_html(name, text_page(font, text, direction), (1400, 360)))
    upright = Image.open(made["ocr-en"])
    turned = SAMPLES / "ocr-en-rotated.png"
    upright.rotate(90, expand=True).save(turned)
    made["ocr-en-rotated"] = str(turned)
    scene = Image.new("RGB", (800, 500), "white")
    pen = ImageDraw.Draw(scene)
    pen.ellipse((80, 120, 320, 360), fill=(220, 30, 30))
    pen.rectangle((460, 130, 700, 370), fill=(30, 70, 220))
    pen.text((300, 410), "OPEN", fill="black", font=ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf" if Path(r"C:\Windows\Fonts\arialbd.ttf").is_file() else r"C:\Windows\Fonts\arial.ttf", 60))
    scene.save(SAMPLES / "vision-scene.png")
    made["vision-scene"] = str(SAMPLES / "vision-scene.png")

    found = voices()
    english = next((v for v, c in found if c.startswith("en")), None)
    other = next(((v, c) for v, c in found if not c.startswith("en") and c.split("-")[0] in OTHER_SPEECH), None)
    made["voices"] = [f"{v} ({c})" for v, c in found]
    if english:
        speak(english, ENGLISH_SPEECH, SAMPLES / "speech-en.wav")
        made["speech-en"] = str(SAMPLES / "speech-en.wav")
    write_wav(SAMPLES / "silence.wav", silence(5.0))
    made["silence"] = str(SAMPLES / "silence.wav")
    if english and other:
        speak(other[0], OTHER_SPEECH[other[1].split("-")[0]], SAMPLES / "speech-other.wav")
        write_wav(SAMPLES / "speech-switch.wav", read_wav(SAMPLES / "speech-en.wav") + silence(0.8) + read_wav(SAMPLES / "speech-other.wav"))
        made["speech-switch"] = str(SAMPLES / "speech-switch.wav")
        made["switch-language"] = other[1].split("-")[0]
    (SAMPLES / "samples.json").write_text(json.dumps(made, ensure_ascii=False, indent=2), encoding="utf-8")
    return made


# --- readers, one per child process --------------------------------------------------------------------------------

def similarity(expected: str, read: str) -> float:
    """Character similarity of two texts with spacing and case ignored (1 = identical), as SequenceMatcher measures it."""
    from difflib import SequenceMatcher

    squash = lambda s: "".join(s.lower().split())
    return round(SequenceMatcher(None, squash(expected), squash(read)).ratio(), 3)


def run_ocr(samples: dict) -> dict:
    from PIL import Image

    from truth_guardian.media import ocr

    results, checks, seconds = [], [], {}
    for name, (words, language) in EXPECT.items():
        if name not in samples:
            continue
        reading = ocr.read_text(samples[name])
        seconds[name] = reading.seconds
        expected = IMAGES[name.replace("-rotated", "")][1].replace("<br>", "\n")
        close = similarity(expected, reading.text)
        found = close >= 0.85
        size = Image.open(samples[name]).size
        inside = all(s.place.box and 0 <= s.place.box[0] and 0 <= s.place.box[1] and s.place.box[0] + s.place.box[2] <= size[0] + 2 and s.place.box[1] + s.place.box[3] <= size[1] + 2 for s in reading.segments)
        right = reading.language == language or (reading.needs_review and language in [a.language for a in reading.alternatives] + [reading.language])
        checks += [check(f"{name}: text read (character similarity {close} >= 0.85)", found, reading.text[:120]), check(f"{name}: language {language} or sent to review", right, f"{reading.language} review={reading.needs_review} {reading.reasons[:2]}"),
                   check(f"{name}: boxes inside the original image", inside)]
        results.append({"sample": name, "similarity": close, "words_found": [w for w in words if w.lower() in reading.text.lower()], **reading.model_dump(include={"language", "language_confidence", "quality", "needs_review", "reasons", "notes", "seconds"}), "text": reading.text, "alternatives": [a.model_dump() for a in reading.alternatives]})
    return {"reader": ocr.reader_name(), "results": results, "checks": checks, "seconds": seconds}


def run_speech(samples: dict) -> dict:
    from truth_guardian.media import speech

    started = time.perf_counter()
    speech.model()
    load = round(time.perf_counter() - started, 2)
    results, checks, seconds = [], [], {"load": load}
    if "speech-en" in samples:
        r = speech.transcribe(Path(samples["speech-en"]))
        seconds["speech-en"] = r.seconds
        heard = r.text.lower()
        checks += [check("speech-en: words heard (ten may be written 10)", "paris" in heard and "france" in heard and ("ten" in heard or "10" in heard), r.text), check("speech-en: language en", r.language == "en", f"{r.language} {r.language_confidence}"),
                   check("speech-en: word times inside the file", all(s.place.start is not None and s.place.end <= 12 for s in r.segments))]
        results.append({"sample": "speech-en", **r.model_dump(include={"language", "language_confidence", "quality", "needs_review", "reasons", "notes"}), "text": r.text, "segments": [s.model_dump() for s in r.segments]})
    r = speech.transcribe(Path(samples["silence"]))
    seconds["silence"] = r.seconds
    checks.append(check("silence: nothing invented, sent to review", not r.segments and r.needs_review, f"{len(r.segments)} segments, {r.reasons}"))
    results.append({"sample": "silence", **r.model_dump(include={"needs_review", "reasons"}), "text": r.text})
    if "speech-switch" in samples:
        r = speech.transcribe(Path(samples["speech-switch"]))
        seconds["speech-switch"] = r.seconds
        spoken = {s.language for s in r.segments}
        checks.append(check(f"switch: en and {samples['switch-language']} both found", {"en", samples["switch-language"]} <= spoken, f"{sorted(spoken)} {r.notes}"))
        results.append({"sample": "speech-switch", **r.model_dump(include={"language", "notes", "needs_review", "reasons"}), "segments": [s.model_dump() for s in r.segments]})
    return {"reader": speech.reader_name(), "results": results, "checks": checks, "seconds": seconds}


def run_vision(samples: dict) -> dict:
    from truth_guardian.media import vision

    server = vision.server()
    started = time.perf_counter()
    server.start()
    load = round(time.perf_counter() - started, 2)
    try:
        r = vision.describe(samples["vision-scene"])
        server_peak = peak_mb(server.process.pid) if server.process else None
    finally:
        vision.stop()
    text = r.text.lower()
    checks = [check("vision: the round red shape", ("circle" in text or "round" in text) and "red" in text), check("vision: the blue square", "square" in text and "blue" in text),
              check("vision: the word OPEN copied", "open" in text), check("vision: sent to review (an opinion)", r.needs_review)]
    return {"reader": vision.reader_name(), "results": [{"sample": "vision-scene", "text": r.text, "reasons": r.reasons}], "checks": checks, "seconds": {"start": load, "describe": r.seconds}, "server_peak_mb": server_peak}


def run_retrieval(_: dict) -> dict:
    from truth_guardian.media import multilingual

    started = time.perf_counter()
    multilingual.e5()
    load = round(time.perf_counter() - started, 2)
    checks, results = [], []
    started = time.perf_counter()
    for query, passages, right in RETRIEVAL:
        ranked = multilingual.rank(query, passages)
        checks.append(check(f"retrieval: {query[:24]}", ranked[0][0] == right, str(ranked)))
        results.append({"query": query, "ranked": ranked, "expected": right})
    return {"reader": "intfloat/multilingual-e5-small", "results": results, "checks": checks, "seconds": {"load": load, "queries": round(time.perf_counter() - started, 2)}}


def run_nli(_: dict) -> dict:
    from truth_guardian.media import multilingual

    started = time.perf_counter()
    multilingual.nli()
    load = round(time.perf_counter() - started, 2)
    checks, results = [], []
    started = time.perf_counter()
    for premise, hypothesis, label in NLI_PAIRS:
        judged = multilingual.judge(premise, hypothesis)
        checks.append(check(f"nli: {hypothesis[:28]} -> {label}", judged["label"] == label, json.dumps(judged, ensure_ascii=False)))
        results.append({"premise": premise, "hypothesis": hypothesis, "expected": label, **judged})
    long_premise = " ".join(["The weather was mild and the streets were quiet."] * 120) + " The museum is closed on Mondays."
    judged = multilingual.judge(long_premise, "The museum is open every day of the week.")
    checks.append(check("nli: a fact at the end of a long premise is still read", judged["label"] == "contradiction" and judged["windows"] > 1, json.dumps(judged)))
    labels = multilingual.nli()[2]
    checks.append(check("nli: labels read by name", set(labels.values()) == {"entailment", "neutral", "contradiction"}, str(labels)))
    return {"reader": "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", "results": results, "checks": checks, "seconds": {"load": load, "pairs": round(time.perf_counter() - started, 2)}}


RUNNERS = {"ocr": run_ocr, "speech": run_speech, "vision": run_vision, "retrieval": run_retrieval, "nli": run_nli}


def child(name: str) -> None:
    samples = json.loads((SAMPLES / "samples.json").read_text(encoding="utf-8"))
    out = RUNNERS[name](samples)
    out["peak_mb"] = peak_mb()
    print("RESULT:" + json.dumps(out, ensure_ascii=False))


def offline_env() -> dict:
    env = dict(os.environ)
    env.update({"HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1", "HF_HUB_DISABLE_TELEMETRY": "1", "OMP_NUM_THREADS": "4",
                "HTTP_PROXY": DEAD_PROXY, "HTTPS_PROXY": DEAD_PROXY, "ALL_PROXY": DEAD_PROXY, "NO_PROXY": "127.0.0.1,localhost",
                "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8"})
    return env


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--child")
    parser.add_argument("--only", default=",".join(COMPONENTS))
    parser.add_argument("--report-dir")
    parser.add_argument("--keep-samples", action="store_true", help="reuse runtime/media-smoke instead of drawing it again")
    args = parser.parse_args()
    if args.child:
        child(args.child)
        return
    if not (args.keep_samples and (SAMPLES / "samples.json").is_file()):
        print("Making samples in", SAMPLES)
        make_samples()
    samples = json.loads((SAMPLES / "samples.json").read_text(encoding="utf-8"))
    previous = json.loads(RESULT.read_text(encoding="utf-8")) if RESULT.is_file() else {}
    components = dict(previous.get("components", {}))
    for name in [n for n in args.only.split(",") if n]:
        started = time.perf_counter()
        done = subprocess.run([sys.executable, __file__, "--child", name], capture_output=True, text=True, encoding="utf-8", env=offline_env(), timeout=1800)
        line = next((l for l in done.stdout.splitlines() if l.startswith("RESULT:")), None)
        if line is None:
            components[name] = {"passed": False, "error": (done.stderr or done.stdout)[-2000:], "wall_seconds": round(time.perf_counter() - started, 1)}
            print(f"{name}: FAILED to run\n{components[name]['error'][-800:]}")
            continue
        out = json.loads(line[7:])
        passed = sum(c["passed"] for c in out["checks"])
        out.update({"checks": len(out["checks"]), "passed_checks": passed, "check_list": out["checks"], "passed": passed == len(out["checks"]), "wall_seconds": round(time.perf_counter() - started, 1)})
        components[name] = out
        print(f"{name}: {passed}/{out['checks']} checks, peak {out.get('peak_mb')} MB{', server ' + str(out['server_peak_mb']) + ' MB' if out.get('server_peak_mb') else ''}, {out['wall_seconds']} s")
        for c in out["check_list"]:
            if not c["passed"]:
                print("   not passed:", c["check"], "|", c["detail"][:300])
    result = {
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"), "network": "cut off (dead proxy; models from local files only)",
        "machine": {"system": platform.platform(), "processor": platform.processor(), "ram_gb": ram_gb(), "python": platform.python_version()},
        "samples": {k: (Path(v).name if isinstance(v, str) and os.sep in v else v) for k, v in samples.items()},
        "note": "Synthetic samples with known content and checks written for them: they show each reader runs offline and reads what it should, not its accuracy on real media.",
        "components": components,
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    if args.report_dir:
        shutil.copy(RESULT, Path(args.report_dir) / f"MEDIA_PILOT_{datetime.now():%Y%m%d}.json")
    print("Written", RESULT)


if __name__ == "__main__":
    main()

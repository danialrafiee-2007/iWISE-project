"""Text in images with Tesseract 5 (tesserocr, which carries the engine) and the tessdata_fast models, locally.

Never every model at once and never a fixed "eng+fas": the image is split into text blocks, Tesseract's orientation and
script detection (OSD) names each block's writing system, and only the few languages written in that script (SCRIPTS,
at most MAX_TRIES, the person's own choice first) are tried; the one Tesseract reads with the highest confidence wins and
the runners-up are kept. OSD names the script, not the language, so when two languages of one script read almost
equally well (Arabic and Persian, say) the reading goes to review instead of guessing; Latin-script text gets a small
function-word check (latin_language) for the same reason. A page turned on its side is read upright and every box is
mapped back to the original image.
"""

import re
import threading
import time
import unicodedata
from collections import Counter
from pathlib import Path

from truth_guardian.media import models_dir
from truth_guardian.media.contract import LOW_TEXT, Alternative, Place, Reading, Segment, bcp47

MAX_TRIES = 3
CLOSE = 5.0  # mean-confidence points (0-100) under which two languages count as a tie
MIN_BLOCK = 12  # pixels; smaller blocks are specks
MIN_CHARACTERS = "5"  # OSD gives up below 50 characters by default, which leaves short signs and captions unread
SCRIPT_SURE = 1.0  # OSD script confidence below which the script is checked by reading (sweep)
ORIENT_SURE = 1.0  # OSD orientation confidence needed before an image is turned
TARGET_LINE = 20.0  # pixels per text line that Tesseract reads best at (see best_scale)
MIN_SCALE, MAX_SCALE = 0.2, 3.0
PAD = 10  # pixels of margin around each block crop
# Scripts tried by reading when OSD is unsure: OSD has called Ethiopic text Cyrillic, and gives Japanese a low score.
SWEEP = ["Latin", "Arabic", "Cyrillic", "Ethiopic", "Japanese", "HanS", "Hangul", "Devanagari", "Greek", "Hebrew", "Thai"]

# Tesseract OSD script name -> the languages tried for it, most used first.
SCRIPTS = {
    "Latin": ["eng"],
    "Arabic": ["ara", "fas", "urd"],
    "Japanese": ["jpn"],
    "Katakana": ["jpn"],
    "Hiragana": ["jpn"],
    "Han": ["chi_sim", "chi_tra", "jpn"],
    "HanS": ["chi_sim"],
    "HanT": ["chi_tra"],
    "Korean": ["kor"],
    "Hangul": ["kor"],
    "Cyrillic": ["rus", "ukr", "bul"],
    "Greek": ["ell"],
    "Hebrew": ["heb", "yid"],
    "Ethiopic": ["amh", "tir"],
    "Devanagari": ["hin", "mar", "nep"],
    "Bengali": ["ben", "asm"],
    "Tamil": ["tam"],
    "Telugu": ["tel"],
    "Kannada": ["kan"],
    "Malayalam": ["mal"],
    "Gujarati": ["guj"],
    "Gurmukhi": ["pan"],
    "Oriya": ["ori"],
    "Thai": ["tha"],
    "Lao": ["lao"],
    "Khmer": ["khm"],
    "Myanmar": ["mya"],
    "Georgian": ["kat"],
    "Armenian": ["hye"],
    "Tibetan": ["bod"],
    "Sinhala": ["sin"],
    "Fraktur": ["deu_latf"],
}
VERTICAL = {"jpn": "jpn_vert", "chi_sim": "chi_sim_vert", "chi_tra": "chi_tra_vert", "kor": "kor_vert"}

# A few function words per Latin-script language: enough to avoid calling Swahili or Yoruba English, not a language model.
FUNCTION_WORDS = {
    "eng": "the and of to in is that for with on are was this it as be by",
    "fra": "le la les et des est une un du que pour dans pas sur au avec",
    "spa": "el la los las de que y en un una es por con para del se",
    "deu": "der die das und ist nicht ein eine zu den mit von sich auf",
    "ita": "il la di che e un una per non sono con del della gli le",
    "por": "o a os de que e um uma para com não do da em no na",
    "nld": "de het een en van is dat niet op te zijn met voor",
    "swa": "na ya wa kwa ni katika la za hii cha kuwa yake au pia",
    "yor": "ati ni ti si ko o mo won fun pelu je wa naa yii",
    "afr": "die en van het nie is dat op te in vir met word",
    "tur": "ve bir bu da de için ile çok ne ama daha olan gibi",
    # Arabic script: Persian, Arabic and Urdu share letters, and their models read each other's text almost equally well.
    "fas": "است در به از که این را با برای می آن یک ها شود بود شد هم تا",
    "ara": "في من على هي هو التي الذي إلى عن أن ما لا مع هذا هذه كان كانت ذلك",
    "urd": "ہے کے کی میں اور سے کو یہ ہیں نہیں تھا ایک پر",
}
# Scripts shared by several languages, whose language is told from the words read.
SHARED_SCRIPTS = {"Latin": ["eng", "fra", "spa", "deu", "ita", "por", "nld", "swa", "yor", "afr", "tur"], "Arabic": ["fas", "ara", "urd"]}
OWN_LETTERS = {"fas": "پچژگ", "urd": "ٹڈڑںے"}  # letters the other Arabic-script languages here do not write
LOOKALIKE = {"Cyrillic": "Latin", "Latin": "Cyrillic", "Greek": "Latin"}  # scripts OSD confuses, checked by reading
# Unicode's name for a letter's script (the first word of the character's name) to the script models' names.
WRITTEN = {"LATIN": "Latin", "ARABIC": "Arabic", "CYRILLIC": "Cyrillic", "ETHIOPIC": "Ethiopic", "HIRAGANA": "Japanese", "KATAKANA": "Japanese",
           "HANGUL": "Hangul", "DEVANAGARI": "Devanagari", "GREEK": "Greek", "HEBREW": "Hebrew", "THAI": "Thai"}
NEAR = 0.9  # a script model scoring this share of the best one or more reads the text about as well
BLOCK_MODE = 6  # Tesseract page segmentation: one uniform block of text
WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
# Tesseract puts a space between Chinese and Japanese characters, which those languages do not use (Korean does).
CJK = "　-〿぀-ヿ㐀-䶿一-鿿＀-￯"
CJK_GAP = re.compile(f"(?<=[{CJK}])\\s+(?=[{CJK}])")
UNSPACED = {"jpn", "jpn_vert", "chi_sim", "chi_sim_vert", "chi_tra", "chi_tra_vert", "script/Japanese", "script/Japanese_vert", "script/HanS", "script/HanT"}

_lock = threading.Lock()


def tessdata() -> Path:
    return models_dir() / "tessdata_fast"


def reader_name() -> str:
    import tesserocr

    return f"Tesseract {tesserocr.tesseract_version().split()[1]} (tesserocr {tesserocr.__version__}), tessdata_fast"


def available(code: str) -> bool:
    return (tessdata() / f"{code}.traineddata").is_file()


def tesseract_codes(languages: list[str]) -> list[str]:
    """BCP 47 codes (fa, ja, zh-Hans) to the Tesseract models that read them; Tesseract codes pass through."""
    from truth_guardian.media.contract import BCP47

    out = []
    for code in languages:
        if available(code):
            out.append(code)
            continue
        out += [t for t, b in BCP47.items() if b == code and not t.endswith("_vert") and available(t)][:1]
    return out


def latin_language(text: str) -> tuple[str | None, float]:
    return function_language(text, SHARED_SCRIPTS["Latin"])


def shared_language(script: str, readings: dict[str, str], best_text: str) -> tuple[str | None, float]:
    """The language of text in a script several languages share. Latin goes by function words. In Arabic script each
    model's own reading is weighed: its function words, plus letters only that language writes, which only its model
    produces (the Persian model writes پ where the Arabic one writes ي). None when the evidence is too thin or tied."""
    if script == "Latin":
        return function_language(best_text, SHARED_SCRIPTS["Latin"])
    scores = {}
    for code in SHARED_SCRIPTS[script]:
        own = readings.get(code, best_text)
        hits = sum(w.lower() in set(FUNCTION_WORDS[code].split()) for w in WORD.findall(own))
        scores[code] = hits + 2 * min(3, sum(own.count(letter) for letter in OWN_LETTERS.get(code, "")))
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    (best, top), (_, second) = ranked[0], ranked[1]
    if top < 2 or top == second:
        return None, 0.0
    return best, round(min(1.0, top / max(1, len(WORD.findall(readings.get(best, best_text))))), 3)


def function_language(text: str, codes: list[str]) -> tuple[str | None, float]:
    """Of `codes`, the language whose function words appear most, with the share of words that matched; None when too
    few words match or two languages tie."""
    words = [w.lower() for w in WORD.findall(text)]
    if len(words) < 4:
        return None, 0.0
    counts = {code: sum(w in set(FUNCTION_WORDS[code].split()) for w in words) for code in codes if code in FUNCTION_WORDS}
    ranked = sorted(counts.items(), key=lambda kv: kv[1], reverse=True)
    (best, hits), (_, second) = ranked[0], ranked[1]
    if hits < 2 or hits == second:
        return None, 0.0
    return best, round(hits / len(words), 3)


def candidates(script: str | None, hint: list[str], tall: bool) -> list[str]:
    """Languages to try for a block: the person's own choice first, then those written in the detected script."""
    tries = [c for c in hint if available(c)]
    for code in SCRIPTS.get(script or "", []):
        if tall and code in VERTICAL and available(VERTICAL[code]):
            tries.append(VERTICAL[code])
        if available(code):
            tries.append(code)
    if not tries and script and (tessdata() / "script" / f"{script}.traineddata").is_file():
        tries.append(f"script/{script}")
    return list(dict.fromkeys(tries))[:MAX_TRIES] or ["eng"]


def unrotate(box: tuple[int, int, int, int], angle: int, size: tuple[int, int]) -> tuple[int, int, int, int]:
    """A box (x, y, w, h) found in the image turned `angle` degrees counter-clockwise, in the original image's pixels.
    `size` is the original (width, height)."""
    x, y, w, h = box
    width, height = size
    if angle == 90:  # turned left: the original x runs down the rotated image from the bottom
        return width - (y + h), x, h, w
    if angle == 180:
        return width - (x + w), height - (y + h), w, h
    if angle == 270:
        return y, height - (x + w), h, w
    return box


def _osd(api, image) -> dict | None:
    from tesserocr import PSM

    api.SetPageSegMode(PSM.OSD_ONLY)
    api.SetImage(image)
    try:
        found = api.DetectOrientationScript()
    except RuntimeError:
        return None
    return found or None


def _read(path: str, lang: str, image, psm=None) -> tuple[list[tuple[str, float, tuple[int, int, int, int]]], float]:
    """Text lines (text, confidence 0-1, box) of one block in one language, and Tesseract's mean confidence (0-100)."""
    from tesserocr import PSM, RIL, PyTessBaseAPI, iterate_level

    with PyTessBaseAPI(path=path, lang=lang, psm=BLOCK_MODE if psm is None else psm) as api:
        api.SetImage(image)
        api.Recognize()
        # The page text is in reading order; tesserocr's line iterator gives Arabic-script lines left to right, letters
        # reversed. So the text comes from the page, and only each line's box and confidence from the iterator.
        ordered = [t.strip() for t in api.GetUTF8Text().split("\n") if t.strip()]
        found = []
        for line in iterate_level(api.GetIterator(), RIL.TEXTLINE):
            try:
                visual = (line.GetUTF8Text(RIL.TEXTLINE) or "").strip()
            except RuntimeError:  # tesserocr raises instead of returning "" for an empty line
                continue
            if visual:
                x1, y1, x2, y2 = line.BoundingBox(RIL.TEXTLINE)
                found.append((visual, round(line.Confidence(RIL.TEXTLINE) / 100, 3), (x1, y1, x2 - x1, y2 - y1)))
        texts = ordered if len(ordered) == len(found) else [visual for visual, _, _ in found]
        lines = [((CJK_GAP.sub("", text) if lang in UNSPACED else text), confidence, box) for text, (_, confidence, box) in zip(texts, found)]
        return lines, float(api.MeanTextConf())


def line_height(image) -> float | None:
    """Median height of the text lines Tesseract's layout analysis finds, in pixels."""
    from tesserocr import PSM, RIL, PyTessBaseAPI

    with PyTessBaseAPI(path=str(tessdata()) + "/", lang="eng", psm=PSM.AUTO) as layout:
        layout.SetImage(image)
        heights = sorted(b[1]["h"] for b in layout.GetComponentImages(RIL.TEXTLINE, True) or [])
    return float(heights[len(heights) // 2]) if heights else None


def best_scale(path: str, image, lang: str) -> tuple[float, "object"]:
    """The image as it is, or resized so its text lines are about TARGET_LINE pixels tall, whichever Tesseract reads
    more of with more confidence (characters read times their confidence). Lines far taller than Tesseract was trained
    on lose whole lines: a Persian sample at 46 px read one line of two at full size and both at half size."""
    from tesserocr import PSM, PyTessBaseAPI

    height = line_height(image)
    sizes = [1.0]
    if height:
        ratio = min(MAX_SCALE, max(MIN_SCALE, TARGET_LINE / height))
        if abs(ratio - 1.0) > 0.25:
            sizes.append(round(ratio, 3))
    best = (-1.0, 1.0, image)
    for size in sizes:
        resized = image if size == 1.0 else image.resize((max(1, round(image.width * size)), max(1, round(image.height * size))), resample=3)  # LANCZOS
        score = _score(path, lang, resized)
        if score > best[0]:
            best = (score, size, resized)
    return best[1], best[2]


def _scored(path: str, lang: str, image) -> tuple[float, str]:
    """How much text a model reads with confidence (characters read times their confidence), and the words it read. The
    mean confidence alone flatters a wrong model that reads a few characters of noise confidently (a Japanese model on
    Amharic did)."""
    from tesserocr import PSM, PyTessBaseAPI

    with PyTessBaseAPI(path=path, lang=lang, psm=PSM.AUTO) as api:
        api.SetImage(image)
        api.Recognize()
        words = [(w.strip(), c) for w, c in api.MapWordConfidences() if w and w.strip()]
    return sum(len(w) * c / 100 for w, c in words), " ".join(w for w, _ in words)


def _score(path: str, lang: str, image) -> float:
    return _scored(path, lang, image)[0]


def written_script(text: str) -> str | None:
    """The script most letters of `text` are written in, by their Unicode names; None without letters it knows."""
    counts = Counter(WRITTEN.get(unicodedata.name(ch, "").split(" ")[0]) for ch in text if ch.isalpha())
    counts.pop(None, None)
    return counts.most_common(1)[0][0] if counts else None


def sweep(path: str, image, detected: str | None) -> str | None:
    """The script whose Tesseract script model reads the most text with confidence (_score), OSD's own guess first.
    Several script models also carry Latin letters: the Hebrew, Devanagari, Hangul, Arabic and Thai ones read a frame
    saying "FIRST SLIDE ONE" exactly as well as the Latin one, and the Hebrew language model then read it as Hebrew. So
    among the models that read about as well as the best (NEAR), the script of the letters actually read wins."""
    order = list(dict.fromkeys(([detected] if detected else []) + SWEEP))
    scored = {s: _scored(path, f"script/{s}", image) for s in order if (tessdata() / "script" / f"{s}.traineddata").is_file()}
    if not scored or max(score for score, _ in scored.values()) <= 0:
        return None
    best = max(scored, key=lambda s: scored[s][0])
    written = written_script(scored[best][1])
    if written and written != best and written in scored and scored[written][0] >= NEAR * scored[best][0]:
        return written
    return best


def read_text(image_or_path, languages: list[str] | None = None) -> Reading:
    """Reads the text in an image. `languages` are the languages the person says the image may use (BCP 47 such as fa,
    ja, am, or Tesseract codes), tried first; without them the script decides."""
    from PIL import Image
    from tesserocr import PSM, RIL, PyTessBaseAPI

    started = time.perf_counter()
    original = image_or_path if isinstance(image_or_path, Image.Image) else Image.open(image_or_path)
    original = original.convert("RGB")
    hint = tesseract_codes(list(languages or []))
    path = str(tessdata()) + "/"
    reading = Reading(kind="image", reader=reader_name())
    with _lock, PyTessBaseAPI(path=path, lang="osd") as osd_api:
        osd_api.SetVariable("min_characters_to_try", MIN_CHARACTERS)
        page = _osd(osd_api, original)
        angle = 0
        if page and page.get("orient_deg") in (90, 180, 270) and page.get("orient_conf", 0) >= ORIENT_SURE:
            angle = int(page["orient_deg"])
            reading.notes.append(f"the image is turned {angle} degrees; it was read upright")
        upright = original.rotate(angle, expand=True) if angle else original
        page_script = (page or {}).get("script_name")
        if not hint and (page_script is None or (page or {}).get("script_conf", 0) < SCRIPT_SURE):
            swept = sweep(path, upright, page_script)
            if swept and swept != page_script:
                reading.notes.append(f"the script detector said {page_script or 'nothing'}; reading the text, {swept} fits best")
            page_script = swept or page_script
        elif not hint and page_script in LOOKALIKE:
            # Capital Latin, Cyrillic and Greek letters look alike, and OSD has read "TRUTH GUARDIAN" as Cyrillic.
            rival = LOOKALIKE[page_script]
            mine, theirs = (_score(path, candidates(s, [], False)[0], upright) for s in (page_script, rival))
            if theirs > mine:
                reading.notes.append(f"the script detector said {page_script}; reading the text, {rival} fits best")
                page_script = rival
        scale, work = best_scale(path, upright, candidates(page_script, hint, tall=False)[0])
        if scale != 1.0:
            reading.notes.append(f"the image was read at {scale:.2f} times its size, where the text reads best")
        with PyTessBaseAPI(path=path, lang="eng", psm=PSM.AUTO) as layout:
            layout.SetImage(work)
            boxes = [b[1] for b in layout.GetComponentImages(RIL.BLOCK, True) or []]
        boxes = [b for b in boxes if b["w"] >= MIN_BLOCK and b["h"] >= MIN_BLOCK] or [{"x": 0, "y": 0, "w": work.width, "h": work.height}]
        weights, scores, choices = 0, 0.0, {}
        for box in boxes:
            # A crop of the colour image with a margin, not Tesseract's thresholded block, which can lose a line.
            x0, y0 = max(0, box["x"] - PAD), max(0, box["y"] - PAD)
            block_image = work.crop((x0, y0, min(work.width, box["x"] + box["w"] + PAD), min(work.height, box["y"] + box["h"] + PAD)))
            box = {"x": x0, "y": y0, "w": block_image.width, "h": block_image.height}
            # The page's script holds unless a block is clearly in another one (a mixed page): OSD on a small crop
            # guesses, and a wrong guess reads Arabic script with a left-to-right model, letters reversed.
            found = _osd(osd_api, block_image) or {}
            script = page_script
            other = found.get("script_name")
            if len(boxes) > 1 and other and other != page_script and found.get("script_conf", 0) >= SCRIPT_SURE:
                tall = box["h"] > 1.5 * box["w"]
                here, there = candidates(page_script, hint, tall)[0], candidates(other, hint, tall)[0]
                if _score(path, there, block_image) > 1.2 * _score(path, here, block_image):  # checked by reading, not taken on trust
                    script = other
                    reading.notes.append(f"a block is in {script} script, unlike the rest of the image")
            tried = []
            for lang in candidates(script, hint, tall=box["h"] > 1.5 * box["w"]):
                lines, mean = _read(path, lang, block_image)
                tried.append((mean, lang, lines))
            tried.sort(key=lambda t: t[0], reverse=True)
            mean, lang, lines = tried[0]
            if not lines:
                continue
            text = " ".join(t for t, _, _ in lines)
            language, language_confidence = (bcp47(lang) if not lang.startswith("script/") else None), round(mean / 100, 3)
            by_words = False
            if script in SHARED_SCRIPTS and not hint:
                # Several languages share this script and their models read each other's text almost equally well
                # (the Arabic model read Persian at 90 against the Persian model's 86, writing پ as ي): the words decide.
                guess, share = shared_language(script, {c: " ".join(t for t, _, _ in l) for _, c, l in tried}, text)
                language, language_confidence, by_words = (bcp47(guess), share, True) if guess else (None, None, False)
                if not guess:  # too few words to tell: the best-reading model's language stays a possibility, not a verdict
                    choices[lang] = max(choices.get(lang, 0.0), round(mean / 100, 3))
                if guess and guess != lang and available(guess):
                    better, better_mean = next(((l, m) for m, c, l in tried if c == guess), None) or _read(path, guess, block_image)
                    if better and better_mean >= mean - 2 * CLOSE:
                        lines, mean, lang = better, better_mean, guess
                        text = " ".join(t for t, _, _ in lines)
            if not by_words and len(tried) > 1 and tried[0][0] - tried[1][0] < CLOSE:
                reading.review(f"{script} text reads almost as well as {tried[0][1]} and {tried[1][1]}; the language is uncertain")
            if language is None:
                reading.review(f"the language of the {script or 'unknown'} text could not be told from the image")
            if script is None:
                reading.review("the writing system could not be detected")
            for alt_mean, alt_lang, _ in tried[1:]:
                choices[alt_lang] = max(choices.get(alt_lang, 0.0), round(alt_mean / 100, 3))
            for line_text, confidence, (x, y, w, h) in lines:
                unscaled = tuple(round(v / scale) for v in (box["x"] + x, box["y"] + y, w, h))
                placed = unrotate(unscaled, angle, original.size)
                reading.segments.append(
                    Segment(text=line_text, role="ocr", language=language, language_confidence=language_confidence, script=script, confidence=confidence, place=Place(box=placed))
                )
            chars = len(text)
            weights += chars
            scores += mean / 100 * chars
    reading.alternatives = [Alternative(language=bcp47(code), confidence=c) for code, c in sorted(choices.items(), key=lambda kv: -kv[1])]
    if not reading.segments:
        reading.review("no text was found")
    else:
        languages_found = [s.language for s in reading.segments if s.language]
        if languages_found:
            reading.language = max(set(languages_found), key=languages_found.count)
            reading.language_confidence = max(s.language_confidence or 0 for s in reading.segments if s.language == reading.language)
        reading.quality = round(scores / weights, 3) if weights else None
        if reading.quality is not None and reading.quality < LOW_TEXT:
            reading.review(f"the text is hard to read (mean confidence {reading.quality:.2f})")
    reading.seconds = round(time.perf_counter() - started, 2)
    return reading

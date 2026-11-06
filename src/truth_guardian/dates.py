"""Days of the week and months read alike in the project's seven languages, as numbers are (multicheck.numbers).

A Persian answer over English documents said "شنبه" (Saturday) for "Sunday" (D-170), and the light check, which reads
only numbers and closeness, could not see it. Weekdays and months are closed lists, so each name becomes a key ("day6"
for Sunday, "month3" for March) whatever the language, and a sentence naming a key that no passage names is doubtful.
Names that are also common words are read only beside a number ("May 2020", "۵ مه") or not at all (Russian "среда",
also "environment"). Persian's own solar months have no fixed Gregorian month, so they are left out.
"""

import re

_DAYS = {
    0: ["monday", "lunes", "lundi", "понедельник", "الاثنين", "الإثنين", "دوشنبه", "星期一", "周一", "礼拜一"],
    1: ["tuesday", "martes", "mardi", "вторник", "الثلاثاء", "سه‌شنبه", "سه شنبه", "سهشنبه", "星期二", "周二", "礼拜二"],
    2: ["wednesday", "miércoles", "miercoles", "mercredi", "в среду", "по средам", "الأربعاء", "الاربعاء", "چهارشنبه", "چهار شنبه", "چهار‌شنبه", "星期三", "周三", "礼拜三"],
    3: ["thursday", "jueves", "jeudi", "четверг", "الخميس", "پنجشنبه", "پنج‌شنبه", "پنج شنبه", "星期四", "周四", "礼拜四"],
    4: ["friday", "viernes", "vendredi", "пятниц", "الجمعة", "جمعه", "星期五", "周五", "礼拜五"],
    5: ["saturday", "sábado", "sabado", "samedi", "суббот", "السبت", "شنبه", "星期六", "周六", "礼拜六"],
    6: ["sunday", "domingo", "dimanche", "воскресень", "الأحد", "الاحد", "یکشنبه", "یک‌شنبه", "یک شنبه", "星期日", "星期天", "周日", "礼拜天", "礼拜日"],
}
_MONTHS = {
    1: ["January", "enero", "janvier", "январ", "يناير", "كانون الثاني", "ژانویه"],
    2: ["February", "febrero", "février", "fevrier", "феврал", "فبراير", "شباط", "فوریه"],
    3: ["March", "marzo", "mars", "март", "مارس", "آذار"],
    4: ["April", "abril", "avril", "апрел", "أبريل", "ابريل", "نيسان", "آوریل"],
    5: ["mayo", "mai", "مايو", "أيار", "ايار"],
    6: ["June", "junio", "juin", "июн", "يونيو", "يونيه", "حزيران", "ژوئن"],
    7: ["July", "julio", "juillet", "июл", "يوليو", "يوليه", "تموز", "ژوئیه", "جولای"],
    8: ["August", "agosto", "août", "aout", "август", "أغسطس", "اغسطس", "آب", "اوت", "آگوست"],
    9: ["September", "septiembre", "setiembre", "septembre", "сентябр", "سبتمبر", "أيلول", "ايلول", "سپتامبر"],
    10: ["October", "octubre", "octobre", "октябр", "أكتوبر", "اكتوبر", "تشرين الأول", "اکتبر"],
    11: ["November", "noviembre", "novembre", "ноябр", "نوفمبر", "تشرين الثاني", "نوامبر"],
    12: ["December", "diciembre", "décembre", "decembre", "декабр", "ديسمبر", "كانون الأول", "دسامبر"],
}
# Common words too, so read only next to a number.
_BESIDE_A_NUMBER = {5: ["May", "мая", "май", "мае", "مه", "می"]}
_STEMS = ("январ", "феврал", "апрел", "июн", "июл", "сентябр", "октябр", "ноябр", "декабр", "пятниц", "суббот", "воскресень", "понедельник", "вторник", "четверг")
_CASED = {name for names in _MONTHS.values() for name in names if name[0].isupper()}
_HAN_MONTH = re.compile(r"(?<![0-9一二三四五六七八九十])(1[0-2]|[1-9]|十[一二]?|[一二三四五六七八九])月")
_HAN_VALUE = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10, "十一": 11, "十二": 12}
_NUMBER = r"[0-9٠-٩۰-۹]+"


def _pattern(name: str, beside_number: bool = False) -> re.Pattern:
    body = re.escape(name).replace(r"\ ", r"[\s‌]*")
    if any("一" <= c <= "鿿" for c in name):
        return re.compile(body)
    tail = r"\w*" if name in _STEMS else r"(?:s|es)?" if name.isascii() else r"(?:\u200c\w+)?"
    core = rf"(?<![\w‌]){body}{tail}(?![\w‌])"
    if beside_number:
        core = rf"(?:{_NUMBER}\s*{core}|{core}\s*{_NUMBER})"
    return re.compile(core, 0 if name in _CASED or beside_number else re.IGNORECASE)


_PATTERNS = sorted(
    [(f"day{k}", name) for k, names in _DAYS.items() for name in names]
    + [(f"month{k}", name) for k, names in _MONTHS.items() for name in names],
    key=lambda pair: -len(pair[1]),
)
_COMPILED = [(key, _pattern(name)) for key, name in _PATTERNS]
_COMPILED += [(f"month{k}", _pattern(name, beside_number=True)) for k, names in _BESIDE_A_NUMBER.items() for name in names]


def calendar(text: str) -> set[str]:
    """The weekdays and months a text names, as language-free keys; a longer name is read before a shorter one inside it."""
    found = set()
    for m in _HAN_MONTH.finditer(text):
        found.add(f"month{int(m.group(1)) if m.group(1).isdigit() else _HAN_VALUE[m.group(1)]}")
    for key, pattern in _COMPILED:
        for m in pattern.finditer(text):
            found.add(key)
            text = text[: m.start()] + " " * (m.end() - m.start()) + text[m.end() :]
    return found

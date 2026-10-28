import pytest

from truth_guardian.language import detect, route

TEXTS = {
    "en": "The museum opened in 1950 and it is the oldest building in the town.",
    "es": "El museo se abrió en 1950 y es el edificio más antiguo de la ciudad.",
    "fr": "Le musée a ouvert en 1950 et il est le plus ancien bâtiment de la ville.",
    "ar": "افتتح المتحف في عام 1950 وهو أقدم مبنى في المدينة التي تقع على النهر.",
    "fa": "این موزه در سال ۱۳۲۹ باز شد و قدیمی‌ترین ساختمان شهر است که کنار رود قرار دارد.",
    "ru": "Музей открылся в 1950 году, и это самое старое здание в городе на реке.",
    "uk": "Музей відкрився у 1950 році, і це найстаріша будівля в місті на річці.",
    "zh": "博物馆于1950年开放，它是这座城市里最古老的建筑。",
    "ja": "博物館は1950年に開館し、町で一番古い建物です。",
}


@pytest.mark.parametrize("code", TEXTS)
def test_each_language_is_told_from_its_own_text(code):
    assert detect(TEXTS[code]).code == code


def test_a_number_or_a_name_has_no_language_of_its_own():
    assert detect("1950").code is None
    assert detect("Anne Frank").code is None


def test_english_over_english_goes_to_the_english_engine():
    r = route("It opened in 1950.", [TEXTS["en"]], "When did the museum open?")
    assert (r.check, r.answer, r.why_not) == ("english", "en", None)


def test_a_short_answer_takes_the_language_of_the_texts_around_it():
    assert route("1950", [TEXTS["es"]], "¿Cuándo se abrió el museo de la ciudad?").answer == "es"
    assert route("1950", [TEXTS["en"]]).check == "english"


@pytest.mark.parametrize("code", ["ar", "es", "fr", "ru", "zh"])
def test_the_other_interface_languages_go_to_the_multilingual_check(code):
    assert route(TEXTS[code], [TEXTS[code]]).check == "multilingual"


def test_an_answer_and_sources_in_different_checked_languages_are_checked_across_them():
    r = route(TEXTS["es"], [TEXTS["en"]])
    assert (r.check, r.answer, r.sources) == ("multilingual", "es", ["en"])


def test_persian_is_never_checked_neither_as_answer_nor_as_source():
    for answer, sources in [(TEXTS["fa"], [TEXTS["fa"]]), (TEXTS["fa"], [TEXTS["en"]]), (TEXTS["en"], [TEXTS["fa"]])]:
        r = route(answer, sources)
        assert (r.check, r.why_not) == (None, "language")


def test_a_language_outside_the_six_gets_no_verdict():
    r = route(TEXTS["uk"], [TEXTS["uk"]])
    assert (r.check, r.answer, r.why_not) == (None, "uk", "language")


def test_texts_without_letters_get_no_verdict():
    r = route("1950", ["1950"])
    assert (r.check, r.why_not) == (None, "unknown_language")


def test_short_latin_or_cyrillic_texts_are_taken_as_the_checked_language_of_their_script_and_say_so():
    r = route("Anne Frank died in 2022.", ["ANNE FRANK DIED IN 1945"])
    assert (r.check, r.answer, r.guessed) == ("english", "en", True)
    assert route("Умерла в 1944.", ["УМЕРЛА В 1945"])[:2] == ("multilingual", "ru")


def test_short_arabic_script_is_never_guessed_since_it_may_be_persian():
    assert route("کتاب ۱۹۴۵", ["کتاب"]).why_not in ("language", "unknown_language")
    assert route("مات ١٩٤٥", ["مات"]).check is None


def test_a_media_reader_language_decides_when_the_texts_cannot():
    assert route("1950", ["1950"], hint="zh-Hans")[:2] == ("multilingual", "zh")
    assert route("1950", ["1950"], hint="fa").why_not == "language"

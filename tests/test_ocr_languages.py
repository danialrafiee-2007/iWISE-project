"""How OCR tells the script and language of text it read: Unicode names, function words, and letters only one language writes."""

from truth_guardian.media import ocr


def test_the_script_is_the_one_most_letters_are_written_in():
    assert ocr.written_script("Привет мир") == "Cyrillic"
    assert ocr.written_script("سلام دنیا") == "Arabic"
    assert ocr.written_script("こんにちは") == "Japanese"
    assert ocr.written_script("Hello мир") == "Latin"
    assert ocr.written_script("12345 !?") is None


def test_the_language_is_the_one_whose_function_words_appear_most():
    assert ocr.function_language("the cat is on the mat and it is red", ["eng", "fra"]) == ("eng", 0.7)
    assert ocr.function_language("the cat sat", ["eng", "fra"]) == (None, 0.0)
    assert ocr.function_language("la la casa grande", ["fra", "spa"]) == (None, 0.0)
    assert ocr.function_language("cat dog bird fish", ["eng", "fra"]) == (None, 0.0)


def test_arabic_script_goes_by_each_models_own_reading_and_letters_only_its_language_writes():
    persian = "این کتاب را برای من است"
    assert ocr.shared_language("Arabic", {"fas": persian, "ara": "اين كتاب را براي من است"}, persian) == ("fas", 0.667)
    assert ocr.shared_language("Arabic", {"fas": "پچ", "ara": "پچ", "urd": "پچ"}, "پچ") == ("fas", 1.0)
    assert ocr.shared_language("Arabic", {}, "کتاب") == (None, 0.0)
    assert ocr.shared_language("Latin", {}, "the cat is on the mat and it is red") == ("eng", 0.7)


def test_spaces_between_chinese_and_japanese_characters_go_but_korean_and_latin_keep_theirs():
    assert ocr.CJK_GAP.sub("", "東京 は 大きい") == "東京は大きい"
    assert ocr.CJK_GAP.sub("", "서울 은 크다") == "서울 은 크다"
    assert ocr.CJK_GAP.sub("", "Tokyo 東京") == "Tokyo 東京"

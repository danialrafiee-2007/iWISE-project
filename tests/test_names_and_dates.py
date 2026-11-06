import pytest

from truth_guardian.dates import calendar
from truth_guardian.guardian import AgentGuardian
from truth_guardian.names import skeleton, written_in
from truth_guardian.schema import AgentStep

TASK = "موزه ریورساید چند کتاب دارد و در چه سالی باز شد؟"


@pytest.mark.parametrize("words", [("Riverside", "ریورساید", "Риверсайд"), ("Alder", "آلدر"), ("London", "لندن"), ("Moscow", "Москва"), ("Tehran", "تهران")])
def test_a_name_has_one_skeleton_in_latin_arabic_and_cyrillic_letters(words):
    assert len({skeleton(w) for w in words}) == 1


def test_a_name_the_question_writes_in_another_script_is_recognised():
    assert written_in("the Riverside Museum", TASK)
    assert written_in("Port Alder", "شهردار پورت آلدر کیست؟")
    assert not written_in("Paris", TASK)
    assert not written_in("Riverside Zorblat", TASK)
    assert not written_in("Riverside", "What is the Riverside Museum?")


def test_the_live_guardian_lets_a_thought_name_what_the_task_names_but_not_an_answer():
    guardian = AgentGuardian(TASK)
    thought = guardian.observe(AgentStep(step=0, kind="thought", content="I will search for the number of books in the Riverside Museum."))
    answer = guardian.observe(AgentStep(step=1, kind="answer", content="The Riverside Museum in Leeds has many books."))
    assert thought is None and answer is not None and "Leeds" in answer.reason


@pytest.mark.parametrize("text, keys", [
    ("The library is closed on Sundays.", {"day6"}),
    ("کتابخانه یکشنبه‌ها تعطیل است.", {"day6"}),
    ("کتابخانه شنبه‌ها تعطیل است.", {"day5"}),
    ("سه شنبه و پنج‌شنبه باز است", {"day1", "day3"}),
    ("La biblioteca cierra los domingos.", {"day6"}),
    ("Fermé le dimanche et en août.", {"day6", "month8"}),
    ("Закрыто по воскресеньям.", {"day6"}),
    ("المكتبة مغلقة يوم الأحد", {"day6"}),
    ("图书馆星期日闭馆，十二月和3月开放。", {"day6", "month12", "month3"}),
    ("We may go. It opened on 5 May 2020.", {"month5"}),
    ("They march in step.", set()),
])
def test_weekdays_and_months_are_read_alike_in_every_language(text, keys):
    assert calendar(text) == keys

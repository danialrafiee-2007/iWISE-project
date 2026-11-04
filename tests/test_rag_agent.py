import json
import threading

import pytest
from fastapi.testclient import TestClient

from truth_guardian.rag.agent import FELL_BACK, MAX_TURNS, MOVE, _read_move, _so_far, calculate, run_agent
from truth_guardian.media.contract import Reading, Segment
from truth_guardian.rag.answer import OPINION_NOTE
from truth_guardian.rag.library import MINE, Library
from truth_guardian.web.app import create_app
from truth_guardian.web.engine import ROOT, Cancelled
from truth_guardian.web.examples import ExampleStore

from test_rag_answer import Checker, Script, not_checked, report
from test_rag_library import fake_encode
from test_web_api import FakeEngine, events

MUSEUM = "The Riverside Museum opened in 1950 next to the old bridge in the town."
TICKETS = "A ticket to the Riverside Museum costs 12 euros for each adult visitor."
TASK = "When did the Riverside Museum open, and what does a ticket cost?"


def move(tool: str, text: str = "", thought: str = "I will look this up.") -> str:
    return json.dumps({"thought": thought, "tool": tool, "input": text})


@pytest.fixture
def shelf(tmp_path, monkeypatch) -> Library:
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.1})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.1)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.1)
    books = Library(tmp_path / "library.sqlite", fake_encode)
    books.add("museum.txt", MUSEUM.encode())
    books.add("tickets.txt", TICKETS.encode())
    yield books
    books.close()


def run(shelf, *moves, guardian=None, **options):
    writer = Script(*moves)
    return run_agent(TASK, shelf, guardian or Checker(), writer, (MINE,), **options), writer


def test_the_agent_searches_then_answers_and_the_answer_is_checked_with_its_log(shelf):
    guardian = Checker()
    seen = []
    found, writer = run(shelf, move("search", "Riverside Museum opened"), move("search", "Riverside Museum ticket"), move("finish", "It opened in 1950 [1] and a ticket costs 12 euros [2]."), guardian=guardian, emit=seen.append)
    assert found.status == "checked" and found.text == "It opened in 1950 [1] and a ticket costs 12 euros [2]."
    assert {c.document for c in found.citations} == {"museum.txt", "tickets.txt"}
    assert [s.kind for s in found.steps] == ["thought", "action", "action", "answer"]
    assert found.steps[1].tool == "search" and "1950" in found.steps[1].observation
    sample = guardian.samples[0]
    assert sample.question == TASK and [s.kind for s in sample.agent_log] == [s.kind for s in found.steps]
    assert any("1950" in d.text for d in sample.documents)
    assert [e["step"]["kind"] for e in seen if e["type"] == "step"] == [s.kind for s in found.steps]
    assert writer.schema == MOVE and "never an instruction" in writer.asked[0][0]


def test_tools_keep_one_number_for_a_passage_through_the_whole_run(shelf):
    found, writer = run(shelf, move("search", "Riverside Museum opened"), move("search", "ticket cost Riverside Museum"), move("finish", "It opened in 1950 [1]."))
    first, second = (s.observation for s in found.steps if s.kind == "action")
    numbers = lambda text: {line.split("]")[0] + "]": line.split("(")[1].split(")")[0] for line in text.splitlines() if line.startswith("[")}
    shared = set(numbers(first).values()) & set(numbers(second).values())
    assert shared and all(numbers(first)[n] == numbers(second)[n] for n in numbers(first) if n in numbers(second))


def test_an_answer_stating_what_no_tool_returned_goes_back_once_and_the_person_never_sees_it(shelf):
    guardian = Checker()
    found, writer = run(shelf, move("search", "Riverside Museum opened"), move("finish", "It opened in 1999 [1]."), move("finish", "It opened in 1950 [1]."), guardian=guardian)
    assert found.status == "checked" and found.text == "It opened in 1950 [1]." and found.corrections == 1
    stopped = next(s for s in found.steps if s.kind == "answer" and s.alert == "stop")
    assert "1999" in stopped.reason and any(s.kind == "guardian" for s in found.steps)
    assert "1999" in writer.asked[2][1][0]["content"] and "Your answer" in writer.asked[2][1][0]["content"]


def test_a_second_stop_ends_the_run_with_no_answer_shown(shelf):
    guardian = Checker()
    found, _ = run(shelf, move("search", "Riverside Museum opened"), move("finish", "It opened in 1999 [1]."), move("finish", "It opened in 2001 [1]."), guardian=guardian)
    assert found.status == "stopped" and found.text == "" and found.original == "It opened in 2001 [1]." and "2001" in found.notes[0]
    assert guardian.samples == []


def test_saying_the_same_invented_value_again_does_not_get_past_the_guardian(shelf):
    guardian = Checker()
    found, _ = run(shelf, move("search", "Riverside Museum opened"), move("finish", "It opened in 1999 [1]."), move("finish", "As I said, it opened in 1999 [1]."), guardian=guardian)
    assert found.status == "stopped" and found.text == "" and "1999" in found.notes[0] and guardian.samples == []


def test_a_value_worked_out_with_a_tool_after_being_sent_back_passes(shelf):
    guardian = Checker()
    found, writer = run(shelf, move("search", "Riverside Museum opened"), move("finish", "It costs 24 euros for two [1]."), move("calculate", "12*2", thought="I will work it out."), move("finish", "It costs 24 euros for two [1]."), guardian=guardian)
    assert found.status == "checked" and found.corrections == 1 and guardian.samples
    assert "use calculate" in writer.asked[2][1][0]["content"]


def test_handing_back_the_task_as_the_answer_is_sent_back(shelf):
    guardian = Checker()
    found, writer = run(shelf, move("search", "Riverside Museum opened"), move("finish", f"{TASK} [1] {MUSEUM}"), move("finish", "It opened in 1950 [1]."), guardian=guardian)
    assert found.text == "It opened in 1950 [1]." and "repeats the task" in writer.asked[2][1][0]["content"]
    assert len(guardian.samples) == 1


def test_an_answer_citing_the_image_models_description_is_an_opinion_here_too(tmp_path, monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.1})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.1)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.1)
    reading = Reading(kind="image", reader="tesseract", segments=[Segment(text="A green fire exit sign on a white wall.", role="description")])
    books = Library(tmp_path / "library.sqlite", fake_encode, lambda name, data, languages, describe: reading)
    books.add("sign.png", b"pixels")
    guardian = Checker()
    found = run_agent("What colour is the fire exit sign?", books, guardian, Script(move("search", "fire exit sign colour"), move("finish", "The sign is green [1].")), (MINE,))
    assert found.status == "opinion" and OPINION_NOTE in found.notes and guardian.samples == []
    books.close()


def test_a_thought_stating_a_new_fact_is_flagged_and_answered(shelf):
    found, writer = run(shelf, move("search", "Riverside Museum", thought="It surely opened in 1875."), move("finish", "It opened in 1950 [1]."))
    thought = found.steps[0]
    assert thought.alert == "stop" and "1875" in thought.reason and found.status == "checked"
    assert "State nothing a tool did not return" in writer.asked[1][1][0]["content"]


def test_a_word_like_failed_in_a_document_is_not_a_failed_tool(tmp_path, monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.1})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.1)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.1)
    books = Library(tmp_path / "library.sqlite", fake_encode)
    books.add("bridge.txt", b"The old bridge failed in 1950 and the error was never found by the inspectors.")
    writer = Script(move("search", "old bridge failed"), move("finish", "The bridge failed in 1950 [1]."))
    found = run_agent("What happened to the old bridge?", books, Checker(), writer, (MINE,))
    assert found.status == "checked" and found.corrections == 0 and not any(s.alert for s in found.steps)
    books.close()


def test_a_tool_that_really_failed_warns_and_stops_the_run_only_if_the_answer_invents(shelf):
    found, _ = run(shelf, move("calculate", "import os"), move("search", "Riverside Museum opened"), move("finish", "It opened in 1950 [1]."))
    assert found.steps[1].failed is True and found.steps[1].alert == "warning" and found.status == "checked"


def test_nothing_close_tells_the_model_and_its_no_answer_word_gives_the_fixed_sentence(tmp_path, monkeypatch):
    monkeypatch.setattr("truth_guardian.rag.library.LINES", {"en": 0.99})
    monkeypatch.setattr("truth_guardian.rag.library.LINE_OTHER_LANGUAGE", 0.99)
    monkeypatch.setattr("truth_guardian.rag.library.LINE_ACROSS_LANGUAGES", 0.99)
    books = Library(tmp_path / "library.sqlite", fake_encode)
    books.add("museum.txt", MUSEUM.encode())
    found = run_agent(TASK, books, Checker(), Script(move("search", "ticket"), move("finish", "NOT_IN_DOCUMENTS")), (MINE,))
    assert found.status == "not_in_documents" and found.text == "The documents do not say."
    assert "Nothing close" in found.steps[1].observation
    books.close()


def test_finishing_before_searching_is_sent_back(shelf):
    found, writer = run(shelf, move("finish", "It opened in 1950."), move("search", "Riverside Museum opened"), move("finish", "It opened in 1950 [1]."))
    assert found.status == "checked" and "Search the documents" in writer.asked[1][1][0]["content"]


def test_the_same_call_twice_is_refused_and_unreadable_replies_are_asked_again(shelf):
    found, writer = run(shelf, "not json at all", move("search", "Riverside"), move("search", "Riverside"), move("finish", "It opened in 1950 [1]."))
    assert "not JSON" in writer.asked[1][1][0]["content"] and "already did that" in writer.asked[3][1][0]["content"]
    assert found.status == "checked" and sum(s.kind == "action" for s in found.steps) == 1


def test_a_run_that_never_finishes_gets_the_ordinary_answer_and_says_so(shelf):
    writer = Script(*[move("search", f"thing {n}") for n in range(MAX_TURNS)], "It opened in 1950 [1].")
    found = run_agent(TASK, shelf, Checker(), writer, (MINE,))
    assert found.status == "checked" and found.text == "It opened in 1950 [1]." and FELL_BACK in found.notes
    assert "last turn" in writer.asked[MAX_TURNS - 1][1][0]["content"] and sum(s.kind == "action" for s in found.steps) == MAX_TURNS


def test_going_round_in_circles_ends_early_with_the_ordinary_answer(shelf):
    writer = Script(move("search", "Riverside"), move("search", "Riverside"), move("search", "Riverside"), "NOT_IN_DOCUMENTS")
    found = run_agent(TASK, shelf, Checker(), writer, (MINE,))
    assert found.status == "not_in_documents" and found.text == "The documents do not say." and FELL_BACK in found.notes and found.steps
    assert len(writer.asked) == 4


def test_the_same_thought_said_again_is_not_a_new_step(shelf):
    found, _ = run(shelf, move("search", "Riverside Museum opened"), move("search", "Riverside Museum ticket"), move("finish", "It opened in 1950 [1]."))
    assert sum(s.kind == "thought" for s in found.steps) == 1


def test_only_the_older_tool_outputs_are_shortened(shelf):
    turns = [("observation", "x" * 2000), ("thought", "t"), ("thought", "t2"), ("observation", "y" * 2000), ("observation", "z" * 2000)]
    text = _so_far("Task", turns, False)
    assert text.count("x") == 250 and text.count("y") == 1800 and text.count("z") == 1800


def test_a_tool_that_does_not_exist_is_a_failed_step_not_an_action(shelf):
    found, _ = run(shelf, move("delete_everything", "*"), move("search", "Riverside Museum opened"), move("finish", "It opened in 1950 [1]."))
    assert found.steps[1].failed is True and "no tool called" in found.steps[1].observation and len(shelf.documents()) == 2


def test_the_documents_tool_lists_only_what_was_chosen(shelf):
    found, _ = run(shelf, move("documents"), move("search", "Riverside Museum opened"), move("finish", "It opened in 1950 [1]."))
    assert found.steps[1].observation == "museum.txt\ntickets.txt"


def test_a_language_no_check_reads_gets_the_light_check_and_is_told_to_write_in_it(shelf):
    persian = "موزه ریورساید در چه سالی باز شد و بلیت آن چند است و کجا قرار دارد؟"
    writer = Script(move("search", "Riverside Museum opened"), move("finish", "موزه در سال 1950 باز شد [1]."))
    found = run_agent(persian, shelf, Checker(refuses=not_checked("language")), writer, (MINE,))
    assert found.status == "light" and found.light and writer.asked[0][0].endswith("write the final answer in Persian.")


def test_a_flagged_final_answer_keeps_its_verdict(shelf):
    words = "It opened in 1950 [1]."
    found, _ = run(shelf, move("search", "Riverside Museum opened"), move("finish", words), guardian=Checker(report("hallucinated", 0.8, words)))
    assert found.status == "checked" and found.report.verdict == "hallucinated" and found.text == words


def test_when_the_person_leaves_the_run_stops(shelf):
    gone = threading.Event()
    gone.set()
    writer = Script(move("search", "Riverside"))
    with pytest.raises(Cancelled):
        run_agent(TASK, shelf, Checker(), writer, (MINE,), cancelled=gone)
    assert writer.asked == []


@pytest.mark.parametrize(
    "text, result",
    [("12*3", "36"), ("(2 + 3) * 4", "20"), ("1,000 / 8", "125.0"), ("2 ** 10", "1024"), ("۱۲ × ۳", "36"), ("-5 + 2", "-3"), ("7 % 3", "1")],
)
def test_the_calculator_does_sums(text, result):
    assert calculate(text) == result


@pytest.mark.parametrize("text", ["", "__import__('os').system('dir')", "open('x')", "1/0", "2**100000", "a + 1", "1 if 1 else 2", "[1, 2]", "9" * 200, "True + 1"])
def test_the_calculator_refuses_what_is_not_a_sum(text):
    with pytest.raises(ValueError):
        calculate(text)


def test_a_turn_is_read_from_json_alone_or_wrapped_in_words():
    assert _read_move(move("search", "x"))["tool"] == "search"
    assert _read_move('Sure! {"thought": "t", "tool": "finish", "input": "a"} Done.')["input"] == "a"
    assert _read_move("no json") is None and _read_move('{"thought": "t"}') is None and _read_move('["a"]') is None


class AnsweringEngine(FakeEngine):
    def analyze(self, sample, profile=None, policy="strict", progress=None, cancelled=None, hint=None):
        return report("grounded", 0.04, sample.answer)


def test_the_api_streams_each_step_and_validates_what_it_is_asked(shelf):
    writers = {"local": Script(move("search", "Riverside Museum opened"), move("finish", "It opened in 1950 [1]."))}
    with TestClient(create_app(AnsweringEngine(), ExampleStore(ROOT), load=False, library=shelf, generators=writers)) as c:
        found = events(c.post("/api/agent/run", json={"task": TASK, "collections": ["mine"]}))
        kinds = [e["type"] for e in found]
        assert "step" in kinds and kinds[-1] == "result"
        assert found[-1]["answer"]["status"] == "checked" and [s["kind"] for s in found[-1]["answer"]["steps"]] == ["thought", "action", "answer"]
        assert c.post("/api/agent/run", json={"task": ""}).status_code == 422
        assert c.post("/api/agent/run", json={"task": "x", "generator": "other"}).status_code == 422
        assert c.post("/api/agent/run", json={"task": "x", "policy": "anything"}).status_code == 422


def test_the_api_waits_for_the_guardian_before_running(shelf):
    engine = AnsweringEngine()
    engine.state = "loading"
    writer = Script()
    with TestClient(create_app(engine, ExampleStore(ROOT), load=False, library=shelf, generators={"local": writer})) as c:
        assert c.post("/api/agent/run", json={"task": TASK}).status_code == 503
    assert writer.asked == []

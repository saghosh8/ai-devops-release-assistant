import json
import os

from devops_assistant import memory


def test_load_history_empty(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(memory, "HISTORY_FILE", os.path.join(tmp_path, ".devops_assistant_history.json"))
    assert memory.load_history() == []


def test_append_and_load_history(tmp_path, monkeypatch):
    hist_file = os.path.join(tmp_path, ".devops_assistant_history.json")
    monkeypatch.setattr(memory, "HISTORY_FILE", hist_file)

    memory.append_history("why is my pod crashing?", "Likely a bad readiness probe.")
    history = memory.load_history()

    assert len(history) == 1
    assert history[0]["question"] == "why is my pod crashing?"
    assert os.path.exists(hist_file)


def test_history_is_capped(tmp_path, monkeypatch):
    hist_file = os.path.join(tmp_path, ".devops_assistant_history.json")
    monkeypatch.setattr(memory, "HISTORY_FILE", hist_file)
    monkeypatch.setattr(memory, "MAX_STORED", 3)

    for i in range(5):
        memory.append_history(f"question {i}", f"summary {i}")

    history = memory.load_history()
    assert len(history) == 3
    assert history[-1]["question"] == "question 4"


def test_build_context_messages(tmp_path, monkeypatch):
    hist_file = os.path.join(tmp_path, ".devops_assistant_history.json")
    monkeypatch.setattr(memory, "HISTORY_FILE", hist_file)

    memory.append_history("q1", "s1")
    messages = memory.build_context_messages(turns=1)

    assert messages == [
        {"role": "user", "content": "q1"},
        {"role": "assistant", "content": "s1"},
    ]

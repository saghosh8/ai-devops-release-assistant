from devops_assistant import observability


def test_estimate_cost_known_model():
    cost = observability.estimate_cost("gemini-3.5-flash", input_tokens=1000, output_tokens=1000)
    assert cost > 0


def test_estimate_cost_unknown_model_is_zero():
    assert observability.estimate_cost("some-unknown-model", 1000, 1000) == 0.0


def test_track_call_logs_a_successful_call(tmp_path):
    log_path = str(tmp_path / "calls.jsonl")

    with observability.track_call("gemini-3.5-flash", "structured_runbook", log_path=log_path) as t:
        t["input_tokens"] = 100
        t["output_tokens"] = 50

    calls = observability.load_calls(log_path)
    assert len(calls) == 1
    assert calls[0]["success"] is True
    assert calls[0]["input_tokens"] == 100
    assert calls[0]["prompt_version"] == observability.PROMPT_VERSIONS["structured_runbook"]
    assert calls[0]["latency_ms"] >= 0


def test_track_call_logs_a_failed_call_and_reraises(tmp_path):
    log_path = str(tmp_path / "calls.jsonl")

    try:
        with observability.track_call("gemini-3.5-flash", "structured_runbook", log_path=log_path):
            raise ValueError("boom")
    except ValueError:
        pass

    calls = observability.load_calls(log_path)
    assert len(calls) == 1
    assert calls[0]["success"] is False
    assert "boom" in calls[0]["error"]


def test_run_eval_reports_pass_and_fail():
    def fake_predict(question: str) -> dict:
        if "pizza" in question:
            return {"category": "Kubernetes"}  # deliberately wrong, to exercise a FAIL
        return {"category": "Kubernetes"}

    cases = [
        {"question": "why is my pod stuck?", "expected_category": "Kubernetes"},
        {"question": "what's the best pizza topping?", "expected_category": "Out of scope"},
    ]
    report = observability.run_eval(fake_predict, cases=cases)
    assert report["total"] == 2
    assert report["passed"] == 1
    assert report["results"][0]["passed"] is True
    assert report["results"][1]["passed"] is False


def test_run_eval_handles_predict_fn_exception():
    def broken_predict(question: str) -> dict:
        raise RuntimeError("API down")

    report = observability.run_eval(broken_predict, cases=observability.EVAL_CASES[:1])
    assert report["passed"] == 0
    assert report["results"][0]["got_category"] is None

"""Tests for node_eval's tracing, token/cost accounting and cost controls.

Every "LLM call" here is a MagicMock. No test may hit the network or spend
money; several tests assert the mock was *never* called, which is the only way
to prove --dry-run is free.

Fake nodes stand in for the real registry so these tests never import the
draft-analysis graph: what is under test is the measurement harness, not the
nodes. A fake node calls `llm_budget.check_llm_allowed` and then
`record_usage`, exactly as `services/retry_utils.py` does around a real call,
so the guardrails and the accounting are exercised for real.
"""

import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
BACKEND_DIR = EVAL_DIR.parents[1] / "services" / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from app.core import llm_budget  # noqa: E402
from app.core import tracing  # noqa: E402


def _load(name: str):
    module_path = EVAL_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"eval_{name}_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


node_eval = _load("node_eval")


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

#: Env that must not leak in from the developer's shell or from a sibling test
#: process. A run with NOESIS_LLM_KILL_SWITCH left set would make every
#: "did it call the LLM" assertion pass for the wrong reason.
_AMBIENT_ENV = (
    "NOESIS_LLM_KILL_SWITCH",
    "EVAL_REPLAY_ONLY",
    "NOESIS_LLM_MAX_CALLS",
    "NOESIS_LLM_MAX_SPEND_USD",
    "NOESIS_LLM_USAGE_LOG",
    "NOESIS_TRACING_BACKEND",
    "NOESIS_TRACING_FILE",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _AMBIENT_ENV:
        monkeypatch.delenv(name, raising=False)
    llm_budget.reset()
    tracing.reset_tracer()
    yield
    llm_budget.reset()
    tracing.reset_tracer()


@pytest.fixture
def trace_file(tmp_path):
    path = tmp_path / "spans.jsonl"
    tracing.configure_tracing(backend="jsonl", file_path=str(path))
    return path


@pytest.fixture
def llm(monkeypatch):
    """The one and only stand-in for a paid LLM call."""
    return MagicMock(name="llm_call", return_value={"ok": True})


def _write_fixture(state_dir: Path, node: str, paper: str, payload: dict | None = None,
                   reviewer_type: str | None = None) -> Path:
    filename = f"{node}__{reviewer_type}.json" if reviewer_type else f"{node}.json"
    path = state_dir / paper / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload or {"draft_content": "x", "stage_only": True}))
    return path


def _spans(trace_file: Path) -> list[dict]:
    if not trace_file.exists():
        return []
    return [json.loads(line) for line in trace_file.read_text().splitlines() if line.strip()]


def _make_node(llm, *, prompt=1000, completion=200, cached=0, calls=1, delay=0.005):
    """A fake node that burns a little wall time and 'calls' the LLM."""
    import time

    def node(state):
        time.sleep(delay)
        for _ in range(calls):
            llm_budget.check_llm_allowed("fake")
            llm(state)
            llm_budget.record_usage(
                model="gpt-5.2",
                prompt_tokens=prompt,
                completion_tokens=completion,
                cached_tokens=cached,
            )
        return {"coverage_gaps": [{"id": "g1", "description": "a gap"}]}

    return node


def _replay(node_name, paper, node_func, state_dir, **kwargs):
    kwargs.setdefault("with_metric", False)
    return node_eval.replay_once(node_name, paper, node_func, state_dir=state_dir, **kwargs)


# ---------------------------------------------------------------------------
# Tracing
# ---------------------------------------------------------------------------

def test_replay_emits_one_node_span_with_nonzero_duration(tmp_path, trace_file, llm):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "detect_gaps", "paperA")

    record = _replay("detect_gaps", "paperA", _make_node(llm), state_dir)

    spans = _spans(trace_file)
    assert len(spans) == 1, f"expected exactly one node span, got {spans}"
    span = spans[0]
    assert span["name"] == "detect_gaps"
    assert span["kind"] == tracing.SpanKind.NODE
    assert span["duration_ms"] > 0, "span recorded zero duration — timing is not wired"
    assert span["attributes"][tracing.NOESIS_NODE_NAME] == "detect_gaps"
    assert span["attributes"]["noesis.eval.paper_id"] == "paperA"
    assert record["span_id"] == span["span_id"]
    assert record["wall_seconds"] > 0


def test_failing_node_span_is_marked_error_but_batch_record_survives(tmp_path, trace_file):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "detect_gaps", "paperA")

    def boom(state):
        raise ValueError("node exploded")

    record = _replay("detect_gaps", "paperA", boom, state_dir)

    assert record["status"] == "error"
    assert record["error_type"] == "ValueError"
    assert "node exploded" in record["error_message"]
    assert record["wall_seconds"] >= 0
    span = _spans(trace_file)[0]
    assert span["status"] == tracing.STATUS_ERROR


# ---------------------------------------------------------------------------
# Token attribution
# ---------------------------------------------------------------------------

def test_tokens_attribute_to_the_node_label_not_the_model(tmp_path, trace_file, llm):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "reviewer_panel_node", "paperA", reviewer_type="methodology")

    record = _replay(
        "reviewer_panel_node", "paperA", _make_node(llm, prompt=12_000, completion=900),
        state_dir, reviewer_type="methodology",
    )

    usage = record["usage"]
    assert usage["calls"] == 1
    assert usage["prompt_tokens"] == 12_000
    assert usage["completion_tokens"] == 900
    assert usage["total_tokens"] == 12_900
    assert usage["unpriced_calls"] == 0
    assert usage["estimated_usd"] > 0, "pricing table did not price a gpt-5.2 call"
    assert usage["by_label"] == {"reviewer_panel_node": 1}, (
        "usage landed on the model name — llm_label(node) is not wrapping the call"
    )
    assert llm_budget.by_label()["reviewer_panel_node"]["calls"] == 1


def test_cost_matches_the_pricing_table(tmp_path, trace_file, llm):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "detect_gaps", "paperA")

    record = _replay(
        "detect_gaps", "paperA", _make_node(llm, prompt=1_000_000, completion=0), state_dir
    )

    expected = llm_budget.estimate_usd("gpt-5.2", 1_000_000, 0, 0)
    assert record["usage"]["estimated_usd"] == pytest.approx(expected, rel=1e-6)


# ---------------------------------------------------------------------------
# --dry-run
# ---------------------------------------------------------------------------

def test_dry_run_makes_zero_llm_calls_and_writes_nothing(tmp_path, capsys, llm):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "detect_gaps", "paperA")
    _write_fixture(state_dir, "editor_pass_node", "paperA")
    results = tmp_path / "results.jsonl"

    exit_code = node_eval.main([
        "--node", "detect_gaps", "--node", "editor_pass_node",
        "--paper", "paperA",
        "--state-dir", str(state_dir),
        "--results", str(results),
        "--dry-run",
    ])

    assert exit_code == 0
    llm.assert_not_called()
    assert not results.exists(), "--dry-run wrote to the results file"
    out = capsys.readouterr().out
    # detect_gaps costs 0, editor_pass_node costs 1 -> band is 0-1.
    assert "estimated LLM calls   : 1-1" in out or "estimated LLM calls   : 0-1" in out
    assert "runnable replays      : 2" in out
    assert "nothing executed" in out


def test_dry_run_call_count_scales_with_repeat_and_ignores_missing_fixtures(tmp_path, capsys):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "reviewer_panel_node", "paperA", reviewer_type="methodology")
    # paperB has no fixture: it cannot run, so it must not inflate the estimate.

    node_eval.main([
        "--node", "reviewer_panel_node",
        "--paper", "paperA", "--paper", "paperB",
        "--reviewer-type", "methodology",
        "--state-dir", str(state_dir),
        "--repeat", "3",
        "--dry-run",
    ])

    out = capsys.readouterr().out
    assert "estimated LLM calls   : 3-6" in out, out
    assert "missing fixtures      : 1" in out
    assert "runnable replays      : 3" in out


def test_large_selection_is_refused_without_yes(tmp_path, capsys, llm, monkeypatch):
    state_dir = tmp_path / "state"
    papers = [f"paper{i}" for i in range(10)]
    for paper in papers:
        _write_fixture(state_dir, "editor_pass_node", paper)
    monkeypatch.setattr(node_eval, "_node_registry", lambda: {"editor_pass_node": _make_node(llm)})

    argv = ["--node", "editor_pass_node", "--state-dir", str(state_dir), "--no-metric",
            "--results", str(tmp_path / "r.jsonl"), "--trace-backend", "noop",
            "--max-estimated-calls", "5"]
    for paper in papers:
        argv += ["--paper", paper]

    assert node_eval.main(argv) == 2
    llm.assert_not_called()
    assert "REFUSED" in capsys.readouterr().out

    assert node_eval.main(argv + ["--yes"]) == 0
    assert llm.call_count == 10


# ---------------------------------------------------------------------------
# Append-only results
# ---------------------------------------------------------------------------

def test_results_file_appends_across_runs(tmp_path, llm, monkeypatch):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "detect_gaps", "paperA")
    results = tmp_path / "results.jsonl"
    monkeypatch.setattr(node_eval, "_node_registry", lambda: {"detect_gaps": _make_node(llm)})

    argv = ["--node", "detect_gaps", "--paper", "paperA", "--state-dir", str(state_dir),
            "--results", str(results), "--no-metric", "--trace-backend", "noop"]

    assert node_eval.main(argv) == 0
    after_first = node_eval.load_records(results)
    assert node_eval.main(argv) == 0
    after_second = node_eval.load_records(results)

    assert len(after_first) == 2  # one replay + one run_summary
    assert len(after_second) == 4, "second run overwrote the first — results are not append-only"
    assert after_second[:2] == after_first, "earlier records were mutated"
    run_ids = {r["run_id"] for r in after_second}
    assert len(run_ids) == 2, "both runs reused a run_id"


def test_partial_batch_is_persisted_before_the_halt(tmp_path, llm, monkeypatch):
    state_dir = tmp_path / "state"
    for paper in ("paperA", "paperB", "paperC"):
        _write_fixture(state_dir, "editor_pass_node", paper)
    results = tmp_path / "results.jsonl"
    monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "2")

    selection = node_eval.build_selection(
        ["editor_pass_node"], ["paperA", "paperB", "paperC"], state_dir=state_dir
    )
    summary = node_eval.run_batch(
        selection, repeat=1, config={}, registry={"editor_pass_node": _make_node(llm)},
        state_dir=state_dir, with_metric=False, results_path=results,
    )

    replays = [r for r in node_eval.load_records(results) if r["record_type"] == "replay"]
    assert len(replays) == 2
    assert summary["halted"] is not None


# ---------------------------------------------------------------------------
# --repeat / variance
# ---------------------------------------------------------------------------

def test_repeat_produces_n_records_and_reports_spread(tmp_path, llm, monkeypatch):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "detect_gaps", "paperA")
    results = tmp_path / "results.jsonl"

    # Latencies 10ms / 30ms / 50ms plus a constant harness overhead. A constant
    # offset cancels out of stdev, so stdev is asserted tightly (20ms) and the
    # mean only loosely.
    delays = iter([0.010, 0.030, 0.050])
    base = _make_node(llm, delay=0)

    def varying(state):
        import time
        time.sleep(next(delays))
        return base(state)

    summary = node_eval.run_batch(
        node_eval.build_selection(["detect_gaps"], ["paperA"], state_dir=state_dir),
        repeat=3, config={}, registry={"detect_gaps": varying},
        state_dir=state_dir, with_metric=False, results_path=results,
    )

    replays = [r for r in node_eval.load_records(results) if r["record_type"] == "replay"]
    assert len(replays) == 3
    assert sorted(r["repeat_index"] for r in replays) == [0, 1, 2]

    stats = summary["per_node"][0]["latency_seconds"]
    assert stats["n"] == 3
    assert stats["mean"] == pytest.approx(0.030, abs=0.025)
    assert stats["stdev"] == pytest.approx(0.020, abs=0.008)
    assert stats["min"] < stats["max"]
    assert summary["per_node"][0]["llm_calls"] == 3


def test_single_run_reports_stdev_none_not_zero(tmp_path, llm):
    record = {
        "record_type": "replay", "node": "n", "paper_id": "p", "reviewer_type": None,
        "status": "ok", "wall_seconds": 1.0, "usage": {}, "metric": None,
    }
    stats = node_eval.aggregate([record])[0]["latency_seconds"]
    assert stats["n"] == 1
    assert stats["stdev"] is None, "one sample reported as zero variance"


def test_recall_variance_is_reported_across_repeats(tmp_path):
    records = []
    for index, recall in enumerate([0.20, 0.40, 0.30]):
        records.append({
            "record_type": "replay", "node": "reviewer_panel_node", "paper_id": "p",
            "reviewer_type": "methodology", "status": "ok", "wall_seconds": 1.0,
            "usage": {}, "repeat_index": index,
            "metric": {"severity_weighted_recall": recall},
        })
    stats = node_eval.aggregate(records)[0]["severity_weighted_recall"]
    assert stats["n"] == 3
    assert stats["mean"] == pytest.approx(0.30)
    assert stats["stdev"] == pytest.approx(0.10)


# ---------------------------------------------------------------------------
# Failures and ceilings
# ---------------------------------------------------------------------------

def test_one_failing_node_does_not_kill_the_batch(tmp_path, llm):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "detect_gaps", "paperA")
    _write_fixture(state_dir, "detect_gaps", "paperB")
    results = tmp_path / "results.jsonl"

    calls = {"n": 0}

    def flaky(state):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("first fixture is bad")
        return _make_node(llm)(state)

    summary = node_eval.run_batch(
        node_eval.build_selection(["detect_gaps"], ["paperA", "paperB"], state_dir=state_dir),
        repeat=1, config={}, registry={"detect_gaps": flaky},
        state_dir=state_dir, with_metric=False, results_path=results,
    )

    assert summary["attempted_replays"] == 2
    assert summary["completed_replays"] == 1
    assert summary["failed_replays"] == 1
    assert summary["halted"] is None
    statuses = {
        r["paper_id"]: r["status"]
        for r in node_eval.load_records(results) if r["record_type"] == "replay"
    }
    assert statuses == {"paperA": "error", "paperB": "ok"}


def test_call_ceiling_stops_the_batch_and_reports_progress(tmp_path, llm, monkeypatch):
    state_dir = tmp_path / "state"
    for paper in ("paperA", "paperB", "paperC", "paperD"):
        _write_fixture(state_dir, "editor_pass_node", paper)
    results = tmp_path / "results.jsonl"
    monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "2")

    summary = node_eval.run_batch(
        node_eval.build_selection(
            ["editor_pass_node"], ["paperA", "paperB", "paperC", "paperD"], state_dir=state_dir
        ),
        repeat=1, config={}, registry={"editor_pass_node": _make_node(llm)},
        state_dir=state_dir, with_metric=False, results_path=results,
    )

    assert summary["planned_replays"] == 4
    assert summary["completed_replays"] == 2, "ceiling did not stop the batch at 2 calls"
    assert summary["halted"]["reason"] == "LLMBudgetExceeded"
    assert summary["halted"]["halted_at"]["paper_id"] == "paperC"
    assert llm.call_count == 2, "an LLM call was made after the ceiling was reached"


def test_spend_ceiling_also_halts(tmp_path, llm, monkeypatch):
    state_dir = tmp_path / "state"
    for paper in ("paperA", "paperB", "paperC"):
        _write_fixture(state_dir, "editor_pass_node", paper)
    monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "0.01")

    summary = node_eval.run_batch(
        node_eval.build_selection(
            ["editor_pass_node"], ["paperA", "paperB", "paperC"], state_dir=state_dir
        ),
        repeat=1, config={},
        # ~$0.0175 of input per call, so the ceiling trips after the first.
        registry={"editor_pass_node": _make_node(llm, prompt=10_000, completion=0)},
        state_dir=state_dir, with_metric=False, results_path=tmp_path / "r.jsonl",
    )

    assert summary["halted"]["reason"] == "LLMBudgetExceeded"
    assert summary["completed_replays"] == 1


def test_kill_switch_blocks_everything(tmp_path, llm, monkeypatch):
    state_dir = tmp_path / "state"
    _write_fixture(state_dir, "editor_pass_node", "paperA")
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")

    summary = node_eval.run_batch(
        node_eval.build_selection(["editor_pass_node"], ["paperA"], state_dir=state_dir),
        repeat=1, config={}, registry={"editor_pass_node": _make_node(llm)},
        state_dir=state_dir, with_metric=False, results_path=tmp_path / "r.jsonl",
    )

    llm.assert_not_called()
    assert summary["completed_replays"] == 0
    assert summary["halted"]["reason"] == "LLMCallBlocked"


# ---------------------------------------------------------------------------
# Supabase safety
# ---------------------------------------------------------------------------

def test_stage_only_is_forced_true_so_nodes_cannot_persist(tmp_path, llm):
    state_dir = tmp_path / "state"
    _write_fixture(
        state_dir, "reviewer_panel_node", "paperA",
        payload={"stage_only": False, "draft_id": "d1"}, reviewer_type="methodology",
    )
    seen = {}

    def capture(state):
        seen.update(state)
        return {}

    _replay("reviewer_panel_node", "paperA", capture, state_dir, reviewer_type="methodology")

    assert seen["stage_only"] is True, (
        "a fixture with stage_only=False would take the direct Supabase persist path"
    )


def test_unknown_node_is_rejected_before_anything_runs(tmp_path, llm):
    with pytest.raises(SystemExit):
        node_eval.main(["--node", "not_a_node", "--paper", "paperA", "--dry-run"])
    llm.assert_not_called()

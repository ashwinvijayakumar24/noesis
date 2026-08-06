"""Tests for the trace -> eval-case miner.

Everything here is synthetic span JSONL in a tmp_path. No network, no DB, no
API key, no fixtures on disk -- the miner is pure file I/O by design and these
tests would be worthless if they needed anything else.

The load-bearing properties, in the order they are tested:
  * each rule fires on a span that should trip it, and stays silent on one
    that should not (a rule that fires on everything is not a rule);
  * a fingerprint depends on identity, never on span ids or input order;
  * dedup holds across overlapping files and across re-runs;
  * the manifest is append-only -- never rewritten, never shrunk;
  * --dry-run leaves the directory byte-identical;
  * garbage lines are counted and skipped, never fatal;
  * empty input is a valid, empty result rather than a crash.
"""

import importlib.util
import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVAL_DIR.parents[1]
for _path in (str(REPO_ROOT), str(REPO_ROOT / "services" / "backend")):
    if _path not in sys.path:
        sys.path.insert(0, _path)


def _load(name: str):
    module_path = EVAL_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(f"eval_{name}_for_tests", module_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


trace_cases = _load("trace_cases")


# ---------------------------------------------------------------------------
# Span builders
# ---------------------------------------------------------------------------


def node_span(
    span_id="n1",
    trace_id="t1",
    name="reviewer_panel_node",
    parent=None,
    status="OK",
    duration_ms=100.0,
    paper="paper-a",
    reviewer=None,
    extra=None,
):
    attributes = {
        "noesis.node.name": name,
        "noesis.eval.paper_id": paper,
        "noesis.eval.fixture": f"/cache/state/{paper}/{name}.json",
        "noesis.eval.repeat_index": 0,
    }
    if reviewer:
        attributes["noesis.eval.reviewer_type"] = reviewer
    attributes.update(extra or {})
    return {
        "name": name,
        "kind": "node",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent,
        "status": status,
        "start_time": 1000.0,
        "end_time": 1000.0 + duration_ms / 1000.0,
        "duration_ms": duration_ms,
        "attributes": attributes,
    }


def llm_span(
    span_id="l1",
    trace_id="t1",
    parent="n1",
    status="OK",
    duration_ms=500.0,
    input_tokens=1000,
    output_tokens=500,
    attempt=0,
    model="gpt-5.2",
    extra=None,
    drop=(),
):
    attributes = {
        "noesis.llm.attempt": attempt,
        "gen_ai.request.model": model,
        "gen_ai.system": "openai",
        "gen_ai.usage.input_tokens": input_tokens,
        "gen_ai.usage.output_tokens": output_tokens,
        "noesis.gen_ai.usage.cached_input_tokens": 0,
        "noesis.gen_ai.usage.estimated_cost_usd": 0.001,
    }
    for key in drop:
        attributes.pop(key, None)
    attributes.update(extra or {})
    return {
        "name": "openai.chat",
        "kind": "llm_call",
        "trace_id": trace_id,
        "span_id": span_id,
        "parent_span_id": parent,
        "status": status,
        "start_time": 1000.0,
        "end_time": 1000.0 + duration_ms / 1000.0,
        "duration_ms": duration_ms,
        "attributes": attributes,
    }


def write_spans(path: Path, spans) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(s) + "\n" for s in spans), encoding="utf-8")
    return path


def run_miner(tmp_path, spans, out_dir=None, rules=None, **thresholds):
    trace_file = write_spans(tmp_path / "spans.jsonl", spans)
    out = out_dir or (tmp_path / "cases")
    return trace_cases.mine(
        [str(trace_file)],
        out,
        rules or list(trace_cases.RULES),
        trace_cases.Thresholds(**thresholds),
    )


def rules_fired(result):
    return sorted({hit.rule for hit in result.hits})


# ---------------------------------------------------------------------------
# Rule: span_error
# ---------------------------------------------------------------------------


def test_span_error_fires_on_non_ok_status(tmp_path):
    result = run_miner(
        tmp_path,
        [
            node_span(),
            llm_span(
                status="ERROR",
                extra={"exception.type": "RetryError", "exception.message": "APITimeoutError"},
            ),
        ],
    )
    hits = [h for h in result.hits if h.rule == "span_error"]
    assert len(hits) == 1
    assert hits[0].evidence["exception_type"] == "RetryError"


def test_span_error_silent_on_clean_run(tmp_path):
    result = run_miner(tmp_path, [node_span(), llm_span()])
    assert "span_error" not in rules_fired(result)


# ---------------------------------------------------------------------------
# Rule: empty_llm_output
# ---------------------------------------------------------------------------


def test_empty_llm_output_fires_on_zero_output_tokens(tmp_path):
    result = run_miner(tmp_path, [node_span(), llm_span(output_tokens=0)])
    hits = [h for h in result.hits if h.rule == "empty_llm_output"]
    assert len(hits) == 1
    assert hits[0].evidence["output_tokens"] == 0


def test_empty_llm_output_fires_when_usage_absent(tmp_path):
    result = run_miner(
        tmp_path, [node_span(), llm_span(drop=("gen_ai.usage.output_tokens",))]
    )
    assert "empty_llm_output" in rules_fired(result)


def test_empty_llm_output_silent_on_normal_call_and_on_errors(tmp_path):
    # A normal call must not trip it, and an *errored* call is span_error's
    # business -- otherwise every failure would produce two cases.
    result = run_miner(
        tmp_path,
        [node_span(), llm_span(output_tokens=500), llm_span(span_id="l2", status="ERROR",
                                                            drop=("gen_ai.usage.output_tokens",))],
    )
    assert "empty_llm_output" not in rules_fired(result)


# ---------------------------------------------------------------------------
# Rule: slow_node
# ---------------------------------------------------------------------------


def test_slow_node_fires_above_bound(tmp_path):
    result = run_miner(tmp_path, [node_span(duration_ms=25_000.0)])
    hits = [h for h in result.hits if h.rule == "slow_node"]
    assert len(hits) == 1
    assert hits[0].evidence["threshold_ms"] == trace_cases.DEFAULT_SLOW_NODE_MS


def test_slow_node_silent_below_bound_and_on_llm_spans(tmp_path):
    # A 25 s *LLM call* is not a slow node: the rule is scoped to node spans so
    # one slow call does not also emit a duplicate node-level case.
    result = run_miner(
        tmp_path, [node_span(duration_ms=19_999.0), llm_span(duration_ms=25_000.0)]
    )
    assert "slow_node" not in rules_fired(result)


def test_slow_node_bound_is_configurable(tmp_path):
    result = run_miner(tmp_path, [node_span(duration_ms=5_000.0)], slow_node_ms=1_000.0)
    assert "slow_node" in rules_fired(result)


# ---------------------------------------------------------------------------
# Rule: oversized_prompt
# ---------------------------------------------------------------------------


def test_oversized_prompt_fires_above_token_bound(tmp_path):
    result = run_miner(tmp_path, [node_span(), llm_span(input_tokens=25_629)])
    hits = [h for h in result.hits if h.rule == "oversized_prompt"]
    assert len(hits) == 1
    assert hits[0].evidence["input_tokens"] == 25_629


def test_oversized_prompt_silent_below_bound(tmp_path):
    result = run_miner(tmp_path, [node_span(), llm_span(input_tokens=19_999)])
    assert "oversized_prompt" not in rules_fired(result)


# ---------------------------------------------------------------------------
# Rule: retry_path
# ---------------------------------------------------------------------------


def test_retry_path_fires_on_second_attempt(tmp_path):
    result = run_miner(tmp_path, [node_span(), llm_span(attempt=1)])
    hits = [h for h in result.hits if h.rule == "retry_path"]
    assert len(hits) == 1
    assert hits[0].evidence["attempt"] == 1


def test_retry_path_silent_on_first_attempt(tmp_path):
    result = run_miner(tmp_path, [node_span(), llm_span(attempt=0)])
    assert "retry_path" not in rules_fired(result)


# ---------------------------------------------------------------------------
# Rule: incomplete_trace
# ---------------------------------------------------------------------------


def test_incomplete_trace_fires_on_missing_parent(tmp_path):
    result = run_miner(tmp_path, [llm_span(parent="gone-forever")])
    hits = [h for h in result.hits if h.rule == "incomplete_trace"]
    assert len(hits) == 1
    assert hits[0].evidence["missing_parent_span_id"] == "gone-forever"


def test_incomplete_trace_silent_when_parent_present(tmp_path):
    result = run_miner(tmp_path, [node_span(span_id="n1"), llm_span(parent="n1")])
    assert "incomplete_trace" not in rules_fired(result)


def test_rules_flag_selects_a_subset(tmp_path):
    spans = [node_span(duration_ms=25_000.0), llm_span(input_tokens=30_000)]
    result = run_miner(tmp_path, spans, rules=["slow_node"])
    assert rules_fired(result) == ["slow_node"]


# ---------------------------------------------------------------------------
# Fingerprints
# ---------------------------------------------------------------------------


def test_fingerprint_is_stable_across_runs(tmp_path):
    spans = [node_span(duration_ms=25_000.0)]
    first = run_miner(tmp_path / "a", spans)
    second = run_miner(tmp_path / "b", spans)
    assert [c["fingerprint"] for c in first.new_cases] == [
        c["fingerprint"] for c in second.new_cases
    ]


def test_fingerprint_ignores_span_ids_and_input_order(tmp_path):
    """Same failure, different run: new span/trace ids, same fingerprint.

    This is the whole reason dedup works. If the fingerprint tracked span ids,
    every re-run would append a fresh copy of every case forever.
    """
    run_a = [
        node_span(span_id="n1", trace_id="t1", duration_ms=25_000.0),
        node_span(span_id="n2", trace_id="t2", name="editor_pass_node", duration_ms=30_000.0),
    ]
    run_b = [
        node_span(span_id="zzz", trace_id="t9", name="editor_pass_node", duration_ms=31_000.0),
        node_span(span_id="yyy", trace_id="t8", duration_ms=26_000.0),
    ]
    a = {c["fingerprint"] for c in run_miner(tmp_path / "a", run_a).new_cases}
    b = {c["fingerprint"] for c in run_miner(tmp_path / "b", run_b).new_cases}
    assert a == b and len(a) == 2


def test_fingerprint_separates_reviewer_branches(tmp_path):
    """The three reviewer branches share a node name and are different cases."""
    result = run_miner(
        tmp_path,
        [
            node_span(span_id="n1", trace_id="t1", reviewer="methods", duration_ms=25_000.0),
            node_span(span_id="n2", trace_id="t2", reviewer="novelty", duration_ms=25_000.0),
        ],
    )
    assert len({c["fingerprint"] for c in result.new_cases}) == 2


def test_fingerprint_separates_rules_on_one_span(tmp_path):
    result = run_miner(
        tmp_path,
        [node_span(span_id="n1", status="ERROR", duration_ms=25_000.0)],
    )
    assert sorted(c["rule"] for c in result.new_cases) == ["slow_node", "span_error"]
    assert len({c["fingerprint"] for c in result.new_cases}) == 2


# ---------------------------------------------------------------------------
# Dedup + append-only store
# ---------------------------------------------------------------------------


def test_repeats_within_one_input_collapse_to_one_case(tmp_path):
    """The same node slow on three repeats is one case, not three."""
    spans = [
        node_span(span_id=f"n{i}", trace_id=f"t{i}", duration_ms=25_000.0 + i) for i in range(3)
    ]
    result = run_miner(tmp_path, spans)
    assert len(result.new_cases) == 1
    assert result.summary(list(trace_cases.RULES), tmp_path, True)["deduped_within_batch"] == 2


def test_overlapping_files_do_not_duplicate(tmp_path):
    shared = node_span(span_id="n1", trace_id="t1", duration_ms=25_000.0)
    only_b = node_span(span_id="n2", trace_id="t2", name="editor_pass_node", duration_ms=25_000.0)
    file_a = write_spans(tmp_path / "a.jsonl", [shared])
    file_b = write_spans(tmp_path / "b.jsonl", [shared, only_b])
    out = tmp_path / "cases"
    result = trace_cases.mine(
        [str(file_a), str(file_b)], out, list(trace_cases.RULES), trace_cases.Thresholds()
    )
    assert len(result.new_cases) == 2  # not 3


def test_second_run_emits_zero_new_cases(tmp_path):
    spans = [node_span(duration_ms=25_000.0), llm_span(input_tokens=30_000)]
    trace_file = write_spans(tmp_path / "spans.jsonl", spans)
    out = tmp_path / "cases"

    first = trace_cases.mine(
        [str(trace_file)], out, list(trace_cases.RULES), trace_cases.Thresholds()
    )
    trace_cases.write_cases(out, first.new_cases)
    assert first.new_cases

    second = trace_cases.mine(
        [str(trace_file)], out, list(trace_cases.RULES), trace_cases.Thresholds()
    )
    assert second.new_cases == []
    assert second.deduped
    assert all(reason == "already_in_manifest" for _, reason in second.deduped)


def test_manifest_is_append_only(tmp_path):
    out = tmp_path / "cases"
    first = run_miner(tmp_path / "a", [node_span(duration_ms=25_000.0)], out_dir=out)
    trace_cases.write_cases(out, first.new_cases)
    manifest = out / trace_cases.MANIFEST_NAME
    before = manifest.read_text(encoding="utf-8")

    second = run_miner(
        tmp_path / "b",
        [node_span(span_id="n9", trace_id="t9", name="editor_pass_node", duration_ms=25_000.0)],
        out_dir=out,
    )
    trace_cases.write_cases(out, second.new_cases)
    after = manifest.read_text(encoding="utf-8")

    assert after.startswith(before), "existing manifest lines were rewritten"
    assert len(after.splitlines()) == len(before.splitlines()) + 1


def test_existing_case_file_is_never_overwritten(tmp_path):
    out = tmp_path / "cases"
    result = run_miner(tmp_path, [node_span(duration_ms=25_000.0)], out_dir=out)
    trace_cases.write_cases(out, result.new_cases)
    path = out / f"case_{result.new_cases[0]['fingerprint']}.json"
    path.write_text('{"hand": "edited"}\n', encoding="utf-8")

    trace_cases.write_cases(out, result.new_cases)  # same case again
    assert json.loads(path.read_text()) == {"hand": "edited"}


def test_manifest_row_points_at_its_case_file(tmp_path):
    out = tmp_path / "cases"
    result = run_miner(tmp_path, [node_span(duration_ms=25_000.0)], out_dir=out)
    trace_cases.write_cases(out, result.new_cases)
    rows = trace_cases.read_manifest(out)
    assert len(rows) == 1
    assert (out / rows[0]["file"]).exists()


# ---------------------------------------------------------------------------
# CLI behaviour
# ---------------------------------------------------------------------------


def _snapshot(directory: Path):
    if not directory.exists():
        return None
    return {
        str(p.relative_to(directory)): p.read_bytes()
        for p in sorted(directory.rglob("*"))
        if p.is_file()
    }


def test_dry_run_writes_nothing_to_a_new_directory(tmp_path):
    trace_file = write_spans(tmp_path / "spans.jsonl", [node_span(duration_ms=25_000.0)])
    out = tmp_path / "cases"
    code = trace_cases.main(
        ["--traces", str(trace_file), "--out-dir", str(out), "--dry-run", "--json"]
    )
    assert code == 0
    assert not out.exists(), "--dry-run created the output directory"


def test_dry_run_leaves_an_existing_store_byte_identical(tmp_path):
    out = tmp_path / "cases"
    seeded = run_miner(tmp_path / "seed", [node_span(duration_ms=25_000.0)], out_dir=out)
    trace_cases.write_cases(out, seeded.new_cases)
    before = _snapshot(out)

    trace_file = write_spans(
        tmp_path / "more.jsonl",
        [node_span(span_id="n9", trace_id="t9", name="editor_pass_node", duration_ms=25_000.0)],
    )
    trace_cases.main(["--traces", str(trace_file), "--out-dir", str(out), "--dry-run"])
    assert _snapshot(out) == before


def test_json_summary_reports_counts(tmp_path, capsys):
    trace_file = write_spans(
        tmp_path / "spans.jsonl",
        [node_span(duration_ms=25_000.0), llm_span(input_tokens=30_000)],
    )
    trace_cases.main(
        ["--traces", str(trace_file), "--out-dir", str(tmp_path / "cases"), "--json"]
    )
    summary = json.loads(capsys.readouterr().out)
    assert summary["spans_examined"] == 2
    assert summary["traces_examined"] == 1
    assert summary["cases_new"] == 2
    assert summary["hits_by_rule"]["slow_node"] == 1
    assert summary["hits_by_rule"]["oversized_prompt"] == 1
    assert summary["rules_version"] == trace_cases.RULES_VERSION


def test_unknown_rule_is_an_error_not_a_silent_noop(tmp_path):
    code = trace_cases.main(
        ["--traces", str(tmp_path / "nope.jsonl"), "--rules", "not_a_rule", "--json"]
    )
    assert code == 2


def test_cli_writes_when_not_dry_run(tmp_path):
    trace_file = write_spans(tmp_path / "spans.jsonl", [node_span(duration_ms=25_000.0)])
    out = tmp_path / "cases"
    trace_cases.main(["--traces", str(trace_file), "--out-dir", str(out)])
    assert (out / trace_cases.MANIFEST_NAME).exists()
    assert len(trace_cases.read_manifest(out)) == 1


# ---------------------------------------------------------------------------
# Robustness
# ---------------------------------------------------------------------------


def test_malformed_lines_are_counted_and_skipped(tmp_path):
    path = tmp_path / "spans.jsonl"
    good = json.dumps(node_span(duration_ms=25_000.0))
    path.write_text(
        "\n".join(
            [
                good,
                "{not json at all",
                "[1, 2, 3]",
                json.dumps({"no": "span id"}),
                "",
                '{"span_id": "x", "trace_id": "t", "kind": "node", "dura',  # truncated
            ]
        ),
        encoding="utf-8",
    )
    result = trace_cases.mine(
        [str(path)], tmp_path / "cases", list(trace_cases.RULES), trace_cases.Thresholds()
    )
    stats = result.parsed.stats
    assert stats.spans_parsed == 1
    assert stats.malformed_lines == 4
    assert stats.blank_lines == 1
    assert len(result.new_cases) == 1


def test_missing_file_is_not_fatal(tmp_path):
    result = trace_cases.mine(
        [str(tmp_path / "does_not_exist.jsonl")],
        tmp_path / "cases",
        list(trace_cases.RULES),
        trace_cases.Thresholds(),
    )
    assert result.new_cases == []
    assert result.parsed.stats.malformed_lines == 1


def test_empty_input_produces_a_valid_empty_result(tmp_path):
    out = tmp_path / "cases"
    write_spans(tmp_path / "spans.jsonl", [])
    code = trace_cases.main(
        ["--traces", str(tmp_path / "spans.jsonl"), "--out-dir", str(out), "--json"]
    )
    assert code == 0
    # Nothing to append; an empty manifest is read back as an empty list, not
    # an error.
    assert trace_cases.read_manifest(out) == []


def test_no_traces_argument_is_not_a_crash(tmp_path):
    assert trace_cases.main(["--out-dir", str(tmp_path / "cases"), "--json"]) == 0


def test_corrupt_manifest_line_does_not_stop_dedup(tmp_path):
    out = tmp_path / "cases"
    result = run_miner(tmp_path, [node_span(duration_ms=25_000.0)], out_dir=out)
    trace_cases.write_cases(out, result.new_cases)
    with open(out / trace_cases.MANIFEST_NAME, "a", encoding="utf-8") as handle:
        handle.write("{garbage\n\n")
    again = run_miner(tmp_path, [node_span(duration_ms=25_000.0)], out_dir=out)
    assert again.new_cases == []


def test_expand_globs_is_order_independent(tmp_path):
    write_spans(tmp_path / "a.jsonl", [node_span()])
    write_spans(tmp_path / "b.jsonl", [node_span()])
    forward = trace_cases.expand_globs([str(tmp_path / "a.jsonl"), str(tmp_path / "b.jsonl")])
    backward = trace_cases.expand_globs([str(tmp_path / "b.jsonl"), str(tmp_path / "a.jsonl")])
    globbed = trace_cases.expand_globs([str(tmp_path / "*.jsonl")])
    assert forward == backward == globbed


# ---------------------------------------------------------------------------
# Honesty + hygiene
# ---------------------------------------------------------------------------


def test_production_cases_are_marked_not_replayable(tmp_path):
    """A prod span carries a draft id and nothing replayable. Say so."""
    span = {
        "name": "editor_pass_node",
        "kind": "node",
        "trace_id": "t1",
        "span_id": "n1",
        "parent_span_id": None,
        "status": "ERROR",
        "start_time": 1000.0,
        "end_time": 1001.0,
        "duration_ms": 1000.0,
        "attributes": {
            "noesis.node.name": "editor_pass_node",
            "noesis.draft.id": "draft-123",
            "noesis.run.id": "run-456",
        },
    }
    result = run_miner(tmp_path, [span])
    case = result.new_cases[0]
    assert case["identity"]["origin"] == "production"
    assert case["replay"]["replayable"] == "no"


def test_eval_cases_admit_the_fixture_is_gitignored(tmp_path):
    result = run_miner(tmp_path, [node_span(duration_ms=25_000.0)])
    replay = result.new_cases[0]["replay"]
    assert replay["replayable"] == "with_local_fixture"
    assert "GITIGNORED" in replay["note"]
    assert replay["command"].startswith("python3 scripts/eval/node_eval.py")


def test_case_records_which_rule_selected_it(tmp_path):
    result = run_miner(tmp_path, [node_span(duration_ms=25_000.0)])
    case = result.new_cases[0]
    assert case["rule"] == "slow_node"
    assert case["rule_doc"]
    assert "20000 ms" in case["why"] or ">=" in case["why"]
    assert case["source"]["span_id"] == "n1"
    assert case["source"]["trace_file"].endswith("spans.jsonl")


def test_every_rule_is_documented():
    for name, predicate in trace_cases.RULES.items():
        assert predicate.__doc__, f"rule {name} has no docstring"
        assert trace_cases.rule_doc(name)


def test_miner_imports_nothing_that_talks_to_a_service():
    source = Path(trace_cases.__file__).read_text(encoding="utf-8")
    for forbidden in ("import openai", "import requests", "import httpx",
                      "supabase", "psycopg", "urllib.request", "import socket"):
        assert forbidden not in source, f"trace_cases.py must not depend on {forbidden}"


def test_no_network_access_during_a_full_run(tmp_path, monkeypatch):
    """Belt and braces: make socket construction explode, then mine anyway."""
    import socket

    def boom(*args, **kwargs):
        raise AssertionError("trace_cases opened a socket")

    monkeypatch.setattr(socket, "socket", boom)
    trace_file = write_spans(
        tmp_path / "spans.jsonl",
        [node_span(duration_ms=25_000.0), llm_span(input_tokens=30_000, status="ERROR")],
    )
    assert trace_cases.main(["--traces", str(trace_file), "--out-dir", str(tmp_path / "c")]) == 0

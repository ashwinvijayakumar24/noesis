"""Tests for the scoped-reviewer-panel two-arm runner.

Nothing here touches the network. ``score_arm`` is driven with a stub embedder
and confirmer through ``match_kwargs``, and the node is a plain function, so the
whole suite runs at $0.

The tests that matter most are the ones guarding identity
(:func:`test_config_hash_separates_the_two_arms` and friends) and the one
guarding against a silent false negative
(:func:`test_require_flag_raises_when_flag_absent`). Both encode failures this
project has actually had.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = EVAL_DIR.parent.parent
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services" / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.eval import panel_arms  # noqa: E402


def _units() -> list[dict]:
    """The 212 label units, read straight off the label snapshot.

    ``ceiling.corpus.load_units()`` rebuilds them by atomizing the OpenReview
    gold and will make a live LLM call on a cache miss. The snapshot carries
    every field the scorer reads, so the tests use it and stay hermetic.
    """
    labels = json.loads(
        (EVAL_DIR / "ceiling" / "hand_labels.json").read_text()
    )["labels"]
    return [
        {
            "unit_id": r["unit_id"],
            "draft_id": r["draft_id"],
            "text": r["text"],
            "severity_weight": r["severity_weight"],
        }
        for r in labels
    ]


# ---------------------------------------------------------------------------
# Bands -- no bare integers
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "count,expected",
    [(0, 0), (1, 1), (9, 1), (10, 1), (11, 2), (20, 2), (21, 3), (76, 8), (212, 22)],
)
def test_band_is_ceil_ten_percent(count, expected):
    """``ceil(10%)``, matching RECAL, so the numbers stay comparable to it."""
    assert panel_arms.band(count) == expected


@pytest.mark.unit
def test_band_rejects_negative():
    with pytest.raises(ValueError):
        panel_arms.band(-1)


@pytest.mark.unit
def test_banded_carries_value_band_and_display():
    out = panel_arms.banded(30)
    assert out == {"value": 30, "band": 3, "display": "30 ± 3"}


@pytest.mark.unit
def test_every_reported_unit_count_is_banded():
    """A unit count in the output must never be a bare int.

    Guards the rule directly rather than trusting each call site.
    """
    score = panel_arms.score_arm({}, 0.44, units=_units())
    for key in ("units_matched_all_212", "units_matched_addressable_76"):
        assert set(score[key]) == {"value", "band", "display"}
    for persona, value in score["units_matched_by_persona"].items():
        assert set(value) == {"value", "band", "display"}, persona


# ---------------------------------------------------------------------------
# Identity -- the arms must not collide
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_config_hash_separates_the_two_arms():
    """The seventh incident of two things sharing one identity does not happen here."""
    off = panel_arms.build_config("off", panel_arms.PAPERS, 2, 0.44)
    on = panel_arms.build_config("on", panel_arms.PAPERS, 2, 0.44)
    h_off, h_on = panel_arms.assert_arms_separate(off, on)
    assert h_off != h_on


@pytest.mark.unit
def test_config_hash_includes_the_flag_value():
    """Not just the arm label: the flag's *value* has to be in the identity."""
    off = panel_arms.build_config("off", panel_arms.PAPERS, 2, 0.44)
    on = panel_arms.build_config("on", panel_arms.PAPERS, 2, 0.44)
    assert off["flag_name"] == on["flag_name"] == panel_arms.FLAG
    assert off["flag_value"] == ""
    assert on["flag_value"] == "1"

    # Strip the flag and the two configs become indistinguishable -- which is
    # exactly the failure this assertion exists to prevent.
    stripped_off = {k: v for k, v in off.items() if k not in ("arm", "flag_value")}
    stripped_on = {k: v for k, v in on.items() if k not in ("arm", "flag_value")}
    assert stripped_off == stripped_on
    assert panel_arms.config_hash(stripped_off) == panel_arms.config_hash(stripped_on)


@pytest.mark.unit
def test_assert_arms_separate_rejects_a_collision():
    cfg = panel_arms.build_config("off", panel_arms.PAPERS, 2, 0.44)
    with pytest.raises(AssertionError, match="collision|same arm"):
        panel_arms.assert_arms_separate(cfg, dict(cfg))


@pytest.mark.unit
def test_config_hash_moves_with_threshold_and_replicates():
    base = panel_arms.build_config("off", panel_arms.PAPERS, 2, 0.44)
    assert panel_arms.config_hash(base) != panel_arms.config_hash(
        panel_arms.build_config("off", panel_arms.PAPERS, 2, 0.55)
    )
    assert panel_arms.config_hash(base) != panel_arms.config_hash(
        panel_arms.build_config("off", panel_arms.PAPERS, 3, 0.44)
    )


@pytest.mark.unit
def test_build_config_rejects_unknown_arm():
    with pytest.raises(ValueError):
        panel_arms.build_config("sideways", panel_arms.PAPERS, 2, 0.44)


# ---------------------------------------------------------------------------
# The flag must exist before the 'on' arm means anything
# ---------------------------------------------------------------------------

class _FakeModule:
    """Stands in for ``reviewer_panel``; ``inspect.getsource`` reads the class."""


@pytest.mark.unit
def test_flag_is_implemented_detects_absence():
    import types

    mod = types.ModuleType("fake_panel")
    assert panel_arms.flag_is_implemented(mod) is False


@pytest.mark.unit
def test_flag_is_implemented_reads_source_not_attributes(tmp_path, monkeypatch):
    """The flag is read via ``os.getenv`` at call time, so it need not be a constant."""
    import importlib.util

    src = tmp_path / "fake_panel.py"
    src.write_text(
        "import os\n"
        "def scoped_enabled():\n"
        f"    return os.getenv({panel_arms.FLAG!r}, '') == '1'\n"
    )
    spec = importlib.util.spec_from_file_location("fake_panel", src)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)

    # No module-level constant carries the name...
    assert not hasattr(mod, panel_arms.FLAG)
    # ...but the source reads it, which is what counts.
    assert panel_arms.flag_is_implemented(mod) is True


@pytest.mark.unit
def test_require_flag_raises_when_flag_absent(monkeypatch):
    """A missing flag must fail loudly, not produce a delta of zero.

    Two arms run under a flag nothing reads execute identical code and report no
    difference -- a false negative indistinguishable from a real one.
    """
    import types

    monkeypatch.setitem(
        sys.modules,
        "app.workflows.draft_analysis.nodes.reviewer_panel",
        types.ModuleType("app.workflows.draft_analysis.nodes.reviewer_panel"),
    )
    with pytest.raises(panel_arms.FlagAbsent) as exc:
        panel_arms.require_flag()
    message = str(exc.value)
    assert panel_arms.FLAG in message
    assert "false negative" in message


# ---------------------------------------------------------------------------
# The $0 control-arm audit
# ---------------------------------------------------------------------------

def _fixture(tmp_path: Path, paper: str, draft: str) -> Path:
    for persona in panel_arms.PERSONAS:
        d = tmp_path / paper
        d.mkdir(parents=True, exist_ok=True)
        (d / f"reviewer_panel_node__{persona}.json").write_text(
            json.dumps({"draft_content": draft, "stage_only": True})
        )
    return tmp_path


@pytest.mark.unit
def test_audit_control_arm_reports_no_truncation_when_compaction_off(tmp_path, monkeypatch):
    """The shipped path delivers the whole manuscript -- the scope doc was wrong."""
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)
    draft = "## Introduction\n" + ("Body sentence. " * 4000) + "\n## Discussion\nThe tail."
    _fixture(tmp_path, "P1", draft)

    out = panel_arms.audit_control_arm(("P1",), state_dir=tmp_path)
    assert out["compaction_enabled"] is False
    assert out["control_is_untruncated"] is True
    assert out["safe_to_measure"] is True
    row = out["papers"][0]
    assert row["discarded_chars"] == 0
    assert row["discarded_fraction"] == 0.0
    assert row["tail_delivered"] is True


@pytest.mark.unit
def test_audit_control_arm_detects_truncation_when_compaction_on(tmp_path, monkeypatch):
    """The audit must be able to say yes, or its 'no' carries no information."""
    monkeypatch.setenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", "1")
    draft = "\n".join(
        f"## {title}\n" + ("Body sentence for this section. " * 400)
        for title in ("Introduction", "Methods", "Results", "Discussion", "Limitations")
    )
    _fixture(tmp_path, "P1", draft)

    out = panel_arms.audit_control_arm(("P1",), state_dir=tmp_path)
    assert out["compaction_enabled"] is True
    assert out["control_is_untruncated"] is False
    # Compaction on makes the control a path production never takes.
    assert out["safe_to_measure"] is False
    assert out["papers"][0]["discarded_chars"] > 0
    assert 0.0 < out["mean_discarded_fraction"] <= 1.0


@pytest.mark.unit
def test_audit_control_arm_makes_no_llm_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    _fixture(tmp_path, "P1", "## Introduction\nShort.")
    # Kill switch on: any network path would raise. It returns, so it made none.
    assert panel_arms.audit_control_arm(("P1",), state_dir=tmp_path)["papers"]


@pytest.mark.unit
def test_audit_control_arm_skips_papers_without_fixtures(tmp_path):
    out = panel_arms.audit_control_arm(("missing",), state_dir=tmp_path)
    assert out["papers"] == []
    assert out["control_is_untruncated"] is False


# ---------------------------------------------------------------------------
# Unverified quotes -- scoping must not raise fabrication
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_unverified_quote_rate_uses_the_production_oracle():
    draft = "The model was trained on 400 examples drawn from the pilot cohort."
    items = [
        {"anchor_text": "trained on 400 examples drawn from the pilot cohort"},
        {"anchor_text": "trained on nine hundred examples from a national sample"},
        {"anchor_text": ""},  # no claim made -> out of the denominator
    ]
    out = panel_arms.unverified_quote_rate(items, draft)
    assert out["anchored"] == 2
    assert out["unverified"] == 1
    assert out["rate"] == 0.5


@pytest.mark.unit
def test_unverified_quote_rate_is_none_without_anchors():
    out = panel_arms.unverified_quote_rate([{"anchor_text": ""}], "draft")
    assert out["anchored"] == 0
    assert out["rate"] is None


# ---------------------------------------------------------------------------
# Usage / cost
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_summarize_usage_computes_cache_hit_rate():
    records = [
        {"usage": {"prompt_tokens": 1000, "cached_tokens": 600, "completion_tokens": 100,
                   "calls": 1, "estimated_usd": 0.01}},
        {"usage": {"prompt_tokens": 1000, "cached_tokens": 400, "completion_tokens": 100,
                   "calls": 1, "estimated_usd": 0.01},
         "match_usage": {"estimated_usd": 0.005}},
    ]
    out = panel_arms.summarize_usage(records, n_runs=2)
    assert out["input_tokens_total"] == 2000
    assert out["input_tokens_per_run"] == 1000.0
    assert out["cached_tokens_total"] == 1000
    assert out["cache_hit_rate"] == 0.5
    assert out["cache_reported"] is True
    assert out["total_usd"] == pytest.approx(0.025)
    assert out["usd_per_run"] == pytest.approx(0.0125)


@pytest.mark.unit
def test_summarize_usage_says_so_when_cache_is_unreported():
    """An unreported cache is not an empty cache.

    If the API stops returning ``cached_tokens`` the metric must go null and say
    ``cache_reported: false`` -- reporting 0.0 would claim the discount was
    measured and found absent, which is a different and much stronger claim.
    """
    records = [{"usage": {"prompt_tokens": 1000, "calls": 1, "estimated_usd": 0.01}}]
    out = panel_arms.summarize_usage(records, n_runs=1)
    assert out["cache_reported"] is False
    assert out["cache_hit_rate"] is None


# ---------------------------------------------------------------------------
# Mechanism check
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_per_persona_counts_report_every_persona():
    records = [
        {"persona": p, "status": "ok"} for p in panel_arms.PERSONAS
    ]
    findings = (
        [{"persona": "literature_positioning"}] * 5
        + [{"persona": "methodology"}] * 2
    )
    out = panel_arms.per_persona_counts(records, findings)
    assert set(out) == set(panel_arms.PERSONAS)
    assert out["literature_positioning"]["findings"] == 5
    assert out["literature_positioning"]["findings_per_call"] == 5.0
    # A persona that produced nothing still appears, with a zero -- absence has
    # to be visible for a uniform-vs-targeted read to be possible.
    assert out["clarity"]["findings"] == 0


@pytest.mark.unit
def test_per_persona_counts_ignore_failed_calls():
    records = [
        {"persona": "methodology", "status": "ok"},
        {"persona": "methodology", "status": "error"},
    ]
    out = panel_arms.per_persona_counts(records, [{"persona": "methodology"}])
    assert out["methodology"]["calls_ok"] == 1
    assert out["methodology"]["findings_per_call"] == 1.0


# ---------------------------------------------------------------------------
# Running an arm (no network)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_run_arm_sets_and_clears_the_flag(tmp_path, monkeypatch):
    monkeypatch.delenv(panel_arms.FLAG, raising=False)
    _fixture(tmp_path, "P1", "## Introduction\nText.")
    seen: list[str] = []

    def fake_replay(node, paper, node_func, **kwargs):
        seen.append(__import__("os").environ.get(panel_arms.FLAG, ""))
        node_func({"draft_content": "x"})
        return {"status": "ok", "paper_id": paper,
                "state_fixture": str(tmp_path / paper / f"reviewer_panel_node__{kwargs['reviewer_type']}.json")}

    def fake_node(state):
        return {"reviewer_outputs": [{"reviewer_id": "r", "weaknesses": ["w"]}]}

    panel_arms.run_arm("on", ("P1",), 1, state_dir=tmp_path,
                       replay=fake_replay, node_func=fake_node)
    assert seen == ["1"] * len(panel_arms.PERSONAS)

    seen.clear()
    panel_arms.run_arm("off", ("P1",), 1, state_dir=tmp_path,
                       replay=fake_replay, node_func=fake_node)
    assert seen == [""] * len(panel_arms.PERSONAS)


@pytest.mark.unit
def test_run_arm_captures_findings_tagged_with_persona(tmp_path, monkeypatch):
    monkeypatch.delenv(panel_arms.FLAG, raising=False)
    _fixture(tmp_path, "P1", "## Introduction\nText.")

    def fake_replay(node, paper, node_func, **kwargs):
        node_func({"draft_content": "x"})
        return {"status": "ok", "paper_id": paper,
                "state_fixture": str(tmp_path / paper / f"reviewer_panel_node__{kwargs['reviewer_type']}.json")}

    def fake_node(state):
        return {"reviewer_outputs": [
            {"reviewer_id": "r", "issues": [{"problem": "A real problem", "anchor_text": "Text."}]}
        ]}

    records = panel_arms.run_arm("off", ("P1",), 1, state_dir=tmp_path,
                                 replay=fake_replay, node_func=fake_node)
    assert len(records) == len(panel_arms.PERSONAS)
    assert {r["persona"] for r in records} == set(panel_arms.PERSONAS)
    for record in records:
        assert record["n_findings"] == 1
        assert record["_findings"][0]["persona"] == record["persona"]


@pytest.mark.unit
def test_run_arm_produces_the_expected_number_of_calls(tmp_path):
    _fixture(tmp_path, "P1", "t")
    _fixture(tmp_path, "P2", "t")
    calls = []

    def fake_replay(node, paper, node_func, **kwargs):
        calls.append((paper, kwargs["reviewer_type"], kwargs["repeat_index"]))
        return {"status": "error", "paper_id": paper, "state_fixture": "x"}

    panel_arms.run_arm("off", ("P1", "P2"), 3, state_dir=tmp_path,
                       replay=fake_replay, node_func=lambda s: {})
    # 2 papers x 3 replicates = 6 runs, each a 3-persona panel.
    assert len(calls) == 6 * len(panel_arms.PERSONAS)
    assert len({(p, r) for p, _, r in calls}) == 6


# ---------------------------------------------------------------------------
# Scoring (stubbed matcher -- no network)
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_score_arm_reports_both_denominators(tmp_path):
    """Both 76 and 212, always; one without the other is not comparable."""
    units = _units()
    target = next(u for u in units if u["draft_id"] == "10eQ4Cfh8p")

    def embedder(texts):
        # Identical vectors -> cosine 1.0 -> everything clears the prefilter.
        return [[1.0, 0.0] for _ in texts]

    def confirmer(pairs):
        # The matcher batches by an ``index`` key and requires it back.
        return [
            {"index": p["index"], "confirmed": p["unit_id"] == target["unit_id"],
             "reason": "stub"}
            for p in pairs
        ]

    findings = {"10eQ4Cfh8p": [{"text": "a finding", "persona": "methodology"}]}
    out = panel_arms.score_arm(
        findings, 0.44, cache_dir=tmp_path, units=units,
        match_kwargs={"embedder": embedder, "confirmer": confirmer},
    )
    assert out["n_units_total"] == 212
    assert out["n_units_addressable"] == 76
    assert out["units_matched_all_212"]["value"] == 1
    assert out["recall_all_212"] == pytest.approx(1 / 212, abs=1e-4)
    assert out["severity_recall_all_212"] is not None
    assert out["units_matched_by_persona"]["methodology"]["value"] <= 1


@pytest.mark.unit
def test_score_arm_attributes_units_to_the_persona_that_found_them(tmp_path):
    """The mechanism check depends on this attribution being right."""
    units = _units()
    target = next(u for u in units if u["draft_id"] == "10eQ4Cfh8p")

    def embedder(texts):
        return [[1.0, 0.0] for _ in texts]

    def confirmer(pairs):
        return [
            {"index": p["index"],
             "confirmed": p["unit_id"] == target["unit_id"]
             and p["noesis_text"] == "lit finding",
             "reason": "stub"}
            for p in pairs
        ]

    findings = {
        "10eQ4Cfh8p": [
            {"text": "lit finding", "persona": "literature_positioning"},
            {"text": "clarity finding", "persona": "clarity"},
        ]
    }
    out = panel_arms.score_arm(
        findings, 0.44, cache_dir=tmp_path, units=units,
        match_kwargs={"embedder": embedder, "confirmer": confirmer},
    )
    by_persona = out["units_matched_by_persona"]
    assert by_persona["clarity"]["value"] == 0
    assert by_persona["methodology"]["value"] == 0
    # literature_positioning gets it only if the unit is in the addressable 76.
    assert by_persona["literature_positioning"]["value"] in (0, 1)


@pytest.mark.unit
def test_score_arm_handles_an_arm_that_found_nothing(tmp_path):
    out = panel_arms.score_arm({"10eQ4Cfh8p": []}, 0.44, cache_dir=tmp_path, units=_units())
    assert out["units_matched_all_212"]["value"] == 0
    assert out["recall_all_212"] == 0.0
    assert all(v["value"] == 0 for v in out["units_matched_by_persona"].values())


@pytest.mark.unit
def test_score_arm_restores_the_global_threshold(tmp_path):
    """``COS_THRESHOLD`` is module state; leaking it would silently retune every
    later scorer in the same process."""
    from scripts.eval import match as match_mod

    before = match_mod.COS_THRESHOLD
    panel_arms.score_arm({"10eQ4Cfh8p": []}, 0.99, cache_dir=tmp_path, units=_units())
    assert match_mod.COS_THRESHOLD == before


# ---------------------------------------------------------------------------
# Sink
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_append_record_is_append_only(tmp_path):
    sink = tmp_path / "panel_arms.jsonl"
    panel_arms.append_record({"arm": "off"}, sink)
    panel_arms.append_record({"arm": "on"}, sink)
    rows = [json.loads(line) for line in sink.read_text().splitlines() if line.strip()]
    assert [r["arm"] for r in rows] == ["off", "on"]


@pytest.mark.unit
def test_append_record_creates_parent(tmp_path):
    sink = tmp_path / "nested" / "deeper" / "panel_arms.jsonl"
    panel_arms.append_record({"arm": "off"}, sink)
    assert sink.exists()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_audit_only_makes_no_calls_and_exits_zero(capsys, monkeypatch):
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)
    assert panel_arms.main(["--audit-only"]) == 0
    out = capsys.readouterr().out
    assert "CONTROL ARM" in out
    assert "control_is_untruncated" in out
    # The assembly measurement is the cost side and is free; it must be in the
    # audit output, not deferred to the paid run.
    assert "ASSEMBLY" in out
    assert "prefix_surviving_fraction" in out


@pytest.mark.unit
def test_cli_refuses_to_spend_when_compaction_is_on(capsys, monkeypatch):
    """Measuring against a path production never takes buys nothing."""
    monkeypatch.setenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", "1")
    assert panel_arms.main(["--arm", "off", "--yes"]) == 2
    assert "Refusing to spend" in capsys.readouterr().out


@pytest.mark.unit
def test_cli_dry_run_without_yes_makes_no_calls(capsys, monkeypatch):
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)
    rc = panel_arms.main(["--arm", "off"])
    assert rc == 0
    assert "Re-run with --yes" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# The assembly measurement -- the cost side, free
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_measure_assembly_reports_both_sides_of_the_trade(monkeypatch):
    """Input falls AND the cacheable prefix falls. Reporting one alone misleads.

    Quoting only the input reduction makes scoping look free; quoting only the
    forfeited prefix makes it look purely costly. The dollar outcome needs both,
    so both must be present in the result.
    """
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)
    monkeypatch.delenv(panel_arms.FLAG, raising=False)

    out = panel_arms.measure_assembly()
    assert out["papers"], "expected the committed fixtures to be present"

    # Scoping sends each persona only its lane, so total input must fall.
    assert out["on_total_chars"] < out["off_total_chars"]
    assert out["input_change"] < 0

    # The manuscript *was* the shared prefix, so most of it must be forfeited.
    assert out["on_prefix_chars"] < out["off_prefix_chars"]
    assert 0.0 <= out["prefix_surviving_fraction"] < 1.0


@pytest.mark.unit
def test_measure_assembly_leaves_the_flag_unset(monkeypatch):
    """The measurement toggles the flag; it must not leak it to later work."""
    monkeypatch.delenv(panel_arms.FLAG, raising=False)
    panel_arms.measure_assembly()
    assert panel_arms.FLAG not in __import__("os").environ


@pytest.mark.unit
def test_measure_assembly_makes_no_llm_calls(monkeypatch):
    monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
    monkeypatch.delenv(panel_arms.FLAG, raising=False)
    # Kill switch on: any network path raises. It returns, so it made none.
    assert panel_arms.measure_assembly()["papers"]


@pytest.mark.unit
def test_scoped_arm_still_covers_every_persona(monkeypatch):
    """No persona may be assembled down to nothing.

    A persona given an empty manuscript block would score zero for a reason
    that has nothing to do with the hypothesis.
    """
    monkeypatch.delenv(panel_arms.FLAG, raising=False)
    out = panel_arms.measure_assembly()
    for row in out["papers"]:
        for persona, chars in row["on_per_persona_chars"].items():
            assert chars > 0, f"{row['paper_id']}/{persona} assembled to nothing"


# ---------------------------------------------------------------------------
# Scoped coverage -- the build's own acceptance criterion, evaluated
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_measure_scoped_coverage_is_stable_across_window_sizes(monkeypatch):
    """Boundary loss must not be what drives the coverage number.

    Windows straddling a section boundary miss, biasing coverage downward. If
    the estimate moved a lot between window sizes it would be measuring its own
    slicing rather than the assembly, and could not support a regression claim.
    """
    monkeypatch.delenv(panel_arms.FLAG, raising=False)
    wide = panel_arms.measure_scoped_coverage(window=80)
    narrow = panel_arms.measure_scoped_coverage(window=40)
    by_paper = {r["paper_id"]: r["coverage"] for r in narrow["papers"]}
    for row in wide["papers"]:
        assert abs(row["coverage"] - by_paper[row["paper_id"]]) < 0.10, row["paper_id"]


@pytest.mark.unit
def test_measure_scoped_coverage_leaves_the_flag_unset(monkeypatch):
    monkeypatch.delenv(panel_arms.FLAG, raising=False)
    panel_arms.measure_scoped_coverage()
    assert panel_arms.FLAG not in __import__("os").environ


@pytest.mark.unit
def test_measure_scoped_coverage_flags_papers_that_lose_text(monkeypatch):
    """On this corpus the budget binds above ~31k chars; that must be visible."""
    monkeypatch.delenv(panel_arms.FLAG, raising=False)
    out = panel_arms.measure_scoped_coverage()
    assert out["papers"], "expected the committed fixtures to be present"
    # Every paper is scored, and the verdict is derived, not assumed.
    assert out["coverage_complete"] == (not out["papers_below_95pct"])
    assert 0.0 <= out["min_coverage"] <= 1.0


# ---------------------------------------------------------------------------
# Scoring spend must not be reported as zero
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_summarize_budget_folds_a_slice_of_events():
    """Scoring happens outside replay_once, so its spend needs its own fold.

    The first recorded run reported ``match_usd: 0.0`` while the matcher was
    making 371 live confirmations -- a confidently wrong zero. This is the fold
    that fixes it.
    """
    class _E:
        def __init__(self, p, c, o, usd):
            self.prompt_tokens, self.cached_tokens = p, c
            self.completion_tokens, self.estimated_usd = o, usd

    out = panel_arms._summarize_budget([_E(100, 40, 10, 0.01), _E(200, 0, 20, 0.02)])
    assert out == {
        "calls": 2,
        "prompt_tokens": 300,
        "cached_tokens": 40,
        "completion_tokens": 30,
        "estimated_usd": 0.03,
    }


@pytest.mark.unit
def test_summarize_budget_of_nothing_is_zero_not_none():
    assert panel_arms._summarize_budget([])["estimated_usd"] == 0.0

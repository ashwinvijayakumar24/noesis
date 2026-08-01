"""Tests for the cost/quality cascade sweep.

Hermetic: nothing here makes a network call. The two paths that would --
``score_arm`` (matcher) and ``run_arm`` (node replay) -- both take injection
seams for exactly that reason.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = EVAL_DIR.parents[1]
for _p in (str(REPO_ROOT), str(REPO_ROOT / "services" / "backend")):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from scripts.eval import cascade_arms as ca  # noqa: E402


# ---------------------------------------------------------------------------
# Bands -- no bare integers escape this harness
# ---------------------------------------------------------------------------

def test_band_is_ten_percent_rounded_up_min_one():
    assert ca.band(0) == 1
    assert ca.band(1) == 1
    assert ca.band(22) == 3
    assert ca.band(54) == 6


def test_banded_carries_value_band_and_display():
    out = ca.banded(22)
    assert out == {"value": 22, "band": 3, "display": "22 ± 3"}


# ---------------------------------------------------------------------------
# Identity -- the hash must include the per-node model assignment
# ---------------------------------------------------------------------------

def _cfg(node="reviewer_panel_node", model="gpt-5-mini", **kw):
    kw.setdefault("papers", ("a", "b"))
    kw.setdefault("repeats", 1)
    kw.setdefault("threshold", 0.44)
    return ca.arm_config(node, model, **kw)


def test_config_includes_the_full_model_assignment_not_just_the_swept_node():
    cfg = _cfg()
    assert cfg["model_assignment"]["reviewer_panel"] == "gpt-5-mini"
    # Every other node is pinned to its production model in the identity.
    assert cfg["model_assignment"]["extract_claims"] == "gpt-5.2-chat-latest"
    assert cfg["model_assignment"]["meta_reviewer"] == "gpt-5.2-chat-latest"
    assert cfg["model_assignment"]["structural_checks"] == "gpt-5.2-chat-latest"


def test_control_arm_leaves_every_node_on_its_production_model():
    cfg = _cfg(model=ca.CONTROL)
    assert set(cfg["model_assignment"].values()) == {"gpt-5.2-chat-latest"}


def test_hash_separates_arms_that_differ_only_by_model():
    a = ca.config_hash(_cfg(model="gpt-5-mini"))
    b = ca.config_hash(_cfg(model="gpt-5-nano"))
    c = ca.config_hash(_cfg(model=ca.CONTROL))
    assert len({a, b, c}) == 3


def test_hash_separates_the_same_model_applied_to_different_nodes():
    a = ca.config_hash(_cfg(node="reviewer_panel_node", model="gpt-5-mini"))
    b = ca.config_hash(_cfg(node="meta_reviewer_node", model="gpt-5-mini"))
    assert a != b


def test_hash_is_stable_across_calls():
    assert ca.config_hash(_cfg()) == ca.config_hash(_cfg())


def test_assert_hashes_distinct_raises_on_collision():
    rec = {"config_hash": "dup", "config": {"node": "n", "arm_model": "m"}}
    other = {"config_hash": "dup", "config": {"node": "n2", "arm_model": "m2"}}
    with pytest.raises(AssertionError, match="collision"):
        ca.assert_hashes_distinct([rec, other])


def test_assert_hashes_distinct_passes_on_real_arms():
    arms = [
        {"config_hash": ca.config_hash(_cfg(model=m)), "config": _cfg(model=m)}
        for m in (ca.CONTROL, "gpt-5-mini", "gpt-5-nano")
    ]
    ca.assert_hashes_distinct(arms)


# ---------------------------------------------------------------------------
# Routing seam
# ---------------------------------------------------------------------------

def test_routed_sets_and_restores_the_override():
    from app.workflows.draft_analysis.model_routing import env_var_for, model_for

    var = env_var_for("reviewer_panel")
    os.environ.pop(var, None)
    assert model_for("reviewer_panel", "gpt-5.2-chat-latest") == "gpt-5.2-chat-latest"
    with ca.routed("reviewer_panel", "gpt-5-mini"):
        assert model_for("reviewer_panel", "gpt-5.2-chat-latest") == "gpt-5-mini"
    assert var not in os.environ


def test_routed_with_none_clears_an_inherited_override():
    from app.workflows.draft_analysis.model_routing import env_var_for, model_for

    var = env_var_for("meta_reviewer")
    os.environ[var] = "gpt-5-nano"
    try:
        with ca.routed("meta_reviewer", None):
            assert model_for("meta_reviewer", "gpt-5.2-chat-latest") == "gpt-5.2-chat-latest"
        assert os.environ[var] == "gpt-5-nano"
    finally:
        os.environ.pop(var, None)


def test_every_swept_node_maps_to_a_real_routed_site():
    from app.workflows.draft_analysis.model_routing import ROUTED_SITES

    assert set(ca.NODE_SITES.values()) <= set(ROUTED_SITES)


# ---------------------------------------------------------------------------
# Structural probe -- the thing that matters more than quality at these tiers
# ---------------------------------------------------------------------------

def test_truncation_counts_as_structurally_broken():
    calls = [{"model": "gpt-5-nano", "finish_reason": "length", "content_chars": 0,
              "content_empty": True, "parsed_is_none": True, "completion_tokens": 1500}]
    out = ca.summarize_structure(calls, "structural_checks")
    assert out["structurally_broken"] is True
    assert out["finish_length"] == 1
    assert out["content_empty"] == 1
    assert out["completion_budget"] == 1500


def test_api_error_counts_as_structurally_broken_and_keeps_a_sample():
    calls = [{"model": "gpt-5-mini", "api_error": "BadRequestError",
              "api_error_message": "temperature does not support 0"}]
    out = ca.summarize_structure(calls, "meta_reviewer_node")
    assert out["structurally_broken"] is True
    assert out["api_error_types"] == ["BadRequestError"]
    assert "temperature" in out["api_error_sample"]


def test_a_clean_arm_is_not_reported_as_broken():
    calls = [{"model": "gpt-5.2-chat-latest", "finish_reason": "stop", "content_chars": 900,
              "content_empty": False, "refusal": False, "parsed_is_none": False,
              "completion_tokens": 400}]
    out = ca.summarize_structure(calls, "reviewer_panel_node")
    assert out["structurally_broken"] is False
    assert out["finish_reasons"] == {"stop": 1}


def test_refusal_counts_as_broken():
    calls = [{"model": "gpt-5-nano", "finish_reason": "stop", "content_empty": False,
              "refusal": True, "parsed_is_none": False}]
    assert ca.summarize_structure(calls, "extract_claims")["structurally_broken"] is True


def test_probe_records_shape_without_capturing_text():
    """The fixtures are real manuscripts; the probe must not copy their text."""
    from openai.resources.chat.completions import completions as c

    class _Msg:
        content = "a very long completion body that must not be stored"
        refusal = None
        parsed = {"ok": True}

    class _Choice:
        finish_reason = "stop"
        message = _Msg()

    class _Usage:
        completion_tokens = 12
        prompt_tokens = 34

    class _Resp:
        choices = [_Choice()]
        usage = _Usage()

    original = c.Completions.parse
    c.Completions.parse = lambda self, **kw: _Resp()
    try:
        sink: list = []
        with ca.structural_probe(sink):
            c.Completions.parse(object(), model="gpt-5-mini")
    finally:
        c.Completions.parse = original

    assert len(sink) == 1
    assert sink[0]["content_chars"] == len(_Msg.content)
    assert sink[0]["finish_reason"] == "stop"
    assert sink[0]["parsed_is_none"] is False
    blob = json.dumps(sink)
    assert "must not be stored" not in blob


def test_probe_restores_the_sdk_methods():
    from openai.resources.chat.completions import completions as c

    before_sync, before_async = c.Completions.parse, c.AsyncCompletions.parse
    with ca.structural_probe([]):
        assert c.Completions.parse is not before_sync
    assert c.Completions.parse is before_sync
    assert c.AsyncCompletions.parse is before_async


# ---------------------------------------------------------------------------
# Findings extraction
# ---------------------------------------------------------------------------

def test_reviewer_panel_findings_come_from_issues_and_weaknesses():
    state = {"reviewer_outputs": [
        {"reviewer_type": "clarity",
         "issues": [{"problem": "Section 3 is unclear"}],
         "weaknesses": ["No ablation"]},
    ]}
    out = ca.findings_from_state("reviewer_panel_node", state)
    assert {f["text"] for f in out} == {"Section 3 is unclear", "No ablation"}
    assert {f["persona"] for f in out} == {"clarity"}


def test_structural_findings_prefer_feedback_text_and_fall_back():
    state = {"structural_feedback": [
        {"feedback_text": "Missing limitations section"},
        {"feedback_text": "", "specific_issue": "No related work"},
        {"feedback_text": "", "specific_issue": ""},
    ]}
    out = ca.findings_from_state("structural_checks", state)
    assert [f["text"] for f in out] == ["Missing limitations section", "No related work"]


def test_meta_review_findings_handle_dicts_and_strings():
    state = {"meta_review": {"must_address": [{"problem": "Weak baseline"}],
                             "consensus_weaknesses": ["Unclear novelty"]}}
    out = ca.findings_from_state("meta_reviewer_node", state)
    assert {f["text"] for f in out} == {"Weak baseline", "Unclear novelty"}


def test_meta_review_extractor_reads_keys_the_schema_actually_defines():
    """The v1 bug: reading keys the node never writes reports every arm as zero."""
    from app.workflows.draft_analysis.schemas import MetaReviewOutput

    fields = set(MetaReviewOutput.model_fields)
    for key in ("must_address", "nice_to_address", "consensus_weaknesses"):
        assert key in fields, key


def test_extract_claims_yields_claims_and_is_not_scorable():
    state = {"claims": [{"claim_text": "We achieve SOTA"}]}
    out = ca.findings_from_state("extract_claims", state)
    assert [f["text"] for f in out] == ["We achieve SOTA"]
    # The point: claims are not critiques, so this node is never scored.
    assert "extract_claims" not in ca.SCORABLE_NODES


def test_findings_are_empty_when_the_node_produced_nothing():
    for node in ca.NODE_SITES:
        assert ca.findings_from_state(node, {}) == []


# ---------------------------------------------------------------------------
# Scoring -- both denominators, always
# ---------------------------------------------------------------------------

@pytest.fixture
def fake_units():
    return [
        {"unit_id": "u1", "draft_id": "p1", "severity_weight": 2.0, "text": "no ablation"},
        {"unit_id": "u2", "draft_id": "p1", "severity_weight": 1.0, "text": "typo"},
    ]


def test_score_arm_reports_both_denominators(monkeypatch, fake_units, tmp_path):
    labels = {"labels": [
        {"unit_id": "u1", "category": "defect_addressable"},
        {"unit_id": "u2", "category": "surface_copyedit"},
    ]}
    monkeypatch.setattr(ca, "EVAL_DIR", tmp_path)
    (tmp_path / "ceiling").mkdir()
    (tmp_path / "ceiling" / "hand_labels.json").write_text(json.dumps(labels))

    from scripts.eval import match as match_mod

    monkeypatch.setattr(match_mod, "match",
                        lambda items, targets, stats=None, **kw: [
                            {"unit_id": "u1", "noesis_id": items[0]["id"], "confirmed": True}
                        ])
    out = ca.score_arm({"p1": [{"text": "missing ablation"}]}, 0.44, units=fake_units)

    assert out["n_units_total"] == 2
    assert out["n_units_addressable"] == 1
    assert out["units_matched_addressable_76"]["display"] == "1 ± 1"
    assert out["units_matched_all_212"]["display"] == "1 ± 1"
    assert out["threshold"] == 0.44


def test_score_arm_dedupes_finding_texts_before_matching(monkeypatch, fake_units, tmp_path):
    monkeypatch.setattr(ca, "EVAL_DIR", tmp_path)
    (tmp_path / "ceiling").mkdir()
    (tmp_path / "ceiling" / "hand_labels.json").write_text(
        json.dumps({"labels": [{"unit_id": "u1", "category": "defect_addressable"}]})
    )
    seen: list[int] = []
    from scripts.eval import match as match_mod
    monkeypatch.setattr(match_mod, "match",
                        lambda items, targets, stats=None, **kw: seen.append(len(items)) or [])
    findings = [{"text": "same"}, {"text": "same"}, {"text": "other"}]
    ca.score_arm({"p1": findings}, 0.44, units=fake_units)
    assert seen == [2]


def test_score_arm_restores_the_global_threshold(monkeypatch, fake_units, tmp_path):
    monkeypatch.setattr(ca, "EVAL_DIR", tmp_path)
    (tmp_path / "ceiling").mkdir()
    (tmp_path / "ceiling" / "hand_labels.json").write_text(json.dumps({"labels": []}))
    from scripts.eval import match as match_mod
    before = match_mod.COS_THRESHOLD
    monkeypatch.setattr(match_mod, "match",
                        lambda items, targets, stats=None, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        ca.score_arm({"p1": [{"text": "x"}]}, 0.99, units=fake_units)
    assert match_mod.COS_THRESHOLD == before


# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------

def test_summarize_usage_reports_per_run_figures():
    records = [
        {"usage": {"calls": 1, "estimated_usd": 0.10, "prompt_tokens": 1000,
                   "completion_tokens": 500, "cached_tokens": 0, "unpriced_calls": 0,
                   "by_model": {"gpt-5.2-chat-latest": 1}}},
        {"usage": {"calls": 1, "estimated_usd": 0.20, "prompt_tokens": 2000,
                   "completion_tokens": 500, "cached_tokens": 100, "unpriced_calls": 0,
                   "by_model": {"gpt-5.2-chat-latest": 1}}},
    ]
    out = ca.summarize_usage(records, 2)
    assert out["usd_total"] == 0.3
    assert out["usd_per_run"] == 0.15
    assert out["tokens_per_run"] == 2000.0
    assert out["models_seen"] == {"gpt-5.2-chat-latest": 2}


def test_summarize_usage_surfaces_unpriced_calls():
    """An unpriced model silently costs $0 in the ledger; it must stay visible."""
    records = [{"usage": {"calls": 1, "estimated_usd": 0.0, "prompt_tokens": 10,
                          "completion_tokens": 10, "cached_tokens": 0,
                          "unpriced_calls": 1, "by_model": {"mystery": 1}}}]
    assert ca.summarize_usage(records, 1)["unpriced_calls"] == 1


def test_every_swept_model_is_priced():
    """A tier with no price entry prices as $0 and escapes the spend ceiling."""
    from app.core.llm_budget import get_price

    for model in ("gpt-5.2-chat-latest", "gpt-5-mini", "gpt-5-nano", "gpt-5.1"):
        assert get_price(model) is not None, model


# ---------------------------------------------------------------------------
# run_arm wiring, with the replay seam
# ---------------------------------------------------------------------------

def test_run_arm_sets_the_override_for_the_swept_node_only(monkeypatch):
    from app.workflows.draft_analysis.model_routing import env_var_for

    observed: list[dict[str, str | None]] = []

    def fake_replay(node, paper, node_func, **kw):
        observed.append({
            "meta": os.environ.get(env_var_for("meta_reviewer")),
            "panel": os.environ.get(env_var_for("reviewer_panel")),
        })
        return {"status": "ok", "usage": {}}

    monkeypatch.setattr(ca, "NODE_COMPLETION_BUDGET", ca.NODE_COMPLETION_BUDGET)
    from scripts.eval import node_eval
    monkeypatch.setattr(node_eval, "_node_registry", lambda: {"meta_reviewer_node": lambda s: {}})

    ca.run_arm("meta_reviewer_node", "gpt-5-mini", papers=("p1",), repeats=1, replay=fake_replay)

    assert observed == [{"meta": "gpt-5-mini", "panel": None}]
    assert env_var_for("meta_reviewer") not in os.environ


def test_run_arm_control_sets_no_override(monkeypatch):
    from app.workflows.draft_analysis.model_routing import env_var_for

    seen: list[str | None] = []

    def fake_replay(node, paper, node_func, **kw):
        seen.append(os.environ.get(env_var_for("meta_reviewer")))
        return {"status": "ok", "usage": {}}

    from scripts.eval import node_eval
    monkeypatch.setattr(node_eval, "_node_registry", lambda: {"meta_reviewer_node": lambda s: {}})
    ca.run_arm("meta_reviewer_node", ca.CONTROL, papers=("p1",), repeats=1, replay=fake_replay)
    assert seen == [None]


def test_run_arm_fans_out_reviewer_panel_over_personas(monkeypatch):
    calls: list[str | None] = []

    def fake_replay(node, paper, node_func, **kw):
        calls.append(kw.get("reviewer_type"))
        return {"status": "ok", "usage": {}}

    from scripts.eval import node_eval
    monkeypatch.setattr(node_eval, "_node_registry", lambda: {"reviewer_panel_node": lambda s: {}})
    ca.run_arm("reviewer_panel_node", ca.CONTROL, papers=("p1",), repeats=1, replay=fake_replay)
    assert sorted(calls) == sorted(ca.PERSONAS)


# ---------------------------------------------------------------------------
# Sink is append-only
# ---------------------------------------------------------------------------

def test_append_records_never_truncates(tmp_path):
    sink = tmp_path / "cascade_arms.jsonl"
    ca.append_records([{"a": 1}], sink)
    ca.append_records([{"a": 2}], sink)
    rows = [json.loads(l) for l in sink.read_text().splitlines()]
    assert rows == [{"a": 1}, {"a": 2}]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def test_a_scoring_failure_does_not_discard_paid_replays(monkeypatch, tmp_path, capsys):
    """match.py raising must not throw away measurements already billed for."""
    monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "1")
    sink = tmp_path / "out.jsonl"
    from scripts.eval import env as env_mod
    monkeypatch.setattr(env_mod, "load_backend_env", lambda *a, **k: [])
    monkeypatch.setattr(
        ca, "run_arm",
        lambda *a, **k: ([{"status": "ok", "usage": {}, "n_findings": 1}], {"p": [{"text": "x"}]}, []),
    )
    monkeypatch.setattr(
        ca, "score_arm",
        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("Missing confirmation for pair index 101")),
    )
    rc = ca.main(["--node", "meta_reviewer_node", "--arm", "control",
                  "--paper", "p", "--results", str(sink)])
    assert rc == 0
    rows = [json.loads(l) for l in sink.read_text().splitlines()]
    replays = [r for r in rows if r.get("status") == "ok"]
    arms = [r for r in rows if r.get("record_type") == "arm"]
    assert replays, "the paid replay must survive a scoring crash"
    assert arms[0]["score"] is None
    assert "Missing confirmation" in arms[0]["score_error"]


def test_main_refuses_to_run_without_a_spend_ceiling(monkeypatch, capsys):
    monkeypatch.delenv("NOESIS_LLM_MAX_SPEND_USD", raising=False)
    monkeypatch.setattr(ca, "main", ca.main)
    from scripts.eval import env as env_mod
    monkeypatch.setattr(env_mod, "load_backend_env", lambda *a, **k: [])
    rc = ca.main(["--node", "meta_reviewer_node", "--arm", "control"])
    assert rc == 2
    assert "NOESIS_LLM_MAX_SPEND_USD" in capsys.readouterr().err


def test_dry_run_spends_nothing_and_prints_distinct_hashes(monkeypatch, capsys):
    monkeypatch.setenv("NOESIS_LLM_MAX_SPEND_USD", "1")
    from scripts.eval import env as env_mod
    monkeypatch.setattr(env_mod, "load_backend_env", lambda *a, **k: [])
    rc = ca.main(["--node", "meta_reviewer_node", "--arm", "control",
                  "--arm", "gpt-5-mini", "--dry-run"])
    assert rc == 0
    out = capsys.readouterr().out
    hashes = [l.split("hash=")[1].strip() for l in out.splitlines() if "hash=" in l]
    assert len(hashes) == 2 and len(set(hashes)) == 2

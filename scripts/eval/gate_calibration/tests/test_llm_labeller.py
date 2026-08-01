"""Unit tests for gate_calibration.llm_labeller.

NO TEST HERE MAKES A NETWORK CALL OR SPENDS MONEY. Every "LLM call" is a stub
transport; several tests assert the transport was NEVER invoked, which is the
only way to prove a guardrail blocks rather than merely records.

All file I/O is under ``tmp_path``. Nothing reads or writes the real
``scripts/eval/results/``, the real ``labels.jsonl``, or the real cache.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

EVAL_DIR = Path(__file__).resolve().parents[2]
BACKEND_DIR = EVAL_DIR.parents[1] / "services" / "backend"
for _p in (str(EVAL_DIR), str(BACKEND_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from app.core import llm_budget  # noqa: E402
from app.core.llm_budget import LLMBudgetExceeded, LLMCallBlocked  # noqa: E402

from gate_calibration import llm_labeller as LL  # noqa: E402
from gate_calibration import label_cli as L  # noqa: E402


#: Env that must not leak in from the developer's shell. A stray
#: NOESIS_LLM_KILL_SWITCH would make every "was it blocked" assertion pass for
#: the wrong reason.
_AMBIENT_ENV = (
    "NOESIS_LLM_KILL_SWITCH",
    "EVAL_REPLAY_ONLY",
    "NOESIS_LLM_MAX_CALLS",
    "NOESIS_LLM_MAX_SPEND_USD",
    "NOESIS_LLM_USAGE_LOG",
)

#: Distinctive enough that a substring match for it is meaningful.
FAKE_KEY = "sk-ant-TESTKEY-must-never-be-written-anywhere-0123456789"


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for name in _AMBIENT_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ANTHROPIC_API_KEY", FAKE_KEY)
    llm_budget.reset()
    yield
    llm_budget.reset()


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def make_export(
    dirpath: Path,
    run_id: str,
    *,
    n_tasks: int = 2,
    parser_quality: float = 0.6923076923076923,
    page_anchor: float = 0.3181818181818182,
    verbatim: float = 0.7272727272727273,
) -> Path:
    """A minimally-shaped export. The hidden scores are deliberately long
    irrational-looking floats so a leak of one is unmistakable in the prompt."""
    tasks = [
        {
            "severity": ["critical", "major", "minor"][i % 3],
            "task_type": "reproducibility",
            "section": f"Section {i}",
            "page_number": i + 1,
            "problem": f"Problem statement {i}",
            "why_it_matters": f"Why {i}",
            "suggested_action": f"Do {i}",
            "anchor_text": f"quoted passage {i}",
        }
        for i in range(n_tasks)
    ]
    payload = {
        "eval_metadata": {
            "draft_file": run_id.split("__")[0],
            "corpus": "no-corpus",
            "analysis_run_id": f"run-{run_id}",
            "generated_at": "2026-06-21T00:00:00Z",
        },
        "draft": {"title": f"[EVAL] {run_id}", "file_type": "pdf"},
        "analysis": {
            "word_count": 8000,
            "structure": {"page_count": 12, "sections": [{"title": "Intro"}]},
            "analysis_metadata": {
                "analysis_status": "complete",
                "readiness_score": 71,
                "revision_quality_metrics": {
                    "page_anchor_coverage": page_anchor,
                    "verbatim_anchor_coverage": verbatim,
                    "anchor_coverage": page_anchor,
                    "total_tasks": n_tasks,
                },
                "publish_gate": {
                    "gate_status": "needs_retry",
                    "publishable": False,
                    "confidence": 0.5,
                    "observed": {
                        "parser_quality_score": parser_quality,
                        "parse_blocked": False,
                    },
                },
            },
        },
        "parser_metadata": {"parser_quality_score": parser_quality},
        "durable_revision_tasks": tasks,
        "reviewer_feedback": [
            {
                "severity": "major",
                "feedback_type": "methodology",
                "section_reference": "Methods",
                "feedback_text": "The ablation is missing.",
            }
        ],
        "meta_reviews": [{"overall_recommendation": "major_revision", "must_address": ["Add ablation"]}],
    }
    path = dirpath / f"{run_id}.json"
    path.write_text(json.dumps(payload))
    return path


@pytest.fixture
def results_dir(tmp_path: Path) -> Path:
    d = tmp_path / "results"
    d.mkdir()
    make_export(d, "aaa__no-corpus__2026-06-21T01-00-00")
    make_export(d, "bbb__no-corpus__2026-06-21T02-00-00", n_tasks=0)
    return d


@pytest.fixture
def rec(results_dir: Path) -> dict:
    return L.load_export(results_dir / "aaa__no-corpus__2026-06-21T01-00-00.json")


@pytest.fixture
def rubric() -> str:
    return LL.load_rubric()


class StubTransport:
    """Records every invocation. ``calls`` is what the guardrail tests assert on."""

    def __init__(self, text: str = '{"label": "ok", "failure_family": "none", "reason": "fine"}',
                 usage: dict | None = None, status: int = 200):
        self.text = text
        self.usage = usage if usage is not None else {"input_tokens": 9000, "output_tokens": 40}
        self.status = status
        self.calls: list[dict] = []

    def __call__(self, url, *, headers, json, timeout):  # noqa: A002 - mirrors httpx.post
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        outer = self

        class _Resp:
            status_code = outer.status

            @staticmethod
            def json():
                return {
                    "content": [{"type": "text", "text": outer.text}],
                    "usage": outer.usage,
                }

        return _Resp()


# ---------------------------------------------------------------------------
# blindness -- assert on the CONSTRUCTED PROMPT, not on the intent
# ---------------------------------------------------------------------------


class TestPromptIsBlind:
    def test_prompt_contains_no_gate_verdict_and_no_score(self, rec, rubric):
        prompt = LL.build_prompt(rec, rubric)
        # The rubric is constant text that NAMES the forbidden fields as an
        # instruction not to look at them; subtract it, then scan everything
        # this prompt actually says about THIS run.
        run_view = prompt.replace(rubric, "")

        # the values themselves
        for score in (
            rec["_hidden"]["parser_quality_score"],
            rec["_hidden"]["page_anchor_coverage"],
            rec["_hidden"]["verbatim_anchor_coverage"],
        ):
            assert repr(score) not in prompt, "an exact score reached the prompt"
            assert f"{score:.3f}" not in run_view
            assert f"{score:.2f}" not in run_view

        # the field names that would carry them
        for token in ("gate_status", "publish_gate", "publishable", "needs_retry",
                      "parser_quality_score", "page_anchor_coverage",
                      "verbatim_anchor_coverage", "readiness_score",
                      "parse_blocked", "analysis_status"):
            assert token not in run_view, f"prompt leaked {token}"

        assert LL.blindness_violations(prompt, rec, rubric) == []
        LL.assert_blind(prompt, rec, rubric)  # does not raise

    def test_low_entropy_scores_are_not_matched_on(self, results_dir, rubric):
        # A score of exactly 1.0 or 0.75 cannot be policed by substring search:
        # "1.0" occurs in ordinary run text. The check must skip it rather than
        # fire on every prompt (which is how a check gets switched off).
        path = make_export(results_dir, "low__no-corpus__2026-06-21T09-00-00",
                           parser_quality=1.0, page_anchor=0.75, verbatim=1.0)
        low = L.load_export(path)
        assert LL.blindness_violations(LL.build_prompt(low, rubric), low, rubric) == []
        # ...but the field names are still policed for that same run
        leaky = LL.build_prompt(low, rubric) + "\nparser_quality_score: 1.0"
        assert LL.blindness_violations(leaky, low, rubric) != []

    def test_the_check_would_fire_if_the_rubric_were_not_subtracted(self, rec, rubric):
        # Guards the exemption itself: the only reason those field names are in
        # the prompt at all is the rubric, and nothing else may add them.
        prompt = LL.build_prompt(rec, rubric)
        assert LL.blindness_violations(prompt, rec, rubric="") != []

    def test_prompt_still_carries_the_critique(self, rec, rubric):
        prompt = LL.build_prompt(rec, rubric)
        assert "Problem statement 0" in prompt
        assert "quoted passage 0" in prompt
        assert "major_revision" in prompt

    def test_prompt_embeds_the_rubric_verbatim(self, rec, rubric):
        prompt = LL.build_prompt(rec, rubric)
        assert rubric in prompt
        assert "Definition of `degraded`" in prompt

    def test_a_leaked_score_is_detected_and_raises(self, rec, rubric):
        leaky = LL.build_prompt(rec, rubric) + f"\nparser_quality_score={rec['_hidden']['parser_quality_score']!r}"
        violations = LL.blindness_violations(leaky, rec, rubric)
        assert violations, "a leaked score must be detected"
        with pytest.raises(LL.BlindnessError):
            LL.assert_blind(leaky, rec, rubric)

    def test_blindness_is_checked_before_any_http(self, rec, rubric, tmp_path, monkeypatch):
        transport = StubTransport()
        monkeypatch.setattr(LL, "build_prompt", lambda r, rb: "leak: gate_status=ok")
        with pytest.raises(LL.BlindnessError):
            LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)
        assert transport.calls == []


# ---------------------------------------------------------------------------
# response parsing -- a malformed reply is a failure, never a silent `ok`
# ---------------------------------------------------------------------------


class TestParseResponse:
    def test_parses_a_well_formed_reply(self):
        out = LL.parse_response('{"label": "degraded", "failure_family": "D3", "reason": "no tasks"}')
        assert out == {"label": "degraded", "failure_family": "D3", "reason": "no tasks"}

    def test_tolerates_a_markdown_fence(self):
        out = LL.parse_response('```json\n{"label": "ok", "failure_family": "none", "reason": "r"}\n```')
        assert out["label"] == "ok"

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "   ",
            "The critique looks fine to me.",
            "{not json",
            '["ok"]',
            '{"label": "fine", "failure_family": "none", "reason": "r"}',
            '{"label": "ok", "failure_family": "D9", "reason": "r"}',
            '{"label": "degraded", "failure_family": "none", "reason": "r"}',
            '{"label": "ok", "failure_family": "D2", "reason": "r"}',
            '{"label": "ok", "failure_family": "none"}',
            '{"label": "ok", "failure_family": "none", "reason": "  "}',
        ],
    )
    def test_malformed_never_becomes_ok(self, text):
        with pytest.raises(LL.ResponseParseError):
            LL.parse_response(text)

    def test_malformed_response_writes_no_label_and_no_cache(self, rec, rubric, tmp_path):
        labels = tmp_path / "labels.jsonl"
        cache = tmp_path / "cache"
        transport = StubTransport(text="I think it's probably fine?")
        with pytest.raises(LL.ResponseParseError):
            LL.label_one(rec, rubric, cache_dir=cache, transport=transport)
        assert not labels.exists()
        assert not list(cache.glob("*.json")) if cache.exists() else True
        # the call really was made, so it must still be accounted for
        assert llm_budget.totals()["calls"] == 1

    def test_cli_records_a_malformed_reply_as_a_failure(
        self, results_dir, tmp_path, monkeypatch, capsys
    ):
        labels = tmp_path / "labels.jsonl"
        transport = StubTransport(text="nope")
        monkeypatch.setattr(LL, "call_model", lambda p, **kw: {"text": "nope", "usage": {}})
        rc = LL.cmd_label(results_dir, labels, tmp_path / "cache", None, 10)
        assert rc == 0
        out = capsys.readouterr().out
        assert "FAILED (no label written)" in out
        assert "failures       : 2" in out
        assert not labels.exists()
        assert transport.calls == []


# ---------------------------------------------------------------------------
# guardrails
# ---------------------------------------------------------------------------


class TestGuardrails:
    def test_kill_switch_blocks_before_any_http(self, rec, rubric, tmp_path, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
        transport = StubTransport()
        with pytest.raises(LLMCallBlocked):
            LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)
        assert transport.calls == [], "the kill switch must block, not merely record"
        assert llm_budget.totals()["calls"] == 0

    def test_replay_only_blocks_before_any_http(self, rec, rubric, tmp_path, monkeypatch):
        monkeypatch.setenv("EVAL_REPLAY_ONLY", "1")
        transport = StubTransport()
        with pytest.raises(LLMCallBlocked):
            LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)
        assert transport.calls == []

    def test_call_ceiling_blocks_before_any_http(self, rec, rubric, tmp_path, monkeypatch):
        monkeypatch.setenv("NOESIS_LLM_MAX_CALLS", "0")
        transport = StubTransport()
        with pytest.raises(LLMBudgetExceeded):
            LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)
        assert transport.calls == []

    def test_usage_is_recorded_under_its_own_label(self, rec, rubric, tmp_path):
        transport = StubTransport(usage={"input_tokens": 9000, "output_tokens": 40})
        LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)

        by_label = llm_budget.by_label()
        assert LL.USAGE_LABEL in by_label, f"expected 'gate_label' spend, got {list(by_label)}"
        bucket = by_label[LL.USAGE_LABEL]
        assert bucket["calls"] == 1
        assert bucket["prompt_tokens"] == 9000
        assert bucket["completion_tokens"] == 40
        assert bucket["unpriced_calls"] == 0
        assert bucket["estimated_usd"] > 0
        # label spend is distinguishable, not merged into the model name
        assert LL.MODEL not in by_label

    def test_anthropic_model_is_priced(self):
        assert llm_budget.get_price(LL.MODEL) is not None
        cost = llm_budget.estimate_usd(LL.MODEL, 1_000_000, 1_000_000, 0)
        assert cost == pytest.approx(3.00 + 15.00)

    def test_cached_anthropic_tokens_are_priced_at_the_cached_rate(self):
        cost = llm_budget.estimate_usd(LL.MODEL, 1_000_000, 0, 1_000_000)
        assert cost == pytest.approx(0.30)

    def test_anthropic_usage_fields_are_summed_not_dropped(self, rec, rubric, tmp_path):
        # Anthropic reports input_tokens EXCLUSIVE of cached tokens.
        transport = StubTransport(
            usage={"input_tokens": 100, "output_tokens": 20, "cache_read_input_tokens": 900}
        )
        LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)
        bucket = llm_budget.by_label()[LL.USAGE_LABEL]
        assert bucket["prompt_tokens"] == 1000
        assert bucket["cached_tokens"] == 900


# ---------------------------------------------------------------------------
# caching
# ---------------------------------------------------------------------------


class TestCache:
    def test_cache_hit_costs_nothing_and_is_byte_identical(self, rec, rubric, tmp_path):
        cache = tmp_path / "cache"
        transport = StubTransport(
            text='{"label": "degraded", "failure_family": "D2", "reason": "generic"}'
        )
        first = LL.label_one(rec, rubric, cache_dir=cache, transport=transport)
        assert first["cached"] is False
        assert len(transport.calls) == 1
        spend_after_first = llm_budget.total_spend_usd()
        cached_bytes = (cache / f"{first['key']}.json").read_bytes()

        second = LL.label_one(rec, rubric, cache_dir=cache, transport=transport)
        assert second["cached"] is True
        assert len(transport.calls) == 1, "a cache hit must not hit the network"
        assert llm_budget.total_spend_usd() == spend_after_first
        assert llm_budget.totals()["calls"] == 1

        assert {k: second[k] for k in ("label", "failure_family", "reason")} == {
            k: first[k] for k in ("label", "failure_family", "reason")
        }
        assert (cache / f"{first['key']}.json").read_bytes() == cached_bytes

    def test_cache_hit_survives_the_kill_switch(self, rec, rubric, tmp_path, monkeypatch):
        cache = tmp_path / "cache"
        LL.label_one(rec, rubric, cache_dir=cache, transport=StubTransport())
        monkeypatch.setenv("NOESIS_LLM_KILL_SWITCH", "1")
        out = LL.label_one(rec, rubric, cache_dir=cache, transport=StubTransport())
        assert out["cached"] is True

    def test_key_changes_with_the_prompt(self, rec, rubric, results_dir):
        other = L.load_export(results_dir / "bbb__no-corpus__2026-06-21T02-00-00.json")
        assert LL.cache_key(LL.build_prompt(rec, rubric)) != LL.cache_key(
            LL.build_prompt(other, rubric)
        )

    def test_key_changes_with_the_prompt_version(self, rec, rubric, monkeypatch):
        before = LL.cache_key(LL.build_prompt(rec, rubric))
        monkeypatch.setattr(LL, "PROMPT_VERSION", "v2")
        assert LL.cache_key(LL.build_prompt(rec, rubric)) != before


# ---------------------------------------------------------------------------
# label file
# ---------------------------------------------------------------------------


class TestLabelStore:
    def test_labels_append_and_carry_the_labeller(self, tmp_path):
        labels = tmp_path / "labels.jsonl"
        LL.append_llm_label(labels, "aaa", {"label": "ok", "failure_family": "none",
                                            "reason": "r1", "key": "sha1"})
        LL.append_llm_label(labels, "bbb", {"label": "degraded", "failure_family": "D3",
                                            "reason": "r2", "key": "sha2"})
        recs = L.read_labels(labels)
        assert [r["run_id"] for r in recs] == ["aaa", "bbb"]
        for r in recs:
            assert r["labeller"] == f"llm:{LL.MODEL}"
            assert r["labeller_type"] == "llm"
            assert r["model"] == LL.MODEL
            assert LL.is_llm_record(r)

    def test_schema_matches_label_cli_so_sweep_consumes_both(self, tmp_path):
        labels = tmp_path / "labels.jsonl"
        L.append_label(labels, "aaa", "ok", "viji", "human note")
        LL.append_llm_label(labels, "bbb", {"label": "ok", "failure_family": "none",
                                            "reason": "model note", "key": "sha"})
        human, model = L.read_labels(labels)
        for key in ("run_id", "label", "note", "labeller", "timestamp", "is_relabel"):
            assert key in human and key in model
        assert not LL.is_llm_record(human)
        assert LL.is_llm_record(model)
        # sweep.py's join keys off run_id and reads label/labeller only
        current = L.latest_labels(labels)
        assert set(current) == {"aaa", "bbb"}

    def test_reason_is_stored_as_the_note(self, tmp_path):
        labels = tmp_path / "labels.jsonl"
        LL.append_llm_label(labels, "aaa", {"label": "unsure", "failure_family": "none",
                                            "reason": "cannot verify without the PDF", "key": "s"})
        assert L.read_labels(labels)[0]["note"] == "cannot verify without the PDF"

    def test_invalid_label_is_rejected(self, tmp_path):
        with pytest.raises(ValueError):
            LL.append_llm_label(tmp_path / "l.jsonl", "aaa",
                                {"label": "maybe", "failure_family": "none", "reason": "r"})


# ---------------------------------------------------------------------------
# agreement
# ---------------------------------------------------------------------------


def _write(labels: Path, pairs: list[tuple[str, str, str]]) -> None:
    """pairs of (run_id, human_label_or_'', llm_label_or_'')."""
    for run_id, h, m in pairs:
        if h:
            L.append_label(labels, run_id, h, "viji")
        if m:
            LL.append_llm_label(labels, run_id, {"label": m, "failure_family": "none",
                                                 "reason": "r", "key": "s"})


class TestAgreement:
    def test_kappa_matches_a_hand_computed_value(self, tmp_path):
        labels = tmp_path / "labels.jsonl"
        # 16 double-labelled runs, all scoreable.
        #   agree degraded: 4   agree ok: 8   human=degraded llm=ok: 3
        #   human=ok llm=degraded: 1
        pairs = (
            [(f"d{i}", "degraded", "degraded") for i in range(4)]
            + [(f"o{i}", "ok", "ok") for i in range(8)]
            + [(f"x{i}", "degraded", "ok") for i in range(3)]
            + [("y0", "ok", "degraded")]
        )
        _write(labels, pairs)

        a = LL.agreement(labels)
        assert a["n_overlap"] == 16
        assert a["n_scoreable"] == 16
        # p_o = 12/16 = 0.75
        # human: degraded 7/16, ok 9/16 ; llm: degraded 5/16, ok 11/16
        # p_e = (7/16)(5/16) + (9/16)(11/16) = (35 + 99)/256 = 134/256 = 0.523437.5
        # kappa = (0.75 - 0.5234375) / (1 - 0.5234375) = 0.4765625/0.4765625...
        p_o = 12 / 16
        p_e = (7 / 16) * (5 / 16) + (9 / 16) * (11 / 16)
        expected = (p_o - p_e) / (1 - p_e)
        assert a["kappa"] == pytest.approx(expected)
        assert a["percent_agreement"] == pytest.approx(0.75)
        assert a["confusion"]["degraded"]["degraded"] == 4
        assert a["confusion"]["degraded"]["ok"] == 3
        assert a["confusion"]["ok"]["degraded"] == 1
        assert a["confusion"]["ok"]["ok"] == 8
        assert a["per_class"]["degraded"]["human_recall"] == pytest.approx(4 / 7)

    def test_kappa_is_refused_below_the_overlap_floor(self, tmp_path):
        labels = tmp_path / "labels.jsonl"
        _write(labels, [(f"r{i}", "ok", "ok") for i in range(14)])
        a = LL.agreement(labels)
        assert a["n_scoreable"] == 14
        assert a["kappa"] is None
        assert a["kappa_withheld"] == "n/a (n=14 < 15)"
        text = LL.format_agreement(a)
        assert "n/a (n=14 < 15)" in text
        assert "Refused, not zero" in text

    def test_kappa_is_refused_on_zero_overlap(self, tmp_path):
        labels = tmp_path / "labels.jsonl"
        _write(labels, [("r0", "ok", ""), ("r1", "", "degraded")])
        a = LL.agreement(labels)
        assert a["n_overlap"] == 0
        assert a["kappa"] is None
        assert "n/a (n=0 < 15)" in LL.format_agreement(a)

    def test_unsure_is_excluded_from_the_headline_kappa(self, tmp_path):
        labels = tmp_path / "labels.jsonl"
        pairs = (
            [(f"d{i}", "degraded", "degraded") for i in range(4)]
            + [(f"o{i}", "ok", "ok") for i in range(11)]
            + [("u0", "unsure", "ok"), ("u1", "ok", "unsure"), ("u2", "unsure", "unsure")]
        )
        _write(labels, pairs)
        a = LL.agreement(labels)
        assert a["n_overlap"] == 18
        assert a["n_scoreable"] == 15, "the three unsure pairs must be dropped"
        assert a["unsure_human_only"] == 1
        assert a["unsure_llm_only"] == 1
        assert a["unsure_both"] == 1
        # headline: perfect agreement on the 15 scoreable
        assert a["kappa"] == pytest.approx(1.0)
        # diagnostic 3-class kappa sees the disagreements and is lower
        assert a["kappa_3class"] < 1.0
        assert "excluded from the headline kappa" in LL.format_agreement(a)

    def test_relabel_supersedes_within_a_rater(self, tmp_path):
        labels = tmp_path / "labels.jsonl"
        L.append_label(labels, "r0", "ok", "viji")
        L.append_label(labels, "r0", "degraded", "viji", superseded=True)
        LL.append_llm_label(labels, "r0", {"label": "degraded", "failure_family": "D3",
                                           "reason": "r", "key": "s"})
        a = LL.agreement(labels)
        assert a["confusion"]["degraded"]["degraded"] == 1
        assert a["confusion"]["ok"]["degraded"] == 0


# ---------------------------------------------------------------------------
# the API key must never escape
# ---------------------------------------------------------------------------


class TestKeyNeverLeaks:
    def test_key_is_sent_as_a_header_and_never_in_the_body(self, rec, rubric, tmp_path):
        transport = StubTransport()
        LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)
        call = transport.calls[0]
        assert call["headers"]["x-api-key"] == FAKE_KEY
        assert FAKE_KEY not in json.dumps(call["json"])

    def test_key_never_reaches_the_cache_or_the_labels_file(self, rec, rubric, tmp_path):
        cache = tmp_path / "cache"
        labels = tmp_path / "labels.jsonl"
        out = LL.label_one(rec, rubric, cache_dir=cache, transport=StubTransport())
        LL.append_llm_label(labels, rec["run_id"], out)
        for path in list(cache.glob("*.json")) + [labels]:
            assert FAKE_KEY not in path.read_text(), f"{path} contains the API key"

    def test_key_never_appears_in_stdout(self, results_dir, tmp_path, monkeypatch, capsys):
        monkeypatch.setattr(
            LL,
            "call_model",
            lambda p, **kw: {
                "text": '{"label": "ok", "failure_family": "none", "reason": "r"}',
                "usage": {"input_tokens": 10, "output_tokens": 5},
            },
        )
        LL.cmd_label(results_dir, tmp_path / "labels.jsonl", tmp_path / "cache", None, 10)
        captured = capsys.readouterr()
        assert FAKE_KEY not in captured.out
        assert FAKE_KEY not in captured.err

    def test_key_never_appears_in_a_raised_exception(self, rec, rubric, tmp_path):
        transport = StubTransport(status=500)
        with pytest.raises(LL.LabellerError) as exc:
            LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)
        assert FAKE_KEY not in str(exc.value)
        assert FAKE_KEY not in repr(exc.value)

    def test_missing_key_is_an_error_not_a_silent_unauthenticated_call(
        self, rec, rubric, tmp_path, monkeypatch
    ):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        transport = StubTransport()
        with pytest.raises(LL.LabellerError):
            LL.label_one(rec, rubric, cache_dir=tmp_path / "c", transport=transport)
        assert transport.calls == []


# ---------------------------------------------------------------------------
# dry run
# ---------------------------------------------------------------------------


class TestDryRun:
    def test_dry_run_spends_nothing_and_writes_nothing(self, results_dir, tmp_path, capsys):
        labels = tmp_path / "labels.jsonl"
        cache = tmp_path / "cache"
        rc = LL.cmd_dry_run(results_dir, labels, cache, None, 100)
        assert rc == 0
        out = capsys.readouterr().out
        assert "LIVE CALLS REQUIRED : 2" in out
        assert "ESTIMATED COST   : $" in out
        assert not labels.exists()
        assert llm_budget.totals()["calls"] == 0

    def test_dry_run_counts_cache_hits_as_free(self, results_dir, rec, rubric, tmp_path, capsys):
        cache = tmp_path / "cache"
        LL.label_one(rec, rubric, cache_dir=cache, transport=StubTransport())
        LL.cmd_dry_run(results_dir, tmp_path / "labels.jsonl", cache, None, 100)
        out = capsys.readouterr().out
        assert "cache hits (free)   : 1" in out
        assert "LIVE CALLS REQUIRED : 1" in out

    def test_dry_run_respects_the_call_ceiling_in_its_estimate(self, results_dir, tmp_path, capsys):
        LL.cmd_dry_run(results_dir, tmp_path / "labels.jsonl", tmp_path / "cache", None, 1)
        out = capsys.readouterr().out
        assert "LIVE CALLS REQUIRED : 2" in out
        assert "-> 1 call(s) would be made" in out


# ---------------------------------------------------------------------------
# label_cli run header (task 5)
# ---------------------------------------------------------------------------


class TestRunHeaderShowsThePaper:
    def test_paper_id_is_parsed_from_the_run_id(self):
        assert L.paper_id_from_run_id("cXs5md5wAq__no-corpus__2026-06-21T03-59-08") == "cXs5md5wAq"

    def test_pdf_path_resolves_under_the_venue_directory(self, tmp_path):
        venue = tmp_path / "ICLR.cc_2024_Conference"
        venue.mkdir()
        pdf = venue / "cXs5md5wAq.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        got = L.resolve_pdf_path("cXs5md5wAq__no-corpus__2026-06-21T03-59-08", openreview_dir=tmp_path)
        assert got == pdf

    def test_missing_pdf_returns_none(self, tmp_path):
        assert L.resolve_pdf_path("nope__no-corpus__x", openreview_dir=tmp_path) is None

    def test_header_shows_paper_id(self, rec):
        header = L.render_run(rec).splitlines()
        assert header[1].startswith("RUN: ")
        assert header[2] == "PAPER: aaa"
        assert header[3].startswith("PDF  : ")

    def test_header_change_does_not_leak_scores(self, rec, rubric):
        assert LL.blindness_violations(LL.build_prompt(rec, rubric), rec, rubric) == []

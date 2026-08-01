"""Unit tests for gate_calibration.label_cli.

All tests operate on synthetic exports under ``tmp_path``. Nothing here reads or
writes ``scripts/eval/results/`` or the real ``labels.jsonl``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from gate_calibration import label_cli as L  # noqa: E402


# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------


def make_export(
    dirpath: Path,
    run_id: str,
    *,
    n_tasks: int = 2,
    parser_quality: float = 1.0,
    page_anchor: float = 0.9,
    verbatim: float = 1.0,
    gate_status: str = "ok",
    publishable: bool = True,
) -> Path:
    """Write a minimally-shaped export matching the real schema."""
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
            "structure": {"page_count": 12, "sections": [{"title": "Intro"}, {"title": "Methods"}]},
            "analysis_metadata": {
                "analysis_status": None,
                "readiness_score": 80,
                "publish_gate": {
                    "gate_status": gate_status,
                    "publishable": publishable,
                    "confidence": "high" if publishable else "low",
                    "observed": {"parser_quality_score": parser_quality, "parse_blocked": False},
                },
                "revision_quality_metrics": {
                    "total_tasks": n_tasks,
                    "page_anchor_coverage": page_anchor,
                    "verbatim_anchor_coverage": verbatim,
                    "anchor_coverage": 1.0,
                },
            },
        },
        "parser_metadata": {"parser_quality_score": parser_quality},
        "durable_revision_tasks": tasks,
        "reviewer_feedback": [
            {
                "severity": "major",
                "feedback_type": "structural",
                "section_reference": "Methods",
                "feedback_text": "Reviewer prose here.",
            }
        ],
        "meta_reviews": [
            {
                "overall_recommendation": "major_revision",
                "must_address": ["Report hyperparameters."],
                "nice_to_address": [],
                "consensus_weaknesses": ["Thin ablations."],
            }
        ],
    }
    path = dirpath / f"{run_id}.json"
    path.write_text(json.dumps(payload))
    return path


def _label_count(stats_output: str, label: str) -> int:
    """Pull one class count out of the --stats distribution block.

    Parses rather than substring-matching so the assertion survives a column
    width change.
    """
    import re

    m = re.search(rf"^\s+{re.escape(label)}\s+(\d+)\s+\(", stats_output, flags=re.MULTILINE)
    assert m is not None, f"no distribution line for {label!r} in:\n{stats_output}"
    return int(m.group(1))


@pytest.fixture
def results_dir(tmp_path: Path) -> Path:
    d = tmp_path / "results"
    d.mkdir()
    make_export(d, "aaa__no-corpus__2026-06-21T01-00-00", page_anchor=0.95)
    make_export(d, "bbb__no-corpus__2026-06-21T02-00-00", page_anchor=0.60,
                gate_status="needs_retry", publishable=False)
    make_export(d, "ccc__no-corpus__2026-06-21T03-00-00", n_tasks=0)
    return d


@pytest.fixture
def labels_path(tmp_path: Path) -> Path:
    return tmp_path / "labels.jsonl"


# ---------------------------------------------------------------------------
# export loading
# ---------------------------------------------------------------------------


class TestLoadExport:
    def test_extracts_the_fields_a_labeller_needs(self, results_dir: Path):
        rec = L.load_export(results_dir / "aaa__no-corpus__2026-06-21T01-00-00.json")
        assert rec["run_id"] == "aaa__no-corpus__2026-06-21T01-00-00"
        assert rec["title"].startswith("[EVAL]")
        assert len(rec["tasks"]) == 2
        assert rec["word_count"] == 8000
        assert rec["sections"] == ["Intro", "Methods"]

    def test_hides_scores_behind_the_underscore_key(self, results_dir: Path):
        rec = L.load_export(results_dir / "bbb__no-corpus__2026-06-21T02-00-00.json")
        h = rec["_hidden"]
        assert h["page_anchor_coverage"] == pytest.approx(0.60)
        assert h["parser_quality_score"] == pytest.approx(1.0)
        assert h["verbatim_anchor_coverage"] == pytest.approx(1.0)
        assert h["gate_status"] == "needs_retry"
        assert h["publishable"] is False

    def test_unparseable_json_raises_malformed_not_a_crash(self, tmp_path: Path):
        bad = tmp_path / "bad.json"
        bad.write_text("{not json")
        with pytest.raises(L.MalformedExport):
            L.load_export(bad)

    def test_aggregate_file_without_eval_metadata_is_malformed(self, tmp_path: Path):
        agg = tmp_path / "scoreboard_copy.json"
        agg.write_text(json.dumps({"runs": [], "mean_score": 0.4}))
        with pytest.raises(L.MalformedExport):
            L.load_export(agg)

    def test_export_missing_analysis_block_is_malformed(self, tmp_path: Path):
        p = tmp_path / "x.json"
        p.write_text(json.dumps({"eval_metadata": {"draft_file": "x"}}))
        with pytest.raises(L.MalformedExport):
            L.load_export(p)

    def test_top_level_list_is_malformed(self, tmp_path: Path):
        p = tmp_path / "y.json"
        p.write_text(json.dumps([1, 2, 3]))
        with pytest.raises(L.MalformedExport):
            L.load_export(p)


class TestIterExports:
    def test_yields_every_valid_export(self, results_dir: Path):
        assert len(list(L.iter_exports(results_dir))) == 3

    def test_malformed_export_is_skipped_without_crashing(self, results_dir: Path, capsys):
        (results_dir / "broken.json").write_text("{{{ truncated")
        recs = list(L.iter_exports(results_dir))
        assert len(recs) == 3  # the three good ones survive
        assert "broken.json" in capsys.readouterr().err

    def test_known_aggregate_stems_are_ignored(self, results_dir: Path):
        (results_dir / "scoreboard.json").write_text(json.dumps({"anything": 1}))
        (results_dir / "openreview_scoreboard.json").write_text(json.dumps({"anything": 1}))
        assert len(list(L.iter_exports(results_dir))) == 3

    def test_missing_directory_exits_cleanly(self, tmp_path: Path):
        with pytest.raises(SystemExit):
            list(L.iter_exports(tmp_path / "nope"))


# ---------------------------------------------------------------------------
# append-only label store
# ---------------------------------------------------------------------------


class TestLabelStore:
    def test_append_creates_the_file_and_writes_one_line(self, labels_path: Path):
        L.append_label(labels_path, "aaa", "degraded", "viji", note="empty output")
        assert labels_path.read_text().count("\n") == 1
        rec = json.loads(labels_path.read_text().strip())
        assert rec["run_id"] == "aaa"
        assert rec["label"] == "degraded"
        assert rec["labeller"] == "viji"
        assert rec["note"] == "empty output"
        assert rec["timestamp"]

    def test_appends_do_not_overwrite_earlier_lines(self, labels_path: Path):
        L.append_label(labels_path, "aaa", "ok", "viji")
        L.append_label(labels_path, "bbb", "degraded", "viji")
        L.append_label(labels_path, "ccc", "unsure", "viji")
        lines = labels_path.read_text().strip().split("\n")
        assert len(lines) == 3
        assert [json.loads(x)["run_id"] for x in lines] == ["aaa", "bbb", "ccc"]

    def test_relabel_appends_rather_than_mutating(self, labels_path: Path):
        L.append_label(labels_path, "aaa", "ok", "viji", note="first call")
        L.append_label(labels_path, "aaa", "degraded", "viji", note="second look", superseded=True)
        lines = labels_path.read_text().strip().split("\n")
        assert len(lines) == 2, "history must be preserved, not rewritten"
        assert json.loads(lines[0])["label"] == "ok"
        assert json.loads(lines[1])["label"] == "degraded"
        assert json.loads(lines[1])["is_relabel"] is True

    def test_latest_labels_takes_the_last_record_per_run(self, labels_path: Path):
        L.append_label(labels_path, "aaa", "ok", "viji")
        L.append_label(labels_path, "aaa", "degraded", "viji", superseded=True)
        L.append_label(labels_path, "bbb", "unsure", "viji")
        current = L.latest_labels(labels_path)
        assert current["aaa"]["label"] == "degraded"
        assert current["bbb"]["label"] == "unsure"
        assert len(current) == 2

    def test_rejects_an_invalid_label_value(self, labels_path: Path):
        with pytest.raises(ValueError):
            L.append_label(labels_path, "aaa", "maybe", "viji")

    def test_missing_label_file_reads_as_empty(self, tmp_path: Path):
        assert L.read_labels(tmp_path / "absent.jsonl") == []
        assert L.latest_labels(tmp_path / "absent.jsonl") == {}

    def test_corrupt_label_line_is_skipped_not_fatal(self, labels_path: Path, capsys):
        L.append_label(labels_path, "aaa", "ok", "viji")
        with labels_path.open("a") as fh:
            fh.write("{ this is not json\n")
        L.append_label(labels_path, "bbb", "degraded", "viji")
        recs = L.read_labels(labels_path)
        assert [r["run_id"] for r in recs] == ["aaa", "bbb"]
        assert "unparseable" in capsys.readouterr().err

    def test_blank_lines_are_tolerated(self, labels_path: Path):
        labels_path.write_text("\n\n" + json.dumps({"run_id": "aaa", "label": "ok"}) + "\n\n")
        assert len(L.read_labels(labels_path)) == 1


# ---------------------------------------------------------------------------
# resume
# ---------------------------------------------------------------------------


class TestResume:
    def test_already_labelled_runs_are_skipped(self, results_dir: Path, labels_path: Path):
        L.append_label(labels_path, "aaa__no-corpus__2026-06-21T01-00-00", "ok", "viji")
        done = set(L.latest_labels(labels_path))
        pending = [e for e in L.iter_exports(results_dir) if e["run_id"] not in done]
        assert [e["run_id"] for e in pending] == [
            "bbb__no-corpus__2026-06-21T02-00-00",
            "ccc__no-corpus__2026-06-21T03-00-00",
        ]

    def test_relabelled_run_stays_skipped(self, results_dir: Path, labels_path: Path):
        rid = "aaa__no-corpus__2026-06-21T01-00-00"
        L.append_label(labels_path, rid, "ok", "viji")
        L.append_label(labels_path, rid, "degraded", "viji", superseded=True)
        done = set(L.latest_labels(labels_path))
        pending = [e for e in L.iter_exports(results_dir) if e["run_id"] not in done]
        assert rid not in {e["run_id"] for e in pending}
        assert len(pending) == 2

    def test_labelling_session_resumes_from_where_it_stopped(
        self, results_dir: Path, labels_path: Path, monkeypatch, capsys
    ):
        # first session: label one run, then quit
        answers = iter(["d", "no tasks at all", "q"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        L.cmd_label(results_dir, labels_path, "viji", None)
        assert len(L.read_labels(labels_path)) == 1

        # second session: the labelled run is not offered again
        answers2 = iter(["o", "", "q"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers2))
        L.cmd_label(results_dir, labels_path, "viji", None)
        recs = L.read_labels(labels_path)
        assert len(recs) == 2
        assert recs[0]["run_id"] != recs[1]["run_id"]

    def test_skip_does_not_record_a_label(self, results_dir: Path, labels_path: Path, monkeypatch):
        answers = iter(["s", "q"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))
        L.cmd_label(results_dir, labels_path, "viji", None)
        assert L.read_labels(labels_path) == []


# ---------------------------------------------------------------------------
# blind presentation
# ---------------------------------------------------------------------------


class TestRenderIsBlind:
    def test_render_shows_the_critique(self, results_dir: Path):
        rec = L.load_export(results_dir / "aaa__no-corpus__2026-06-21T01-00-00.json")
        text = L.render_run(rec)
        assert "Problem statement 0" in text
        assert "quoted passage 0" in text
        assert "major_revision" in text

    def test_render_never_leaks_the_gate_verdict_or_scores(self, results_dir: Path):
        for path in sorted(results_dir.glob("*.json")):
            text = L.render_run(L.load_export(path)).lower()
            for forbidden in (
                "page_anchor_coverage",
                "parser_quality",
                "verbatim_anchor",
                "gate_status",
                "publishable",
                "needs_retry",
                "publish_gate",
            ):
                assert forbidden not in text, f"{path.name} leaked {forbidden}"

    def test_render_handles_a_run_with_zero_tasks(self, results_dir: Path):
        rec = L.load_export(results_dir / "ccc__no-corpus__2026-06-21T03-00-00.json")
        text = L.render_run(rec)
        assert "DURABLE REVISION TASKS (0)" in text
        assert "T4" in text  # points the labeller at the tie-break

    def test_render_sorts_critical_tasks_first(self, tmp_path: Path):
        d = tmp_path / "r"
        d.mkdir()
        p = make_export(d, "zz", n_tasks=3)  # severities: critical, major, minor
        text = L.render_run(L.load_export(p))
        assert text.index("severity=critical") < text.index("severity=major") < text.index(
            "severity=minor"
        )


# ---------------------------------------------------------------------------
# stats
# ---------------------------------------------------------------------------


class TestStats:
    def test_reports_zero_labelled_and_n_available(self, results_dir: Path, labels_path: Path, capsys):
        L.cmd_stats(results_dir, labels_path)
        out = capsys.readouterr().out
        assert "exports available : 3" in out
        assert "runs labelled     : 0" in out
        assert "runs remaining    : 3" in out

    def test_counts_each_label_class(self, results_dir: Path, labels_path: Path, capsys):
        L.append_label(labels_path, "aaa__no-corpus__2026-06-21T01-00-00", "ok", "viji")
        L.append_label(labels_path, "bbb__no-corpus__2026-06-21T02-00-00", "degraded", "viji")
        L.append_label(labels_path, "ccc__no-corpus__2026-06-21T03-00-00", "unsure", "viji")
        L.cmd_stats(results_dir, labels_path)
        out = capsys.readouterr().out
        assert "runs labelled     : 3" in out
        assert _label_count(out, "degraded") == 1
        assert _label_count(out, "ok") == 1
        assert _label_count(out, "unsure") == 1
        assert "usable for metrics (degraded+ok): 2" in out

    def test_relabel_is_counted_once_but_history_is_reported(
        self, results_dir: Path, labels_path: Path, capsys
    ):
        rid = "aaa__no-corpus__2026-06-21T01-00-00"
        L.append_label(labels_path, rid, "ok", "viji")
        L.append_label(labels_path, rid, "degraded", "viji", superseded=True)
        L.cmd_stats(results_dir, labels_path)
        out = capsys.readouterr().out
        assert "runs labelled     : 1" in out
        assert "label records on disk (incl. superseded relabels): 2" in out
        assert _label_count(out, "degraded") == 1
        assert _label_count(out, "ok") == 0

    def test_warns_when_the_sample_is_too_small_for_metrics(
        self, results_dir: Path, labels_path: Path, capsys
    ):
        L.append_label(labels_path, "aaa__no-corpus__2026-06-21T01-00-00", "ok", "viji")
        L.cmd_stats(results_dir, labels_path)
        assert "WARNING" in capsys.readouterr().out

    def test_labels_without_a_matching_export_are_flagged(
        self, results_dir: Path, labels_path: Path, capsys
    ):
        L.append_label(labels_path, "ghost-run", "ok", "viji")
        L.cmd_stats(results_dir, labels_path)
        assert "have no matching export" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# relabel command
# ---------------------------------------------------------------------------


class TestRelabelCommand:
    def test_appends_a_new_record_and_keeps_the_old_one(
        self, results_dir: Path, labels_path: Path, monkeypatch, capsys
    ):
        rid = "bbb__no-corpus__2026-06-21T02-00-00"
        L.append_label(labels_path, rid, "ok", "viji", note="looked fine")
        answers = iter(["d", "on second read the anchors are fabricated"])
        monkeypatch.setattr("builtins.input", lambda *_: next(answers))

        assert L.cmd_relabel(results_dir, labels_path, rid, "viji") == 0

        recs = L.read_labels(labels_path)
        assert len(recs) == 2
        assert recs[0]["label"] == "ok"
        assert recs[0]["note"] == "looked fine"
        assert recs[1]["label"] == "degraded"
        assert recs[1]["is_relabel"] is True
        assert L.latest_labels(labels_path)[rid]["label"] == "degraded"

    def test_refuses_a_run_that_was_never_labelled(self, results_dir: Path, labels_path: Path):
        rid = "aaa__no-corpus__2026-06-21T01-00-00"
        assert L.cmd_relabel(results_dir, labels_path, rid, "viji") == 1
        assert L.read_labels(labels_path) == []

    def test_refuses_a_run_id_with_no_export(self, results_dir: Path, labels_path: Path):
        L.append_label(labels_path, "ghost", "ok", "viji")
        assert L.cmd_relabel(results_dir, labels_path, "ghost", "viji") == 1
        assert len(L.read_labels(labels_path)) == 1

    def test_quitting_leaves_the_label_untouched(
        self, results_dir: Path, labels_path: Path, monkeypatch
    ):
        rid = "aaa__no-corpus__2026-06-21T01-00-00"
        L.append_label(labels_path, rid, "ok", "viji")
        monkeypatch.setattr("builtins.input", lambda *_: "q")
        assert L.cmd_relabel(results_dir, labels_path, rid, "viji") == 0
        assert len(L.read_labels(labels_path)) == 1


# ---------------------------------------------------------------------------
# argument parsing
# ---------------------------------------------------------------------------


class TestCli:
    def test_stats_flag_routes_to_stats(self, results_dir: Path, labels_path: Path, capsys):
        rc = L.main(["--stats", "--results-dir", str(results_dir), "--labels", str(labels_path)])
        assert rc == 0
        assert "exports available : 3" in capsys.readouterr().out

    def test_defaults_point_at_the_repo_results_dir(self):
        args = L.build_parser().parse_args([])
        assert args.results_dir.name == "results"
        assert args.labels.name == "labels.jsonl"

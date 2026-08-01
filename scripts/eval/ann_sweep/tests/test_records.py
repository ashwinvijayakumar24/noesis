"""Record assembly, append-only persistence, and ANN-vs-exact recall.

Pure -- no database. These cover the properties that make results trustworthy
after the fact: nothing is overwritten, every record is keyed, and the two
recalls never share a key.
"""

from __future__ import annotations

import json

import pytest

from scripts.eval.ann_sweep.sweep import (
    CorpusFingerprint,
    QuerySet,
    ann_recall_vs_exact,
    append_record,
    make_record,
    read_records,
)

CORPUS = CorpusFingerprint(documents=118, chunks=2124, project_id="proj-1")


class TestAnnRecallVsExact:
    def test_identical_result_sets_score_one(self):
        exact = {"q1": ["a", "b", "c"]}
        assert ann_recall_vs_exact({"q1": ["a", "b", "c"]}, exact, 3) == 1.0

    def test_order_within_top_k_does_not_matter(self):
        """Recall@k is set overlap; ranking quality is NDCG's job, not this one."""
        exact = {"q1": ["a", "b", "c"]}
        assert ann_recall_vs_exact({"q1": ["c", "a", "b"]}, exact, 3) == 1.0

    def test_half_overlap_scores_half(self):
        exact = {"q1": ["a", "b", "c", "d"]}
        assert ann_recall_vs_exact({"q1": ["a", "b", "x", "y"]}, exact, 4) == 0.5

    def test_averaged_over_queries_not_pooled(self):
        exact = {"q1": ["a", "b"], "q2": ["c", "d"]}
        approx = {"q1": ["a", "b"], "q2": ["z", "y"]}
        assert ann_recall_vs_exact(approx, exact, 2) == 0.5

    def test_missing_query_in_approx_counts_as_zero_not_skipped(self):
        exact = {"q1": ["a"], "q2": ["b"]}
        assert ann_recall_vs_exact({"q1": ["a"]}, exact, 1) == 0.5

    def test_denominator_is_exact_size_when_corpus_is_smaller_than_k(self):
        """Dividing by k would report <1.0 for an index that lost nothing."""
        exact = {"q1": ["a", "b"]}
        assert ann_recall_vs_exact({"q1": ["a", "b"]}, exact, 50) == 1.0

    def test_truncation_to_k_is_applied_to_both_sides(self):
        exact = {"q1": ["a", "b", "c", "d"]}
        assert ann_recall_vs_exact({"q1": ["a", "b", "c", "d"]}, exact, 2) == 1.0
        assert ann_recall_vs_exact({"q1": ["c", "d", "a", "b"]}, exact, 2) == 0.0

    def test_no_scorable_queries_returns_none_not_zero(self):
        assert ann_recall_vs_exact({}, {}, 10) is None
        assert ann_recall_vs_exact({"q": []}, {"q": []}, 10) is None


class TestMakeRecord:
    def test_corpus_fingerprint_and_n_are_always_present(self):
        rec = make_record("ef_search", {"ef_search": 80}, CORPUS, n_queries=59)
        assert rec["corpus_fingerprint"]["documents"] == 118
        assert rec["corpus_fingerprint"]["chunks"] == 2124
        assert rec["n_queries"] == 59
        assert "n = 59" in rec["n_note"]

    def test_the_two_recalls_have_distinct_keys(self):
        rec = make_record(
            "ef_search", {"ef_search": 80}, CORPUS, 59,
            ann_recall={"recall@50": 0.9}, label_metrics={"metrics": {"recall@10": 0.4}},
        )
        assert rec["ann_recall_vs_exact"]["recall@50"] == 0.9
        assert rec["metrics_vs_labels"]["metrics"]["recall@10"] == 0.4

    def test_small_corpus_caveat_travels_with_every_record(self):
        rec = make_record("ef_search", {}, CORPUS, 59)
        assert "asymptotic" in rec["corpus_fingerprint"]["note"]

    def test_absent_measurement_yields_explicit_nulls_not_missing_keys(self):
        rec = make_record("build", {}, CORPUS, 59, status="build_failed", error="boom")
        assert rec["latency_server_ms"] is None
        assert rec["plan_index_used"] is None
        assert rec["status"] == "build_failed"
        assert rec["error"] == "boom"

    def test_extra_fields_merge(self):
        rec = make_record("ef_search", {}, CORPUS, 59, extra={"queries_fingerprint": "abc"})
        assert rec["queries_fingerprint"] == "abc"


class TestAppendOnly:
    def test_records_append_rather_than_overwrite(self, tmp_path):
        path = tmp_path / "ann_sweep.jsonl"
        append_record(make_record("ef_search", {"ef_search": 10}, CORPUS, 59), path)
        append_record(make_record("ef_search", {"ef_search": 20}, CORPUS, 59), path)
        records = read_records(path)
        assert len(records) == 2
        assert [r["params"]["ef_search"] for r in records] == [10, 20]

    def test_rerunning_the_same_point_lands_beside_the_old_one(self):
        """Two identical keys disagreeing must be VISIBLE, not silently resolved
        in favour of whichever ran last."""
        import tempfile

        with tempfile.TemporaryDirectory() as d:
            path = f"{d}/r.jsonl"
            append_record(make_record("ef_search", {"ef_search": 80}, CORPUS, 59), path)
            append_record(make_record("ef_search", {"ef_search": 80}, CORPUS, 59), path)
            recs = read_records(path)
            assert len(recs) == 2
            assert recs[0]["params"] == recs[1]["params"]

    def test_existing_content_is_byte_preserved(self, tmp_path):
        path = tmp_path / "r.jsonl"
        path.write_text('{"pre_existing": true}\n')
        append_record(make_record("exact", {}, CORPUS, 59), path)
        lines = path.read_text().splitlines()
        assert lines[0] == '{"pre_existing": true}'
        assert len(lines) == 2

    def test_parent_directory_is_created(self, tmp_path):
        path = tmp_path / "deep" / "nested" / "r.jsonl"
        append_record(make_record("exact", {}, CORPUS, 59), path)
        assert path.exists()

    def test_each_line_is_independently_parseable(self, tmp_path):
        path = tmp_path / "r.jsonl"
        for ef in (10, 20, 40):
            append_record(make_record("ef_search", {"ef_search": ef}, CORPUS, 59), path)
        for line in path.read_text().splitlines():
            json.loads(line)

    def test_read_records_on_a_missing_file_is_empty_not_an_error(self, tmp_path):
        assert read_records(tmp_path / "nope.jsonl") == []


class TestQuerySet:
    def test_length_mismatch_is_rejected_at_construction(self):
        with pytest.raises(ValueError, match="same length"):
            QuerySet(query_ids=["a", "b"], embeddings=[[0.1]])

    def test_len_is_the_query_count(self):
        assert len(QuerySet(["a", "b"], [[0.1], [0.2]])) == 2


class TestElideVectors:
    """A stored plan is evidence about which index ran. The floats are not."""

    def test_long_vector_literals_are_replaced(self):
        from scripts.eval.ann_sweep.search import elide_vectors

        plan = "Sort Key: ((dc.embedding <=> '[" + ",".join(["0.0123456"] * 200) + "]'::vector))"
        out = elide_vectors(plan)
        assert "'<vector>'" in out
        assert "0.0123456" not in out
        assert len(out) < 80

    def test_short_literals_and_uuids_survive(self):
        from scripts.eval.ann_sweep.search import elide_vectors

        plan = "Filter: (project_id = 'e7a1c0b0-0000-4000-8000-000000000001'::uuid)"
        assert elide_vectors(plan) == plan

    def test_plan_structure_is_preserved(self):
        from scripts.eval.ann_sweep.search import elide_vectors

        plan = (
            "Limit\n  ->  Index Scan using idx_x on document_chunks dc\n"
            "        Order By: (dc.embedding <=> '[" + ",".join(["0.1"] * 100) + "]'::vector)"
        )
        out = elide_vectors(plan)
        assert out.splitlines()[1].strip() == "->  Index Scan using idx_x on document_chunks dc"

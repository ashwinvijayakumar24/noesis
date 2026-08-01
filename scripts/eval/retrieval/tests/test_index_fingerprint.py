"""The record must identify what was searched, not only what it was scored against.

Regression test for a concurrency incident: one agent re-chunked the shared eval
corpus in place while another measured a control arm against it. Both runs
produced records with identical ``labels_fingerprint``, ``queries_fingerprint``
and ``config_hash``, because label fingerprints hash document ids and document
ids are ``uuid5`` over file content -- which re-chunking does not change.

The contaminated control read recall@10 0.2186 against a 5,924-chunk index where
the real control reads 0.2195 against 5,948. Nothing in the record could have
told them apart, so nothing downstream could either.
"""

from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = str(Path(__file__).resolve().parents[4])
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from scripts.eval.retrieval.run_retrieval_eval import (  # noqa: E402
    INDEX_NOT_APPLICABLE,
    INDEX_UNKNOWN,
    config_hash,
    index_fingerprint,
)


def test_mock_retriever_is_not_applicable_not_unknown():
    """A retriever that never touches the DB has no index state to report.

    That is different from a DB-backed run whose index could not be identified.
    Collapsing the two would turn a clean run into a suspicious one and, worse,
    make a genuinely suspicious one look routine.
    """
    assert index_fingerprint("mock") == {"index_state": INDEX_NOT_APPLICABLE}


def test_failure_is_reported_never_raised():
    """A fingerprint that can fail a run gets removed the first time it is
    inconvenient, and is then missing exactly when it matters."""
    fp = index_fingerprint("dense", project_id="00000000-0000-0000-0000-000000000000")
    assert fp["index_state"] in {INDEX_UNKNOWN, "0c/0d"} or "index_n_chunks" in fp


def test_index_state_participates_in_the_config_hash():
    """The whole point. Two corpora must not share a hash.

    Built from literal config dicts rather than a live DB so the property is
    tested even on a machine with no database.
    """
    base = {
        "retriever": "dense",
        "k": 10,
        "labels_fingerprint": "230c6ea9d9b7e8fd",
        "queries_fingerprint": "1f6c584e8fd6c055",
    }
    legacy = {**base, "index_state": "5948c/344d", "index_digest": "8d3edbe3f3b28cdb"}
    exact = {**base, "index_state": "5924c/344d", "index_digest": "0000000000000000"}

    assert config_hash(legacy) != config_hash(exact), (
        "two different corpora produced the same config hash -- the incident "
        "this test exists to prevent has recurred"
    )
    assert config_hash(legacy) == config_hash(dict(legacy)), "hash must be stable"

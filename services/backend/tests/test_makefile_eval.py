from pathlib import Path


def test_eval_openreview_supports_papers_variable_and_skip_env():
    repo_root = Path(__file__).resolve().parents[3]
    text = (repo_root / "Makefile").read_text()

    assert "PAPERS ?=" in text
    assert "PAPER_ARGS = $(if $(PAPERS),--paper-ids $(PAPERS),)" in text
    assert "-e EVAL_SKIP_EXTERNAL_SOURCE_DISCOVERY=1" in text
    assert "-e EVAL_DISABLE_PRE_REVIEWER_HALT=1" in text
    assert "--limit $(LIMIT) $(PAPER_ARGS)" in text

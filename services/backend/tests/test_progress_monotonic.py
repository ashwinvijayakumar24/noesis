"""The progress bar must never run backwards.

`useAnalysisStream.ts` assigns `data.progress` unconditionally, so any published
percentage lower than the previous one is a visible backwards jump in the user's
progress bar. The percentages are hardcoded constants in the graph and in
reviewer_panel.py, and they were non-monotonic in execution order.

These tests read the constants out of the source rather than importing the
module, so they pin what is actually published without needing a live run.
"""

import re
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[1]
GRAPH_PY = BACKEND / "app" / "workflows" / "draft_analysis" / "graph.py"
REVIEWER_PANEL_PY = (
    BACKEND / "app" / "workflows" / "draft_analysis" / "nodes" / "reviewer_panel.py"
)

# The two backwards jumps this test was written for. Kept as literals so the bug
# stays documented even after the values move: 78 -> 76 (run_quality_diagnostics
# then structural_checks) and 95 -> 90 (meta_review then synthesize_report_start).
KNOWN_BAD_PAIRS = [
    ("diagnostic_findings", 78, "structural_checks_start", 76),
    ("meta_review", 95, "synthesize_report_start", 90),
]

# Published from inside reviewer_panel_node, which fans out 3-way. Not part of
# graph.py's constants but sits on the normal path between editor_pass and
# reviewer_judge, so it constrains the numbers on either side.
_PANEL_START = 84
_PANEL_DONE = 87


def _graph_progress() -> dict[str, int]:
    """event name -> percentage, from the publish_progress calls in graph.py."""
    src = GRAPH_PY.read_text(encoding="utf-8")
    found: dict[str, int] = {}
    for event, pct in re.findall(
        r'publish_progress\(\s*draft_id,\s*"([a-z_]+)",\s*(\d+)', src
    ):
        pct = int(pct)
        # "external_sources" is published from both the eval-skip and normal
        # branches; they must agree.
        if event in found:
            assert found[event] == pct, (
                f'"{event}" published with conflicting percentages '
                f"{found[event]} and {pct}"
            )
        found[event] = pct
    return found


@pytest.fixture(scope="module")
def progress() -> dict[str, int]:
    values = _graph_progress()
    assert values, "no publish_progress constants found in graph.py"
    return values


# Execution order established from graph.py's edges and routing functions:
#   extract_structure -> profile_manuscript -> extract_references -> extract_claims
#   -> categorize_claims -> verify_citations -> search_literature -> map_citations
#   -> detect_gaps -> discover_external_sources -> citation_judge_node
#   -> run_quality_diagnostics -> structural_checks -> editor_pass_node
#   -> [reviewer fan-out] -> reviewer_judge_node -> meta_reviewer_node
#   -> synthesize_report
_PRE_EDITOR = [
    "extract_structure_start", "extract_structure",
    "manuscript_profile_start", "manuscript_profile",
    "extract_references_start", "extract_references",
    "extract_claims_start", "extract_claims",
    "categorize_claims_start", "categorize_claims",
    "verify_citations_start", "verify_citations",
    "search_literature_start", "search_literature",
    "map_citations_start", "map_citations",
    "detect_gaps_start", "detect_gaps",
    "external_sources_start", "external_sources",
    "citation_judge_start", "citation_judge",
    "diagnostic_findings_start", "diagnostic_findings",
    "structural_checks_start", "structural_checks",
    "editor_pass_start", "editor_pass",
]
_POST_PANEL = [
    "reviewer_judge_start", "reviewer_judge",
    "meta_review_start", "meta_review",
    "synthesize_report_start", "synthesize_report",
]

# route_to_reviewer_panel returns "synthesize_report" directly when the editor
# desk-rejects, and again when the preliminary publish gate halts the run. Both
# branches skip reviewer_panel_node, reviewer_judge_node and meta_reviewer_node.
_SKIP_BRANCH = ["synthesize_report_start", "synthesize_report"]


def _assert_strictly_increasing(sequence: list[tuple[str, int]], path: str) -> None:
    for (prev_name, prev), (name, cur) in zip(sequence, sequence[1:]):
        assert cur > prev, (
            f"{path}: progress goes backwards or stalls, "
            f'"{prev_name}"={prev} then "{name}"={cur}'
        )


def _seq(progress: dict[str, int], events: list[str]) -> list[tuple[str, int]]:
    missing = [e for e in events if e not in progress]
    assert not missing, f"events missing from graph.py: {missing}"
    return [(e, progress[e]) for e in events]


def test_normal_path_is_strictly_increasing(progress):
    seq = (
        [("start", 3)]
        + _seq(progress, _PRE_EDITOR)
        + [("reviewer_panel_start", _PANEL_START), ("reviewer_panel_done", _PANEL_DONE)]
        + _seq(progress, _POST_PANEL)
        + [("workflow_complete", 98), ("complete", 100)]
    )
    _assert_strictly_increasing(seq, "normal path")


def test_desk_reject_path_is_strictly_increasing(progress):
    """Editor desk-reject: editor_pass_node -> synthesize_report."""
    seq = (
        [("start", 3)]
        + _seq(progress, _PRE_EDITOR)
        + _seq(progress, _SKIP_BRANCH)
        + [("workflow_complete", 98), ("complete", 100)]
    )
    _assert_strictly_increasing(seq, "desk-reject path")


def test_preliminary_halt_path_is_strictly_increasing(progress):
    """Preliminary publish-gate halt: same skip, different reason."""
    seq = (
        [("start", 3)]
        + _seq(progress, _PRE_EDITOR)
        + _seq(progress, _SKIP_BRANCH)
        + [("workflow_complete", 98), ("complete", 100)]
    )
    _assert_strictly_increasing(seq, "preliminary-halt path")


def test_every_value_is_within_0_and_100(progress):
    for event, pct in progress.items():
        assert 0 <= pct <= 100, f'"{event}" publishes {pct}, outside 0-100'


def test_reviewer_panel_anchors_still_match_the_source():
    """The panel percentages live in reviewer_panel.py, outside this fix's scope.
    If they change, the numbers on either side in graph.py must be rechecked."""
    src = REVIEWER_PANEL_PY.read_text(encoding="utf-8")
    published = {
        int(p) for p in re.findall(r'"reviewer_panel",\s*\n\s*(\d+),', src)
    }
    assert published == {_PANEL_START, _PANEL_DONE}, (
        f"reviewer_panel.py now publishes {sorted(published)}; "
        f"expected {[_PANEL_START, _PANEL_DONE]}"
    )


# --------------------------------------------------------------- regression ---

@pytest.mark.parametrize("earlier,earlier_pct,later,later_pct", KNOWN_BAD_PAIRS)
def test_known_backwards_jumps_are_gone(progress, earlier, earlier_pct, later, later_pct):
    """Fails against the OLD constants. Each pair is a real regression that
    shipped: the second event runs after the first but published a lower number."""
    assert later_pct < earlier_pct, "KNOWN_BAD_PAIRS must record an actual decrease"
    assert progress[later] > progress[earlier], (
        f'regression: "{earlier}"={progress[earlier]} then "{later}"={progress[later]}; '
        f"originally {earlier_pct} -> {later_pct}"
    )


def test_reviewer_judge_no_longer_undercuts_the_reviewer_panel(progress):
    """Third backwards jump on the same path: reviewer_panel finishes at 87 but
    reviewer_judge_start published 85."""
    assert progress["reviewer_judge_start"] > _PANEL_DONE, (
        f'reviewer_judge_start={progress["reviewer_judge_start"]} '
        f"must exceed the reviewer panel's completion value {_PANEL_DONE}"
    )


def test_extract_claims_no_longer_undercuts_extract_references(progress):
    """Fourth backwards jump: extract_references ended at 13, extract_claims_start
    published 12."""
    assert progress["extract_claims_start"] > progress["extract_references"]

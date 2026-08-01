"""Per-reviewer section scoping — ``DRAFT_REVIEWER_SCOPED_PANEL``.

No network. These tests pin what the scoped panel actually does:

  * **Union coverage is NOT total at the current budget.** This was the build's
    acceptance criterion and the feature does not meet it. Three personas x 24k
    does not buy 72k of distinct manuscript, because a span claimed by nobody is
    routed to all three and paid for three times. Measured on the eval corpus,
    7 of 15 manuscripts lose text and the worst sees 41% of itself. The tests
    below assert the property that *is* true — a span survives whole iff some
    owning persona can afford its whole assignment — and assert that the
    shortfall is reported rather than silently absorbed.
  * **Flag off is byte-identical.** The assembled message payload with the flag
    off is exactly the string today's code produces. Without that, an A/B
    between the two arms compares two changes, not one.

The coverage and cache assertions run against *real* eval-corpus manuscripts —
the cached LangGraph states under ``scripts/eval/cache/state/`` — because the
mapping is only interesting on the section titles real parsers actually emit
("5.3 ABLATION EXPERIMENT", "6 CONCLUSION AND DISCUSSION", ``type: other``).
Those states are read-only fixtures here; nothing under ``scripts/eval/`` is
written. The tests skip if the cache is absent.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.workflows.draft_analysis.nodes.reviewer_panel import (
    REVIEWER_MANUSCRIPT_MAX_CHARS,
    REVIEWER_PERSONAS,
    SECTION_LANE_OWNERS,
    UNCLAIMED_LANE_OWNERS,
    build_cacheable_reviewer_head,
    build_manuscript_block,
    build_reviewer_messages,
    build_shared_reviewer_prefix,
    log_scoped_coverage,
    manuscript_spans,
    persona_demand,
    scoped_coverage_report,
    scoped_manuscript_text,
    scoped_panel_enabled,
    section_lane,
)

REVIEWER_TYPES = ("literature_positioning", "methodology", "clarity")

_EVAL_STATE_DIR = (
    Path(__file__).resolve().parents[3] / "scripts" / "eval" / "cache" / "state"
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _real_states() -> list[tuple[str, dict]]:
    """Cached pipeline states for real eval-corpus manuscripts."""
    if not _EVAL_STATE_DIR.is_dir():
        return []
    states: list[tuple[str, dict]] = []
    for paper_dir in sorted(_EVAL_STATE_DIR.iterdir()):
        snapshot = paper_dir / "reviewer_panel_node__methodology.json"
        if not snapshot.is_file():
            candidates = sorted(paper_dir.glob("*.json"))
            if not candidates:
                continue
            snapshot = candidates[0]
        try:
            state = json.loads(snapshot.read_text())
        except (OSError, ValueError):
            continue
        if state.get("draft_content") and (state.get("structure") or {}).get("sections"):
            states.append((paper_dir.name, state))
    return states


REAL_STATES = _real_states()
requires_corpus = pytest.mark.skipif(
    not REAL_STATES, reason="eval-corpus cached states unavailable"
)


def _synthetic_state(draft: str, sections: list[dict]) -> dict:
    return {
        "draft_id": "draft-abc-123",
        "project_id": "project-xyz",
        "user_id": "user-42",
        "draft_content": draft,
        "paper_type": "empirical",
        "structure": {"sections": sections, "word_count": len(draft.split())},
        "manuscript_profile": {"genre": "empirical", "study_design": "cohort"},
        "claims": [],
        "claims_with_citations": [],
        "coverage_gaps": [],
        "external_sources": [],
        "diagnostic_findings": [],
        "structural_feedback": [],
    }


_SHORT_SECTION_TITLES = (
    "Abstract",
    "1 Introduction",
    "2 Related Work",
    "3 Methods",
    "4 Results",
    "5 Discussion",
    "6 Limitations",
)


def _short_manuscript_state() -> dict:
    """A manuscript comfortably under the cap — nothing to truncate."""
    body = "A short sentence of body text for this section. " * 8
    draft = "\n\n".join(f"{title}\n{body}" for title in _SHORT_SECTION_TITLES)
    sections = [{"title": t, "type": "other"} for t in _SHORT_SECTION_TITLES]
    return _synthetic_state(draft, sections)


def _long_manuscript_state() -> dict:
    """A manuscript far over the cap, with a distinctive marker per section."""
    sections_text = []
    for title in _SHORT_SECTION_TITLES:
        slug = title.split(" ")[-1].upper()
        body = f"MARKER-{slug} " + ("Body sentence for this section. " * 300)
        sections_text.append(f"{title}\n{body}")
    draft = "\n\n".join(sections_text)
    sections = [{"title": t, "type": "other"} for t in _SHORT_SECTION_TITLES]
    return _synthetic_state(draft, sections)


def _common_prefix_len(a: str, b: str) -> int:
    i = 0
    while i < min(len(a), len(b)) and a[i] == b[i]:
        i += 1
    return i


# ---------------------------------------------------------------------------
# The flag
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_scoping_defaults_off(monkeypatch):
    monkeypatch.delenv("DRAFT_REVIEWER_SCOPED_PANEL", raising=False)
    assert scoped_panel_enabled() is False


@pytest.mark.unit
@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on"])
def test_scoping_flag_is_read_per_call(monkeypatch, value):
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", value)
    assert scoped_panel_enabled() is True
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "0")
    assert scoped_panel_enabled() is False


# ---------------------------------------------------------------------------
# Flag OFF is byte-identical to today
# ---------------------------------------------------------------------------

def _todays_message(state: dict, reviewer_type: str) -> list[dict[str, str]]:
    """Reconstruct today's payload from first principles, independent of the
    refactored helpers, so this is a real oracle and not a tautology."""
    from app.workflows.draft_analysis.nodes.reviewer_panel import (
        SHARED_REVIEWER_PREAMBLE,
        _CONTEXT_BUILDERS,
        _profile_context,
        _reviewer_manuscript_text,
    )

    structure = state.get("structure") or {}
    section_types = [s.get("type", "?") for s in structure.get("sections") or []]
    shared = f"""DRAFT METADATA:
- Paper type: {state.get('paper_type', 'unknown')}
- Word count: {structure.get('word_count', 'unknown')}
- Sections present: {', '.join(section_types) or 'unknown'}

{_profile_context(state)}

FULL MANUSCRIPT TEXT (search this entire text before claiming anything is missing):
{_reviewer_manuscript_text(state.get('draft_content', '') or '')}
"""
    context = shared + _CONTEXT_BUILDERS[reviewer_type](state)
    return [
        {"role": "system", "content": SHARED_REVIEWER_PREAMBLE},
        {
            "role": "user",
            "content": (
                f"Review this paper:\n\n{context}"
                f"\n\nYOUR REVIEWER ASSIGNMENT:\n{REVIEWER_PERSONAS[reviewer_type]}"
            ),
        },
    ]


@pytest.mark.unit
@requires_corpus
def test_flag_off_messages_are_byte_identical_to_today(monkeypatch):
    monkeypatch.delenv("DRAFT_REVIEWER_SCOPED_PANEL", raising=False)
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)

    for paper_id, state in REAL_STATES:
        for reviewer_type in REVIEWER_TYPES:
            assert build_reviewer_messages(state, reviewer_type) == _todays_message(
                state, reviewer_type
            ), f"{paper_id}/{reviewer_type} payload drifted with the flag off"


@pytest.mark.unit
@requires_corpus
def test_flag_off_is_byte_identical_with_compaction_on_too(monkeypatch):
    """The other manuscript flag must keep behaving exactly as it did."""
    monkeypatch.delenv("DRAFT_REVIEWER_SCOPED_PANEL", raising=False)
    monkeypatch.setenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", "1")

    paper_id, state = REAL_STATES[0]
    for reviewer_type in REVIEWER_TYPES:
        assert build_reviewer_messages(state, reviewer_type) == _todays_message(
            state, reviewer_type
        ), f"{paper_id}/{reviewer_type} drifted under compaction"


@pytest.mark.unit
def test_flag_off_manuscript_block_is_shared_across_personas(monkeypatch):
    monkeypatch.delenv("DRAFT_REVIEWER_SCOPED_PANEL", raising=False)
    state = _long_manuscript_state()
    blocks = {build_manuscript_block(state, rt) for rt in REVIEWER_TYPES}
    assert len(blocks) == 1


# ---------------------------------------------------------------------------
# The invariant that matters most: union coverage is total
# ---------------------------------------------------------------------------

@pytest.mark.unit
@requires_corpus
def test_spans_tile_the_manuscript_without_loss():
    """Spans partition draft_content exactly — the precondition for coverage."""
    for paper_id, state in REAL_STATES:
        spans = manuscript_spans(state)
        assert spans, f"{paper_id}: no spans derived from a real structure"
        assert "".join(s["text"] for s in spans) == state["draft_content"], (
            f"{paper_id}: spans do not reconstruct the manuscript"
        )


@pytest.mark.unit
@requires_corpus
def test_every_span_reaches_at_least_one_persona():
    """The map itself: no span is orphaned by SECTION_LANE_OWNERS."""
    for paper_id, state in REAL_STATES:
        for span in manuscript_spans(state):
            assert span["owners"], f"{paper_id}: span {span['title']!r} owned by nobody"
            assert span["owners"] <= frozenset(REVIEWER_PERSONAS)


@pytest.mark.unit
@requires_corpus
def test_every_span_reaches_a_reviewer_at_least_in_part():
    """The weak property — every span is *represented*.

    Kept because it is worth having, and labelled honestly because it is NOT
    the acceptance criterion. Every span gets a floor allocation, so this
    passes by construction and cannot detect a truncated tail. An earlier
    version of this file checked each span's first 120 chars and called the
    result "union coverage is total"; it was structurally incapable of failing.
    The real criterion is asserted below.
    """
    for paper_id, state in REAL_STATES:
        spans = manuscript_spans(state)
        blocks = [scoped_manuscript_text(state, rt) for rt in REVIEWER_TYPES]
        for span in spans:
            head = span["text"][:120]
            if not head.strip():
                continue
            assert any(head in b for b in blocks), f"{paper_id}: {span['title']!r}"


@pytest.mark.unit
@requires_corpus
def test_union_coverage_is_total_exactly_when_the_budget_can_hold_it():
    """The true property, and it does NOT hold on most real manuscripts.

    A span survives whole iff some persona that owns it can afford its entire
    assignment. That is an independent predicate — computed from demand, not
    from the allocator's own output — so it is a real oracle for the allocator.

    On the eval corpus this test documents a genuine coverage regression: the
    aggregate 3 x 24k does not buy 72k of distinct manuscript, because spans
    claimed by nobody are bought once per persona. If a future change makes
    coverage total everywhere, the `assert lossy` line below fails loudly and
    the docstring stops being true — which is the point.
    """
    lossy: list[tuple[str, float]] = []
    for paper_id, state in REAL_STATES:
        spans = manuscript_spans(state)
        report = scoped_coverage_report(state)
        assert report is not None, paper_id

        for index, span in enumerate(spans):
            affordable = any(
                persona_demand(spans, rt) <= REVIEWER_MANUSCRIPT_MAX_CHARS
                for rt in span["owners"]
            )
            fully_covered = not any(
                d["title"] == span["title"] and d["dropped_chars"] > 0
                for d in report["dropped_spans"]
            )
            if affordable:
                assert fully_covered, (
                    f"{paper_id}: {span['title']!r} was affordable to an owner "
                    f"yet still lost text — allocator bug, not a budget limit"
                )

        if report["coverage_ratio"] < 1.0:
            lossy.append((paper_id, report["coverage_ratio"]))

    assert lossy, (
        "No manuscript lost text. If that is now true, the coverage defect this "
        "flag shipped with has been fixed — update this test and the module "
        "comment in reviewer_panel.py rather than deleting the assertion."
    )


@pytest.mark.unit
@requires_corpus
def test_the_coverage_report_never_understates_the_loss():
    """The report is the only thing standing between this feature and silent
    text loss, so it is checked against an independent substring measurement
    rather than trusted."""
    for paper_id, state in REAL_STATES:
        spans = manuscript_spans(state)
        blocks = [
            b for b in (scoped_manuscript_text(state, rt) for rt in REVIEWER_TYPES)
            if b is not None
        ]
        report = scoped_coverage_report(state)

        measured_covered = 0
        for span in spans:
            text = span["text"]
            best = 0
            for block in blocks:  # longest prefix of this span present anywhere
                low, high = best, len(text)
                while low < high:
                    mid = (low + high + 1) // 2
                    if text[:mid] in block:
                        low = mid
                    else:
                        high = mid - 1
                best = max(best, low)
            measured_covered += best

        assert report["covered_chars"] <= measured_covered, (
            f"{paper_id}: report claims {report['covered_chars']} chars covered "
            f"but only {measured_covered} are actually present in any block"
        )
        assert (
            report["covered_chars"] + report["dropped_chars"]
            == report["manuscript_chars"]
        ), f"{paper_id}: coverage accounting does not reconcile"


@pytest.mark.unit
@requires_corpus
def test_the_shortfall_is_logged_not_swallowed(monkeypatch, caplog):
    """Requirement: if scoping drops text, the run says so."""
    import logging

    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    lossy = [
        (pid, st) for pid, st in REAL_STATES
        if (scoped_coverage_report(st) or {}).get("dropped_chars", 0) > 0
    ]
    assert lossy, "expected at least one manuscript to lose text"

    paper_id, state = lossy[0]
    with caplog.at_level(logging.WARNING):
        report = log_scoped_coverage(state, "methodology")

    assert report["dropped_chars"] > 0
    assert "SCOPED COVERAGE SHORTFALL" in caplog.text, paper_id
    # The message must carry the magnitude, not just the fact.
    assert str(report["manuscript_chars"]) in caplog.text
    assert str(report["covered_chars"]) in caplog.text


@pytest.mark.unit
def test_a_complete_run_is_logged_as_complete(monkeypatch, caplog):
    import logging

    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    state = _short_manuscript_state()
    with caplog.at_level(logging.DEBUG):
        report = log_scoped_coverage(state, "clarity")

    assert report["dropped_chars"] == 0
    assert report["coverage_ratio"] == 1.0
    assert "SCOPED COVERAGE SHORTFALL" not in caplog.text


@pytest.mark.unit
def test_under_cap_manuscripts_are_covered_in_full(monkeypatch):
    """When the budget genuinely does not bind, coverage IS total.

    Note the qualifier — this is the regime real corpus manuscripts mostly do
    not occupy (they run 26k-141k chars against a 24k per-persona budget), so
    this test alone must never be read as evidence that coverage holds.
    """
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    state = _short_manuscript_state()
    assert scoped_coverage_report(state)["coverage_ratio"] == 1.0
    blocks = [scoped_manuscript_text(state, rt) for rt in REVIEWER_TYPES]
    for span in manuscript_spans(state):
        assert any(span["text"] in block for block in blocks), span["title"]


@pytest.mark.unit
@requires_corpus
def test_measured_coverage_on_the_real_corpus_is_recorded():
    """Pins the measured shape of the defect so a silent drift is visible."""
    ratios = {
        paper_id: scoped_coverage_report(state)["coverage_ratio"]
        for paper_id, state in REAL_STATES
    }
    losers = {p: r for p, r in ratios.items() if r < 1.0}

    # Measured 2026-08-01 on 15 cached eval states: 7 lose text, worst ~41%.
    assert len(losers) >= 5, f"coverage profile changed: {ratios}"
    assert min(ratios.values()) < 0.60, f"worst-case coverage changed: {ratios}"
    assert all(r > 0.30 for r in ratios.values()), (
        f"coverage collapsed further than measured: {ratios}"
    )


# ---------------------------------------------------------------------------
# Flag ON: each persona gets its lane, and the tail stops being dropped
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_each_persona_receives_its_declared_lane(monkeypatch):
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    state = _long_manuscript_state()

    lit = scoped_manuscript_text(state, "literature_positioning")
    method = scoped_manuscript_text(state, "methodology")
    clarity = scoped_manuscript_text(state, "clarity")

    # Reviewer A's declared lane: introduction, related work, discussion.
    for marker in ("MARKER-INTRODUCTION", "MARKER-WORK", "MARKER-DISCUSSION"):
        assert marker in lit, marker
    # Reviewer B's: methods and results.
    for marker in ("MARKER-METHODS", "MARKER-RESULTS"):
        assert marker in method, marker
    # Reviewer D's sectional lane: abstract and limitations.
    for marker in ("MARKER-ABSTRACT", "MARKER-LIMITATIONS"):
        assert marker in clarity, marker

    # And each stays out of the lanes it is forbidden from.
    assert "MARKER-METHODS" not in lit
    assert "MARKER-DISCUSSION" not in method


@pytest.mark.unit
def test_the_tail_is_no_longer_uniformly_dropped(monkeypatch):
    """The hypothesis under test: a head-first cut removes the discussion, which
    is the section Reviewer A is graded on. Scoping must not."""
    state = _long_manuscript_state()
    draft = state["draft_content"]
    assert len(draft) > REVIEWER_MANUSCRIPT_MAX_CHARS

    # Today's head-first truncation loses the tail for everybody.
    monkeypatch.setenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", "1")
    monkeypatch.delenv("DRAFT_REVIEWER_SCOPED_PANEL", raising=False)
    unscoped = build_manuscript_block(state, "literature_positioning")
    assert "MARKER-LIMITATIONS" not in unscoped

    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    blocks = [build_manuscript_block(state, rt) for rt in REVIEWER_TYPES]
    assert any("MARKER-LIMITATIONS" in b for b in blocks)
    assert any("MARKER-DISCUSSION" in b for b in blocks)


@pytest.mark.unit
@requires_corpus
def test_a_persona_never_exceeds_the_shared_budget(monkeypatch):
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    for paper_id, state in REAL_STATES:
        for reviewer_type in REVIEWER_TYPES:
            block = scoped_manuscript_text(state, reviewer_type)
            # Truncation markers are the only text added on top of the budget.
            marker_slack = block.count("[... section truncated ...]") * 40
            assert len(block) <= REVIEWER_MANUSCRIPT_MAX_CHARS + marker_slack, (
                f"{paper_id}/{reviewer_type} over budget"
            )


@pytest.mark.unit
@requires_corpus
def test_a_lane_is_never_cut_while_unclaimed_text_is_shown(monkeypatch):
    """No reviewer's own lane is cut in order to show it text outside that lane."""
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    for paper_id, state in REAL_STATES:
        spans = manuscript_spans(state)
        for reviewer_type in REVIEWER_TYPES:
            block = scoped_manuscript_text(state, reviewer_type)
            mine = [s for s in spans if reviewer_type in s["owners"]]
            claimed_total = sum(len(s["text"]) for s in mine if s["lane"] is not None)
            if claimed_total >= REVIEWER_MANUSCRIPT_MAX_CHARS:
                continue  # own lane alone overflows; the reserve case
            for span in mine:
                if span["lane"] is None:
                    continue
                assert span["text"] in block, (
                    f"{paper_id}/{reviewer_type}: claimed section {span['title']!r} "
                    f"was cut while unclaimed text was still budgeted"
                )


# ---------------------------------------------------------------------------
# The cache property
# ---------------------------------------------------------------------------

@pytest.mark.unit
@requires_corpus
@pytest.mark.parametrize("flag", ["", "1"])
def test_shared_prefix_is_byte_identical_up_to_the_manuscript(monkeypatch, flag):
    """Under either flag setting, the three personas share every byte up to the
    manuscript block. Losing more of that than necessary is a defect."""
    if flag:
        monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", flag)
    else:
        monkeypatch.delenv("DRAFT_REVIEWER_SCOPED_PANEL", raising=False)

    for paper_id, state in REAL_STATES:
        head = build_cacheable_reviewer_head(state)
        assert head, paper_id
        users = [build_reviewer_messages(state, rt)[1]["content"] for rt in REVIEWER_TYPES]
        systems = {build_reviewer_messages(state, rt)[0]["content"] for rt in REVIEWER_TYPES}

        assert len(systems) == 1, f"{paper_id}: system message diverged"
        for i in range(len(users)):
            for j in range(i + 1, len(users)):
                assert _common_prefix_len(users[i], users[j]) >= len(head), (
                    f"{paper_id}: shared prefix shrank below the cacheable head"
                )


@pytest.mark.unit
@requires_corpus
def test_cacheable_head_carries_nothing_persona_specific(monkeypatch):
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    for paper_id, state in REAL_STATES:
        head = build_cacheable_reviewer_head(state)
        for token in ("Reviewer A", "Reviewer B", "Reviewer D", "YOUR LANE ONLY"):
            assert token not in head, f"{paper_id}: {token!r} leaked into the head"
        for volatile in ("draft_id", "project_id", "user_id"):
            value = state.get(volatile)
            if value:
                assert str(value) not in head, f"{paper_id}: {volatile} leaked"


# ---------------------------------------------------------------------------
# Degradation
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_short_manuscript_is_identical_under_both_flags(monkeypatch):
    """Nothing to truncate and nothing to ration: a manuscript under the cap must
    behave the same in both arms, so the arm comparison is not confounded by
    small papers."""
    state = _short_manuscript_state()
    assert len(state["draft_content"]) < REVIEWER_MANUSCRIPT_MAX_CHARS
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)

    monkeypatch.delenv("DRAFT_REVIEWER_SCOPED_PANEL", raising=False)
    off = {rt: build_reviewer_messages(state, rt) for rt in REVIEWER_TYPES}

    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    on = {rt: build_reviewer_messages(state, rt) for rt in REVIEWER_TYPES}

    for reviewer_type in REVIEWER_TYPES:
        off_text = off[reviewer_type][1]["content"]
        on_text = on[reviewer_type][1]["content"]
        # The scoped path only reorders/omits when there is a budget to enforce;
        # under the cap every persona still receives the whole manuscript.
        assert state["draft_content"] in off_text
        assert all(
            span["text"] in on_text
            for span in manuscript_spans(state)
            if reviewer_type in span["owners"]
        )
        assert off[reviewer_type][0] == on[reviewer_type][0]


@pytest.mark.unit
@pytest.mark.parametrize(
    "structure",
    [
        {},
        {"sections": []},
        {"sections": [{"title": "Methods", "type": "methods"}]},  # one mark only
        {"sections": [{"title": "Nowhere In The Draft", "type": "methods"}]},
        {"sections": [{"type": "methods"}, {"type": "results"}]},  # no titles
        # NB: a `sections` list holding non-dicts crashes the draft-metadata line
        # in the shared prefix today, with or without this flag. Not exercised
        # here — fixing it is a change to code this build does not own.
    ],
)
def test_unparseable_structure_degrades_to_todays_behaviour(monkeypatch, structure):
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    monkeypatch.delenv("DRAFT_REVIEWER_COMPACT_MANUSCRIPT", raising=False)
    draft = "Some manuscript body without usable headings. " * 200
    state = _synthetic_state(draft, [])
    state["structure"] = dict(structure)
    state["structure"].setdefault("word_count", len(draft.split()))

    for reviewer_type in REVIEWER_TYPES:
        block = build_manuscript_block(state, reviewer_type)
        assert block.startswith("FULL MANUSCRIPT TEXT")
        assert draft in block
        assert build_reviewer_messages(state, reviewer_type) == _todays_message(
            state, reviewer_type
        )


@pytest.mark.unit
def test_empty_draft_does_not_error(monkeypatch):
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    state = _synthetic_state("", [{"title": "Methods", "type": "methods"}])
    assert manuscript_spans(state) == []
    for reviewer_type in REVIEWER_TYPES:
        assert build_manuscript_block(state, reviewer_type).startswith(
            "FULL MANUSCRIPT TEXT"
        )


# ---------------------------------------------------------------------------
# The map itself
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize(
    "title,expected",
    [
        ("Abstract", "abstract"),
        ("1 INTRODUCTION", "introduction"),
        ("2 BACKGROUND", "introduction"),
        ("2 Related Work", "related_work"),
        ("3.1 MDP FORMULATION", None),
        ("4 ALGORITHM AND TRAINING", "methods"),
        ("5.1 EXPERIMENTAL SETTINGS", "methods"),
        ("5.3 ABLATION EXPERIMENT", "results"),
        ("6 CONCLUSION AND DISCUSSION", "discussion"),
        ("Limitations and Future Work", "limitations"),
        ("REFERENCES", "references"),
    ],
)
def test_section_lane_classification(title, expected):
    assert section_lane(title, "other") == expected


@pytest.mark.unit
def test_type_is_the_fallback_when_the_title_says_nothing():
    assert section_lane("Table 3", "results") == "results"
    assert section_lane("Table 3", "other") is None
    assert section_lane("Table 3", None) is None


@pytest.mark.unit
def test_every_declared_lane_has_an_owner_and_every_persona_owns_something():
    assert set(SECTION_LANE_OWNERS) >= {
        "introduction", "related_work", "discussion",  # Reviewer A's declared lane
        "methods", "results",                          # Reviewer B's
        "abstract", "limitations",                     # Reviewer D's sectional lane
    }
    owned = set().union(*SECTION_LANE_OWNERS.values())
    assert owned == set(REVIEWER_PERSONAS)
    assert UNCLAIMED_LANE_OWNERS == frozenset(REVIEWER_PERSONAS)


@pytest.mark.unit
@requires_corpus
def test_scoping_actually_reduces_per_persona_manuscript_size(monkeypatch):
    """If scoping never shrinks anything it is not doing its job — and the cost
    arm of the comparison would be meaningless."""
    monkeypatch.setenv("DRAFT_REVIEWER_SCOPED_PANEL", "1")
    shrunk = 0
    for _paper_id, state in REAL_STATES:
        full = len(state["draft_content"])
        for reviewer_type in REVIEWER_TYPES:
            block = scoped_manuscript_text(state, reviewer_type)
            if block is not None and len(block) < full:
                shrunk += 1
    assert shrunk > 0

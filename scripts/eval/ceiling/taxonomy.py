"""The taxonomy the ceiling study labels against, and why it is shaped this way.

The question this has to answer is *how much of the 94% miss is worth
engineering against*, so a category earns its place only if putting a unit in it
changes what someone would build. Descriptive categories ("clarity", "novelty")
were rejected on that test.

Eight categories, applied with a fixed precedence so every unit gets exactly one
label. The precedence runs from "no system could fairly be scored on this" down
to "a system should have caught this", and ``defect_addressable`` is the
**residual** -- a unit lands there only if nothing else claims it. That makes the
ceiling a *lower* bound, which is the honest direction for a number that is about
to be used to set a target.

Precedence, highest first
-------------------------
1. ``context_dependent`` -- the text cannot be understood standing alone. Either
   it references a sibling unit ("This will add more strength to the paper.",
   "The authors should square these two facts.") or it is a bare lead-in ("This
   paper has significant defects with clarity."). **These are manufactured by
   the labelling pipeline, not by the reviewers**: ``atomize_reviews_v1`` splits
   a reviewer's prose into "atomic, independently-verifiable concerns" and the
   split points fall mid-argument. Nothing a reviewer system emits can or should
   match "This will add more strength to the paper." Counting these in the
   denominator depresses every recall number in the head-to-head by construction.
2. ``meta_venue`` -- about the venue, page limits, or submission fit rather than
   the manuscript ("I would suggest the authors consider a journal paper
   instead.").
3. ``surface_copyedit`` -- typos, spacing, notation slips, missing figure axis
   labels, unresolved ``(ref)`` placeholders. Split out of
   ``defect_addressable`` deliberately, and this is the taxonomy's most
   consequential departure from the brief. These *are* findable by reading, so
   burying them in "unaddressable" would understate the ceiling; but a
   pre-submission reviewer whose recall is carried by "comma missing after
   Equation 7" is not the product, so counting them as addressable would inflate
   a target that a roadmap is about to chase. Reported as its own line, and the
   ceiling is given both with and without it.
4. ``generic_non_defect`` -- an evaluative remark that names no verifiable flaw
   and asks for nothing specific ("This complexity might make it challenging for
   practitioners", "the method is largely theoretical"). Concentrated almost
   entirely in one reviewer, and worth separating because it is unmatchable in
   the same way ``context_dependent`` is, for a different reason.
5. ``needs_literature`` -- requires knowing what else exists: a named prior work,
   a novelty delta against it, a baseline the manuscript never mentions.
   Addressable in principle by a retrieval-equipped reviewer, which makes this
   the one non-addressable bucket with a plausible roadmap.
6. ``needs_expertise`` -- domain judgement the manuscript's own text does not
   contain: numerical-analysis correctness, a derivation the reviewer performed,
   a field-priority opinion, a claim about what is standard practice.
7. ``request_not_defect`` -- an ask with no flaw asserted ("Are there plans
   to...", "Could you elaborate on..."). If the ask presupposes a gap ("the
   authors should define X earlier" implies X is undefined) it is a defect, not
   a request.
8. ``defect_addressable`` -- residual. A concrete flaw in the manuscript's own
   text, findable by reading it: unsupported claim, missing ablation or baseline,
   undefined term, internal contradiction, unreported experimental detail,
   missing limitation, incomplete table.

Orthogonal flag
---------------
``requires_non_text`` marks units that depend on a figure, a rendered table, or
page layout -- things GROBID text extraction does not carry. Both systems read
GROBID output, so these are out of reach on modality grounds regardless of
category. Reported separately rather than folded into a category, because the
fix is a different one (multimodal parsing, not better prompting).
"""

from __future__ import annotations

CATEGORIES = (
    "context_dependent",
    "meta_venue",
    "surface_copyedit",
    "generic_non_defect",
    "needs_literature",
    "needs_expertise",
    "request_not_defect",
    "defect_addressable",
)

#: Precedence order, highest first. Identical to CATEGORIES; kept as a separate
#: name so the ordering intent survives a reordering of the tuple above.
PRECEDENCE = CATEGORIES

#: The categories a roadmap could plausibly target today.
ADDRESSABLE = ("defect_addressable",)

#: Addressable only if the system is given literature retrieval. Reported as the
#: marginal bucket, because it is the one place where an architecture change --
#: rather than prompt work -- moves the ceiling.
ADDRESSABLE_WITH_RETRIEVAL = ("defect_addressable", "needs_literature")

#: Findable by reading, but not what the product is for. See category 3.
ADDRESSABLE_INCLUDING_SURFACE = ("defect_addressable", "surface_copyedit")

#: Unmatchable by construction: no reviewer output can or should be credited.
UNMATCHABLE = ("context_dependent", "generic_non_defect", "meta_venue")

CATEGORY_DESCRIPTIONS = {
    "context_dependent": "Fragment that references a sibling unit or is a bare lead-in; artefact of atomize_reviews_v1 segmentation.",
    "meta_venue": "About the venue, page limits or submission fit rather than the manuscript.",
    "surface_copyedit": "Typo, spacing, notation slip, missing axis label, unresolved (ref) placeholder.",
    "generic_non_defect": "Evaluative remark naming no verifiable flaw and asking for nothing specific.",
    "needs_literature": "Requires knowing what else exists: named prior work, novelty delta, unmentioned baseline.",
    "needs_expertise": "Domain judgement not contained in the manuscript's text.",
    "request_not_defect": "An ask with no flaw asserted.",
    "defect_addressable": "Concrete flaw in the manuscript's own text, findable by reading it.",
}


def validate(category: str) -> str:
    if category not in CATEGORIES:
        raise ValueError(f"unknown category {category!r}; expected one of {CATEGORIES}")
    return category

# Executive Decision: Noesis vs. Reviewer3

> May 10, 2026 note: This file is retained as historical competitive/positioning context. It is not the current product or pricing source of truth. Use `current_state.md` for current Noesis status, especially the caveat that Stripe production pricing is not finished and lab outreach is starting now.

**Date:** April 25, 2026
**Status:** Active strategic decision
**Author:** Founder review

---

## 1. Situation Assessment — Honest

You found [reviewer3.com](https://reviewer3.com) and felt the wind go out of the room. That reaction is natural and worth examining, because the facts are more favorable than the fear.

**What Reviewer3 actually is:**
- Founded 2025. Single investor (E14 Fund, MIT-affiliated). ~5,000 users across 120 countries.
- Pre-seed/seed stage. Small team. One year old.
- $49.99/review or $129/month flat. No team plan publicly listed.
- SOC 2 Type II certified. PDF-anchored critique.

**What Reviewer3 does NOT do:**
- No external citation verification — it reads your citations as written and trusts them
- No literature gap detection — cannot identify papers you should have cited
- No citation-to-claim mapping — cannot tell you which claims lack support
- No BibTeX/library management
- No paper discovery
- Training data skews toward ML conference reviews (ICLR, NeurIPS, ACL are public); thin signal for biomedical, social science, and humanities
- Cannot tell you which journal to target or what desk-rejection risk looks like

**What Reviewer3 does well:**
- Structural manuscript critique (argument, methods, reproducibility, limitations)
- Speed (under 10 minutes)
- Clean privacy story (SOC 2, no training on manuscripts)
- Clear "Reviewer 1/2/3 panel" metaphor that resonates

**The honest overlap:** The tagline ("know what reviewers will say before you submit") is the same territory. The *product* is not the same product.

---

## 2. Noesis's Structural Moat

Reviewer3 critiques your *writing*. Noesis critiques your *argument against your literature*.

That distinction is load-bearing:

| Capability | Reviewer3 | Noesis |
|---|---|---|
| Manuscript structure critique | ✅ | ✅ |
| Argument strength / novelty | ✅ | ✅ |
| Citation-to-claim mapping | ❌ | ✅ |
| Literature gap detection | ❌ | ✅ |
| "You should have cited X" | ❌ | ✅ |
| BibTeX / reference management | ❌ | ✅ |
| Paper discovery from gaps | ❌ | ✅ |
| Humanities / biomed calibration | ❌ (thin) | Stack-agnostic |
| Per-claim support evidence | ❌ | ✅ |

The correct framing: **Reviewer3 tells you your argument is weak. Noesis tells you your argument is weak AND which papers would fix it.** That second half is the reason researchers don't just fix problems they find — they don't know where to look. Noesis closes that loop.

This is not a feature gap that Reviewer3 will fill in a sprint. Citation verification requires external API integrations (Semantic Scholar, OpenAlex, PubMed), a document corpus, chunk-level embeddings, and a literature-to-claim matching pipeline. That's 6–9 months of backend work and a fundamentally different architecture. Noesis has this *now*.

---

## 3. Decision Options

### Option A — Stay the course, sharpen positioning
Noesis continues as a draft-aware literature intelligence platform. Tighten the positioning around the Reviewer3 gap: "Reviewer3 finds the holes in your argument. Noesis finds the papers that fill them."

**Pros:** No context switch. Current technical moat is real. Natural response to a discoverable competitor gap.
**Cons:** Reviewer3 has more polish on the pure manuscript critique UX. Head-to-head conversion battles will happen.

### Option B — Pivot to grant proposal review only
Abandon manuscript review. Rebuild for NIH/NSF/ERC grant proposal critique.

**Pros:** Less crowded. Large market ($6.2B grant writing services). NIH's July 2025 AI policy (NOT-OD-25-132) bans AI-generated grant content but explicitly permits critique tools — this creates urgency.
**Cons:** Full pivot wastes current technical moat. Same architecture still needed; the reframe is shallow. Grant review is harder to sell PLG (proposals are higher stakes, longer cycles, more anxiety about AI compliance).

### Option C — Add grant review as a second product surface (recommended)
Keep the manuscript review product. Add a "Grant Proposal Review" mode that reuses the same stack (upload proposal → map claims to literature → identify gaps → simulate study section critique). Position as: manuscript review for submission, grant review for funding.

**Pros:** Same backend, near-zero incremental technical work. Opens a B2B institutional sales motion (research offices, graduate programs). Differentiates from Reviewer3 (which has no grant mode). Aligns with NIH policy tailwind.
**Cons:** Adds a second ICP to serve. Messaging gets more complex if done sloppily.

---

## 4. Recommended Path

**Option C with a sequenced rollout.**

### Phase 1 — Sharpen the weapon (now, 30 days)
Reviewer3 owns "AI peer review." Don't fight that label. Own a different and more specific one:

> **"Literature-grounded manuscript review."**
> Reviewer3 reviews your writing. Noesis reviews your argument against the evidence.

Concrete actions:
1. Update landing page headline: lean into "Find the papers Reviewer 2 will ask about before they do."
2. Add a direct comparison table on the homepage (no need to name them — "Other tools review your writing. Noesis reviews your literature coverage.").
3. Build one shareable artifact: a public "Coverage Gap Report" preview — a real example showing a manuscript's claims mapped to literature gaps. Make it viral-shareable for academic Twitter.
4. Every onboarding email should demonstrate the claim-to-literature gap workflow within the first session.

### Phase 2 — Go deep at GT (30–60 days)
Don't try to go wide yet. Reviewer3 is already in 120 countries with 5K users. You cannot win at global scale right now.

Win at Georgia Tech first:
- Target 3–5 GT PhD advisors (CS, BME, ECE are the densest programs).
- Get one lab to commit to using Noesis for their next submission cycle.
- CREATE-X and VentureLab are warm channels — use them.
- One faculty testimonial from a GT PI shared on r/GradSchool or the GT PhD Slack reaches 5–10 other R1 universities organically.

**This is DoorDash's playbook.** They launched as PaloAltoDelivery.com. One campus, full density, word of mouth. Then expanded.

### Phase 3 — Grant proposal mode (60–90 days)
Build a "Grant Review" tab or toggle alongside manuscript review. Workflow is nearly identical:
- Upload NIH/NSF Specific Aims or full proposal
- Map claims to cited literature (existing pipeline)
- Detect gaps relative to NIH study section priorities
- Generate study-section-style critique without writing content for the user

Pricing: Keep individual PLG. Add a "Research Group" plan at $49/month (5 seats). Add an institutional inquiry form for research offices (first B2B lead generation, $500–$2K/month ACV).

NIH's NOT-OD-25-132 (July 2025) bans AI-generated grant text. Critique-only tools like Noesis are explicitly permitted. This regulatory tailwind is real and time-sensitive — several grant writing tools will be forced to remove or nerf features in the next 6 months. Noesis's "no auto-writing, reviewer behavior only" architecture is already compliant.

---

## 5. What NOT to Do

- **Do not rebuild Reviewer3.** Competing on manuscript structure critique alone against a team that is 12 months ahead on that specific UX is a losing battle. Fight on the terrain where you have the moat.
- **Do not pivot away entirely.** The technical investment in citation-to-claim mapping, BibTeX resolution, and paper discovery is the defensible asset. A full pivot abandons it.
- **Do not try to out-market them globally at this stage.** 120 countries is noise — most of those users churned after one free review. Depth at one institution is worth more than shallow breadth.
- **Do not lower pricing to undercut.** $49.99/review is Reviewer3's price. Competing on price trains users to see this as a commodity. Compete on capability.

---

## 6. Competitive Positioning Summary

| | Reviewer3 | Noesis |
|---|---|---|
| **Core claim** | "Know what reviewers will say" | "Know what Reviewer 2 will ask for — and find it" |
| **Moat** | Speed, UX polish, SOC 2 | Draft + literature integration, citation-to-claim mapping |
| **Gap they can't close** | No literature corpus, no citation verification | Polish, brand recognition |
| **Target ICP** | Individual researcher, pre-submission | Individual researcher + lab groups, submission prep |
| **Grant mode** | None | Build in 60 days |
| **B2B path** | Early enterprise interest listed | Research offices, grad programs |
| **Funding** | E14 Fund (seed, undisclosed) | Seed-stage, pre-raise |

---

## 7. One-Line Decision

**Do not pivot. Sharpen the moat, go deep at GT, and add grant review as a second surface in 60 days.**

Reviewer3 is a peer competitor at the same stage, not a market incumbent. Their gap — no literature intelligence, no citation verification — is your structural advantage. They cannot buy that gap closed in a sprint. You have it now.

---

*Sources: reviewer3.com, manusights.com competitive analysis, NIH NOT-OD-25-132, ERC 2026 application data, OpenView PLG benchmarks, DoorDash/Figma/Tinder campus GTM case studies.*

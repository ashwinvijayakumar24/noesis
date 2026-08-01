# Reference Critique: *“We Need Fairness and Explainability in Algorithmic Hiring”*  
**Track:** Blue Sky Ideas  
**Overall Assessment:** Important topic, but lacks novelty positioning, methodological specificity, and engagement with foundational fairness and hiring literature. Reads more as a community call-to-action than a research vision with concrete technical contributions.

---

## 1. Major Methodological & Conceptual Issues

### HIGH — No Clear Technical Contribution or Research Agenda
> *“We argue for concentrated research around the thesis that…”*  
> *“We envision the research community addressing these gaps…”*

The paper primarily advocates for research rather than proposing a concrete framework, formal model, or algorithmic contribution. For a Blue Sky track this may be partially acceptable, but:

- No formal definition of *multi-stage fairness* is provided.
- No formal problem statement or theorem-level research questions.
- No illustrative example showing how fairness constraints fail under stage composition.
- No conceptual framework explaining how fairness constraints propagate across pipeline stages.

The thesis (“single-stage fairness can be extended to multi-stage processes”) is asserted but not substantiated. There is no argument for why this extension is tractable, feasible, or even coherent under known fairness impossibility results.

**Reviewer 2 likely comment:**  
> “This reads like a position paper advocating more fairness research rather than proposing a principled research program.”

---

### HIGH — Oversimplified Modeling of Hiring as a Multi-Armed Bandit

> *“When modeling the hiring process as a MAB problem we have a set of arms a ∈ A, such that each applicant is an arm…”*

Modeling each applicant as a bandit arm is problematic:

1. **Arms in standard MAB are reusable; applicants are not.**  
   Hiring decisions are typically one-shot with delayed and censored outcomes.
2. **Feedback loops are ignored.**  
   Decisions affect applicant behavior, labor market composition, and applicant pool demographics.
3. **Pipeline structure conflicts with standard MAB assumptions.**  
   Rewards are not IID, nor independent of earlier screening stages.
4. **Selection bias and selective labels problem** (Kleinberg et al., Lakkaraju et al.) are not addressed.
5. **Outcome observability problem:** “Applicant success?” is often unobserved for rejected candidates.

This modeling choice is neither defended nor problematized. There is no discussion of alternative frameworks:
- Markov Decision Processes (MDPs)
- Sequential decision processes with partial observability
- Causal inference under selection
- Dynamic mechanism design

**Severity justification:** The core technical framing rests on this assumption.

---

### HIGH — Ignores Known Fairness Impossibility Results in Sequential Settings

The paper references Chouldechova and Roth but does not engage with:

- Kleinberg, Mullainathan & Raghavan (2016/2017) impossibility results.
- The tension between calibration, equalized odds, and base rates.
- How these trade-offs compound in multi-stage pipelines.
- Dynamic fairness (Liu et al., 2018; Hu & Chen; Heidari et al.).
- Feedback effects in dynamic systems (Ensign et al., 2018 predictive policing feedback loops).

Claiming that single-stage fairness can be “extended in a principled way” is extremely strong given existing impossibility theorems. The paper neither acknowledges nor reconciles these.

---

### MEDIUM — Lack of Empirical or Theoretical Demonstration

> *“In our exploratory work, we adopt a subset of the standard notions of fairness, and we perform analysis on real admissions data [43, 44]…”*

This is asserted but not summarized:
- What dataset?
- What fairness definitions?
- What were the findings?
- Did fairness degrade across stages?

No figure or simulation demonstrates pipeline-level unfairness amplification. A minimal motivating experiment would strengthen the paper substantially.

---

## 2. Citation Gaps and Literature Positioning

### HIGH — Missing Seminal Fairness Literature

Notably absent (or insufficiently engaged):

- Kleinberg et al. (2017) — Inherent trade-offs in risk scores.
- Hardt et al. (2016) — Equalized Odds.
- Dwork et al. (2012) — Fairness through awareness.
- Corbett-Davies & Goel (2018) — The measure and mismeasure of fairness.
- Ensign et al. (2018) — Runaway feedback loops.
- Liu et al. (2018) — Delayed impact of fair ML.
- Heidari et al. — Long-term fairness.
- Barocas, Hardt, Narayanan (2019) — Fairness and ML (book).

Given the thesis centers on extending fairness to multi-stage/dynamic systems, the omission of dynamic fairness literature is particularly serious.

---

### MEDIUM — Hiring-Specific Literature Underdeveloped

The draft references UpTurn and Facebook settlements but lacks:

- Industrial-organizational psychology literature on hiring validity and bias.
- Adverse impact doctrine (e.g., 4/5ths rule under EEOC).
- Structured interviews vs. algorithmic scoring comparisons.
- Audit studies of resume screening (e.g., Bertrand & Mullainathan 2004).
- Recent empirical audits of algorithmic hiring tools.

If the paper is about fairness in hiring, it must integrate domain-specific scholarship beyond CS.

---

### MEDIUM — Overemphasis on AAMAS Internal Framing

Sections enumerating AAMAS areas (“Area 7 – Markets/Game Theory…”) feel conference-internal rather than scholarly. This weakens the academic contribution and reads as community marketing.

---

## 3. Structural & Organizational Problems

### HIGH — Thesis is Vague and Non-Falsifiable

> *“Data-driven approaches… can be extended—in a principled way—to the full, multistage hiring process.”*

This is not operationalized:
- What does “principled” mean?
- What guarantees are sought?
- Preservation of which fairness metric?
- Under what assumptions?

A strong Blue Sky thesis should articulate:
- A formal conjecture.
- A conceptual framework.
- A set of testable hypotheses.

---

### MEDIUM — Abstract Lacks Specific Contributions

The abstract:
- States the problem.
- Mentions broad challenges.
- Invokes AAMAS.

It does **not**:
- Propose a model.
- Outline specific research questions.
- Indicate technical innovation.

It reads more like a call-to-arms editorial.

---

### MEDIUM — Incomplete Section

The draft ends mid-sentence:

> *“However, in hiring, credit, and housing there are a number of”*

This suggests structural incompleteness and weakens the submission significantly.

---

## 4. Novelty Positioning

### LOW–MEDIUM — Topic is Important but Not Novel

By 2020, fairness in hiring and dynamic fairness were already active areas. The novelty claim rests on:

- Multi-stage hiring pipeline modeling.
- Multi-stakeholder fairness.

However:
- Multi-stage fairness had already been discussed in dynamic fairness literature.
- Multi-stakeholder fairness exists in mechanism design and participatory ML literature.
- No explicit differentiation from prior dynamic fairness or sequential allocation work.

The paper should explicitly answer:

> How is fairness in hiring pipelines different from fairness in lending pipelines, criminal justice pipelines, or dynamic recommendation systems?

Currently, this distinction is not made.

---

## 5. Writing & Clarity Issues

### MEDIUM — Repetitive and Diffuse

The manuscript repeatedly:
- States fairness is important.
- States algorithms are deployed.
- States AAMAS is well-positioned.

Less space is devoted to:
- Concrete modeling challenges.
- Formal definitions.
- Counterexamples.

---

### LOW — Minor Clarity/Style Issues

- Typographical inconsistencies (“Lousiana” misspelling).
- Some formatting issues around math notation.
- Occasional overlong sentences.
- Figure 1 not clearly explained in text.
- “Rawlsian notion of equal treatment of equals [40]” oversimplifies Rawls.

---

## 6. What Reviewer 2 Would Say

> “This submission identifies an important problem but does not articulate a sufficiently concrete research agenda. The modeling choice (applicants as bandit arms) is oversimplified and ignores known issues such as selective labels and feedback loops. The paper does not engage deeply with impossibility results in fairness nor with the substantial dynamic fairness literature. It reads more like a community position statement than a research vision. I encourage the authors to formalize multi-stage fairness, provide a toy model showing composition failure, and clarify how their proposal differs from existing work on dynamic and long-term fairness.”

---

## 7. Summary of Severity

| Category | Severity |
|----------|----------|
| Technical contribution missing | **HIGH** |
| Oversimplified MAB modeling | **HIGH** |
| Missing engagement with fairness impossibility results | **HIGH** |
| Citation gaps (dynamic fairness, seminal works) | **HIGH** |
| Hiring domain literature underdeveloped | MEDIUM |
| Weak novelty positioning | MEDIUM |
| Abstract and structure weaknesses | MEDIUM |
| Writing/clarity issues | LOW |

---

# Overall Recommendation (as a reviewer)

Promising topic and strong authorship team, but requires:

1. A formal definition of multi-stage fairness.
2. Engagement with dynamic fairness and impossibility results.
3. Clear differentiation from prior work.
4. Either a conceptual framework or a motivating theoretical/empirical example.
5. Removal of conference-internal framing.

As written, this is closer to a perspective piece than a rigorous Blue Sky research vision.
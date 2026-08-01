# Reference Critique  
**Manuscript:** *Federated Learning in Medical Image Analysis: A Systematic Survey*  
**Journal:** Electronics (MDPI)  
**Type:** Systematic Review  

---

# Overall Assessment

The manuscript addresses a timely and important topic — Federated Learning (FL) in medical image analysis. However, despite its relevance, the review suffers from **major methodological weaknesses, limited rigor in the systematic process, insufficient positioning relative to prior surveys, and structural weaknesses that undermine its contribution as a “systematic survey.”**  

Below is a structured critique with severity ratings.

---

# 1. Major Methodological Issues

## 1.1 Single-Database Search (HIGH)

> “This systematic literature review was carried out in the SCOPUS database.”

Limiting the search to **only SCOPUS** is a critical flaw for a systematic review. A high-quality systematic review in AI/medical imaging must include at least:

- PubMed/MEDLINE  
- IEEE Xplore  
- Web of Science  
- ACM Digital Library  
- arXiv (for rapidly evolving ML fields)

The authors state:

> “Using the same criteria, a second search was performed in the PubMed database, but no additional articles were retrieved.”

This is implausible given the volume of FL-medical imaging publications indexed in PubMed since 2020. This strongly suggests:
- Poorly designed search strings  
- Overly restrictive filters  
- Incorrect query logic  

This severely threatens reproducibility and completeness.

---

## 1.2 Inadequate Search Strategy (HIGH)

The search string is:

> (a) 'federated learning' OR 'federated machine learning'; (b) 'medical image' OR 'medical imaging'.

Major omissions:
- No MeSH terms (for PubMed)
- No synonyms such as:
  - “distributed learning”
  - “collaborative learning”
  - “privacy-preserving learning”
  - “healthcare imaging”
  - “radiology”
- No Boolean nesting clarity
- No search field specification (title? abstract? keywords?)

This likely excluded relevant work.

---

## 1.3 Lack of Inclusion/Exclusion Criteria Transparency (HIGH)

The filtering process states:

> “42 articles were discarded for not meeting the criteria…”

But no explicit criteria are defined beyond imaging modality. Missing:

- Language restrictions?
- Conference vs journal?
- Peer-review requirement?
- Clinical validation requirement?
- Minimum dataset size?
- Evaluation metrics?

The exclusion:

> “20 articles were excluded once they were focused on topics unrelated to this study.”

This is vague and non-reproducible.

---

## 1.4 Extremely Small Final Sample (HIGH)

Only **22 original articles** were included.

Given the explosive growth of FL in medical imaging (2020–2024), this number is unrealistically small and suggests:

- Severe under-coverage
- Selection bias
- Incomplete retrieval

A systematic review with only 22 studies in such a hot field is likely underpowered to draw meaningful conclusions.

---

## 1.5 No Risk of Bias or Quality Assessment (HIGH)

There is no:

- Study quality scoring
- Risk of bias analysis
- Dataset bias discussion
- Statistical heterogeneity assessment
- Publication bias analysis

PRISMA is cited, but PRISMA compliance requires more than a diagram.

---

## 1.6 No Meta-Analysis or Quantitative Synthesis (MEDIUM)

Although not mandatory, the paper reports:

> “reported accuracy”

Yet:
- No cross-study metric harmonization
- No performance comparison framework
- No analysis of variability
- No discussion of statistical significance

This reduces the paper to a descriptive summary rather than a systematic evaluation.

---

# 2. Citation Gaps

## 2.1 Missing Seminal FL Works (HIGH)

The manuscript cites:

> “introduced in a study published by Google in 2017 [8]”

But does not clearly reference:
- McMahan et al., 2017 (FedAvg — foundational)
- Kairouz et al., 2021 (Comprehensive FL survey)
- Li et al., 2020 (FedProx)
- Karimireddy et al., 2020 (SCAFFOLD)
- Wang et al., 2020 (FedNova)

A systematic survey must include methodological FL foundations, not only medical applications.

---

## 2.2 Missing Prior Surveys (HIGH)

There have already been surveys on:
- Federated learning in healthcare
- FL in medical imaging
- Privacy-preserving AI in radiology

The manuscript does not convincingly differentiate itself from:

- Rieke et al., 2020 (Nature Medicine – FL in healthcare)
- Sheller et al., 2020 (Brain tumor segmentation FL)
- Recent 2022–2023 surveys on FL in medical AI

Without comparative positioning, the novelty is unclear.

---

## 2.3 Privacy & Security Literature Underrepresented (MEDIUM)

The manuscript claims:

> “The data exchanged is encrypted to ensure that no other devices access private information.”

This is misleading and oversimplified. Missing discussion of:

- Gradient leakage attacks
- Model inversion attacks
- Membership inference attacks
- Differential privacy
- Secure aggregation protocols

This is a major conceptual gap in a privacy-focused review.

---

# 3. Structural Problems

## 3.1 Weak Abstract (MEDIUM)

The abstract:
- Is overly descriptive
- Does not quantify scope
- Does not report number of included studies
- Does not specify time range
- Does not state major findings

A systematic review abstract must include:
- Objective
- Methods (databases, timeframe)
- Number of studies
- Key trends
- Key challenges
- Contributions

---

## 3.2 No Clear Contribution Statement (HIGH)

The paper claims:

> “The main purpose of this article is to present the current state-of-the-art…”

This is insufficient. What differentiates this survey from others?

Missing:
- Taxonomy contribution?
- Benchmark comparison?
- Architectural classification?
- Clinical validation analysis?
- Regulatory analysis?

Currently, it reads as a descriptive aggregation.

---

## 3.3 Poor Section Balance (MEDIUM)

Section 2 (“Federated Learning”) explains basic FL concepts that are widely known and not specific to medical imaging. It consumes significant space but adds little novelty.

Meanwhile:
- No deep technical analysis
- No taxonomy of FL strategies
- No comparison across modalities in structured form

---

## 3.4 Over-Reliance on Figures and Tables Without Critical Analysis (MEDIUM)

The manuscript includes many summary tables, but:

- No cross-comparison discussion
- No synthesis of trends
- No identification of dominant architectures
- No failure mode analysis

A systematic survey must interpret, not just summarize.

---

# 4. Novelty Positioning

## 4.1 Unclear Differentiation from Existing Surveys (HIGH)

The paper does not explain:

- How it differs from existing FL-in-healthcare surveys
- Why modality restriction (MRI, CT, X-ray, histology) is novel
- What analytical dimension is new

Restricting to imaging modalities alone is not a sufficient novelty claim.

---

## 4.2 No Theoretical or Conceptual Framework (MEDIUM)

The survey lacks:
- Taxonomy of FL paradigms (cross-silo vs cross-device)
- Communication efficiency strategies
- Personalization approaches
- Heterogeneity mitigation techniques
- Regulatory landscape discussion (GDPR, HIPAA)

Without a framework, it reads as a list rather than a structured synthesis.

---

# 5. Writing and Clarity Issues

## 5.1 Language Redundancy and Informality (MEDIUM)

Examples:

> “AI is in a development stage that can use medical images to successfully detect and diagnose pathological conditions successfully.”

Repetition of “successfully.”

> “very high-quality AI-based models, mainly deep machine-based models”

Redundant phrasing.

---

## 5.2 Overgeneralized Claims (HIGH)

> “The data exchanged is encrypted…”

Not universally true in FL. Many implementations do not include secure aggregation by default.

> “FL facilitates real-time model updates…”

This is not inherent to FL and is often impractical in cross-silo healthcare settings.

These statements oversimplify and misrepresent technical realities.

---

## 5.3 Typographical Issues (LOW)

- “ASystematic Survey” (missing space in title)
- Formatting inconsistencies
- Some awkward transitions

Minor but noticeable.

---

# 6. What Reviewer 2 Would Say

Expect the following:

1. “This is not a true systematic review — it lacks multi-database search, transparent criteria, and quality assessment.”
2. “The manuscript does not position itself relative to existing surveys.”
3. “Only 22 studies in such a rapidly growing field suggests an incomplete search.”
4. “The technical depth is insufficient for a journal like Electronics.”
5. “The novelty and contribution are unclear.”
6. “The authors oversimplify privacy guarantees in federated learning.”
7. “The survey lacks critical insight and reads as a descriptive listing.”

---

# 7. Summary of Severity

| Category | Severity |
|----------|----------|
Methodological rigor | HIGH |
Search completeness | HIGH |
Novelty positioning | HIGH |
Citation coverage | HIGH |
Privacy/security analysis | HIGH |
Structural clarity | MEDIUM |
Writing quality | MEDIUM |
Formatting | LOW |

---

# Final Verdict (If Reviewing)

**Recommendation: Major Revision (borderline reject).**

To reach publishable quality, the authors would need to:

1. Redesign the systematic search across multiple databases.
2. Expand the study pool substantially.
3. Add explicit inclusion/exclusion criteria.
4. Conduct quality assessment of included studies.
5. Compare and position against existing surveys.
6. Provide a structured taxonomy of FL approaches.
7. Critically analyze privacy/security limitations.
8. Reduce generic FL background and increase analytical depth.

Currently, the manuscript functions more as a **narrative overview** than a rigorous systematic survey.
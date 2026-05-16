# Noesis - Historical Create-X Startup Launch Pitch Deck Guide

> May 10, 2026 note: Historical fundraising/pitch material. Use `../../current_state.md` for current product, pricing, and outreach status.

> **CEO Advisory Note:** This guide has been sharpened with a CEO lens for narrative, market sizing, competitive positioning, and Create-X-specific framing. Every slide has a "why this works" rationale. Read the Execution section at the end before building.

---

## Context & Audience

**Program:** Georgia Tech Create-X Startup Launch (summer cohort)
**What Create-X cares about:**
1. Student founder with a real, lived problem
2. Early market validation (not just an idea)
3. Coachability and self-awareness about gaps
4. Credible path to revenue (not moon-shot fantasies)

**What Create-X does NOT care about:**
- Perfect product
- Big user numbers (this early)
- Polished pitch deck design over substance

**Tone:** Confident and honest. You have a working product with real beta users. Some features are built; others are planned. Say which is which — Create-X directors have seen hundreds of founders; they will respect honesty and flag anyone who oversells.

**Deck length:** 12 slides. No more. Every slide must earn its place.

---

## Slide-by-Slide Guide

---

### Slide 1 — Cover / Title

**Headline:** Noesis

**Tagline:** Know What Reviewer 2 Will Say Before You Submit

**Sub-headline:** AI-powered pre-submission peer review for academic researchers

**Elements:**
- Your name: Ashwin Vijayakumar
- Affiliation: Georgia Tech
- Contact: [your GT email]
- Noesis logo / wordmark (centered)
- Date / cohort you're applying to

**Design:**
- Dark charcoal background (#0F0F14) with rose-crimson accent (#E5484D) — matches the brand
- OR clean white — either works, just be consistent through the deck
- Inter font, Semibold for the headline

**CEO Note — Why "Reviewer 2" works:**
This is one of the best taglines in academic SaaS right now. Every single person in the room who has ever reviewed a paper — and Create-X directors almost certainly have — will laugh and immediately get it. "Reviewer 2" is a universal academic meme. It signals that the founder understands the culture, not just the market. Don't change this tagline.

---

### Slide 2 — The Problem

**Headline:** Researchers Lose Months to Preventable Rejections

**Open with a story (30-second read):**

> A PhD student spends 8 months writing a paper. Reviewer 2 rejects it: *"The authors fail to cite Zhang et al. (2023) and do not address the methodological critique raised by Liu et al. (2021)."* Both papers were publicly available. The student could have caught this before submission — but had no tool to help them look.

**Three data points below the story:**
- 60–90% rejection rate at top venues (Nature, IEEE, ACM, NeurIPS)
- 3–6 months lost per revision cycle after rejection
- A single rejection can delay graduation or jeopardize a grant renewal deliverable

**Closing punch line:**
> "Every existing tool helps you *find* papers. None of them tell you *what a reviewer will flag in your draft*."

**Visual suggestion:** A "REJECT" email from a journal (you can mock one), or a simple timeline: Write (8 mo) → Submit → Reject (1 mo) → Revise (3 mo) → Resubmit. Show the waste.

**CEO Note — Why this structure:**
Problem slides fail when they lead with data. Data doesn't create empathy — stories do. The story makes the pain visceral. The data validates that it's systematic, not a one-off. The closing line positions the gap in the market without naming competitors yet. This order matters: story → validation → gap.

---

### Slide 3 — The Solution

**Headline:** Noesis Reviews Your Draft Against Your Own Literature — Before Submission

**Three-step visual flow:**

```
[1. Upload Draft]          [2. Upload Library]         [3. Get Reviewer Feedback]
PDF, DOCX, paste text  →  BibTeX from Zotero, or   →  "Claim 3 in Section 2 is
from Overleaf              let us discover papers       unsupported. Zhang et al.
                                                        (2023) contradicts your
                                                        assumption. Add a citation
                                                        or qualify your claim."
```

**Key callout box (make this visually prominent):**
> "We don't rewrite your research. We tell you what a reviewer will flag — backed by specific passages from papers you already chose."

**What makes this different from ChatGPT (one line):**
> We analyze your draft *against your own literature library* — every feedback item is source-grounded to a specific paper passage.

**Honest note for the deck:** Core analysis is live and working in production. Overleaf browser extension is in active development (label as "In development" if you show it).

**CEO Note — Why "We don't rewrite" matters:**
Researchers are deeply protective of their intellectual contribution. Any hint of "AI writes your paper" is an immediate trust killer in this market. Leading with "we don't rewrite" is counterintuitive but correct — it's the single most important trust signal for academic users. This line has to be on the solution slide, not buried in fine print.

---

### Slide 4 — Product Demo (Screenshots)

**Headline:** What Noesis Actually Looks Like

**Show 3–4 real screenshots:**

1. **Upload screen** — the drag-and-drop interface for draft + BibTeX import tab
2. **Analysis results** — a real claim extracted from a draft, a coverage gap flagged with severity
3. **Feedback item with source grounding** — the exact passage from a cited paper that informs the critique. Example:
   > *"Based on: Zhang et al. (2023) — 'Our model achieved 97.2% accuracy, compared to the 91.4% reported by Liu et al.' Your claim in Section 3 assumes state-of-the-art accuracy but does not reference this benchmark."*
4. **Draft comparison** (if you have it working) — before/after improvement score

**Annotation guidance:**
- Use callout arrows to highlight the key parts of each screenshot
- If a screen is still in development, add a small "In development" badge in the corner
- Do NOT show mockups as if they are real — Create-X directors will ask you to demo it live

**CEO Note — This is your credibility moment:**
No other slide matters more than Slide 4. A working, real product screenshot from a live URL is worth ten slides of market analysis. If you can demo it live during the interview (open a browser tab), do that instead of or in addition to screenshots. The ability to show a working product is your strongest differentiator from the 80% of applicants who have only an idea.

---

### Slide 5 — Who We Serve

**Headline:** Our Customer: The PI With a Grant Deadline

**Two-column layout:**

**Primary Buyer — Principal Investigator (PI)**
- Controls lab budget: $500K–$5M NSF/NIH grants
- Manages 4–8 graduate researchers and their publication timelines
- Publication output directly tied to grant renewal and lab reputation
- $49/month = 0.01% of annual grant budget — rounding error
- Pain: "One rejection costs us 6 months and weakens our renewal proposal"

**Secondary Buyer — Postdoc / Senior PhD Student**
- Active publication pressure (job market depends on publications)
- Limited budget authority; pays individually at $12/month
- Pain: "I don't know if my literature review is complete enough before I submit"

**Bottom callout:**
> We are NOT targeting undergrads or casual readers. We're targeting researchers with deadlines, grant budgets, and professional consequences for rejection.

**CEO Note — Why the PI focus is strategically correct:**
The grad student is the user; the PI is the buyer. This is the B2B2C motion every successful academic SaaS company runs (think Overleaf, Benchling, Notion for teams). The PI has budget authority and a direct financial incentive to prevent rejection — one month of delay to a grant deliverable costs more than a year of Noesis subscriptions. Lead with the buyer, not the user, when talking to Create-X. It shows commercial maturity.

---

### Slide 6 — Traction (Be Honest Here)

**Headline:** Early Validation — Real Researchers, Real Feedback

**What to show:**
- ✅ **Product live in production** — running at noesis.is
- ✅ **Beta users actively testing:**
  - Researchers in biological sciences labs at Georgia Tech
  - Researchers at institutions in Texas (independently reached out)
- ✅ **Core workflow validated end-to-end:** upload → analysis → actionable feedback
- ✅ **Qualitative signal:** Early users have identified reviewer-style gaps they say they would not have caught manually without the tool
- ✅ **Monetization infrastructure live:** Stripe checkout, Free/Pro/Lab tiers configured, first paying users pending formal launch
- 🚧 **Paper discovery, draft comparison, BibTeX import:** Built and in testing

**Tone calibration:**
Say this out loud before writing it: "We have a handful of real researchers using this, and two of them told me they found a gap they would have missed." That sentence is more credible than "12 active users with 94% satisfaction." Don't inflate. Don't minimize. Say exactly what you have.

**CEO Note — Why honesty wins with Create-X:**
Create-X has seen hundreds of applications. They can smell inflated traction claims. The founders who get accepted are the ones who say "here's exactly what I have, here's what I've learned from it, and here's why I'm confident enough to keep going." That's coachability. That's what they're investing in — the founder, not the metrics.

---

### Slide 7 — Market Size

**Headline:** The Academic Research Software Market Is Large and Underserved

**Top-down (for context):**
- ~8 million active researchers globally (Web of Science)
- ~200K new papers published per month on arXiv alone
- Adjacent tools have validated the market: Elicit ($18M raised), Scite (significant VC backing), Semantic Scholar (backed by Allen Institute)

**Bottom-up (your credible number — lead with this):**

> **Beachhead:** Georgia Tech alone has 4,000+ active graduate researchers and 500+ faculty PIs.
>
> **US R1 universities:** ~200 institutions × average 2,000 active researchers × 10% conversion at $20/month = **$96M ARR addressable in R1 universities alone**
>
> **Lab tier focus:** If 5,000 PI-led labs in the US adopt Lab tier ($49/mo × 5 users):
> **= $2.9M ARR from labs, not counting individual subscribers**

**Key message for Create-X:**
> We don't need to win the whole market. Winning Georgia Tech → R1 universities → top 50 US research institutions is a clear, 3-year path to $5M ARR. That's the scope of this program.

**CEO Note — Bottom-up is more credible than top-down:**
For a Create-X interview (not a VC pitch), lead with the bottom-up number. "Georgia Tech has 4,000 researchers, I'm targeting 100 by Demo Day" is a more credible story than "the global research software TAM is $2B." Program directors will respect the founder who has done the math on their specific beachhead. Save the big TAM slide for VC decks.

---

### Slide 8 — Competition

**Headline:** Everyone Helps Researchers Find Papers. Nobody Reviews Their Draft.

**Comparison table:**

| Tool | What They Do | Our Advantage |
|------|-------------|---------------|
| Elicit ($18M raised) | Find relevant papers | We analyze the draft you already wrote |
| Scite | Track citation sentiment in published work | We map claims to evidence gaps in *your* unpublished draft |
| SciSpace | Summarize papers you find | We critique your arguments, not theirs |
| Research Rabbit | Build citation networks | We integrate into your submission workflow |
| ChatGPT / GPT-4 | General Q&A, text generation | We're source-grounded to your specific library — not the internet |

**Key message (make this large on the slide):**
> "The category of 'pre-submission AI peer review' does not yet exist as a product. We are creating it."

**CEO Note — "We are creating the category" is both true and risky:**
This is a double-edged sword. Category creation is exciting but it also means you have to educate buyers. For Create-X, frame it as opportunity: you've identified a gap that well-funded companies with similar technology have missed. For future investor decks, you'll need to add "why hasn't someone done this already?" — the answer is that AI quality wasn't good enough until GPT-5.2, and the researcher workflow integration is hard to get right. Both are your moats.

---

### Slide 9 — Business Model

**Headline:** SaaS Subscriptions — Tight Free Tier Drives Upgrade

**Pricing table:**

| Tier | Price | For Whom | Limit That Drives Upgrade |
|------|-------|----------|--------------------------|
| Free | $0 | Individual researcher trying it out | 10 drafts/month — ~2 weeks of active use |
| Pro | $12/month | Individual postdoc or PhD student | No lab sharing |
| Lab | $49/month | PI + up to 5 lab members | Our primary growth engine |

**Revenue mechanics:**
- Free tier is deliberately restrictive — 10 drafts = 2 active weeks for a publishing researcher
- Lab tier ($49) is charged to a grant budget, not a personal card — much lower churn
- Viral loop: PI invites 4 grad students → each grad student shares with their cohort → word spreads lab-to-lab

**Forward-looking milestones (honest estimates):**
- Month 1 post-launch: 3–5 paying customers, $150–$250 MRR
- Month 3: 50+ paying users, $2K–$5K MRR
- Month 6: 200+ users, $10K MRR — threshold to pursue seed round

**CEO Note — The viral loop is your strongest growth mechanism:**
Lab tier isn't just a revenue line — it's a distribution mechanism. When a PI adopts Noesis for their lab, you get 5 users instead of 1, and those grad students will carry the habit to their next position (postdoc, faculty role, industry). Benchling used exactly this motion in life sciences. Mention this to Create-X — it shows you understand how SaaS grows in academic institutions.

---

### Slide 10 — Product Roadmap

**Headline:** Where We're Going — Deeper Into the Researcher's Workflow

**Three phases:**

**Phase 1 — Core review (✅ Live now)**
- Draft upload & AI analysis (PDF, DOCX, text)
- Citation gap detection with severity scoring
- Reviewer-style feedback with source grounding (specific paper passages)
- BibTeX import from Zotero/Mendeley
- Paper discovery (PubMed, arXiv, Semantic Scholar)
- Stripe checkout (Free, Pro, Lab tiers)

**Phase 2 — Workflow integration (🚧 In development — next 60 days)**
- Chrome extension for Overleaf (analyze from your LaTeX editor without leaving it)
- Real-time progress streaming during analysis (WebSocket)
- Draft version comparison & improvement tracking

**Phase 3 — Lab collaboration (📋 Planned — Month 3–4)**
- Shared lab projects for PI + grad students
- Reviewer simulation (multiple AI reviewer personas by discipline)
- Journal-specific review profiles (Nature vs. IEEE vs. PLOS formatting and expectations)
- Grant proposal analysis (same workflow, different document type — huge expansion)

**CEO Note — Grant proposals are a significant expansion opportunity:**
Phase 3 includes grant proposal analysis. This is important to name but not over-pitch right now. NSF/NIH grant proposals face the same problem — reviewers flag missing citations, weak methodology framing, unsupported claims. The grant proposal analysis feature, if validated, could be a separate product line at 5–10x the price point. Note it as a future direction without making it your primary pitch — you want to stay focused.

---

### Slide 11 — The Ask / Why Create-X

**Headline:** We're Building at Georgia Tech — Create-X Gets Us to Demo Day With Real Traction

**Why Georgia Tech is the right launch market:**
- 4,000+ active graduate researchers; 500+ faculty PIs with publication pressure
- Multiple R1 departments actively publishing in competitive venues
- Built-in network for user research, beta testing, and word-of-mouth
- Georgia Tech's brand gives credibility when expanding to other R1 universities

**What we're asking for:**
- Acceptance into the **Startup Launch Summer Program**
- Access to the Create-X mentor network — specifically someone with experience selling to research institutions or academic IT
- Structured support for user research interviews with GT researchers (warm introductions to lab managers or department heads)
- Cohort credibility: "Create-X cohort company" signals legitimacy to early university partners and future angel investors

**What we commit to delivering by Demo Day:**
- ✅ 50+ activated users (at least one draft uploaded and analyzed)
- ✅ 3+ paying Lab customers (PIs paying from grant budgets)
- ✅ One documented case study: a PI who used Noesis before a real submission and found actionable gaps
- ✅ $1,000+ MRR
- ✅ Validated interview data: 20+ researcher interviews with documented pain points

**CEO Note — The specific Demo Day commitments matter:**
Create-X will remember what you promise. Be conservative. "50 activated users and 3 paying customers by Demo Day" is achievable and specific. Don't promise 500 users unless you have a credible plan to reach them. The willingness to commit to specific, measurable outcomes signals that you understand execution, not just vision.

---

### Slide 12 — Founder

**Headline:** The Builder

**Content:**
- **Ashwin Vijayakumar** — Founder & Engineer, Georgia Tech
- Full-stack: React, Python/FastAPI, AI/LLM pipelines, cloud infrastructure (Vercel + AWS + Supabase)
- Built Noesis from zero to production in ~6 weeks — full stack, solo
- [Add your personal connection to the problem — did you watch a friend go through a rejection cycle? Did you TA a research methods course? Do you have a family member in academia? The personal story matters here]

**What's missing (be transparent):**
> Solo technical founder. The gap I'm actively filling: a co-founder with domain expertise in academic publishing or enterprise sales to universities. Create-X can help me find that person or the mentorship to develop those skills.

**CEO Note — Naming your gap is a strength, not a weakness:**
Create-X has seen hundreds of founders who claim to have every skill. The founder who says "I can build anything, but I need help with university sales cycles" is more trustworthy than one who claims to be complete. It's also the honest truth — solo technical founders almost always need GTM help in B2B SaaS. Name it. They'll respect it. They may even have a co-founder match for you.

---

## Execution Instructions

### Step 1 — Build the Slides

**Tool:** Google Slides (shareable link) or Canva (easier design)

**Design system:**
- Background: `#0F0F14` (dark charcoal) OR `#FFFFFF` (clean white) — pick one and stick to it
- Accent color: `#E5484D` (rose-crimson) for headers, callout boxes, highlighted data
- Font: Inter (available in Google Slides via "More fonts" or free at fonts.google.com)
  - Headlines: Inter Semibold, 36–44pt
  - Body: Inter Regular, 18–22pt
  - Callout boxes: Inter Semibold, 20pt, accent color background
- Max 5 bullets per slide — if you have 6, cut one
- Use real screenshots for Slides 4 and 6 — no mockups presented as real

**Slide layout notes:**
- Slides 1–3: Text-heavy narrative, that's fine — these are the story
- Slides 4, 6: Screenshots dominate — text annotates, doesn't compete
- Slides 7–9: Tables and numbers — clean grid layout, use accent color for key row
- Slides 10–12: Lists with status icons — ✅ 🚧 📋 work well visually

---

### Step 2 — Practice the 4-Minute Pitch

**The verbal story arc:**

**Hook (30 sec):**
> "Reviewer 2 rejected my friend's paper for a citation that was publicly available — one he could have found in 5 minutes if he'd known to look. That happens 60–90% of the time at top venues. We built Noesis to catch it before submission."

**Product demo (90 sec):**
Open a browser to the live product. Upload a real (or anonymized) draft. Show the analysis output. Walk through one feedback item with its source citation. This is the most valuable 90 seconds of the interview.

**Business case (60 sec):**
> "PIs manage $500K–$5M grants. A single rejection costs them 6 months and weakens their renewal proposal. At $49/month, we're a rounding error on their budget. Three paying Lab customers by Demo Day is our goal."

**Ask (30 sec):**
> "We're live with beta users at Georgia Tech. Create-X gives us the structured mentorship, the user research support, and the credibility signal to reach 50 activated researchers by Demo Day. That's the inflection point we're targeting."

---

### Step 3 — Anticipate Hard Questions

**"What makes this defensible — can't ChatGPT do this?"**
> "ChatGPT doesn't know your literature. Noesis analyzes your draft *against your own library* — every feedback item is grounded in a specific passage from papers you chose to cite. That citation-aware, library-specific workflow can't be replicated with a general chatbot. We're not doing general AI — we're doing source-grounded academic review."

**"You only have a few beta users. Why should we believe there's a market?"**
> "We have a working product, not an idea. The users we have are real researchers who told us they found gaps they would have missed manually. The market exists and is validated by adjacent tools: Elicit raised $18M solving the discovery problem. We're solving the harder, more valuable problem — what to do with your draft once you have the papers. The category is newer; the pain is the same."

**"What does success in the program look like for you?"**
> "By Demo Day: 50 activated users, 3 paying Lab customers — PIs billing to grant budgets — and one documented case study of a researcher who used Noesis before a real submission and said it helped. That's the proof point that unlocks a seed round."

**"Why you? Why now?"**
> "I'm a Georgia Tech engineer who built the full stack in 6 weeks. GPT-5.2 only became capable enough for source-grounded academic analysis in the last few months — the technology window just opened. And Georgia Tech gives me direct access to exactly the researchers I need to validate and distribute this. The timing is right."

**"What's the biggest risk?"**
> "Distribution. Building the product is the part I'm good at. Getting into labs — past the PI's skepticism about AI tools — is the hard part. That's exactly what I'm asking Create-X to help with: structured access to researchers for user interviews, and mentorship from someone who's sold to research institutions before."

---

## Appendix — Key Data Points to Know Cold

Have these memorized before your interview. Don't read them off a slide.

| Fact | Number | Source |
|------|--------|--------|
| Active researchers globally | ~8 million | Web of Science |
| arXiv papers per month | ~200K | arXiv stats |
| Typical rejection rate (top venues) | 60–90% | Published in venue stats |
| Elicit funding (comparison) | $18M raised | Crunchbase |
| GT active grad researchers (approx) | 4,000+ | GT enrollment data |
| Your Lab tier price | $49/month | Your pricing page |
| Your Pro tier price | $12/month | Your pricing page |
| Free tier limit | 10 drafts/month | Your product |
| Demo Day commitment | 50 users, 3 Labs, $1K MRR | This deck |

---

## What to Do After This Deck Is Submitted

Once accepted, return to the Sprint 1 E2E testing priorities:

1. Review and merge the `feature/websocket-progress` worktree (real-time progress streaming for Phase 2)
2. Review and merge the `feature/chrome-extension` worktree (Overleaf integration for Phase 2)
3. Run `cd infra && docker-compose down && docker-compose up --build` to validate the full upload → analysis pipeline end-to-end with GPT-5.2
4. Upgrade to OpenAI Tier 1 for parallel batch upload support (3 req/min limit on free tier blocks multi-file uploads)

The Create-X application deadline is your forcing function. Ship the deck, submit, then get back to building.

---

*Guide created: March 2026 | For internal use — Noesis / Ashwin Vijayakumar / Georgia Tech Create-X application*

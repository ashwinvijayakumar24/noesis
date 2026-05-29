# Noesis Skills Reference

## All Available Skills

### Engineering & Code Quality

| Skill | Summary |
|-------|---------|
| **engineering-skills** | 23 production-ready engineering skills covering architecture, frontend, backend, fullstack, QA, DevOps, security, AI/ML, data engineering, and specialized tools like Playwright Pro, Stripe integration, AWS, and MS365. Includes 30+ Python automation tools (all stdlib-only). Best for broad engineering tasks across the stack. |
| **engineering-advanced-skills** | 25 advanced skills covering agent design, RAG architecture, MCP servers, CI/CD pipelines, database design, observability, security auditing, release management, and platform operations. Ideal for complex infrastructure, RAG optimization, and production ops work. |
| **simplify** | Reviews changed code for reuse, quality, and efficiency, then auto-fixes issues found. Use after writing new code to catch duplication, poor patterns, or inefficiencies before committing. |
| **full-output-enforcement** | Overrides default LLM truncation behavior to ensure complete, unabridged code generation. Bans placeholder patterns like `// ... rest of code` and handles token-limit splits cleanly. Essential when generating large files or complete implementations. |
| **optimize** | Diagnoses and fixes UI performance issues across loading speed, rendering, animations, images, and bundle size. Use when the app feels slow, janky, or when you want to reduce bundle size and improve load times. |

### Security & Operations

| Skill | Summary |
|-------|---------|
| **security-check** | Scans for hardcoded secrets, missing auth on routes, SQL injection risk, and other OWASP vulnerabilities. Critical for a platform handling academic research data and Stripe payment info. |
| **check-gpt** | Audits all Python files for incorrect `max_tokens` usage since GPT-5.2 requires `max_completion_tokens`. A Noesis-specific safeguard to prevent 400 errors from the OpenAI API. |

### Testing & Deployment

| Skill | Summary |
|-------|---------|
| **test-flow** | Runs the full Noesis end-to-end checklist: document upload → analysis → RAG chat → draft analysis. Purpose-built for validating the core user flow works after changes. |
| **docker-logs** | Tails noesis-backend and noesis-celery-worker logs and summarizes recent errors. Quick way to diagnose backend issues without manually parsing container output. |
| **deploy** | Deploys frontend to Vercel production and verifies SEO assets are live. Handles the deployment pipeline so you don't have to run manual Vercel commands. |

### UI/UX Design & Frontend

| Skill | Summary |
|-------|---------|
| **impeccable** | Creates distinctive, production-grade frontend interfaces with high design quality. Generates creative, polished code that avoids generic AI aesthetics. Call with `craft` for shape-then-build, `teach` for design context setup, or `extract` to pull reusable components and tokens. |
| **design-taste-frontend** | Senior UI/UX Engineer skill that enforces metric-based rules, strict component architecture, CSS hardware acceleration, and balanced design engineering. Overrides default LLM biases toward generic-looking UIs. |
| **high-end-visual-design** | Teaches the AI to design like a high-end agency — defines exact fonts, spacing, shadows, card structures, and animations that make a website feel expensive. Blocks all the common defaults that make AI designs look cheap. |
| **shape** | Plans UX and UI for a feature before writing code. Runs a structured discovery interview, then produces a design brief that guides implementation. Use during planning phase to establish design direction before coding. |
| **critique** | Evaluates design from a UX perspective with quantitative scoring, persona-based testing, automated anti-pattern detection, and actionable feedback. Use to review components or pages before shipping. |
| **audit** | Runs technical quality checks across accessibility, performance, theming, responsive design, and anti-patterns. Generates a scored report with P0-P3 severity ratings and an actionable fix plan. |
| **polish** | Performs a final quality pass fixing alignment, spacing, consistency, and micro-detail issues before shipping. The "last mile" skill for going from good to great before deploying. |
| **layout** | Improves layout, spacing, and visual rhythm. Fixes monotonous grids, inconsistent spacing, and weak visual hierarchy. Use when a page feels "off" but you can't pinpoint why. |
| **typeset** | Improves typography by fixing font choices, hierarchy, sizing, weight, and readability. Use when text doesn't feel intentional or headings/body aren't well-differentiated. |
| **colorize** | Adds strategic color to monochromatic or visually dull interfaces. Use when the dark theme feels too gray or sections need more visual differentiation. |
| **adapt** | Adapts designs for different screen sizes, devices, and platforms. Implements breakpoints, fluid layouts, and touch targets. Essential for mobile responsiveness. |
| **animate** | Adds purposeful animations, micro-interactions, and motion effects that improve usability. Use to make transitions feel polished and interactions feel responsive. |
| **delight** | Adds moments of joy, personality, and unexpected touches that make interfaces memorable. Elevates functional to delightful — good for onboarding flows and key moments. |
| **bolder** | Amplifies safe or boring designs to be more visually interesting. Increases impact while maintaining usability. Use when a component looks too generic or bland. |
| **quieter** | Tones down visually aggressive or overstimulating designs. Reduces intensity while preserving quality. Use when something feels too loud or overwhelming. |
| **distill** | Strips designs to their essence by removing unnecessary complexity. Use when a UI feels cluttered or has too many competing elements. |
| **clarify** | Improves unclear UX copy, error messages, microcopy, labels, and instructions. Use when users might be confused by interface text or error states. |
| **overdrive** | Pushes interfaces past conventional limits with shaders, spring physics, scroll-driven reveals, and 60fps animations. Use sparingly for hero sections or landing page wow-factor. |
| **redesign-existing-projects** | Upgrades existing websites to premium quality. Audits current design, identifies generic AI patterns, and applies high-end standards without breaking functionality. Works with any CSS framework. |

### Design System Presets

| Skill | Summary |
|-------|---------|
| **minimalist-ui** | Clean editorial-style interfaces with warm monochrome palette, typographic contrast, flat bento grids, and muted pastels. No gradients or heavy shadows. Good reference but Noesis already has its own design system. |
| **industrial-brutalist-ui** | Raw mechanical interfaces with Swiss typographic print and military terminal aesthetics. Rigid grids, extreme type scale contrast, utilitarian color. Not aligned with Noesis's design system. |
| **stitch-design-taste** | Semantic Design System for Google Stitch. Generates DESIGN.md files with strict typography, calibrated color, and micro-motion standards. Not directly applicable to Noesis. |

### Content & Writing

| Skill | Summary |
|-------|---------|
| **humanizer** | Removes signs of AI-generated writing from text. Detects and fixes patterns like inflated symbolism, promotional language, em dash overuse, AI vocabulary words, and filler phrases. Great for landing page copy and marketing content. |

### Product & Business

| Skill | Summary |
|-------|---------|
| **product-skills** | 8 product skills: PM toolkit with RICE prioritization, agile product owner, product strategist with OKR cascades, UX researcher, UI design system, competitive teardown, landing page generator, and SaaS scaffolder. |
| **marketing-skills** | 42-skill marketing division with 7 specialist pods: content, SEO, CRO, channels, growth, intelligence, and sales. Includes 27 Python tools. Comprehensive marketing automation. |
| **business-growth-skills** | Customer success (health scoring, churn prediction), sales engineering (RFP analysis), revenue operations (pipeline, GTM metrics), and contract/proposal writing. |
| **c-level-skills** | Strategic business advice from 10 executive perspectives (CEO, CTO, COO, CPO, CMO, CFO, CRO, CISO, CHRO, Executive Mentor). Runs multi-role board meetings and delivers structured recommendations. |
| **finance-skills** | Financial analyst with ratio analysis, DCF valuation, budget variance, and rolling forecasts. Useful for fundraising prep and financial modeling. |
| **pm-skills** | 6 project management skills for Atlassian users: PM with portfolio management, scrum master, Jira expert, Confluence expert, admin, and template creator. |
| **ra-qm-skills** | 12 regulatory affairs and quality management skills for HealthTech/MedTech (ISO 13485, MDR, FDA, ISO 27001, GDPR). Not directly relevant to Noesis. |

### Utility

| Skill | Summary |
|-------|---------|
| **find-skills** | Helps discover and install new agent skills. Use when you need functionality that might exist as an installable skill but isn't currently available. |
| **keybindings-help** | Configures keyboard shortcuts and keybindings for Claude Code. Use when customizing the development environment. |
| **claude-developer-platform** | Builds apps with the Claude API or Anthropic SDK. Triggers when code imports `anthropic` or `@anthropic-ai/sdk`. Not relevant since Noesis uses OpenAI. |

---

## Noesis-Specific Recommendations

### Use Consistently (Every Session)

| Skill | When | Why |
|-------|------|-----|
| **check-gpt** | After any backend changes | Prevents GPT-5.2 `max_tokens` regressions — a single wrong param breaks the entire pipeline |
| **security-check** | Before every deploy | Noesis handles academic data + Stripe payments; one leaked key or unprotected route is catastrophic |
| **simplify** | After writing new code | Catches duplication and inefficiency before it accumulates |
| **test-flow** | After any backend/API changes | Validates the core upload → analysis → chat pipeline still works |

### Use for Frontend Work

| Skill | When | Why |
|-------|------|-----|
| **design-taste-frontend** | Starting any frontend task | Enforces Noesis's dark charcoal + rose-crimson design system with proper component architecture |
| **impeccable** | Building new components/pages | Ensures production-grade quality, avoids generic AI look |
| **polish** | Before deploying frontend changes | Catches alignment, spacing, and consistency issues |
| **audit** | Monthly or before major releases | Accessibility + performance + theming scored report |
| **adapt** | When building new pages | Ensures mobile responsiveness — critical for researchers on tablets/phones |
| **clarify** | When writing error messages or UI copy | Academic users expect precise, clear language |

### Use for Growth & Launch (Priority: Now)

| Skill | When | Why |
|-------|------|-----|
| **marketing-skills** | Planning outreach campaigns | 42 skills across SEO, content, CRO, growth — covers the full funnel for Georgia Tech launch |
| **humanizer** | Writing landing page copy, emails | Removes AI-sounding patterns from outreach and marketing content |
| **product-skills** | Feature prioritization, user research | RICE prioritization + competitive teardowns help focus limited resources |
| **c-level-skills** | Strategic decisions, fundraising prep | Multi-perspective analysis for pricing, positioning, and investor conversations |
| **business-growth-skills** | Churn prevention, sales pipeline | Customer health scoring + GTM metrics as you scale past early adopters |

### Use for Infrastructure & Performance

| Skill | When | Why |
|-------|------|-----|
| **engineering-advanced-skills** | RAG optimization, CI/CD, observability | Covers RAG architecture (Phase 1 priority), database design, and production monitoring |
| **engineering-skills** | Stripe integration, AWS, DevOps | Broad coverage for backend + infrastructure tasks |
| **optimize** | When app feels slow | Diagnoses rendering, bundle size, and loading speed issues |
| **docker-logs** | Debugging backend issues | Quick error summaries from backend + Celery containers |
| **deploy** | Shipping to production | Handles Vercel deployment + SEO verification |

### Use Occasionally

| Skill | When | Why |
|-------|------|-----|
| **shape** | Planning major new features | Structured UX discovery before coding prevents rework |
| **critique** | Reviewing completed UI work | Quantitative UX scoring catches issues you might miss |
| **animate** / **delight** | After core functionality works | Micro-interactions elevate the experience but aren't critical path |
| **full-output-enforcement** | Generating large files | Prevents truncation when writing complete implementations |
| **finance-skills** | Fundraising prep (Month 6) | DCF modeling and financial projections for seed raise |

### Skip for Noesis

| Skill | Why |
|-------|-----|
| **ra-qm-skills** | MedTech regulatory — not applicable |
| **industrial-brutalist-ui** | Doesn't match Noesis design system |
| **stitch-design-taste** | Google Stitch specific |
| **claude-developer-platform** | Noesis uses OpenAI, not Anthropic SDK |
| **pm-skills** | Atlassian-focused; Noesis doesn't use Jira/Confluence |
| **minimalist-ui** | Noesis has its own established design system |

---

## Quick Reference: What to Run When

```
Before committing backend code    → check-gpt + security-check + simplify
Before deploying                  → test-flow + audit + deploy
Starting a new frontend component → design-taste-frontend + impeccable
Finishing a frontend component    → polish + adapt
Writing marketing copy            → marketing-skills + humanizer
Planning a new feature            → shape + product-skills
Monthly health check              → audit + security-check + optimize
Fundraising prep                  → c-level-skills + finance-skills + business-growth-skills
```

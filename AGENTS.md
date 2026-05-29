<claude-mem-context>
# Memory Context

# [noesis] recent context, 2026-05-28 9:32pm EDT

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (18,730t read) | 581,725t work | 97% savings

### Apr 28, 2026
S14 Noesis tagline refinement — multiple rounds of 50-char company description options (Apr 28 at 12:14 AM)
S15 Ashwin's YC Application Motivation — Background and Path (Apr 28 at 12:17 AM)
S12 Noesis company description — 50-char tagline brainstorm with recommendation (Apr 28 at 12:17 AM)
S16 Noesis — Push dev changes to production via CI/CD and verify pipeline success (Apr 28 at 12:37 AM)
### Apr 30, 2026
S18 Noesis Beta Outreach Plan — 5-Day Sprint Document Created (Apr 30 at 1:40 PM)
### May 10, 2026
S19 Noesis improvements.md — Full 3-Pillar RFC Written to Project Root (May 10 at 8:52 PM)
### May 11, 2026
S20 Noesis improvements.md — Open Questions Replaced with Resolved + New Follow-Ups (May 11 at 12:25 AM)
S25 Noesis Git — Kill-State Tagged and Repo Reset to Pre-Kill Active Dev State (May 11 at 12:40 AM)
### May 23, 2026
261 11:28a 🔵 Noesis Backend Infrastructure — Full Stack Inventory
### May 24, 2026
262 12:03p ✅ Noesis README — Resume Metrics and Architecture Details Added
263 12:04p ✅ Noesis README — Resume Bullet Points Added for Public GitHub Release
### May 25, 2026
264 2:20p ⚖️ Noesis — Revived for Output Quality Audit and Pivot to Lab/Enterprise Tier
266 " 🔵 Noesis Git History — Kill-State Commits Identified for Snapshot/Restore
268 " ✅ Noesis Git — Kill-State Tagged and Repo Reset to Pre-Kill Active Dev State
S29 Locate .env file and set up environment variables for Noesis backend (May 25 at 2:20 PM)
275 2:24p 🔵 OpenAI API Key Exposed in Plain Text Chat Message
276 2:25p 🔵 Noesis Backend — .env File Location and Environment Variable Map
280 2:32p 🔵 Noesis — Missing src/lib/supabase.ts Module
281 2:33p 🔵 Noesis Frontend — src/lib/ Directory Entirely Missing
284 " 🔴 Noesis Frontend — Created Missing src/lib/supabase.ts
285 " 🔵 Noesis Frontend — analytics Lib API Surface Identified
289 2:34p ✅ Noesis Frontend — .env.local Created with Supabase Credentials
290 " 🔵 Noesis Docker Compose — Frontend Missing Supabase Env Vars in Container
S35 Noesis Frontend — .env.local Created with Supabase Credentials (May 25 at 2:34 PM)
293 2:42p 🔵 Noesis Frontend — lib/errorHandler Missing, Login.tsx Import Broken
294 2:43p 🔵 Noesis Frontend — Complete lib/ Gap Map: api, apiErrors, errorHandler All Missing
297 7:06p ⚖️ Noesis Output Quality Evaluation Strategy — LLM Comparison Framework
298 7:07p 🔵 Noesis Draft Analysis Output — Sepsis MLA Paper (draft_id: c6599176)
300 " 🔵 Noesis Paper Recommendations — Wrong Draft Linked, Zero Results for Test Draft
303 7:10p 🟣 Noesis Output Quality Export Script — JSON + Markdown Generated Inside Container
308 7:12p 🔵 Docker cp Permission — Intermittent Socket Access Failure on Second Call
309 " 🟣 Noesis Evaluation Export Files — Successfully Copied to Host Workspace
### May 27, 2026
317 1:46p 🔵 Noesis Git Working Tree — Extensive Uncommitted Changes Including New Workflow Nodes and Migrations
318 1:59p ⚖️ Noesis Feature Scope Reduction — Remove Literature Map and Paper Discovery
319 " ⚖️ Noesis Feature Reduction — Remove Literature Map, Paper Discovery, Paper Summarization
320 2:12p ⚖️ Noesis Feature Scope — Remove Literature Map, Paper Discovery, and Paper Summarization
321 2:13p 🔵 Noesis Feature Surface Map — Full Scope of Features Under Consideration for Removal
### May 28, 2026
322 4:16p ⚖️ Noesis Homepage — Full Overhaul Planned with Linear Dark Theme
323 " 🔵 Noesis Frontend — Full Codebase Audit for Homepage Overhaul
324 4:18p ⚖️ Noesis Homepage — Full Overhaul Planned with Linear Dark Theme
325 4:19p ⚖️ Noesis Homepage — Full Overhaul Planned with Linear Dark Theme
326 " 🟣 PublicLayout Component Created — Shared Shell for All Public Pages
327 4:20p 🟣 Landing.tsx — Full Homepage Rebuild with Linear Dark Theme
328 4:21p 🟣 Pricing.tsx — Full Rebuild with 4-Tier Structure and Linear Dark Theme
329 " 🟣 PrivacyPolicy.tsx — Full Rebuild with Accurate Data Flow and Linear Dark Theme
330 " ✅ sitemap.xml — Updated Lastmod Dates and Added /privacy URL
331 4:22p 🔴 pricingCopy.test.ts — Em-Dash vs Hyphen Mismatch Fixed
332 " 🔵 Frontend Lint — 156 Pre-Existing Errors, New Public Pages Clean
333 4:23p 🔵 Dev Server Fails on 127.0.0.1:5173 with EPERM
334 4:37p 🟣 Noesis Landing Page — External Source Lookup Disclosure Added
335 5:00p ⚖️ Noesis Pricing — Payment Buttons Temporarily Disabled Pending Stripe Integration
336 " ✅ Noesis Pricing — Pro/Team/Enterprise Buttons Disabled Pending Stripe
337 5:09p 🔄 Noesis Pricing Page — Full Layout and Copy Overhaul
338 " ✅ Noesis — Domain Migration from noesis.app to noesis.is Across Frontend
339 5:12p ✅ Noesis Pricing — Button Disable Commit Landed on main (d866cef)
340 5:17p ⚖️ Noesis Landing Page — Auth Buttons Disabled for Soft Launch
341 " 🔵 Noesis Landing.tsx — Auth Entry Points Mapped
342 " ✅ Noesis PublicLayout.tsx — Nav Auth Buttons Disabled for Soft Launch
343 5:18p ✅ Noesis App.tsx + ProtectedRoute.tsx — All Auth Routes Redirect to Homepage
344 7:20p 🔵 Noesis — Vercel Project Architecture Confirmed

Access 582k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>

<project-workflow>
For every user request in this project that involves a multi-step task, implementation,
planning, design work, debugging, review, or analysis, first search for the most relevant
available skills for the task. Select the best-fit skill or minimal set of skills, announce
which skill(s) are being used and why, then follow those skill instructions while completing
the task.
</project-workflow>

<claude-mem-context>
# Memory Context

# [noesis] recent context, 2026-06-04 10:50pm EDT

Legend: 🎯session 🔴bugfix 🟣feature 🔄refactor ✅change 🔵discovery ⚖️decision
Format: ID TIME TYPE TITLE
Fetch details: get_observations([IDs]) | Search: mem-search skill

Stats: 50 obs (18,303t read) | 630,484t work | 97% savings

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
### May 25, 2026
S29 Locate .env file and set up environment variables for Noesis backend (May 25 at 2:20 PM)
S35 Noesis Frontend — .env.local Created with Supabase Credentials (May 25 at 2:34 PM)
### May 27, 2026
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
### May 29, 2026
345 2:01p ⚖️ Noesis Output Quality — Stress Test Niche Selection Request
346 2:14p ⚖️ Noesis Output Quality — Two Additional Test Niches Selected
347 2:15p 🟣 EmptyStateGuide — Redesigned with Import .bib CTA + Compact Layout
348 " ✅ ProjectDetail.tsx — EmptyStateGuide Wired to Import Modal
349 2:33p 🔵 Noesis Literature Upload — Duplicate Records on Retry After Partial Failure
350 2:34p 🔵 Noesis Document Upload — No Idempotency Guard in Upload Pipeline
351 " 🔴 Noesis Document Upload — Idempotency Helpers Added to documents.py
352 2:35p 🔴 Noesis Document Upload — Full Idempotency Implementation with Deterministic Storage Paths
353 " 🟣 Noesis DB Migration 026 — Partial Unique Index for Manual Upload Idempotency
354 2:36p 🔴 Noesis Document Upload — Orphaned Storage Object Cleanup on Concurrent Duplicate Insert
355 " 🔵 Noesis UploadDocumentModal — Frontend Already Handles duplicate Flag and Partial Failure Retry
356 " 🔴 Noesis documents.py — file.filename None Safety via original_filename Variable
357 " 🔴 Noesis UploadDocumentModal — selectedFiles Snapshot on Submit
358 2:37p ✅ Noesis Idempotency Fix — Working Tree State at Completion
359 2:50p 🔵 Noesis Supabase Schema — Actual Table Names vs Expected Names + Column Inventory
360 " 🔵 Noesis Live DB State — Two Active Projects with 8 and 9 Documents Post-Upload Bug
361 2:51p ⚖️ Noesis Output Quality — 2 Additional Stress-Test Niches Needed
362 2:53p 🔵 Noesis Export — docker cp Blocked by Socket Permissions
363 " 🟣 Noesis Export Script — exports/export_latest_noesis_draft_tmp.py Created
364 2:54p 🔵 Noesis Export Script — ModuleNotFoundError When Run from /tmp
365 " 🔵 Noesis Export — Sodium-Ion Battery Draft Successfully Exported
366 2:56p 🟣 Noesis Sodium-Ion Battery Draft Export — Confirmed Full Quality Data in exports/
368 " 🔵 Noesis Export — Heredoc Python via docker exec Breaks on Host Shell Escape
369 2:57p 🟣 Noesis Export — Draft PDF Full Text Extracted and Injected into Sodium-Ion Export
370 2:58p 🟣 Noesis Sodium-Ion Export — Final Enriched Files Confirmed on Host
371 3:06p 🔵 Noesis Output Quality Bug — Cross-Project Content Contamination in Sodium-Ion Battery Meta Review

Access 630k tokens of past work via get_observations([IDs]) or mem-search skill.
</claude-mem-context>

<project-workflow>
For every user request in this project that involves a multi-step task, implementation,
planning, design work, debugging, review, or analysis, first search for the most relevant
available skills for the task. Select the best-fit skill or minimal set of skills, announce
which skill(s) are being used and why, then follow those skill instructions while completing
the task.
</project-workflow>

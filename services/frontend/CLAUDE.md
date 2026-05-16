# Frontend Context

Last updated: May 10, 2026

Read `../../current_state.md` before broad frontend changes.

## Stack

- React 19
- TypeScript 5.9
- Vite 7.2
- Tailwind package v4 with local `tailwind.config.js` tokens
- React Router 7
- Supabase client auth
- `@heroicons/react/24/outline`

## Current Product Surfaces

- `src/pages/ProjectDetail.tsx`: live project workspace
- `src/pages/DraftAnalysis.tsx`: full draft review view
- `src/pages/Pricing.tsx`: plan copy and checkout trigger; Stripe is not production-finished
- `src/pages/Landing.tsx`: current GTM positioning
- `src/pages/PrivacyPolicy.tsx`: privacy/no-training copy

Primary tabs in the workspace:

- `Literature`
- `Literature Map`
- `Discover`
- `Drafts`

Chat is not a core product surface.

## Design Rules

Source of truth: `services/frontend/tailwind.config.js`

- Background: `bg-bg-void`, `bg-bg-surface`
- Accent: `accent-primary` / `#E5484D`
- Borders: `border-border-default`
- Max radius: `rounded-xl`; never `rounded-2xl` or `rounded-3xl`
- Headings: `font-semibold`; avoid `font-bold`
- Transitions: `duration-fast`
- Icons: `@heroicons/react/24/outline`

## Component Guidance

- Reuse existing UI primitives in `src/components/ui/`.
- Keep SaaS/research UI dense, quiet, and utilitarian.
- Do not add marketing-style hero treatment inside authenticated tools.
- Use precise workflow language: Literature Map, Discover, Draft Analysis.
- Keep privacy copy visible around draft/document upload contexts.

## Current Frontend Priorities

1. Finish Stripe pricing/checkout UX once backend production config is ready.
2. Strengthen collaboration UX once backend shared projects exist.
3. Add inline editing/Overleaf workflow surfaces.
4. Improve feedback-to-document anchoring UX.
5. Make structured errors visible for uploads, BibTeX, quotas, and analysis failures.

## Verification

```bash
cd services/frontend
npm run build
npm run lint
npm run test
```

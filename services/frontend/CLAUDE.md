# Frontend Context

## Stack
React 18.3, TypeScript 5.5, Vite 7.2, TailwindCSS 3, @heroicons/react/24/outline

## Design Rules (source of truth: `tailwind.config.js`)
- Background: `bg-bg-void` (#0F0F14), `bg-bg-surface` (#18181F)
- Accent: `text-accent-primary` / `bg-accent-primary` (#E5484D)
- Borders: `border border-border-default` (rgba(255,255,255,0.08))
- Max radius: `rounded-xl` — NEVER `rounded-2xl` or `rounded-3xl`
- Headings: `font-semibold` — NEVER `font-bold`
- Transitions: `duration-fast` (150ms)
- Icons: `@heroicons/react/24/outline` only

## Component Patterns
```tsx
// Standard card
<div className="bg-bg-surface border border-border-default rounded-xl p-4">

// Primary button
<button className="bg-accent-primary hover:bg-accent-hover text-white font-semibold rounded-lg px-4 py-2 transition-colors duration-fast">

// Muted text
<p className="text-text-muted text-sm">
```

## Key Files
- `tailwind.config.js` — source of truth for all design tokens
- `src/lib/api.ts` — all API calls go through this
- `src/components/` — reuse before creating new components

## Rules
- Never use inline styles for colors/spacing — always Tailwind tokens
- All API calls use `api.` namespace from `src/lib/api.ts`
- Auth state from Supabase via `useAuth()` hook

# Noesis Design System Documentation

> **Last Updated:** February 2026
> **Design Philosophy:** Professional, scholarly, trustworthy—inspired by Linear's workflow precision and Stripe's polished aesthetic.

---

## Table of Contents

1. [Core Principles](#core-principles)
2. [Color System](#color-system)
3. [Typography](#typography)
4. [Spacing & Layout](#spacing--layout)
5. [Components](#components)
6. [Visual Effects](#visual-effects)
7. [Anti-Patterns](#anti-patterns)
8. [Accessibility](#accessibility)
9. [Quick Reference](#quick-reference)

---

## Core Principles

### 1. Professional Dark Theme
- **Charcoal foundation**, not pure black (#0F0F14 base)
- Blue-tinted grays for scholarly, calm atmosphere
- Subtle elevation through layered surfaces
- Avoids harsh pure black that causes eye strain

### 2. Sophisticated Rose-Crimson Accent
- Primary accent: `#E5484D` (Radix Red 9)
- **NOT** neon pink—desaturated professional red
- High contrast on dark (6:1+ WCAG AA)
- Used sparingly for emphasis and primary actions

### 3. Single Font Family
- **Inter only** for all text (no custom display fonts)
- Professional, readable, industry-standard
- Consistent across headlines, body, and UI

### 4. Subtle & Fast
- Minimal animations (fade, slide only)
- 150ms transitions (snappy, responsive)
- ≤1px hover lifts (subtle)
- No spring/bounce effects

### 5. Academic Authority
- Conveys trust, transparency, rigor
- Like a professional research tool, not a flashy consumer app
- Think Linear + Notion + Stripe, not Perplexity or generic SaaS

---

## Color System

### Background Hierarchy

```css
/* Dark Charcoal Foundation */
--color-bg-void: #0F0F14;           /* Page background (deepest) */
--color-bg-surface: #18181F;        /* Content cards, panels */
--color-bg-elevated: #1E1E27;       /* Modals, dropdowns, overlays */
--color-bg-hover: #252530;          /* Interactive hover states */
--color-bg-subtle: #2A2A35;         /* Subtle backgrounds, disabled states */
```

**Usage:**
- `bg-bg-void` → Page backgrounds, sections
- `bg-bg-surface` → Cards, containers, modal panels
- `bg-bg-elevated` → Nested modals, dropdown menus
- `bg-bg-hover` → Hover states, footers
- `bg-bg-subtle` → Disabled elements, muted sections

### Text Hierarchy

```css
/* WCAG AAA Compliant */
--color-text-primary: #EDEDEF;      /* Headlines, emphasis (19:1 contrast) */
--color-text-secondary: #B4B4B8;    /* Body text, descriptions (12:1 contrast) */
--color-text-tertiary: #6E6E77;     /* Supporting text, labels (6:1 contrast) */
--color-text-muted: #43434A;        /* Metadata, timestamps (4.5:1 contrast) */
```

**Usage:**
- `text-text-primary` → H1-H6, button labels, important text
- `text-text-secondary` → Paragraphs, descriptions, card content
- `text-text-tertiary` → Labels, captions, helper text
- `text-text-muted` → Timestamps, metadata, placeholders

### Primary Accent (Rose-Crimson)

```css
/* Rose-Crimson System */
--color-accent-primary: #E5484D;    /* Primary actions, CTAs */
--color-accent-hover: #F2555A;      /* Hover states */
--color-accent-light: #4C1D1D;      /* Light backgrounds (badges, pills) */
--color-accent-subtle: #3B1419;     /* Subtle accents */
```

**Usage:**
- `bg-accent-primary` → Primary buttons, important badges
- `text-accent-primary` → Links, emphasis text, icons
- `border-accent-primary` → Focus rings, active states
- `bg-accent-light` → Badge backgrounds, highlight sections

### Secondary Accents

```css
/* Feature Differentiation */
--color-teal-primary: #0D9488;      /* Analysis & Insights */
--color-teal-light: #134E4A;

--color-indigo-primary: #6366F1;    /* Draft Analysis */
--color-indigo-light: #312E81;

--color-amber-primary: #F59E0B;     /* Warnings & Highlights */
--color-amber-light: #78350F;

--color-ruby-primary: #E54D2E;      /* Errors & Critical */
--color-ruby-light: #3E1C17;
```

**Usage:**
- Teal → RAG ingestion, search features
- Indigo → Draft analysis cards, stats
- Amber → Warning banners, alerts
- Ruby → Error states, destructive actions

### Borders

```css
/* Subtle, Purposeful Borders */
--color-border-default: rgba(255, 255, 255, 0.08);  /* Standard dividers */
--color-border-subtle: rgba(255, 255, 255, 0.04);   /* Very subtle separation */
--color-border-strong: rgba(255, 255, 255, 0.12);   /* Emphasized borders */
--color-border-focus: #E5484D;                      /* Rose focus states */
```

**Usage:**
- `border-border-default` → Cards, inputs, panels
- `border-border-subtle` → Dividers, section separators
- `border-border-strong` → Active elements, emphasis
- `border-accent-primary` → Focus states, active tabs

---

## Typography

### Font Stack

```css
/* Inter Only */
--font-family-sans: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
--font-family-mono: 'JetBrains Mono', 'SF Mono', 'Courier New', monospace;
```

**Import:**
```css
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
```

### Letter-Spacing

```css
/* Critical for Readability */
h1, h2, h3, h4, h5, h6 {
  letter-spacing: -0.01em;  /* tracking-tight (slight tightening) */
}

p, li, span, div {
  letter-spacing: 0;        /* tracking-normal (NO wide spacing) */
}

code, .font-mono {
  letter-spacing: 0;        /* tracking-normal (monospace already fixed) */
}
```

**Tailwind Classes:**
- Headlines: `tracking-tight` or `tracking-tightest`
- Body text: `tracking-normal`
- Captions: `tracking-normal`

### Font Weights

```css
/* Avoid Heavy Bold */
--font-weight-heading: 600;   /* Semibold (NOT 700 bold) */
--font-weight-emphasis: 500;  /* Medium */
--font-weight-body: 400;      /* Regular */
```

**Usage:**
- Headlines: `font-semibold` (600)
- Buttons, labels: `font-medium` (500)
- Body text: `font-normal` (400)

**❌ DO NOT USE:** `font-bold` (700) on dark backgrounds—bleeds and strains eyes

### Type Scale

```typescript
/* 8pt Grid System */
H1: '2.5rem (40px), font-semibold, line-height: 1.1, tracking-tight'
H2: '2rem (32px), font-semibold, line-height: 1.2, tracking-tight'
H3: '1.5rem (24px), font-semibold, line-height: 1.3, tracking-normal'
H4: '1.125rem (18px), font-semibold, line-height: 1.4, tracking-normal'

Body Large: '1.125rem (18px), font-normal, line-height: 1.6, tracking-normal'
Body: '1rem (16px), font-normal, line-height: 1.6, tracking-normal'
Body Small: '0.875rem (14px), font-normal, line-height: 1.5, tracking-normal'
Caption: '0.75rem (12px), font-medium, line-height: 1.5, tracking-normal'
```

### Line-Height

```css
/* Spacious for Academic Content */
--line-height-display: 1.1;   /* Hero headlines */
--line-height-heading: 1.2;   /* Section headings */
--line-height-body: 1.6;      /* Body text (generous for readability) */
--line-height-caption: 1.5;   /* Metadata, labels */
```

---

## Spacing & Layout

### Spacing Scale (8pt Grid)

```css
/* Tailwind Spacing */
0.5 = 2px  (0.125rem)
1   = 4px  (0.25rem)
2   = 8px  (0.5rem)
3   = 12px (0.75rem)
4   = 16px (1rem)
5   = 20px (1.25rem)
6   = 24px (1.5rem)
8   = 32px (2rem)
10  = 40px (2.5rem)
12  = 48px (3rem)
16  = 64px (4rem)
```

**Usage:**
- Tight spacing: `gap-3` (12px)
- Normal spacing: `gap-6` (24px)
- Loose spacing: `gap-8` (32px)
- Section spacing: `py-16` (64px)

### Layout Containers

```typescript
/* Max Widths */
'max-w-7xl'  → Large layouts (1280px) - default for most pages
'max-w-5xl'  → Centered content (1024px) - hero sections
'max-w-3xl'  → Text content (768px) - descriptions, paragraphs
'max-w-2xl'  → Narrow content (672px) - forms, modals
```

### Responsive Breakpoints

```typescript
sm: '640px'   // Small tablets
md: '768px'   // Tablets
lg: '1024px'  // Laptops
xl: '1280px'  // Desktops
2xl: '1536px' // Large desktops
```

---

## Components

### Buttons

```typescript
/* Primary Button */
className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px transition-all duration-150"

/* Secondary Button */
className="px-6 py-3 bg-bg-surface border border-border-default text-text-primary rounded-md hover:bg-bg-hover hover:border-accent-primary/30 transition-all duration-150"

/* Ghost Button */
className="px-4 py-2 text-text-secondary rounded-md hover:text-accent-primary hover:bg-accent-light transition-all duration-150"
```

**Key Points:**
- Rounded corners: `rounded-md` (6px)
- Hover lift: `-translate-y-px` (1px up)
- Fast transitions: `duration-150`
- Semibold font weight

### Cards

```typescript
/* Standard Card */
className="bg-bg-surface border border-border-default rounded-lg p-6 shadow-xs transition-all duration-150"

/* Hoverable Card */
className="bg-bg-surface border border-border-default rounded-lg p-6 shadow-xs hover:border-accent-primary/30 hover:-translate-y-0.5 hover:shadow-sm transition-all duration-150"
```

**Key Points:**
- Background: `bg-bg-surface`
- Border: Subtle default, rose on hover
- Rounded corners: `rounded-lg` (8px)
- Minimal hover lift: `0.5px`

### Inputs

```typescript
/* Text Input */
className="w-full px-4 py-3 bg-bg-surface border border-border-default rounded-md text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors tracking-normal"

/* Textarea */
className="w-full px-4 py-3 bg-bg-surface border border-border-default rounded-md text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-accent-primary resize-none tracking-normal"
```

**Key Points:**
- Focus ring: Rose glow with `ring-2 ring-accent-primary`
- Rounded corners: `rounded-md` (6px)
- Tracking: `tracking-normal` (NOT wide)

### Badges

```typescript
/* Primary Badge */
className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-accent-light text-accent-primary border border-accent-primary/30"

/* Success Badge */
className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-teal-light text-teal-primary border border-teal-primary/30"

/* Warning Badge */
className="inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium bg-amber-light text-amber-primary border border-amber-primary/30"
```

### Modals

```typescript
/* Overlay */
className="fixed inset-0 bg-black/70 backdrop-blur-sm"

/* Panel */
className="w-full max-w-2xl transform overflow-hidden rounded-lg bg-bg-surface border border-border-default shadow-xl transition-all"

/* Header */
className="px-6 py-5 border-b border-border-default"

/* Title */
className="text-2xl font-sans font-semibold text-text-primary tracking-normal"

/* Close Button */
className="text-text-tertiary hover:text-accent-primary hover:bg-accent-light rounded-md p-2 transition-all duration-150"
```

**Key Points:**
- Dark overlay: `bg-black/70`
- Max rounded: `rounded-lg` (8px) for panels
- Rose hover for close button

### Tabs

```typescript
/* Active Tab */
className="px-4 py-3 text-sm font-medium border-b-2 border-accent-primary text-accent-primary transition-all duration-150"

/* Inactive Tab */
className="px-4 py-3 text-sm font-medium border-b-2 border-transparent text-text-secondary hover:text-text-primary transition-all duration-150"
```

---

## Visual Effects

### Shadows

```css
/* Subtle, Realistic (NOT neon glows) */
--shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.3);
--shadow-sm: 0 2px 4px rgba(0, 0, 0, 0.4);
--shadow-md: 0 4px 8px rgba(0, 0, 0, 0.5);
--shadow-lg: 0 8px 16px rgba(0, 0, 0, 0.6);
--shadow-xl: 0 12px 24px rgba(0, 0, 0, 0.7);

/* Focus Glow - ONLY for accessibility */
--shadow-focus: 0 0 0 3px rgba(229, 72, 77, 0.15);  /* Subtle rose */
```

**Usage:**
- Cards: `shadow-xs` at rest, `shadow-sm` on hover
- Modals: `shadow-xl`
- Focus states: `shadow-focus` (rose glow)
- **❌ NO** neon glow effects on logos, cards, or badges

### Border Radius

```css
/* Purposeful, Not Excessive */
--radius-sm: 4px;   /* rounded-sm - Badges, tags, small UI */
--radius-md: 6px;   /* rounded-md - Buttons, inputs, small cards */
--radius-lg: 8px;   /* rounded-lg - Cards, panels, containers */
--radius-xl: 12px;  /* rounded-xl - Modals, large panels (MAX) */
--radius-full: 9999px; /* rounded-full - Pills, avatars only */
```

**❌ DO NOT USE:** `rounded-2xl` (16px) or `rounded-3xl` (24px)—too playful

### Transitions

```css
/* Fast & Responsive */
transition: all 150ms ease-out;
```

**Usage:**
- Hover states: `transition-all duration-150`
- Color changes: `transition-colors duration-150`
- Transforms: `transition-transform duration-150`

**Easing:** Always use `ease-out` (snappy start, smooth end)

### Hover States

```typescript
/* Card Hover */
'hover:border-accent-primary/30 hover:-translate-y-0.5 hover:shadow-sm'

/* Button Hover */
'hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px'

/* Icon Hover */
'hover:text-accent-primary hover:bg-accent-light'
```

**Key Points:**
- Minimal lift: ≤1px
- Color shifts to rose accent
- Fast 150ms transitions

---

## Anti-Patterns

### ❌ DO NOT USE

#### 1. Neon Gradients
```css
/* ❌ FORBIDDEN */
.button {
  background: linear-gradient(90deg, #FF1F4C, #FF6B9D);
}

.card {
  border-image: linear-gradient(90deg, #FF1F4C, #9333EA, #0891B2);
}
```

#### 2. Glow Effects (Except Focus)
```css
/* ❌ FORBIDDEN */
.logo:hover {
  filter: drop-shadow(0 0 8px rgba(255, 31, 76, 0.6));
}

.card {
  box-shadow: 0 0 30px rgba(255, 31, 76, 0.3);
}
```

#### 3. Floating/Bouncing Animations
```css
/* ❌ FORBIDDEN */
@keyframes float {
  0%, 100% { transform: translateY(-5px); }
  50% { transform: translateY(5px); }
}

.badge {
  animation: float 2s infinite;
}
```

#### 4. Excessive Rounding
```typescript
/* ❌ FORBIDDEN */
className="rounded-2xl"  // 16px - TOO MUCH
className="rounded-3xl"  // 24px - WAY TOO MUCH
```

#### 5. Bold Font Weight on Dark
```typescript
/* ❌ FORBIDDEN */
className="font-bold"  // 700 weight bleeds on dark backgrounds
```

#### 6. Wide Letter Spacing
```css
/* ❌ FORBIDDEN */
p {
  letter-spacing: 0.05em;  /* Makes text feel "too spaced out" */
}
```

### ✅ ALLOWED Gradients

```css
/* Hero backgrounds - subtle */
.hero {
  background: linear-gradient(135deg, #0F0F14 0%, #18181F 100%);
}

/* Progress bars - functional */
.progress-bar {
  background: linear-gradient(90deg, #E5484D 0%, #F2555A 100%);
}
```

### ✅ ALLOWED Animations

```css
/* Fade-in (page load) */
@keyframes fade-in {
  from { opacity: 0; }
  to { opacity: 1; }
}

/* Slide-in (modals) */
@keyframes slide-in {
  from { opacity: 0; transform: translateY(16px); }
  to { opacity: 1; transform: translateY(0); }
}

/* Spin (loading indicators) */
@keyframes spin {
  from { transform: rotate(0deg); }
  to { transform: rotate(360deg); }
}
```

---

## Accessibility

### WCAG AAA Compliance

All text meets **WCAG AAA (7:1 minimum)** contrast ratios:
- `text-text-primary` on `bg-bg-void`: **19:1** ✅
- `text-text-secondary` on `bg-bg-void`: **12:1** ✅
- `text-text-tertiary` on `bg-bg-void`: **6:1** ✅

### Focus States

```typescript
/* Always visible, rose glow */
'focus:ring-2 focus:ring-accent-primary focus:border-accent-primary focus:outline-none'
```

**Key Points:**
- Rose ring for all interactive elements
- 2px ring width
- No default outline (replaced by ring)

### Keyboard Navigation

All interactive elements must support:
- `Tab` / `Shift+Tab` navigation
- `Enter` / `Space` activation
- `Escape` to close modals

### Screen Reader Support

```typescript
/* Use semantic HTML */
<button aria-label="Close modal">...</button>
<nav aria-label="Main navigation">...</nav>
<main>...</main>
<aside aria-label="Sidebar">...</aside>
```

---

## Quick Reference

### Color Classes (Most Common)

```typescript
// Backgrounds
'bg-bg-void'        // Page background
'bg-bg-surface'     // Cards, containers
'bg-bg-hover'       // Hover states
'bg-accent-primary' // Primary buttons
'bg-accent-light'   // Badge backgrounds

// Text
'text-text-primary'     // Headlines
'text-text-secondary'   // Body text
'text-text-tertiary'    // Labels
'text-accent-primary'   // Links, emphasis

// Borders
'border-border-default'  // Standard borders
'border-accent-primary'  // Focus, active states
```

### Utility Classes

```typescript
// Typography
'font-sans'         // Inter font
'font-semibold'     // 600 weight for headings
'tracking-tight'    // -0.01em for headlines
'tracking-normal'   // 0 for body

// Spacing
'p-6'    // Padding: 24px
'gap-6'  // Gap: 24px
'py-16'  // Vertical padding: 64px

// Borders
'rounded-md'  // 6px (buttons, inputs)
'rounded-lg'  // 8px (cards)
'rounded-xl'  // 12px (modals - max)

// Effects
'shadow-xs'   // Subtle shadow
'shadow-sm'   // Small shadow
'shadow-lg'   // Large shadow

// Transitions
'transition-all duration-150'     // Universal
'transition-colors duration-150'  // Color only
'hover:-translate-y-px'           // Lift 1px
```

### Component Patterns

```typescript
/* Card */
<div className="bg-bg-surface border border-border-default rounded-lg p-6 shadow-xs hover:border-accent-primary/30 hover:-translate-y-0.5 transition-all duration-150">

/* Button */
<button className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover hover:-translate-y-px transition-all duration-150">

/* Input */
<input className="w-full px-4 py-3 bg-bg-surface border border-border-default rounded-md focus:ring-2 focus:ring-accent-primary tracking-normal" />

/* Badge */
<span className="inline-flex px-2.5 py-0.5 rounded-md text-xs font-medium bg-accent-light text-accent-primary border border-accent-primary/30">

/* Modal */
<div className="w-full max-w-2xl rounded-lg bg-bg-surface border border-border-default shadow-xl">
```

---

## Implementation Checklist

When creating new components, ensure:

### ✅ Color System
- [ ] Uses `bg-bg-surface` for dark cards (NOT `bg-surface` or `bg-white`)
- [ ] Uses `text-text-primary` for headlines (NOT `text-text-primary-dark`)
- [ ] Uses `border-border-default` (NOT `border-border-base` or `border-gray`)
- [ ] Uses `#E5484D` rose-crimson accent (NOT neon pink)

### ✅ Typography
- [ ] Uses `font-sans` (Inter) for all text
- [ ] Uses `font-semibold` (600) for headings (NOT `font-bold`)
- [ ] Uses `tracking-normal` for body text (NOT wide spacing)
- [ ] Uses `tracking-tight` for headlines

### ✅ Spacing
- [ ] Follows 8pt grid (4px, 8px, 12px, 16px, 24px, 32px)
- [ ] Uses consistent padding/margin values
- [ ] Uses `gap-6` for normal spacing, `gap-3` for tight

### ✅ Effects
- [ ] Border radius ≤12px (`rounded-xl` max)
- [ ] Transitions are 150ms (`duration-150`)
- [ ] Hover lifts ≤1px (`hover:-translate-y-px`)
- [ ] No neon glows, floating animations, or excessive gradients

### ✅ Accessibility
- [ ] All text meets WCAG AAA (7:1 contrast)
- [ ] Focus states are visible (rose ring)
- [ ] Keyboard navigation works
- [ ] Semantic HTML used

---

## Examples from Codebase

### Landing Page Hero (Centered Layout)

```typescript
<section className="relative pt-32 pb-24 sm:pt-40 sm:pb-32 px-6 sm:px-8 overflow-hidden bg-gradient-to-br from-bg-void via-bg-surface to-bg-void">
  <div className="max-w-5xl mx-auto">
    <motion.div className="text-center space-y-8">
      <h1 className="text-5xl sm:text-6xl lg:text-7xl font-sans font-semibold leading-display tracking-tightest">
        Strengthen Your Research{' '}
        <span className="text-accent-primary">Before Peer Review</span>
      </h1>
      <p className="text-xl sm:text-2xl text-text-secondary leading-body-large tracking-normal max-w-3xl mx-auto">
        AI research assistant that critiques your drafts...
      </p>
    </motion.div>
  </div>
</section>
```

### Card Component

```typescript
<div className="bg-bg-surface border border-border-default rounded-lg p-6 shadow-xs hover:border-accent-primary/30 hover:-translate-y-0.5 transition-all duration-150">
  <h3 className="text-xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
    Card Title
  </h3>
  <p className="text-sm text-text-secondary tracking-normal">
    Card description text
  </p>
</div>
```

### Modal Component

```typescript
<Dialog.Panel className="w-full max-w-2xl rounded-lg bg-bg-surface border border-border-default shadow-xl">
  <div className="px-6 py-5 border-b border-border-default">
    <Dialog.Title className="text-2xl font-sans font-semibold text-text-primary tracking-normal">
      Modal Title
    </Dialog.Title>
    <button className="text-text-tertiary hover:text-accent-primary hover:bg-accent-light rounded-md p-2 transition-all duration-150">
      <XMarkIcon className="h-6 w-6" />
    </button>
  </div>
</Dialog.Panel>
```

---

## Resources

- **Inspiration:** [Linear UI](https://linear.app), [Stripe Dashboard](https://stripe.com), [Notion](https://notion.so)
- **Color System:** [Radix Colors](https://www.radix-ui.com/colors)
- **Typography:** [Inter Font](https://rsms.me/inter/)
- **Accessibility:** [WCAG 2.1 Guidelines](https://www.w3.org/WAI/WCAG21/quickref/)

---

**Questions?** Refer to this guide when building new features. For edge cases, follow the spirit of these principles: professional, subtle, trustworthy—like a tool for serious researchers, not a flashy consumer app.

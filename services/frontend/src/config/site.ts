// Freeze mode: backend is offline. Marketing pages stay live; all backend-dependent
// routes (auth, projects, draft analysis, checkout) redirect to the Contact page.
// Flip VITE_FREEZE_MODE back to false (or remove it) to restore the full app.
export const FREEZE_MODE = import.meta.env.VITE_FREEZE_MODE === 'true'

// Sales contact target used by the Contact page and CTAs during freeze mode.
export const CONTACT_EMAIL = 'ashwin@noesis.is'

// Optional booking link (Calendly / Cal.com). Leave empty to hide the "Book a demo"
// button and fall back to the mailto CTA only.
export const BOOKING_URL = ''

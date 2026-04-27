/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'sans': ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Courier New', 'monospace'],
        // HEADING FONT — uncomment one line to swap active font:
        // 'heading': ['Plus Jakarta Sans', 'Inter', 'sans-serif'],         // ✅ ACTIVE (default)
        // 'heading': ['Sora', 'Inter', 'sans-serif'],                      // option 2: geometric (not bad)
        // 'heading': ['Manrope', 'Inter', 'sans-serif'],                   // option 3: modern
        // 'heading': ['DM Sans', 'Inter', 'sans-serif'],                   // option 4: editorial
        // 'heading': ['Space Grotesk', 'Inter', 'sans-serif'],             // option 5: technical
        // 'heading': ['Outfit', 'Inter', 'sans-serif'],                    // option 6: clean
        // 'heading': ['Figtree', 'Inter', 'sans-serif'],                   // option 7: friendly
        // 'heading': ['Bricolage Grotesque', 'Inter', 'sans-serif'],       // option 8: editorial
        'heading': ['Helvetica Now Display', 'Helvetica Neue', 'Arial', 'sans-serif'],  // option 9: Helvetica Now Display (local)
      },
      letterSpacing: {
        'tightest': '-0.02em',      // Display headings
        'tighter': '-0.015em',       // Page titles
        'tight': '-0.01em',          // Section headings
        'snug': '-0.005em',          // Subsection headings
        'normal': '0em',             // Body text
        'wide': '0.01em',            // Captions
        'mono': '0.02em',            // Monospace
      },
      lineHeight: {
        'display': '1.1',            // Hero text
        'heading-1': '1.15',         // Page titles
        'heading-2': '1.2',          // Section headings
        'heading-3': '1.3',          // Subsection headings
        'heading-4': '1.4',          // Card titles
        'body-large': '1.6',         // Emphasized content
        'body': '1.6',               // Standard body (spacious!)
        'body-small': '1.5',         // Supporting text
        'caption': '1.5',            // Metadata
      },
      colors: {
        // DARK THEME: Professional Charcoal Foundation
        // Primary Canvas - Charcoal (NOT pure black)
        'bg-void': '#0F0F14',            // Deep charcoal - Page background
        'bg-page': '#0F0F14',            // Alias
        'bg-canvas': '#0F0F14',          // Legacy alias

        // Surface Layers - Subtle Elevation via Blue-Tinted Grays
        'bg-surface': '#18181F',         // Slate-900 tone - Content cards
        'bg-elevated': '#1E1E27',        // Modals, dropdowns, overlays
        'bg-hover': '#252530',           // Interactive hover states
        'bg-subtle': '#2A2A35',          // Subtle backgrounds, disabled states

        // Accent Backgrounds - Desaturated, Professional
        'bg-success-dark': '#0D1F17',    // Dark green tint - Success states
        'bg-success': '#0D1F17',         // Alias
        'bg-info-dark': '#0F1419',       // Dark blue tint - Info panels
        'bg-info': '#0F1419',            // Alias
        'bg-warning-dark': '#1F1A0D',    // Dark amber tint - Warning states
        'bg-warning': '#1F1A0D',         // Alias
        'bg-accent-dark': '#0D1F1D',     // Dark teal tint - Feature highlights
        'bg-accent': '#0D1F1D',          // Alias

        // Legacy support (for gradual migration)
        'bg-base': '#0F0F14',
        'surface': '#18181F',
        'surface-hover': '#1E1E27',
        'surface-active': '#252530',

        // Text Hierarchy - High Contrast for Dark (WCAG AAA)
        'text-primary': '#EDEDEF',       // Radix Slate 12 - Headlines (19:1 contrast)
        'text-secondary': '#B4B4B8',     // Radix Slate 11 - Body text (12:1 contrast)
        'text-tertiary': '#6E6E77',      // Radix Slate 10 - Supporting text (6:1)
        'text-muted': '#43434A',         // Radix Slate 9 - Metadata (4.5:1)

        // Primary Accent: Rose-Crimson (Professional, NOT Neon)
        'accent-primary': '#E5484D',     // Radix Red 9 - Primary actions
        'accent-hover': '#F2555A',       // Radix Red 10 - Hover states
        'accent-light': '#4C1D1D',       // Radix Red 3 Dark - Light backgrounds
        'accent-subtle': '#3B1419',      // Radix Red 2 Dark - Subtle accents

        // Secondary Accents - Feature Differentiation (Dark Optimized)
        // Teal - Analysis & Insights
        'teal-primary': '#0D9488',       // Teal-600 - Professional teal
        'teal-light': '#134E4A',         // Teal-900 - Dark backgrounds
        'teal-50': '#134E4A',
        'teal-100': '#134E4A',
        'teal-200': '#115E59',
        'teal-600': '#0D9488',
        'teal-700': '#0F766E',

        // Indigo - Draft Analysis
        'indigo-primary': '#6366F1',     // Indigo-500 - Vibrant but not neon
        'indigo-light': '#312E81',       // Indigo-900 - Dark backgrounds
        'indigo-50': '#312E81',
        'indigo-100': '#312E81',
        'indigo-200': '#3730A3',
        'indigo-600': '#6366F1',
        'indigo-700': '#4F46E5',

        // Amber - Warnings & Highlights
        'amber-primary': '#F59E0B',      // Amber-500 - Warm amber
        'amber-light': '#78350F',        // Amber-900 - Dark backgrounds
        'amber-50': '#78350F',
        'amber-100': '#78350F',
        'amber-200': '#92400E',
        'amber-600': '#F59E0B',
        'amber-700': '#D97706',

        // Rose - Critical Feedback (Alias for accent)
        'rose-primary': '#E5484D',       // Same as accent-primary
        'rose-light': '#4C1D1D',         // Same as accent-light
        'rose-50': '#3B1419',
        'rose-100': '#4C1D1D',
        'rose-200': '#6E2B30',
        'rose-600': '#E5484D',
        'rose-700': '#F2555A',

        // Ruby - Errors & Critical
        'ruby-primary': '#E54D2E',       // Warm red - Error states
        'ruby-light': '#3E1C17',         // Ruby-950 - Dark backgrounds

        // Emerald palette (kept for backward compatibility)
        'emerald-50': '#134E4A',
        'emerald-100': '#134E4A',
        'emerald-200': '#115E59',
        'emerald-600': '#059669',
        'emerald-700': '#047857',
        'emerald-800': '#065F46',

        // Border System - Subtle White Alpha (Linear-inspired)
        'border-default': 'rgba(255, 255, 255, 0.08)',  // Standard dividers
        'border-subtle': 'rgba(255, 255, 255, 0.04)',   // Very subtle separation
        'border-strong': 'rgba(255, 255, 255, 0.12)',   // Emphasized borders
        'border-focus': '#E5484D',                      // Rose focus states

        // Legacy border support
        'border-base': 'rgba(255, 255, 255, 0.08)',
        'border-active': '#E5484D',

        // Supporting Accents (kept for data viz)
        'accent-teal': '#0D9488',
        'accent-purple': '#9333EA',

        // Legacy accent (backward compatibility)
        accent: {
          primary: '#E5484D',
          hover: '#F2555A',
          light: '#4C1D1D',
        },

        // Semantic Colors (Dark Optimized)
        success: '#0D9488',              // Teal-600
        'success-light': '#134E4A',      // Teal-900
        warning: '#F59E0B',              // Amber-500
        'warning-light': '#78350F',      // Amber-900
        error: '#E54D2E',                // Ruby (warm red)
        'error-light': '#3E1C17',        // Ruby-950
        info: '#6366F1',                 // Indigo-500
        'info-light': '#312E81',         // Indigo-900
      },
      spacing: {
        // 8pt Grid System
        '1': '4px',      // Tight spacing (icons, badges)
        '2': '8px',      // Small gaps
        '3': '12px',     // Standard gaps
        '4': '16px',     // Medium gaps (default)
        '5': '20px',     // Large gaps
        '6': '24px',     // Section spacing
        '8': '32px',     // Large section spacing
        '10': '40px',    // Very large spacing
        '12': '48px',    // Hero spacing
        '16': '64px',    // Extra large spacing
      },
      maxWidth: {
        'container-sm': '640px',    // Narrow content
        'container-md': '768px',    // Standard forms
        'container-lg': '1024px',   // Default content width
        'container-xl': '1280px',   // Wide layouts
        'container-2xl': '1536px',  // Maximum width
      },
      borderRadius: {
        'sm': '4px',      // Badges, tags, small UI elements
        'md': '6px',      // Buttons, inputs, small cards
        'lg': '8px',      // Cards, panels, content containers
        'xl': '12px',     // Modals, large panels (MAX - no rounded-3xl)
        'full': '9999px', // Pills, avatars only
      },
      boxShadow: {
        // Dark Theme Shadows - Stronger for Visibility (Realistic, NO Glow)
        'xs': '0 1px 2px rgba(0, 0, 0, 0.3)',
        'sm': '0 2px 4px rgba(0, 0, 0, 0.4)',
        'md': '0 4px 8px rgba(0, 0, 0, 0.5)',
        'lg': '0 8px 16px rgba(0, 0, 0, 0.6)',
        'xl': '0 12px 24px rgba(0, 0, 0, 0.7)',

        // Focus Glow - ONLY for accessibility (subtle rose)
        'focus': '0 0 0 3px rgba(229, 72, 77, 0.15)',
        'rose-glow': '0 0 0 3px rgba(229, 72, 77, 0.15)',

        // Legacy support
        'success': '0 0 0 3px rgba(13, 148, 136, 0.15)',
        'info': '0 0 0 3px rgba(99, 102, 241, 0.15)',
      },
      transitionDuration: {
        'fast': '150ms',    // Fast, responsive (Linear-inspired)
        'base': '150ms',    // Default (was 200ms)
        'slow': '300ms',
        'bounce': '400ms',
      },
      transitionTimingFunction: {
        'smooth': 'cubic-bezier(0.4, 0, 0.2, 1)',
        'bounce': 'cubic-bezier(0.16, 1, 0.3, 1)',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-200px 0' },
          '100%': { backgroundPosition: '200px 0' }
        },
        'slide-in': {
          '0%': { opacity: '0', transform: 'translateY(16px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' }
        },
        'fade-in': {
          '0%': { opacity: '0' },
          '100%': { opacity: '1' }
        },
        'scale-in': {
          '0%': { opacity: '0', transform: 'scale(0.96)' },
          '100%': { opacity: '1', transform: 'scale(1)' }
        },
        'spin': {
          '0%': { transform: 'rotate(0deg)' },
          '100%': { transform: 'rotate(360deg)' }
        },
        'shimmer-sweep': {
          '0%': { transform: 'translateX(-100%)' },
          '100%': { transform: 'translateX(300%)' }
        },
      },
      animation: {
        shimmer: 'shimmer 1.5s infinite',
        'shimmer-sweep': 'shimmer-sweep 1.8s ease-in-out infinite',
        'slide-in': 'slide-in 250ms cubic-bezier(0.16, 1, 0.3, 1)',
        'fade-in': 'fade-in 300ms ease-out',
        'scale-in': 'scale-in 200ms cubic-bezier(0.16, 1, 0.3, 1)',
        'spin': 'spin 0.8s linear infinite',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
      },
    },
  },
  plugins: [],
}

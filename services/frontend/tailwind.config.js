/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      fontFamily: {
        'sans': ['Inter', 'system-ui', 'sans-serif'],
        'serif': ['Lora', 'Georgia', 'serif'],
        'mono': ['JetBrains Mono', 'Courier New', 'monospace'],
      },
      colors: {
        // Background Hierarchy - Slate/Charcoal theme inspired by VS Code
        'bg-base': '#1a1d23',
        'surface': '#242832',
        'surface-hover': '#2d3340',
        'surface-active': '#363d4e',

        // Border Colors - Complementary slate tones
        'border-base': '#363d4e',
        'border-subtle': '#2d3340',

        // Text Hierarchy - Slate-complementary text colors
        'text-primary': '#e6e8eb',
        'text-secondary': '#b4b8c0',
        'text-tertiary': '#7d8290',
        'text-muted': '#6b7280',

        // Accent Colors - Subdued slate-blue for professional appearance
        accent: {
          primary: '#64748b',    // slate-500 - darker, more professional
          hover: '#475569',      // slate-600 - darker on hover
          light: '#cbd5e1',      // slate-300 - for light variants
        },

        // Semantic Colors
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        info: '#3B82F6',
      },
      spacing: {
        // Using standard Tailwind spacing (4px base unit) - already perfect
      },
      borderRadius: {
        // Using standard Tailwind radius - already perfect
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' }
        },
        'slide-in': {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' }
        }
      },
      animation: {
        shimmer: 'shimmer 2s infinite linear',
        'slide-in': 'slide-in 0.3s ease-out'
      }
    },
  },
  plugins: [],
}

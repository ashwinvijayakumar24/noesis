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
        'display': ['Syne', 'Inter', 'system-ui', 'sans-serif'],
        'mono': ['JetBrains Mono', 'Courier New', 'monospace'],
      },
      letterSpacing: {
        'tighter': '-0.02em',
        'tight-custom': '-0.015em',
        'tight': '-0.01em',
        'normal': '0em',
        'mono': '0.02em',
      },
      colors: {
        // Deep Space Backgrounds
        'bg-void': '#0a0a0f',
        'bg-surface': '#12121a',
        'bg-elevated': '#1a1a24',
        'bg-hover': '#22222e',

        // Legacy support (for gradual migration)
        'bg-base': '#0a0a0f',
        'surface': '#12121a',
        'surface-hover': '#1a1a24',
        'surface-active': '#22222e',

        // Neon Pink Accent System
        'neon-pink': {
          DEFAULT: '#FF1F4C',
          bright: '#FF2D5A',
          subtle: 'rgba(255, 31, 76, 0.08)',
        },

        // Border Colors
        'border-base': 'rgba(255, 255, 255, 0.08)',
        'border-focus': 'rgba(255, 31, 76, 0.3)',
        'border-active': '#FF1F4C',
        'border-subtle': 'rgba(255, 255, 255, 0.05)',

        // Text Hierarchy - High Contrast
        'text-primary': '#f8f8ff',
        'text-secondary': '#c0c0d0',
        'text-tertiary': '#8080a0',
        'text-muted': '#505070',

        // Supporting Accents
        'accent-teal': '#00d9ff',
        'accent-purple': '#a855f7',

        // Legacy accent (for backward compatibility)
        accent: {
          primary: '#FF1F4C',
          hover: '#FF2D5A',
          light: 'rgba(255, 31, 76, 0.2)',
        },

        // Semantic Colors
        success: '#10B981',
        warning: '#F59E0B',
        error: '#EF4444',
        info: '#00d9ff',
      },
      boxShadow: {
        'neon-glow': '0 0 30px rgba(255, 31, 76, 0.3)',
        'neon-glow-lg': '0 0 60px rgba(255, 31, 76, 0.4)',
        'focus-pink': '0 0 0 4px rgba(255, 31, 76, 0.1)',
        'card-lift': '0 20px 60px rgba(255, 31, 76, 0.15)',
      },
      keyframes: {
        shimmer: {
          '0%': { backgroundPosition: '-1000px 0' },
          '100%': { backgroundPosition: '1000px 0' }
        },
        'gradient-shimmer': {
          '0%': { backgroundPosition: '0% 50%' },
          '50%': { backgroundPosition: '100% 50%' },
          '100%': { backgroundPosition: '0% 50%' }
        },
        'pulse-glow': {
          '0%, 100%': {
            boxShadow: '0 0 20px rgba(255, 31, 76, 0.2)',
            opacity: '1'
          },
          '50%': {
            boxShadow: '0 0 40px rgba(255, 31, 76, 0.4)',
            opacity: '0.9'
          }
        },
        'slide-in': {
          '0%': { transform: 'translateX(100%)', opacity: '0' },
          '100%': { transform: 'translateX(0)', opacity: '1' }
        },
        'fade-in-up': {
          '0%': { opacity: '0', transform: 'translateY(20px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' }
        },
        'float': {
          '0%, 100%': { transform: 'translateY(0px)' },
          '50%': { transform: 'translateY(-20px)' }
        },
      },
      animation: {
        shimmer: 'shimmer 2s infinite linear',
        'gradient-shimmer': 'gradient-shimmer 4s ease infinite',
        'pulse-glow': 'pulse-glow 2s ease-in-out infinite',
        'slide-in': 'slide-in 0.3s ease-out',
        'fade-in-up': 'fade-in-up 0.5s ease-out',
        'float': 'float 6s ease-in-out infinite',
      },
      backgroundImage: {
        'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
        'gradient-text': 'linear-gradient(90deg, #f8f8ff 0%, #FF1F4C 50%, #f8f8ff 100%)',
      },
      backdropBlur: {
        'xl': '20px',
      }
    },
  },
  plugins: [],
}

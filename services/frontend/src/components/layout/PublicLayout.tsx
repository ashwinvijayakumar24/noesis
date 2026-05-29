import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { NoesisLogo } from '../ui/NoesisLogo'

interface PublicLayoutProps {
  children: ReactNode
  className?: string
}

const navLinks = [
  { label: 'Home', to: '/' },
  { label: 'Pricing', to: '/pricing' },
  { label: 'Privacy', to: '/privacy' },
]

function navLinkClass(isActive: boolean) {
  return [
    'rounded-md px-3 py-2 text-sm font-medium transition-colors duration-150',
    isActive
      ? 'bg-bg-elevated text-text-primary'
      : 'text-text-tertiary hover:bg-bg-elevated/70 hover:text-text-primary',
  ].join(' ')
}

export default function PublicLayout({ children, className = '' }: PublicLayoutProps) {
  const location = useLocation()

  return (
    <div className={`min-h-screen bg-bg-void text-text-primary ${className}`}>
      <header className="sticky top-0 z-40 border-b border-border-default bg-bg-surface/95 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link to="/" className="group inline-flex items-center">
            <NoesisLogo size="sm" className="transition-opacity duration-150 group-hover:opacity-80" />
          </Link>

          <nav className="hidden items-center gap-1 md:flex" aria-label="Public navigation">
            {navLinks.map((link) => (
              <Link
                key={link.to}
                to={link.to}
                className={navLinkClass(location.pathname === link.to)}
              >
                {link.label}
              </Link>
            ))}
          </nav>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled
              className="cursor-not-allowed rounded-md px-3 py-2 text-sm font-medium text-text-muted opacity-70"
            >
              Sign In
            </button>
            <button
              type="button"
              disabled
              className="inline-flex cursor-not-allowed items-center gap-2 rounded-md border border-border-default bg-bg-elevated px-3 py-2 text-sm font-semibold text-text-tertiary opacity-80"
            >
              Get Started
            </button>
          </div>
        </div>
      </header>

      {children}

      <footer className="border-t border-border-default bg-bg-void px-4 py-10 sm:px-6 lg:px-8">
        <div className="mx-auto flex max-w-7xl flex-col gap-6 md:flex-row md:items-center md:justify-between">
          <div className="space-y-2">
            <NoesisLogo size="sm" />
            <p className="max-w-md text-sm leading-6 text-text-tertiary">
              Draft-aware pre-submission review for researchers.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-4 text-sm text-text-tertiary">
            <Link to="/pricing" className="transition-colors duration-150 hover:text-text-primary">
              Pricing
            </Link>
            <Link to="/privacy" className="transition-colors duration-150 hover:text-text-primary">
              Privacy
            </Link>
            <a
              href="mailto:avijayakumar41@gatech.edu"
              className="transition-colors duration-150 hover:text-text-primary"
            >
              Contact
            </a>
            <span className="font-mono text-xs text-text-muted">© 2026 Noesis</span>
          </div>
        </div>
      </footer>
    </div>
  )
}

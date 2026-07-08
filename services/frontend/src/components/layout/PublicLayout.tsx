import type { ReactNode } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { NoesisLogo } from '../ui/NoesisLogo'
import { FREEZE_MODE } from '../../config/site'

interface PublicLayoutProps {
  children: ReactNode
  className?: string
}

// Pricing exposes self-serve consumer tiers — drop it from nav in B2B freeze mode.
const navLinks = [
  { label: 'Home', to: '/' },
  ...(FREEZE_MODE ? [] : [{ label: 'Pricing', to: '/pricing' }]),
  { label: 'Privacy', to: '/privacy' },
]

function navLinkClass(isActive: boolean) {
  return [
    'group relative px-3 py-2 text-sm font-medium transition-colors duration-150',
    'after:absolute after:bottom-1 after:left-3 after:h-px after:w-[calc(100%-1.5rem)] after:origin-left after:scale-x-0 after:bg-accent-primary after:transition-transform after:duration-150 after:ease-out hover:after:scale-x-100',
    isActive ? 'text-text-primary' : 'text-text-tertiary hover:text-text-primary',
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
            {FREEZE_MODE ? (
              <Link
                to="/contact"
                className="inline-flex items-center gap-2 rounded-md border border-accent-primary/60 bg-accent-primary px-3 py-2 text-sm font-semibold text-white transition-colors duration-150 hover:border-accent-hover hover:bg-accent-hover"
              >
                Contact Sales
              </Link>
            ) : (
              <>
                <Link
                  to="/login"
                  className="rounded-md px-3 py-2 text-sm font-medium text-text-secondary transition-colors duration-150 hover:bg-bg-elevated/70 hover:text-text-primary"
                >
                  Sign In
                </Link>
                <Link
                  to="/signup"
                  className="inline-flex items-center gap-2 rounded-md border border-accent-primary/60 bg-accent-primary px-3 py-2 text-sm font-semibold text-white transition-colors duration-150 hover:border-accent-hover hover:bg-accent-hover"
                >
                  Get Started
                </Link>
              </>
            )}
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
            {!FREEZE_MODE && (
              <Link to="/pricing" className="transition-colors duration-150 hover:text-text-primary">
                Pricing
              </Link>
            )}
            <Link to="/privacy" className="transition-colors duration-150 hover:text-text-primary">
              Privacy
            </Link>
            <a
              href="mailto:ashwin@noesis.is"
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

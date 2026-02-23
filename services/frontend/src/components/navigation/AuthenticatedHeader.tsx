import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../../stores/authStore'
import { MagnifyingGlassIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import { Menu } from '@headlessui/react'

interface Breadcrumb {
  label: string
  href?: string
}

interface AuthenticatedHeaderProps {
  breadcrumbs?: Breadcrumb[]
  onSearchOpen?: () => void
}

export default function AuthenticatedHeader({ breadcrumbs = [], onSearchOpen }: AuthenticatedHeaderProps) {
  const { user, signOut } = useAuthStore()
  const navigate = useNavigate()

  const handleSignOut = async () => {
    await signOut()
    navigate('/login')
  }

  return (
    <header className="sticky top-0 z-50 h-14 bg-bg-surface/95 backdrop-blur-md border-b border-border-default">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-full">
        <div className="flex items-center justify-between h-full">
          {/* Left: Logo + Breadcrumbs */}
          <div className="flex items-center gap-4">
            {/* Logo - Compact */}
            <Link
              to="/projects"
              className="flex items-center gap-2 group transition-all duration-150"
            >
              <img
                src="/noesis.png"
                alt="Noesis"
                className="h-6 transition-all duration-150"
              />
              <span className="hidden sm:inline text-sm font-sans font-semibold text-text-primary transition-colors duration-150 group-hover:text-accent-primary">
                Noesis
              </span>
            </Link>

            {/* Breadcrumbs - Hidden on mobile */}
            {breadcrumbs.length > 0 && (
              <>
                <div className="hidden md:block h-6 w-px bg-border-default" />
                <nav className="hidden md:flex items-center gap-2 text-sm">
                  {breadcrumbs.map((crumb, index) => (
                    <div key={index} className="flex items-center gap-2">
                      {index > 0 && (
                        <ChevronRightIcon className="h-4 w-4 text-text-muted" />
                      )}
                      {crumb.href ? (
                        <Link
                          to={crumb.href}
                          className="text-text-secondary hover:text-accent-primary transition-colors duration-150 font-medium max-w-[200px] truncate"
                        >
                          {crumb.label}
                        </Link>
                      ) : (
                        <span className="text-accent-primary font-semibold max-w-[200px] truncate">
                          {crumb.label}
                        </span>
                      )}
                    </div>
                  ))}
                </nav>
              </>
            )}
          </div>

          {/* Right: Search + User Menu */}
          <div className="flex items-center gap-3">
            {/* Global Search Button - Touch-friendly */}
            {onSearchOpen && (
              <button
                onClick={onSearchOpen}
                className="group flex items-center gap-2 px-3 sm:px-4 py-2 sm:py-2.5 min-h-[48px] text-sm text-text-tertiary hover:text-accent-primary bg-bg-surface hover:bg-bg-elevated rounded-md border border-border-default hover:border-accent-primary/30 transition-all duration-150"
              >
                <MagnifyingGlassIcon className="h-5 w-5 sm:h-4 sm:w-4" />
                <span className="hidden sm:inline font-medium">Search</span>
                <kbd className="hidden md:inline-flex items-center px-1.5 py-0.5 text-xs font-mono text-text-muted bg-bg-elevated rounded border border-border-default">
                  ⌘K
                </kbd>
              </button>
            )}

            {/* User Menu Dropdown - Touch-friendly */}
            <Menu as="div" className="relative">
              <Menu.Button className="flex items-center gap-2 px-3 sm:px-4 py-2 sm:py-2.5 min-h-[48px] text-sm font-medium text-text-secondary hover:text-text-primary bg-bg-surface hover:bg-bg-elevated rounded-md border border-border-default hover:border-accent-primary/30 transition-all duration-150">
                <div className="hidden md:flex items-center gap-2">
                  <div className="h-6 w-6 rounded-full bg-accent-light border border-accent-primary/30 flex items-center justify-center">
                    <span className="text-xs font-semibold text-accent-primary">
                      {user?.email?.charAt(0).toUpperCase() || 'U'}
                    </span>
                  </div>
                  <span className="font-mono text-xs max-w-[150px] truncate">{user?.email}</span>
                </div>
                <svg className="h-5 w-5 md:h-4 md:w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M16 7a4 4 0 11-8 0 4 4 0 018 0zM12 14a7 7 0 00-7 7h14a7 7 0 00-7-7z" />
                </svg>
              </Menu.Button>

              <Menu.Items className="absolute right-0 mt-2 w-56 bg-bg-surface rounded-lg shadow-lg border border-border-default overflow-hidden">
                <div className="px-4 py-3 border-b border-border-default">
                  <p className="text-xs text-text-muted font-mono mb-1">Signed in as</p>
                  <p className="text-sm text-text-primary font-medium truncate">{user?.email}</p>
                </div>

                <div className="py-1">
                  <Menu.Item>
                    {({ active }) => (
                      <Link
                        to="/projects"
                        className={`${
                          active ? 'bg-bg-elevated text-text-primary' : 'text-text-secondary'
                        } flex items-center gap-3 px-4 py-3 min-h-[48px] text-sm transition-colors duration-150`}
                      >
                        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 7v10a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-6l-2-2H5a2 2 0 00-2 2z" />
                        </svg>
                        My Projects
                      </Link>
                    )}
                  </Menu.Item>
                </div>

                <div className="border-t border-border-default py-1">
                  <Menu.Item>
                    {({ active }) => (
                      <button
                        onClick={handleSignOut}
                        className={`${
                          active ? 'bg-red-950/30 text-red-400' : 'text-text-secondary'
                        } flex items-center gap-3 w-full px-4 py-3 min-h-[48px] text-sm transition-colors duration-150`}
                      >
                        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
                        </svg>
                        Sign Out
                      </button>
                    )}
                  </Menu.Item>
                </div>
              </Menu.Items>
            </Menu>
          </div>
        </div>
      </div>
    </header>
  )
}

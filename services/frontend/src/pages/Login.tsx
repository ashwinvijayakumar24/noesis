import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import { EnvelopeIcon, LockClosedIcon } from '@heroicons/react/24/outline'
import { NoesisLogo } from '../components/ui/NoesisLogo'

export default function Login() {
  useEffect(() => {
    document.title = 'Login Paused | Noesis'
  }, [])

  return (
    <div className="min-h-screen bg-bg-void flex items-center justify-center p-6">
      <motion.div
        initial={{ opacity: 0, y: 16 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.35 }}
        className="relative z-10 w-full max-w-md"
      >
        <div className="mb-8 text-center">
          <Link to="/" className="mb-4 inline-flex items-center gap-3">
            <NoesisLogo size="lg" />
          </Link>
          <p className="text-sm font-mono text-text-muted">AI-powered research workspace</p>
        </div>

        <div className="rounded-lg border border-border-default bg-bg-surface p-8">
          <div className="mb-6 inline-flex items-center gap-2 rounded-lg border border-accent-primary/30 bg-accent-light px-3 py-2 text-xs font-semibold uppercase tracking-widest text-accent-primary">
            <LockClosedIcon className="h-4 w-4" />
            Beta Coming Soon
          </div>

          <h1 className="mb-4 text-3xl font-sans font-semibold text-text-primary">
            Sign in is paused
          </h1>
          <p className="mb-8 text-sm leading-relaxed text-text-secondary">
            Noesis beta access is temporarily closed while the product is being reworked. Existing app routes are unavailable during this transition.
          </p>

          <div className="space-y-5">
            <div>
              <label htmlFor="email" className="mb-2 block text-sm font-medium text-text-secondary">
                Email address
              </label>
              <div className="relative">
                <EnvelopeIcon className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-text-muted" />
                <input
                  id="email"
                  type="email"
                  disabled
                  className="w-full rounded-lg border border-border-default bg-bg-void py-3 pl-12 pr-4 text-text-muted opacity-60"
                  placeholder="Beta access paused"
                />
              </div>
            </div>

            <button
              type="button"
              disabled
              className="w-full cursor-not-allowed rounded-lg bg-accent-primary py-3 font-semibold text-white opacity-50"
            >
              Beta Coming Soon
            </button>
          </div>

          <div className="mt-6 text-center text-sm text-text-tertiary">
            New accounts are paused during the pivot.
          </div>
        </div>

        <p className="mt-8 text-center text-sm font-mono text-text-muted">
          © 2026 Noesis
        </p>
      </motion.div>
    </div>
  )
}

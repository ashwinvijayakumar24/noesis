import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { supabase } from '../lib/supabase'
import { useAuthStore } from '../stores/authStore'
import { analytics, trackEvent } from '../lib/analytics'

export default function AuthCallback() {
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const { initialize } = useAuthStore()

  useEffect(() => {
    document.title = 'Authenticating... | Noesis'

    const handleCallback = async () => {
      try {
        // Get session from URL hash
        const { data, error: sessionError } = await supabase.auth.getSession()

        if (sessionError) {
          console.error('Session error:', sessionError)
          throw sessionError
        }

        if (data.session) {
          // Initialize auth store with session
          await initialize()

          // Track OAuth sign-in
          if (data.session.user.email) {
            analytics.identify(data.session.user.email)
            trackEvent.signIn()
          }

          // Redirect to main app
          navigate('/projects')
        } else {
          throw new Error('No session found')
        }
      } catch (err) {
        console.error('OAuth callback error:', err)
        setError('Authentication failed. Please try again.')

        // Redirect to login after 3 seconds
        setTimeout(() => navigate('/login'), 3000)
      }
    }

    handleCallback()
  }, [navigate, initialize])

  if (error) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center p-6">
        <div className="max-w-md w-full">
          {/* Logo/Brand */}
          <div className="text-center mb-8">
            <Link to="/" className="inline-flex items-center gap-3 mb-4">
              <img src="/noesis.png" alt="Noesis" className="h-12" />
              <span className="text-2xl font-serif font-semibold text-text-primary">Noesis</span>
            </Link>
            <p className="text-text-muted text-sm font-mono">AI-powered research workspace</p>
          </div>

          {/* Error Card */}
          <div className="bg-surface rounded-lg border border-border-base p-8 text-center">
            <p className="text-red-500 mb-2">{error}</p>
            <p className="text-text-tertiary text-sm">Redirecting to login...</p>
          </div>

          {/* Footer */}
          <p className="text-center text-sm font-mono text-text-muted mt-8">
            © 2026 Noesis
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-base flex items-center justify-center p-6">
      <div className="max-w-md w-full">
        {/* Logo/Brand */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-3 mb-4">
            <img src="/noesis.png" alt="Noesis" className="h-12" />
            <span className="text-2xl font-serif font-semibold text-text-primary">Noesis</span>
          </Link>
          <p className="text-text-muted text-sm font-mono">AI-powered research workspace</p>
        </div>

        {/* Loading Card */}
        <div className="bg-surface rounded-lg border border-border-base p-8 text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent mb-4"></div>
          <p className="text-text-secondary">Completing sign-in...</p>
        </div>

        {/* Footer */}
        <p className="text-center text-sm font-mono text-text-muted mt-8">
          © 2026 Noesis
        </p>
      </div>
    </div>
  )
}

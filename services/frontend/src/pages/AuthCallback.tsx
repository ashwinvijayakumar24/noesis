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
        // Initialize auth store first (sets up listeners)
        await initialize()

        // Check for email confirmation token (query params)
        const searchParams = new URLSearchParams(window.location.search)
        const tokenHash = searchParams.get('token_hash')
        const type = searchParams.get('type')

        if (tokenHash && type === 'signup') {
          // Email confirmation - verify OTP
          const { data: sessionData, error: verifyError } = await supabase.auth.verifyOtp({
            token_hash: tokenHash,
            type: 'signup'
          })

          if (verifyError) {
            throw verifyError
          }

          if (sessionData.session) {
            // Track signup completion
            if (sessionData.session.user.email) {
              analytics.identify(sessionData.session.user.email)
              trackEvent.signUp()
            }

            // Redirect to projects
            navigate('/projects')
            return
          }
        }

        // If no explicit token_hash, wait for Supabase to auto-create session
        // Modern Supabase automatically creates sessions via detectSessionInUrl
        await new Promise(resolve => setTimeout(resolve, 3000))

        // Check if session was auto-created
        const { data: { session: autoSession } } = await supabase.auth.getSession()
        if (autoSession) {
          // Track signup completion
          if (autoSession.user.email) {
            analytics.identify(autoSession.user.email)
            trackEvent.signUp()
          }

          // Redirect to projects
          navigate('/projects')
          return
        }

        // OAuth callback (Google, etc)
        const hashParams = new URLSearchParams(window.location.hash.substring(1))
        const accessToken = hashParams.get('access_token')
        const refreshToken = hashParams.get('refresh_token')
        const code = searchParams.get('code')

        if (accessToken || refreshToken || code) {
          // Wait for Supabase's onAuthStateChange to process the OAuth callback
          await new Promise(resolve => setTimeout(resolve, 2000))

          // After waiting, check if session was created
          const { data } = await supabase.auth.getSession()

          if (data.session) {
            // Track OAuth sign-in
            if (data.session.user.email) {
              analytics.identify(data.session.user.email)
              trackEvent.signIn()
            }

            // Redirect to main app
            navigate('/projects')
            return
          }
        }

        throw new Error('No session found')
      } catch (err) {
        console.error('Authentication callback error:', err)
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

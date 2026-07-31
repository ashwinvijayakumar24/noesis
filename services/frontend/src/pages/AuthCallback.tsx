import { useEffect, useState } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { NoesisLogo } from '../components/ui/NoesisLogo'
import { supabase } from '../lib/supabase'
import { useAuthStore } from '../stores/authStore'
import { analytics, trackEvent } from '../lib/analytics'

const OTP_TYPES = new Set(['signup', 'magiclink', 'recovery', 'invite', 'email_change', 'email'])

export default function AuthCallback() {
  const [error, setError] = useState<string | null>(null)
  const navigate = useNavigate()
  const { initialize } = useAuthStore()

  useEffect(() => {
    document.title = 'Authenticating... | Noesis'

    const handleCallback = async () => {
      try {
        const searchParams = new URLSearchParams(window.location.search)
        const hashParams = new URLSearchParams(window.location.hash.substring(1))
        const urlError = searchParams.get('error_description')
          || searchParams.get('error')
          || hashParams.get('error_description')
          || hashParams.get('error')
        if (urlError) {
          throw new Error(urlError)
        }

        const code = searchParams.get('code')
        const tokenHash = searchParams.get('token_hash')
        const type = searchParams.get('type')
        const accessToken = hashParams.get('access_token')
        const refreshToken = hashParams.get('refresh_token')

        if (code) {
          const { data, error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
          if (exchangeError) {
            throw exchangeError
          }

          if (data.session) {
            if (data.session.user.email) {
              analytics.identify(data.session.user.email)
              trackEvent.signIn()
            }

            window.history.replaceState({}, document.title, '/auth/callback')
            await initialize()
            navigate('/projects')
            return
          }
        }

        if (tokenHash && type && OTP_TYPES.has(type)) {
          const { data: sessionData, error: verifyError } = await supabase.auth.verifyOtp({
            token_hash: tokenHash,
            type: type as any,
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

            window.history.replaceState({}, document.title, '/auth/callback')
            await initialize()
            navigate('/projects')
            return
          }
        }

        if (accessToken && refreshToken) {
          const { data, error: setSessionError } = await supabase.auth.setSession({
            access_token: accessToken,
            refresh_token: refreshToken,
          })
          if (setSessionError) {
            throw setSessionError
          }

          if (data.session) {
            if (data.session.user.email) {
              analytics.identify(data.session.user.email)
              trackEvent.signIn()
            }

            window.history.replaceState({}, document.title, '/auth/callback')
            await initialize()
            navigate('/projects')
            return
          }
        }

        await initialize()
        const { data: { session } } = await supabase.auth.getSession()
        if (session) {
          navigate('/projects')
          return
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
            <Link to="/" className="inline-flex items-center mb-4">
              <NoesisLogo size="lg" />
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
          <Link to="/" className="inline-flex items-center mb-4">
            <NoesisLogo size="lg" />
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

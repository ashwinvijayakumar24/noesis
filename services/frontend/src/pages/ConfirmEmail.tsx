import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams, Link } from 'react-router-dom'
import { NoesisLogo } from '../components/ui/NoesisLogo'
import { CheckCircleIcon, XCircleIcon } from '@heroicons/react/24/outline'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function ConfirmEmail() {
  const [searchParams] = useSearchParams()
  const [status, setStatus] = useState<'loading' | 'success' | 'error'>('loading')
  const navigate = useNavigate()

  useEffect(() => {
    document.title = 'Confirm Email | Noesis'

    const confirmEmail = async () => {
      const token = searchParams.get('token')
      const type = searchParams.get('type')

      if (!token || !type) {
        setStatus('error')
        return
      }

      try {
        const response = await fetch(
          `${API_URL}/auth/confirm?token=${encodeURIComponent(token)}&type=${encodeURIComponent(type)}`
        )

        if (response.ok) {
          setStatus('success')
          // Redirect to login after 3 seconds
          setTimeout(() => navigate('/login'), 3000)
        } else {
          setStatus('error')
        }
      } catch (err) {
        console.error('Email confirmation error:', err)
        setStatus('error')
      }
    }

    confirmEmail()
  }, [searchParams, navigate])

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

        {/* Confirmation Card */}
        <div className="bg-surface rounded-lg border border-border-base p-8 text-center">
          {status === 'loading' && (
            <div className="space-y-4">
              <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
              <p className="text-text-secondary">Confirming your email...</p>
            </div>
          )}

          {status === 'success' && (
            <div className="space-y-4">
              <CheckCircleIcon className="h-16 w-16 text-green-500 mx-auto" />
              <h2 className="text-2xl font-serif font-semibold text-text-primary">
                Email Confirmed!
              </h2>
              <p className="text-text-secondary">
                Your account is now active. Redirecting to login...
              </p>
              <button
                onClick={() => navigate('/login')}
                className="text-accent-primary hover:text-accent-hover font-medium transition-colors"
              >
                Go to login now
              </button>
            </div>
          )}

          {status === 'error' && (
            <div className="space-y-4">
              <XCircleIcon className="h-16 w-16 text-red-500 mx-auto" />
              <h2 className="text-2xl font-serif font-semibold text-text-primary">
                Confirmation Failed
              </h2>
              <p className="text-text-secondary">
                This link is invalid or expired. Please sign up again or contact support.
              </p>
              <button
                onClick={() => navigate('/signup')}
                className="text-accent-primary hover:text-accent-hover font-medium transition-colors"
              >
                Return to signup
              </button>
            </div>
          )}
        </div>

        {/* Footer */}
        <p className="text-center text-sm font-mono text-text-muted mt-8">
          © 2026 Noesis
        </p>
      </div>
    </div>
  )
}

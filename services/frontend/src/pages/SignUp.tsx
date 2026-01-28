import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { CheckCircleIcon } from '@heroicons/react/24/outline'
import { useAuthStore } from '../stores/authStore'
import { supabase } from '../lib/supabase'
import toast from 'react-hot-toast'
import { analytics, trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'

export default function SignUp() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [signupSuccess, setSignupSuccess] = useState(false)
  const { signUp, loading } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    document.title = 'Sign Up | Noesis'
  }, [])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    if (!email || !password || !confirmPassword) {
      toast.error('Please fill in all fields')
      return
    }

    if (password !== confirmPassword) {
      toast.error('Passwords do not match')
      return
    }

    if (password.length < 6) {
      toast.error('Password must be at least 6 characters')
      return
    }

    try {
      await signUp(email, password)
      analytics.identify(email)
      trackEvent.signUp()
      // Show success message instead of navigating
      setSignupSuccess(true)
    } catch (error: any) {
      handleError(error, 'sign up')
    }
  }

  const handleGoogleSignup = async () => {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`
        }
      })

      if (error) {
        console.error('Google sign-up error:', error)
        toast.error('Google sign-up failed. Please try again.')
      }
    } catch (err) {
      console.error('Google sign-up error:', err)
      toast.error('Google sign-up failed. Please try again.')
    }
  }

  // Show success message after signup
  if (signupSuccess) {
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

          {/* Success Card */}
          <div className="bg-surface rounded-lg border border-border-base p-8 text-center">
            <div className="space-y-4">
              <CheckCircleIcon className="h-16 w-16 text-green-500 mx-auto" />
              <h2 className="text-2xl font-serif font-semibold text-text-primary">
                Check Your Email
              </h2>
              <p className="text-text-secondary">
                We sent a confirmation link to <strong className="text-text-primary">{email}</strong>
              </p>
              <p className="text-text-tertiary text-sm">
                Click the link in the email to activate your account.
                It may take a few minutes to arrive. Don't forget to check your spam folder.
              </p>
              <button
                onClick={() => navigate('/login')}
                className="text-accent-primary hover:text-accent-hover font-medium transition-colors"
              >
                Return to login
              </button>
            </div>
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

        {/* Signup Card */}
        <div className="bg-surface rounded-lg border border-border-base p-8">
          <h2 className="text-2xl font-serif font-semibold text-text-primary mb-6">
            Create your account
          </h2>

          {/* Google OAuth */}
          <div className="mb-6">
            <button
              type="button"
              onClick={handleGoogleSignup}
              disabled={loading}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-white border border-border-base rounded-lg hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-accent-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              <svg className="h-5 w-5" viewBox="0 0 24 24">
                <path
                  fill="#4285F4"
                  d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
                />
                <path
                  fill="#34A853"
                  d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
                />
                <path
                  fill="#FBBC05"
                  d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
                />
                <path
                  fill="#EA4335"
                  d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
                />
              </svg>
              <span className="text-gray-700 font-medium">
                Continue with Google
              </span>
            </button>

            <div className="relative my-6">
              <div className="absolute inset-0 flex items-center">
                <div className="w-full border-t border-border-base" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-2 bg-surface text-text-muted">Or sign up with email</span>
              </div>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-text-secondary mb-2">
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 bg-bg-base border border-border-base rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                placeholder="you@example.com"
                autoComplete="off"
                disabled={loading}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-text-secondary mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-bg-base border border-border-base rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                placeholder="••••••••"
                autoComplete="off"
                disabled={loading}
              />
              <p className="mt-2 text-xs font-mono text-text-muted">At least 6 characters</p>
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-text-secondary mb-2">
                Confirm password
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-4 py-3 bg-bg-base border border-border-base rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                placeholder="••••••••"
                autoComplete="off"
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent-primary text-white font-semibold py-3 rounded-lg hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-surface focus:ring-accent-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Creating account...' : 'Sign up'}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-text-tertiary">
            Already have an account?{' '}
            <Link to="/login" className="text-accent-primary hover:text-accent-hover font-medium transition-colors">
              Sign in
            </Link>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-sm font-mono text-text-muted mt-8">
          Join researchers using Noesis
        </p>
      </div>
    </div>
  )
}

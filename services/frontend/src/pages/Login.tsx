import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { supabase } from '../lib/supabase'
import toast from 'react-hot-toast'
import { analytics, trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'
import { motion } from 'framer-motion'
import { EnvelopeIcon, LockClosedIcon } from '@heroicons/react/24/outline'

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export default function Login() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [unverifiedEmail, setUnverifiedEmail] = useState<string | null>(null)
  const { signIn, loading } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    document.title = 'Login | Noesis'
  }, [])

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    if (!email || !password) {
      toast.error('Please fill in all fields')
      return
    }

    try {
      await signIn(email, password)
      analytics.identify(email)
      trackEvent.signIn()
      toast.success('Welcome back!')
      navigate('/projects')
    } catch (error: any) {
      // Check if error is due to unverified email
      const errorMessage = error.message || ''
      if (errorMessage.includes('verify your email') || errorMessage.includes('email not confirmed')) {
        setUnverifiedEmail(email)
        toast.error('Please verify your email before logging in')
      } else {
        handleError(error, 'sign in')
      }
    }
  }

  const handleResendConfirmation = async () => {
    if (!unverifiedEmail) return

    try {
      const response = await fetch(`${API_URL}/auth/resend-confirmation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: unverifiedEmail })
      })

      if (response.ok) {
        toast.success('Confirmation email sent! Check your inbox.')
      } else {
        toast.error('Failed to resend confirmation')
      }
    } catch (err) {
      toast.error('Failed to resend confirmation')
    }
  }

  const handleGoogleLogin = async () => {
    try {
      const { error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: `${window.location.origin}/auth/callback`
        }
      })

      if (error) {
        console.error('Google sign-in error:', error)
        toast.error('Google sign-in failed. Please try again.')
      }
    } catch (err) {
      console.error('Google sign-in error:', err)
      toast.error('Google sign-in failed. Please try again.')
    }
  }

  return (
    <div className="min-h-screen bg-bg-void flex items-center justify-center p-6 relative overflow-hidden">
      {/* Decorative Background Glow */}
      <div className="absolute top-1/4 right-1/4 w-96 h-96 bg-accent-primary/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 left-1/4 w-96 h-96 bg-accent-teal/10 rounded-full blur-[120px] pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="max-w-md w-full relative z-10"
      >
        {/* Logo/Brand */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-3 mb-4 group">
            <img
              src="/noesis.png"
              alt="Noesis"
              className="h-12 transition-all duration-150 group-hover:drop-shadow-[0_0_8px_rgba(255,31,76,0.6)]"
            />
            <span className="text-2xl font-sans font-semibold text-text-primary">Noesis</span>
          </Link>
          <p className="text-text-muted text-sm font-mono">AI-powered research workspace</p>
        </div>

        {/* Login Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="bg-bg-surface rounded-lg border border-border-default p-8 backdrop-blur-sm"
        >
          <h2 className="text-3xl font-sans font-semibold text-text-primary mb-6">
            Sign in to your account
          </h2>

          {/* Unverified Email Message */}
          {unverifiedEmail && (
            <motion.div
              initial={{ opacity: 0, height: 0 }}
              animate={{ opacity: 1, height: 'auto' }}
              className="mb-6 p-4 bg-warning/10 border border-warning/30 rounded-lg"
            >
              <p className="text-sm text-warning mb-2">
                Please verify your email before logging in. Check your inbox for the confirmation link.
              </p>
              <button
                onClick={handleResendConfirmation}
                className="text-sm text-accent-primary hover:text-accent-primary-bright font-medium underline"
              >
                Resend confirmation email
              </button>
            </motion.div>
          )}

          {/* Google OAuth */}
          <div className="mb-6">
            <button
              type="button"
              onClick={handleGoogleLogin}
              disabled={loading}
              className="w-full flex items-center justify-center gap-3 px-4 py-3 bg-white border border-border-default rounded-lg hover:bg-gray-50 hover:border-accent-primary/30 focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-accent-primary disabled:opacity-50 disabled:cursor-not-allowed transition-all duration-150"
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
                <div className="w-full border-t border-border-default" />
              </div>
              <div className="relative flex justify-center text-sm">
                <span className="px-3 bg-bg-surface text-text-muted font-mono">Or continue with email</span>
              </div>
            </div>
          </div>

          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email Input with Icon */}
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-text-secondary mb-2">
                Email address
              </label>
              <div className="relative">
                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none">
                  <EnvelopeIcon className="h-5 w-5" />
                </div>
                <input
                  id="email"
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full pl-12 pr-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary focus:shadow-focus-pink focus:bg-bg-elevated hover:border-border-focus transition-all duration-150 disabled:opacity-50"
                  placeholder="you@example.com"
                  autoComplete="email"
                  disabled={loading}
                />
              </div>
            </div>

            {/* Password Input with Icon */}
            <div>
              <label htmlFor="password" className="block text-sm font-medium text-text-secondary mb-2">
                Password
              </label>
              <div className="relative">
                <div className="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none">
                  <LockClosedIcon className="h-5 w-5" />
                </div>
                <input
                  id="password"
                  type="password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full pl-12 pr-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary focus:shadow-focus-pink focus:bg-bg-elevated hover:border-border-focus transition-all duration-150 disabled:opacity-50"
                  placeholder="••••••••"
                  autoComplete="current-password"
                  disabled={loading}
                />
              </div>
            </div>

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent-primary text-white font-semibold py-3 rounded-lg hover:shadow-sm hover:scale-[1.02] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-2 focus:ring-offset-bg-surface disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 transition-all duration-150"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                  Signing in...
                </span>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-text-tertiary">
            Don't have an account?{' '}
            <Link to="/signup" className="text-accent-primary hover:text-accent-primary-bright font-semibold transition-colors">
              Sign up
            </Link>
          </div>
        </motion.div>

        {/* Footer */}
        <p className="text-center text-sm font-mono text-text-muted mt-8">
          © 2026 Noesis
        </p>
      </motion.div>
    </div>
  )
}

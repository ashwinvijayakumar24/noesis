import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'
import { analytics, trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'

export default function SignUp() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
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
      toast.success('Account created! Welcome to Noesis')
      navigate('/projects')
    } catch (error: any) {
      handleError(error, 'sign up')
    }
  }

  return (
    <div className="min-h-screen bg-neutral-950 flex items-center justify-center p-6">
      <div className="max-w-md w-full">
        {/* Logo/Brand */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-3 mb-4">
            <img src="/noesis.png" alt="Noesis" className="h-12" />
            <span className="text-2xl font-serif font-semibold text-neutral-50">Noesis</span>
          </Link>
          <p className="text-neutral-500 text-sm font-mono">AI-powered research workspace</p>
        </div>

        {/* Signup Card */}
        <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-8">
          <h2 className="text-2xl font-serif font-semibold text-neutral-50 mb-6">
            Create your account
          </h2>

          <form onSubmit={handleSubmit} className="space-y-5">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-neutral-300 mb-2">
                Email address
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                placeholder="you@example.com"
                autoComplete="off"
                disabled={loading}
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-neutral-300 mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                placeholder="••••••••"
                autoComplete="off"
                disabled={loading}
              />
              <p className="mt-2 text-xs font-mono text-neutral-500">At least 6 characters</p>
            </div>

            <div>
              <label htmlFor="confirmPassword" className="block text-sm font-medium text-neutral-300 mb-2">
                Confirm password
              </label>
              <input
                id="confirmPassword"
                type="password"
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                placeholder="••••••••"
                autoComplete="off"
                disabled={loading}
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full bg-accent-primary text-white font-semibold py-3 rounded-lg hover:bg-accent-hover focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-neutral-900 focus:ring-accent-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
            >
              {loading ? 'Creating account...' : 'Sign up'}
            </button>
          </form>

          <div className="mt-6 text-center text-sm text-neutral-400">
            Already have an account?{' '}
            <Link to="/login" className="text-accent-primary hover:text-accent-hover font-medium transition-colors">
              Sign in
            </Link>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-sm font-mono text-neutral-600 mt-8">
          Join researchers using Noesis
        </p>
      </div>
    </div>
  )
}

import { useState, useEffect, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { EnvelopeIcon, KeyIcon } from '@heroicons/react/24/outline'
import { useAuthStore } from '../stores/authStore'
import { supabase } from '../lib/supabase'
import toast from 'react-hot-toast'
import { analytics, trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'
import { motion } from 'framer-motion'
import { NoesisLogo } from '../components/ui/NoesisLogo'

export default function SignUp() {
  const [email, setEmail] = useState('')
  const [otp, setOtp] = useState('')
  const [step, setStep] = useState<'email' | 'otp'>('email')
  const [resendTimer, setResendTimer] = useState(0)
  const { sendOtp, verifyOtp, loading } = useAuthStore()
  const navigate = useNavigate()

  useEffect(() => {
    document.title = 'Sign Up | Noesis'
  }, [])

  // Countdown timer for resend button
  useEffect(() => {
    if (resendTimer > 0) {
      const timer = setTimeout(() => setResendTimer(resendTimer - 1), 1000)
      return () => clearTimeout(timer)
    }
  }, [resendTimer])

  const handleSendOtp = async (e: FormEvent) => {
    e.preventDefault()

    if (!email) {
      toast.error('Please enter your email')
      return
    }

    // Basic email validation
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/
    if (!emailRegex.test(email)) {
      toast.error('Please enter a valid email address')
      return
    }

    try {
      await sendOtp(email)
      analytics.identify(email)
      trackEvent.signUp()
      setStep('otp')
      setResendTimer(60) // 60 second cooldown
      toast.success('Check your email for a 6-digit code')
    } catch (error: any) {
      handleError(error, 'send verification code')
    }
  }

  const handleVerifyOtp = async (e: FormEvent) => {
    e.preventDefault()

    if (!otp) {
      toast.error('Please enter the 6-digit code')
      return
    }

    if (otp.length !== 6) {
      toast.error('Code must be 6 digits')
      return
    }

    try {
      await verifyOtp(email, otp)
      toast.success('Welcome to Noesis!')
      navigate('/projects')
    } catch (error: any) {
      if (error.message?.includes('expired')) {
        toast.error('Code expired. Please request a new one.')
      } else if (error.message?.includes('invalid')) {
        toast.error('Invalid code. Please try again.')
      } else {
        handleError(error, 'verify code')
      }
    }
  }

  const handleResendOtp = async () => {
    if (resendTimer > 0) return

    try {
      await sendOtp(email)
      setResendTimer(60)
      toast.success('New code sent! Check your email.')
    } catch (error: any) {
      handleError(error, 'resend code')
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

  return (
    <div className="min-h-screen bg-bg-void flex items-center justify-center p-6 relative overflow-hidden">
      {/* Decorative Background Glow */}
      <div className="absolute top-1/4 left-1/4 w-96 h-96 bg-accent-purple/10 rounded-full blur-[120px] pointer-events-none" />
      <div className="absolute bottom-1/4 right-1/4 w-96 h-96 bg-accent-primary/10 rounded-full blur-[120px] pointer-events-none" />

      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.5 }}
        className="max-w-md w-full relative z-10"
      >
        {/* Logo/Brand */}
        <div className="text-center mb-8">
          <Link to="/" className="inline-flex items-center gap-3 mb-4 group">
            <NoesisLogo size="lg" />
          </Link>
          <p className="text-text-muted text-sm font-mono">AI-powered research workspace</p>
        </div>

        {/* Signup Card */}
        <motion.div
          initial={{ opacity: 0, scale: 0.95 }}
          animate={{ opacity: 1, scale: 1 }}
          transition={{ duration: 0.5, delay: 0.1 }}
          className="bg-bg-surface rounded-lg border border-border-default p-8 backdrop-blur-sm"
        >
          <h2 className="text-3xl font-sans font-semibold text-text-primary mb-6">
            {step === 'email' ? 'Create your account' : 'Enter verification code'}
          </h2>

          {/* Google OAuth - Only show on email step */}
          {step === 'email' && (
            <div className="mb-6">
              <button
                type="button"
                onClick={handleGoogleSignup}
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
                  <span className="px-3 bg-bg-surface text-text-muted font-mono">Or sign up with email</span>
                </div>
              </div>
            </div>
          )}

          {/* Email Step */}
          {step === 'email' && (
            <form onSubmit={handleSendOtp} className="space-y-5">
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
                    autoFocus
                  />
                </div>
                <p className="mt-2 text-xs font-mono text-text-muted">
                  We'll send you a 6-digit code to verify your email
                </p>
              </div>

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
                    Sending code...
                  </span>
                ) : (
                  'Continue'
                )}
              </button>
            </form>
          )}

          {/* OTP Verification Step */}
          {step === 'otp' && (
            <div className="space-y-5">
              <div className="bg-bg-elevated border border-border-default rounded-lg p-4 mb-6">
                <p className="text-sm text-text-secondary mb-2">
                  We sent a 6-digit code to:
                </p>
                <p className="text-base font-semibold text-accent-primary">
                  {email}
                </p>
                <button
                  onClick={() => {
                    setStep('email')
                    setOtp('')
                  }}
                  className="text-xs text-text-muted hover:text-text-secondary mt-2 transition-colors"
                >
                  Change email →
                </button>
              </div>

              <form onSubmit={handleVerifyOtp} className="space-y-5">
                <div>
                  <label htmlFor="otp" className="block text-sm font-medium text-text-secondary mb-2">
                    Verification code
                  </label>
                  <div className="relative">
                    <div className="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none">
                      <KeyIcon className="h-5 w-5" />
                    </div>
                    <input
                      id="otp"
                      type="text"
                      inputMode="numeric"
                      pattern="[0-9]*"
                      maxLength={6}
                      value={otp}
                      onChange={(e) => setOtp(e.target.value.replace(/\D/g, ''))}
                      className="w-full pl-12 pr-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary placeholder:text-text-muted focus:outline-none focus:border-accent-primary focus:shadow-focus-pink focus:bg-bg-elevated hover:border-border-focus transition-all duration-150 disabled:opacity-50 text-2xl tracking-widest text-center font-mono"
                      placeholder="000000"
                      autoComplete="one-time-code"
                      disabled={loading}
                      autoFocus
                    />
                  </div>
                  <p className="mt-2 text-xs font-mono text-text-muted">
                    Enter the 6-digit code from your email
                  </p>
                </div>

                <button
                  type="submit"
                  disabled={loading || otp.length !== 6}
                  className="w-full bg-accent-primary text-white font-semibold py-3 rounded-lg hover:shadow-sm hover:scale-[1.02] active:scale-[0.98] focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-2 focus:ring-offset-bg-surface disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100 transition-all duration-150"
                >
                  {loading ? (
                    <span className="flex items-center justify-center gap-2">
                      <svg className="animate-spin h-5 w-5" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                      </svg>
                      Verifying...
                    </span>
                  ) : (
                    'Verify & Continue'
                  )}
                </button>

                <div className="text-center">
                  <button
                    type="button"
                    onClick={handleResendOtp}
                    disabled={resendTimer > 0 || loading}
                    className="text-sm text-text-muted hover:text-accent-primary disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {resendTimer > 0 ? (
                      `Resend code in ${resendTimer}s`
                    ) : (
                      'Resend code'
                    )}
                  </button>
                </div>
              </form>
            </div>
          )}

          <div className="mt-6 text-center text-sm text-text-tertiary">
            Already have an account?{' '}
            <Link to="/login" className="text-accent-primary hover:text-accent-primary-bright font-semibold transition-colors">
              Sign in
            </Link>
          </div>
        </motion.div>

        {/* Footer */}
        <p className="text-center text-sm font-mono text-text-muted mt-8">
          Join researchers using Noesis
        </p>
      </motion.div>
    </div>
  )
}

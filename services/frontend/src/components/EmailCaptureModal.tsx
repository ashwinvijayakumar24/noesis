import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { XMarkIcon, SparklesIcon, CheckCircleIcon } from '@heroicons/react/24/outline'
import { Button } from './ui/Button'

interface EmailCaptureModalProps {
  isOpen: boolean
  onClose: () => void
  onSubmit: (email: string) => void
}

export default function EmailCaptureModal({ isOpen, onClose, onSubmit }: EmailCaptureModalProps) {
  const [email, setEmail] = useState('')
  const [submitted, setSubmitted] = useState(false)
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!email || !email.includes('@')) return

    setLoading(true)
    try {
      // Call parent onSubmit
      await onSubmit(email)
      setSubmitted(true)

      // Close modal after 2 seconds
      setTimeout(() => {
        onClose()
        setSubmitted(false)
        setEmail('')
      }, 2000)
    } catch (error) {
      console.error('Email capture error:', error)
    } finally {
      setLoading(false)
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={onClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="relative bg-bg-surface border border-border-default rounded-lg shadow-2xl max-w-md w-full p-8"
          >
            {/* Close Button */}
            <button
              onClick={onClose}
              className="absolute top-4 right-4 text-text-muted hover:text-text-primary transition-colors"
            >
              <XMarkIcon className="h-5 w-5" />
            </button>

            {!submitted ? (
              <>
                {/* Header */}
                <div className="text-center space-y-3 mb-6">
                  <div className="inline-flex items-center justify-center w-12 h-12 bg-accent-primary/10 rounded-full">
                    <SparklesIcon className="h-6 w-6 text-accent-primary" />
                  </div>
                  <h3 className="text-2xl font-bold text-text-primary">
                    Want to Analyze Your Own Drafts?
                  </h3>
                  <p className="text-text-secondary">
                    Sign up for free to upload papers, import references, and get AI-powered feedback before submission.
                  </p>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="space-y-4">
                  <div>
                    <label htmlFor="email" className="block text-sm font-medium text-text-secondary mb-2">
                      Email Address
                    </label>
                    <input
                      id="email"
                      type="email"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      placeholder="you@university.edu"
                      className="w-full px-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent"
                      required
                    />
                  </div>

                  <Button
                    type="submit"
                    variant="primary"
                    size="lg"
                    className="w-full"
                    disabled={loading}
                  >
                    {loading ? 'Signing Up...' : 'Get Free Access'}
                  </Button>
                </form>

                {/* Benefits */}
                <div className="mt-6 space-y-2 text-sm text-text-secondary">
                  <div className="flex items-start gap-2">
                    <CheckCircleIcon className="h-5 w-5 text-green-500 flex-shrink-0" />
                    <span>2 draft analyses per month on Free</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckCircleIcon className="h-5 w-5 text-green-500 flex-shrink-0" />
                    <span>30 PDF uploads and 30 BibTeX references per month</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckCircleIcon className="h-5 w-5 text-green-500 flex-shrink-0" />
                    <span>5 Discover searches and 5 Literature Map refreshes per day</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <CheckCircleIcon className="h-5 w-5 text-green-500 flex-shrink-0" />
                    <span>No credit card required</span>
                  </div>
                </div>

                {/* Footer */}
                <p className="mt-6 text-xs text-center text-text-muted">
                  By signing up, you agree to our{' '}
                  <a href="/privacy" className="text-accent-primary hover:underline">
                    Privacy Policy
                  </a>
                </p>
              </>
            ) : (
              /* Success State */
              <div className="text-center space-y-4 py-8">
                <div className="inline-flex items-center justify-center w-16 h-16 bg-green-500/10 rounded-full">
                  <CheckCircleIcon className="h-8 w-8 text-green-500" />
                </div>
                <h3 className="text-2xl font-bold text-text-primary">Check Your Email!</h3>
                <p className="text-text-secondary">
                  We've sent you a confirmation link to <strong>{email}</strong>
                </p>
                <p className="text-sm text-text-muted">
                  Click the link to complete your signup and start analyzing your drafts.
                </p>
              </div>
            )}
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}

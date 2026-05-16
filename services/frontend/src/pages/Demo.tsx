import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import { SparklesIcon, ArrowRightIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { NoesisLogo } from '../components/ui/NoesisLogo'
import { Button } from '../components/ui/Button'
import EmailCaptureModal from '../components/EmailCaptureModal'
import DraftAnalysisShowcase from '../components/draft-analysis/DraftAnalysisShowcase'

export default function Demo() {
  const navigate = useNavigate()
  const [showEmailModal, setShowEmailModal] = useState(false)
  const [analysisComplete, setAnalysisComplete] = useState(false)

  useEffect(() => {
    document.title = 'Demo - Noesis Draft Analysis'
    const readyTimer = setTimeout(() => {
      setAnalysisComplete(true)
      const emailTimer = setTimeout(() => setShowEmailModal(true), 5000)
      return () => clearTimeout(emailTimer)
    }, 1200)

    return () => clearTimeout(readyTimer)
  }, [])

  const handleSignup = () => {
    navigate('/signup')
  }

  const handleEmailSubmit = async (email: string) => {
    try {
      navigate(`/signup?email=${encodeURIComponent(email)}`)
      toast.success('Redirecting to signup...')
    } catch (error) {
      toast.error('Something went wrong. Please try again.')
      throw error
    }
  }

  return (
    <div className="min-h-screen bg-bg-void text-text-primary">
      <div className="border-b border-accent-primary/20 bg-accent-primary/10 py-2">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-6 sm:px-8">
          <div className="flex items-center gap-2 text-sm">
            <SparklesIcon className="h-4 w-4 text-accent-primary" />
            <span className="font-semibold text-accent-primary">Demo Mode</span>
            <span className="text-text-secondary">Scripted draft-analysis walkthrough. No live analysis is running.</span>
          </div>
          <Button onClick={handleSignup} variant="primary" size="sm">
            Sign Up Free
          </Button>
        </div>
      </div>

      <nav className="border-b border-border-default bg-bg-surface/95 backdrop-blur-md">
        <div className="mx-auto flex h-14 max-w-7xl items-center justify-between px-6 sm:px-8">
          <NoesisLogo size="sm" />
          <button
            onClick={() => navigate('/')}
            className="text-sm text-text-secondary transition-colors duration-150 hover:text-text-primary"
          >
            ← Back to Home
          </button>
        </div>
      </nav>

      <div className="mx-auto max-w-7xl px-6 py-8 sm:px-8">
        {!analysisComplete ? (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            className="flex min-h-[60vh] flex-col items-center justify-center"
          >
            <div className="space-y-4 text-center">
              <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent" />
              <h2 className="text-2xl font-semibold text-text-primary">Loading scripted analysis</h2>
              <p className="text-text-secondary">Preparing the draft, issue list, and exact manuscript jump targets.</p>
            </div>
          </motion.div>
        ) : (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            className="space-y-6"
          >
            <div className="space-y-2">
              <div className="flex items-center gap-2 text-sm text-text-muted">
                <span>Demo Project</span>
                <span>/</span>
                <span>Sepsis deployment review</span>
              </div>
              <h1 className="text-4xl font-semibold tracking-tight text-text-primary">Interactive Draft Analysis Demo</h1>
              <p className="max-w-3xl text-text-secondary">
                This page uses the same presentation layer as the landing-page showcase. The issue list, status changes, and manuscript jumps are all local-only so the interaction stays faithful without running real analysis.
              </p>
            </div>

            <DraftAnalysisShowcase />

            <div className="rounded-xl border border-accent-primary/20 bg-gradient-to-br from-accent-primary/10 to-accent-primary/5 p-8 text-center">
              <h3 className="text-2xl font-semibold text-text-primary">Want to analyze your own draft?</h3>
              <p className="mx-auto mt-3 max-w-2xl text-text-secondary">
                Sign up to build a project library, generate a Literature Map, discover missing papers, and run the full two-pass draft analysis workflow on your own manuscript.
              </p>
              <div className="mt-6 flex items-center justify-center gap-4">
                <Button onClick={handleSignup} variant="primary" size="lg" className="flex items-center gap-2">
                  Sign Up Free
                  <ArrowRightIcon className="h-5 w-5" />
                </Button>
                <button
                  onClick={() => navigate('/')}
                  className="px-6 py-3 text-text-secondary transition-colors duration-150 hover:text-text-primary"
                >
                  Learn More
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </div>

      <EmailCaptureModal
        isOpen={showEmailModal}
        onClose={() => setShowEmailModal(false)}
        onSubmit={handleEmailSubmit}
      />
    </div>
  )
}

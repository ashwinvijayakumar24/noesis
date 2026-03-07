import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { motion } from 'framer-motion'
import { ClipboardDocumentIcon, CheckIcon, UserGroupIcon, SparklesIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'

interface ReferralStats {
  referral_code: string
  total_invited: number
  total_joined: number
  credits_earned: number
}

export default function ReferralWidget() {
  const { session } = useAuthStore()
  const [stats, setStats] = useState<ReferralStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    if (session?.access_token) {
      loadReferralStats()
    }
  }, [session])

  const loadReferralStats = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      const response = await fetch('/api/referrals/stats', {
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })

      if (!response.ok) {
        throw new Error('Failed to load referral stats')
      }

      const data = await response.json()
      setStats(data)
    } catch (error) {
      console.error('Error loading referral stats:', error)
      // Gracefully handle error - don't show toast
    } finally {
      setLoading(false)
    }
  }

  const generateReferralCode = async () => {
    if (!session?.access_token) return

    try {
      const response = await fetch('/api/referrals/generate', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })

      if (!response.ok) {
        throw new Error('Failed to generate referral code')
      }

      const data = await response.json()
      setStats(data)
      toast.success('Referral code generated!')
    } catch (error) {
      console.error('Error generating referral code:', error)
      toast.error('Failed to generate referral code')
    }
  }

  const copyReferralLink = () => {
    if (!stats?.referral_code) return

    const referralLink = `${window.location.origin}/signup?ref=${stats.referral_code}`
    navigator.clipboard.writeText(referralLink)
    setCopied(true)
    toast.success('Referral link copied to clipboard!')

    setTimeout(() => setCopied(false), 2000)
  }

  if (loading) {
    return (
      <div className="bg-bg-surface border border-border-default rounded-lg p-6 animate-pulse">
        <div className="h-6 bg-bg-hover rounded w-1/3 mb-4"></div>
        <div className="h-4 bg-bg-hover rounded w-2/3"></div>
      </div>
    )
  }

  if (!stats?.referral_code) {
    return (
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        className="bg-bg-surface border border-border-default rounded-lg p-6"
      >
        <div className="flex items-start gap-4">
          <div className="shrink-0 w-12 h-12 rounded-lg bg-accent-light border border-accent-primary/30 flex items-center justify-center">
            <UserGroupIcon className="h-6 w-6 text-accent-primary" />
          </div>
          <div className="flex-1">
            <h3 className="text-lg font-sans font-semibold text-text-primary mb-2 tracking-normal">
              Invite Colleagues
            </h3>
            <p className="text-sm text-text-secondary mb-4 leading-relaxed tracking-normal">
              Share Noesis with your research colleagues and earn credits when they join.
            </p>
            <button
              onClick={generateReferralCode}
              className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover transition-all duration-150 text-sm"
            >
              Generate Referral Code
            </button>
          </div>
        </div>
      </motion.div>
    )
  }

  const referralLink = `${window.location.origin}/signup?ref=${stats.referral_code}`

  return (
    <motion.div
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      className="bg-bg-surface border border-border-default rounded-lg p-6"
    >
      {/* Header */}
      <div className="flex items-start gap-4 mb-6">
        <div className="shrink-0 w-12 h-12 rounded-lg bg-accent-light border border-accent-primary/30 flex items-center justify-center">
          <UserGroupIcon className="h-6 w-6 text-accent-primary" />
        </div>
        <div className="flex-1">
          <h3 className="text-lg font-sans font-semibold text-text-primary mb-1 tracking-normal">
            Invite Colleagues
          </h3>
          <p className="text-sm text-text-secondary tracking-normal">
            Share your unique referral code with fellow researchers
          </p>
        </div>
      </div>

      {/* Referral Code Display */}
      <div className="mb-6">
        <label className="text-xs font-mono text-text-muted mb-2 block">Your Referral Code</label>
        <div className="bg-bg-void border border-border-default rounded-md p-4 font-mono text-lg text-accent-primary text-center tracking-wider">
          {stats.referral_code}
        </div>
      </div>

      {/* Referral Link with Copy Button */}
      <div className="mb-6">
        <label className="text-xs font-mono text-text-muted mb-2 block">Referral Link</label>
        <div className="flex gap-2">
          <input
            type="text"
            value={referralLink}
            readOnly
            className="flex-1 bg-bg-void border border-border-default rounded-md px-4 py-2 text-sm text-text-secondary font-mono"
          />
          <button
            onClick={copyReferralLink}
            className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover transition-all duration-150 flex items-center gap-2"
          >
            {copied ? (
              <>
                <CheckIcon className="h-4 w-4" />
                Copied
              </>
            ) : (
              <>
                <ClipboardDocumentIcon className="h-4 w-4" />
                Copy
              </>
            )}
          </button>
        </div>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-3 gap-4">
        <div className="bg-bg-void border border-border-default rounded-md p-4 text-center">
          <div className="text-2xl font-sans font-semibold text-accent-primary mb-1">
            {stats.total_invited}
          </div>
          <div className="text-xs font-mono text-text-muted">Invited</div>
        </div>
        <div className="bg-bg-void border border-border-default rounded-md p-4 text-center">
          <div className="text-2xl font-sans font-semibold text-teal-primary mb-1">
            {stats.total_joined}
          </div>
          <div className="text-xs font-mono text-text-muted">Joined</div>
        </div>
        <div className="bg-bg-void border border-border-default rounded-md p-4 text-center">
          <div className="text-2xl font-sans font-semibold text-indigo-primary mb-1">
            {stats.credits_earned}
          </div>
          <div className="text-xs font-mono text-text-muted">Credits</div>
        </div>
      </div>

      {/* Info Message */}
      {stats.total_joined > 0 && (
        <div className="mt-4 flex items-start gap-2 text-xs text-text-tertiary bg-accent-light border border-accent-primary/20 rounded-md p-3">
          <SparklesIcon className="h-4 w-4 text-accent-primary shrink-0 mt-0.5" />
          <p className="tracking-normal">
            You've invited <span className="font-semibold text-accent-primary">{stats.total_joined}</span> colleague
            {stats.total_joined !== 1 ? 's' : ''} to Noesis. Thank you for spreading the word!
          </p>
        </div>
      )}
    </motion.div>
  )
}

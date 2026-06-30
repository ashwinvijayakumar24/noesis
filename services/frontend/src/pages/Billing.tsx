import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import toast from 'react-hot-toast'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import PageContainer from '../components/layout/PageContainer'
import { Button } from '../components/ui/Button'

interface UsageData {
  plan_tier: string
  drafts_analyzed: number
  drafts_limit: number
  documents_uploaded: number
  documents_limit: number
  bib_refs_imported: number
  bib_refs_limit: number
}

export function usagePct(used: number, limit: number): number {
  if (limit >= 9999 || limit <= 0) return 0
  return Math.min(Math.round((used / limit) * 100), 100)
}

export function planLabel(tier: string): string {
  const labels: Record<string, string> = {
    free: 'Free',
    pro: 'Pro',
    team: 'Research Group',
  }
  return labels[tier] ?? (tier.charAt(0).toUpperCase() + tier.slice(1))
}

function UsageBar({ label, used, limit }: { label: string; used: number; limit: number }) {
  const pct = usagePct(used, limit)
  const isUnlimited = limit >= 9999
  return (
    <div>
      <div className="mb-1 flex justify-between text-sm text-text-secondary">
        <span>{label}</span>
        <span>{used} / {isUnlimited ? '∞' : limit}</span>
      </div>
      <div className="h-2 rounded-full bg-bg-elevated">
        {!isUnlimited && (
          <div
            className="h-2 rounded-full bg-accent-primary transition-all"
            style={{ width: `${pct}%` }}
          />
        )}
      </div>
    </div>
  )
}

export default function Billing() {
  const { session } = useAuthStore()
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [usage, setUsage] = useState<UsageData | null>(null)
  const [loading, setLoading] = useState(true)
  const [canceling, setCanceling] = useState(false)

  const fetchUsage = (token: string) => {
    setLoading(true)
    api.subscriptions
      .getUsage(token)
      .then((data) => setUsage(data as UsageData))
      .catch(() => toast.error('Failed to load usage data.'))
      .finally(() => setLoading(false))
  }

  useEffect(() => {
    document.title = 'Billing | Noesis'
    if (searchParams.get('subscribed') === 'true') {
      toast.success("You're now subscribed to Pro!")
    }
  }, [searchParams])

  useEffect(() => {
    if (!session?.access_token) return
    fetchUsage(session.access_token)
  }, [session])

  const handleManageBilling = async () => {
    if (!session?.access_token) return
    try {
      const result = (await api.subscriptions.getPortalSession(session.access_token)) as {
        url: string
      }
      window.location.href = result.url
    } catch {
      toast.error('Failed to open billing portal.')
    }
  }

  const handleCancel = async () => {
    if (!session?.access_token) return
    if (
      !window.confirm(
        "Cancel your subscription? You'll keep access until the end of your billing period.",
      )
    )
      return
    try {
      setCanceling(true)
      await api.subscriptions.cancel(session.access_token, { cancel_immediately: false })
      toast.success('Subscription will cancel at period end.')
      fetchUsage(session.access_token)
    } catch {
      toast.error('Failed to cancel subscription.')
    } finally {
      setCanceling(false)
    }
  }

  const isPaid = usage?.plan_tier && usage.plan_tier !== 'free'

  return (
    <PageContainer title="Billing" maxWidth="2xl">
      {loading ? (
        <div className="text-text-secondary">Loading…</div>
      ) : usage ? (
        <div className="space-y-6">
          {/* Plan badge */}
          <div className="flex items-center gap-3">
            <span className="text-sm text-text-secondary">Current plan</span>
            <span className="rounded-md border border-accent-primary/30 bg-accent-light/40 px-2 py-1 text-xs font-semibold text-accent-primary">
              {planLabel(usage.plan_tier)}
            </span>
          </div>

          {/* Usage bars */}
          <div className="rounded-xl border border-border-default bg-bg-surface p-6">
            <h2 className="mb-4 text-sm font-semibold text-text-primary">Monthly Usage</h2>
            <div className="space-y-4">
              <UsageBar
                label="Draft Analyses"
                used={usage.drafts_analyzed}
                limit={usage.drafts_limit}
              />
              <UsageBar
                label="PDF Uploads"
                used={usage.documents_uploaded}
                limit={usage.documents_limit}
              />
              <UsageBar
                label="BibTeX References"
                used={usage.bib_refs_imported}
                limit={usage.bib_refs_limit}
              />
            </div>
          </div>

          {/* CTAs */}
          <div className="flex flex-col gap-3 sm:flex-row">
            {!isPaid && (
              <Button variant="primary" size="md" onClick={() => navigate('/pricing')}>
                Upgrade to Pro
              </Button>
            )}
            {isPaid && (
              <>
                <Button variant="secondary" size="md" onClick={handleManageBilling}>
                  Manage Billing
                </Button>
                <Button
                  variant="secondary"
                  size="md"
                  onClick={handleCancel}
                  disabled={canceling}
                  className="border-red-500/30 text-red-400 hover:bg-red-500/10"
                >
                  {canceling ? 'Canceling…' : 'Cancel Subscription'}
                </Button>
              </>
            )}
          </div>
        </div>
      ) : (
        <p className="text-text-secondary">No subscription data available.</p>
      )}
    </PageContainer>
  )
}

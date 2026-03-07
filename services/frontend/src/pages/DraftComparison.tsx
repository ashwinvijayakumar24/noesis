import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { motion } from 'framer-motion'
import { ArrowLeftIcon, CheckCircleIcon, XCircleIcon, ArrowTrendingUpIcon, DocumentTextIcon } from '@heroicons/react/24/outline'
import PageContainer from '../components/layout/PageContainer'
import { Badge } from '../components/ui/Badge'

interface Draft {
  id: string
  title: string
  version: number
  created_at: string
}

interface Narrative {
  evolution_summary?: string
  key_improvements?: string[]
  remaining_gaps?: string[]
  reviewer_readiness?: 'not_ready' | 'partially_ready' | 'ready'
}

interface FeedbackTracked {
  feedback_text: string
  severity: string
  section_reference?: string
  resolution_status: 'resolved' | 'still_pending' | 'partially_addressed' | 'new_issue'
}

interface ComparisonData {
  comparison_id?: string
  improvement_score: number
  claims_added: number
  claims_improved: number
  claims_removed?: number
  gaps_resolved: number
  feedback_addressed: number
  feedback_tracked?: FeedbackTracked[]
  narrative?: Narrative
  word_count_v1?: number
  word_count_v2?: number
  changes?: ComparisonChange[]
  summary?: string
}

interface ComparisonChange {
  type: 'claim_added' | 'claim_improved' | 'claim_removed' | 'gap_resolved' | 'feedback_addressed'
  title: string
  description: string
  section?: string
  severity?: 'low' | 'medium' | 'high'
}

export default function DraftComparison() {
  const { projectId, draftV1Id, draftV2Id } = useParams<{
    projectId: string
    draftV1Id: string
    draftV2Id: string
  }>()
  const navigate = useNavigate()
  const { session } = useAuthStore()

  const [loading, setLoading] = useState(true)
  const [draftV1, setDraftV1] = useState<Draft | null>(null)
  const [draftV2, setDraftV2] = useState<Draft | null>(null)
  const [comparison, setComparison] = useState<ComparisonData | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (session?.access_token && projectId && draftV1Id && draftV2Id) {
      loadComparison()
    }
  }, [projectId, draftV1Id, draftV2Id, session])

  const loadComparison = async () => {
    if (!session?.access_token || !projectId || !draftV1Id || !draftV2Id) return

    try {
      setLoading(true)
      setError(null)

      // Load both drafts metadata
      const [draft1, draft2] = await Promise.all([
        api.drafts.get(session.access_token, draftV1Id),
        api.drafts.get(session.access_token, draftV2Id)
      ])

      setDraftV1(draft1)
      setDraftV2(draft2)

      // Load comparison data
      const comparisonData = await api.drafts.compare(
        session.access_token,
        projectId,
        draftV1Id,
        draftV2Id
      )

      setComparison(comparisonData)
    } catch (error: any) {
      console.error('Failed to load comparison:', error)
      setError(error.message || 'Failed to load comparison')
      toast.error('Failed to load comparison')
    } finally {
      setLoading(false)
    }
  }

  const getScoreColor = (score: number): string => {
    if (score >= 75) return 'text-teal-primary border-teal-primary/30 bg-teal-light'
    if (score >= 50) return 'text-amber-primary border-amber-primary/30 bg-amber-light'
    return 'text-ruby-primary border-ruby-primary/30 bg-ruby-light'
  }

  const getChangeIcon = (type: string) => {
    switch (type) {
      case 'claim_added':
      case 'claim_improved':
      case 'gap_resolved':
      case 'feedback_addressed':
        return <CheckCircleIcon className="h-5 w-5 text-teal-primary" />
      case 'claim_removed':
        return <XCircleIcon className="h-5 w-5 text-ruby-primary" />
      default:
        return null
    }
  }

  const getChangeBgColor = (type: string): string => {
    switch (type) {
      case 'claim_added':
      case 'claim_improved':
        return 'bg-teal-light border-teal-primary/30'
      case 'claim_removed':
        return 'bg-ruby-primary/10 border-ruby-primary/20'
      case 'gap_resolved':
      case 'feedback_addressed':
        return 'bg-indigo-primary/10 border-indigo-primary/20'
      default:
        return 'bg-bg-elevated border-border-default'
    }
  }

  const getChangeLabel = (type: string): string => {
    switch (type) {
      case 'claim_added':
        return 'Claim Added'
      case 'claim_improved':
        return 'Claim Improved'
      case 'claim_removed':
        return 'Claim Removed'
      case 'gap_resolved':
        return 'Gap Resolved'
      case 'feedback_addressed':
        return 'Feedback Addressed'
      default:
        return type
    }
  }

  if (loading) {
    return (
      <PageContainer
        breadcrumbs={[
          { label: 'Projects', href: '/projects' },
          { label: 'Project', href: `/projects/${projectId}` },
          { label: 'Compare Drafts' }
        ]}
        backLink={`/projects/${projectId}`}
        backLabel="Back to Project"
      >
        <div className="flex items-center justify-center py-20">
          <div className="text-center">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
            <p className="mt-4 text-text-tertiary">Loading comparison...</p>
          </div>
        </div>
      </PageContainer>
    )
  }

  if (error || !comparison || !draftV1 || !draftV2) {
    return (
      <PageContainer
        breadcrumbs={[
          { label: 'Projects', href: '/projects' },
          { label: 'Project', href: `/projects/${projectId}` },
          { label: 'Compare Drafts' }
        ]}
        backLink={`/projects/${projectId}`}
        backLabel="Back to Project"
      >
        <div className="text-center py-20">
          <XCircleIcon className="h-16 w-16 text-ruby-primary mx-auto mb-4" />
          <h3 className="text-xl font-semibold text-text-primary mb-2">Failed to Load Comparison</h3>
          <p className="text-text-secondary mb-6">{error || 'Could not load draft comparison data'}</p>
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
          >
            <ArrowLeftIcon className="h-5 w-5 inline mr-2" />
            Back to Project
          </button>
        </div>
      </PageContainer>
    )
  }

  return (
    <PageContainer
      breadcrumbs={[
        { label: 'Projects', href: '/projects' },
        { label: 'Project', href: `/projects/${projectId}` },
        { label: 'Compare Drafts' }
      ]}
      backLink={`/projects/${projectId}`}
      backLabel="Back to Project"
    >
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
      >
        {/* Header */}
        <div className="mb-8">
          <h1 className="text-3xl font-sans font-semibold text-text-primary mb-2">
            Draft Version Comparison
          </h1>
          <p className="text-text-secondary">
            Comparing improvements from v{draftV1.version} to v{draftV2.version}
          </p>
        </div>

        {/* Draft Headers - Side by Side */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-8">
          {/* Draft V1 */}
          <div className="bg-bg-surface border border-border-default rounded-lg p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-lg border-2 border-text-tertiary bg-bg-void flex items-center justify-center">
                  <DocumentTextIcon className="h-5 w-5 text-text-tertiary" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-text-primary mb-1">{draftV1.title}</h3>
                <p className="text-sm text-text-muted font-mono">Version {draftV1.version}</p>
              </div>
            </div>
            <div className="text-sm text-text-secondary">
              <p>Created: {new Date(draftV1.created_at).toLocaleDateString('en-US', {
                month: 'long',
                day: 'numeric',
                year: 'numeric'
              })}</p>
              {comparison.word_count_v1 != null && <p className="mt-1 font-mono">{comparison.word_count_v1.toLocaleString()} words</p>}
            </div>
          </div>

          {/* Draft V2 */}
          <div className="bg-bg-surface border-2 border-accent-primary rounded-lg p-6">
            <div className="flex items-start gap-3 mb-4">
              <div className="flex-shrink-0">
                <div className="w-10 h-10 rounded-lg border-2 border-accent-primary bg-accent-light flex items-center justify-center">
                  <DocumentTextIcon className="h-5 w-5 text-accent-primary" />
                </div>
              </div>
              <div className="flex-1">
                <h3 className="text-lg font-semibold text-text-primary mb-1">{draftV2.title}</h3>
                <p className="text-sm text-accent-primary font-mono">Version {draftV2.version} (Latest)</p>
              </div>
            </div>
            <div className="text-sm text-text-secondary">
              <p>Created: {new Date(draftV2.created_at).toLocaleDateString('en-US', {
                month: 'long',
                day: 'numeric',
                year: 'numeric'
              })}</p>
              {comparison.word_count_v2 != null && <p className="mt-1 font-mono">{comparison.word_count_v2.toLocaleString()} words</p>}
            </div>
          </div>
        </div>

        {/* Improvement Score */}
        <div className="bg-bg-surface border border-border-default rounded-lg p-8 mb-8">
          <div className="flex items-center justify-between mb-6">
            <div>
              <h3 className="text-xl font-semibold text-text-primary mb-1">Overall Improvement</h3>
              <p className="text-sm text-text-secondary">
                Comprehensive analysis of changes between versions
              </p>
            </div>
            <div className="text-center">
              <div className={`inline-flex items-center gap-2 px-6 py-3 text-3xl font-semibold rounded-lg border-2 ${getScoreColor(comparison.improvement_score)}`}>
                <ArrowTrendingUpIcon className="h-8 w-8" />
                {comparison.improvement_score}
                <span className="text-xl font-medium">/100</span>
              </div>
            </div>
          </div>

          {/* Summary Stats */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div className="bg-bg-base border border-border-default rounded-lg p-4">
              <div className="text-sm text-text-muted mb-1">Claims Improved</div>
              <div className="text-2xl font-semibold text-teal-primary">{comparison.claims_improved}</div>
            </div>
            <div className="bg-bg-base border border-border-default rounded-lg p-4">
              <div className="text-sm text-text-muted mb-1">Issues Addressed</div>
              <div className="text-2xl font-semibold text-indigo-primary">{comparison.feedback_addressed}</div>
            </div>
            <div className="bg-bg-base border border-border-default rounded-lg p-4">
              <div className="text-sm text-text-muted mb-1">Gaps Resolved</div>
              <div className="text-2xl font-semibold text-teal-primary">{comparison.gaps_resolved}</div>
            </div>
            <div className="bg-bg-base border border-border-default rounded-lg p-4">
              <div className="text-sm text-text-muted mb-1">Claims Added</div>
              <div className="text-2xl font-semibold text-accent-primary">{comparison.claims_added}</div>
            </div>
          </div>
        </div>

        {/* AI Narrative */}
        {comparison.narrative && (
          <div className="bg-bg-surface border border-border-default rounded-xl p-6 mb-6">
            <div className="flex items-start justify-between mb-3">
              <h3 className="text-lg font-semibold text-text-primary">Analysis Narrative</h3>
              {comparison.narrative.reviewer_readiness && (
                <span className={`text-xs font-semibold px-2.5 py-1 rounded-lg border ${
                  comparison.narrative.reviewer_readiness === 'ready'
                    ? 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30'
                    : comparison.narrative.reviewer_readiness === 'partially_ready'
                    ? 'text-amber-400 bg-amber-400/10 border-amber-400/30'
                    : 'text-red-400 bg-red-400/10 border-red-400/30'
                }`}>
                  {{
                    ready: 'Reviewer Ready',
                    partially_ready: 'Partially Ready',
                    not_ready: 'Not Ready'
                  }[comparison.narrative.reviewer_readiness]}
                </span>
              )}
            </div>
            {comparison.narrative.evolution_summary && (
              <p className="text-sm text-text-secondary leading-relaxed mb-4">{comparison.narrative.evolution_summary}</p>
            )}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {comparison.narrative.key_improvements && comparison.narrative.key_improvements.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-emerald-400 uppercase tracking-wide mb-2">Key Improvements</p>
                  <ul className="space-y-1.5">
                    {comparison.narrative.key_improvements.map((item, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                        <CheckCircleIcon className="h-4 w-4 text-emerald-400 shrink-0 mt-0.5" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              {comparison.narrative.remaining_gaps && comparison.narrative.remaining_gaps.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-amber-400 uppercase tracking-wide mb-2">Still Needs Work</p>
                  <ul className="space-y-1.5">
                    {comparison.narrative.remaining_gaps.map((item, i) => (
                      <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                        <XCircleIcon className="h-4 w-4 text-amber-400 shrink-0 mt-0.5" />
                        {item}
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Feedback Resolution Tracking */}
        {comparison.feedback_tracked && comparison.feedback_tracked.length > 0 && (
          <div className="bg-bg-surface border border-border-default rounded-xl p-6 mb-6">
            <h3 className="text-lg font-semibold text-text-primary mb-4">Feedback Resolution</h3>
            <div className="space-y-2">
              {comparison.feedback_tracked.map((item, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-bg-base border border-border-default">
                  <span className={`shrink-0 text-sm font-bold mt-0.5 ${
                    item.resolution_status === 'resolved' ? 'text-emerald-400' : 'text-amber-400'
                  }`}>
                    {item.resolution_status === 'resolved' ? '✓' : '○'}
                  </span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm text-text-secondary leading-snug">{item.feedback_text}</p>
                    {item.section_reference && (
                      <span className="text-xs text-text-tertiary font-mono mt-0.5 block">{item.section_reference}</span>
                    )}
                  </div>
                  <Badge variant={item.resolution_status === 'resolved' ? 'success' : 'warning'}>
                    {item.resolution_status === 'resolved' ? 'Resolved' : 'Pending'}
                  </Badge>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Detailed Changes (legacy / fallback) */}
        {comparison.changes && comparison.changes.length > 0 && (
        <div className="bg-bg-surface border border-border-default rounded-lg p-6">
          <h3 className="text-xl font-semibold text-text-primary mb-4">Detailed Changes</h3>
            <div className="space-y-3">
              {comparison.changes.map((change, index) => (
                <motion.div
                  key={index}
                  initial={{ opacity: 0, x: -20 }}
                  animate={{ opacity: 1, x: 0 }}
                  transition={{ delay: index * 0.05, duration: 0.3 }}
                  className={`border rounded-lg p-4 ${getChangeBgColor(change.type)}`}
                >
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 mt-0.5">
                      {getChangeIcon(change.type)}
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-2">
                        <Badge variant={
                          change.type === 'claim_added' || change.type === 'claim_improved' ? 'success' :
                          change.type === 'claim_removed' ? 'error' : 'info'
                        }>
                          {getChangeLabel(change.type)}
                        </Badge>
                        {change.section && (
                          <span className="text-xs font-mono text-text-muted">{change.section}</span>
                        )}
                        {change.severity && (
                          <Badge variant={
                            change.severity === 'high' ? 'error' :
                            change.severity === 'medium' ? 'warning' : 'neutral'
                          }>
                            {change.severity}
                          </Badge>
                        )}
                      </div>
                      <h4 className="font-semibold text-text-primary mb-1">{change.title}</h4>
                      <p className="text-sm text-text-secondary leading-relaxed">{change.description}</p>
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
        </div>
        )}

        {/* Action Buttons */}
        <div className="flex items-center gap-4 mt-8">
          <button
            onClick={() => navigate(`/projects/${projectId}/drafts/${draftV1Id}`)}
            className="px-6 py-3 bg-bg-surface border border-border-default text-text-primary font-semibold rounded-lg hover:bg-bg-hover hover:border-accent-primary/30 transition-all"
          >
            View v{draftV1.version}
          </button>
          <button
            onClick={() => navigate(`/projects/${projectId}/drafts/${draftV2Id}`)}
            className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
          >
            View v{draftV2.version}
          </button>
        </div>
      </motion.div>
    </PageContainer>
  )
}

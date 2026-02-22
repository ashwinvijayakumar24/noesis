import { useMemo } from 'react'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ExclamationCircleIcon,
  DocumentTextIcon,
  BeakerIcon,
  ChatBubbleLeftRightIcon,
  ClockIcon
} from '@heroicons/react/24/outline'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  requires_citation: boolean
  existing_citations: string[]
}

interface Gap {
  id: string
  gap_type: string
  priority: string
}

interface Feedback {
  id: string
  severity: string
  feedback_type: string
}

interface DraftHealthSummaryProps {
  draft: {
    id: string
    title: string
    version: number
    updated_at: string
  }
  claims: Claim[]
  gaps: Gap[]
  feedback: Feedback[]
  addressedItems: string[]
  onReanalyze?: () => void  // Optional - no longer used (re-analyze removed)
  isReanalyzing?: boolean
}

export default function DraftHealthSummary({
  draft,
  claims,
  gaps,
  feedback,
  addressedItems,
  onReanalyze,
  isReanalyzing = false
}: DraftHealthSummaryProps) {
  // Calculate metrics
  const metrics = useMemo(() => {
    const claimsNeedingCitation = claims.filter(
      c => c.requires_citation && (!c.existing_citations || c.existing_citations.length === 0)
    ).length

    const criticalGaps = gaps.filter(g => g.priority === 'critical' || g.priority === 'high').length
    const criticalFeedback = feedback.filter(f => f.severity === 'critical').length
    const majorFeedback = feedback.filter(f => f.severity === 'major').length

    // Calculate total action items
    const totalActionItems = claimsNeedingCitation + gaps.length + feedback.filter(f =>
      f.severity === 'critical' || f.severity === 'major'
    ).length

    // Calculate addressed count
    const addressedCount = addressedItems.length

    // Calculate progress percentage
    const progressPercent = totalActionItems > 0
      ? Math.round((addressedCount / totalActionItems) * 100)
      : 100

    // Calculate health score (0-100)
    let healthScore = 100
    healthScore -= claimsNeedingCitation * 5
    healthScore -= criticalGaps * 15
    healthScore -= criticalFeedback * 10
    healthScore -= majorFeedback * 5
    // Bonus for addressed items
    healthScore += addressedCount * 3
    healthScore = Math.max(0, Math.min(100, healthScore))

    const healthStatus: 'good' | 'needs_work' | 'critical' =
      healthScore >= 70 ? 'good' :
      healthScore >= 40 ? 'needs_work' : 'critical'

    return {
      claims_count: claims.length,
      claims_needing_citation: claimsNeedingCitation,
      gaps_count: gaps.length,
      critical_gaps: criticalGaps,
      feedback_count: feedback.length,
      critical_feedback: criticalFeedback,
      major_feedback: majorFeedback,
      total_action_items: totalActionItems,
      addressed_count: addressedCount,
      progress_percent: progressPercent,
      health_score: healthScore,
      health_status: healthStatus
    }
  }, [claims, gaps, feedback, addressedItems])

  // Health status display config (neon-brutalist aesthetic)
  const healthConfig = {
    good: {
      borderColor: 'border-success/60',
      gradientFrom: 'from-bg-surface',
      gradientTo: 'to-bg-elevated',
      accentColor: 'text-success',
      icon: <CheckCircleIcon className="h-16 w-16" />,
      label: 'Good Health',
      progressGradient: 'linear-gradient(90deg, #00d9ff 0%, #00d9ff 100%)' // Teal
    },
    needs_work: {
      borderColor: 'border-warning/60',
      gradientFrom: 'from-bg-surface',
      gradientTo: 'to-bg-elevated',
      accentColor: 'text-warning',
      icon: <ExclamationTriangleIcon className="h-16 w-16" />,
      label: 'Needs Work',
      progressGradient: 'linear-gradient(90deg, #F59E0B 0%, #00d9ff 100%)' // Orange to teal
    },
    critical: {
      borderColor: 'border-error/60',
      gradientFrom: 'from-bg-surface',
      gradientTo: 'to-bg-elevated',
      accentColor: 'text-error',
      icon: <ExclamationCircleIcon className="h-16 w-16" />,
      label: 'Critical Issues',
      progressGradient: 'linear-gradient(90deg, #FF1F4C 0%, #F59E0B 100%)' // Pink to orange
    }
  }

  const config = healthConfig[metrics.health_status]

  // Calculate time since last analysis
  const timeSinceAnalysis = useMemo(() => {
    const now = new Date()
    const updated = new Date(draft.updated_at)
    const diffMs = now.getTime() - updated.getTime()
    const diffHours = Math.floor(diffMs / (1000 * 60 * 60))
    const diffDays = Math.floor(diffHours / 24)

    if (diffDays > 0) return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
    if (diffHours > 0) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
    return 'Just now'
  }, [draft.updated_at])

  return (
    <div className={`bg-gradient-to-br ${config.gradientFrom} ${config.gradientTo} rounded-2xl border-2 ${config.borderColor} p-8 mb-6 transition-all duration-300`}>
      {/* Header Row - Health Icon + Score */}
      <div className="flex items-start justify-between mb-8">
        <div className="flex items-center gap-6">
          {/* Large animated icon */}
          <div className={`${config.accentColor} transition-transform duration-300 hover:scale-110`}>
            {config.icon}
          </div>

          {/* Health Score Display */}
          <div>
            <div className="flex items-baseline gap-3 mb-2">
              <h2 className={`font-display font-extrabold text-7xl ${config.accentColor} tracking-tighter`}>
                {metrics.health_score}%
              </h2>
              <span className="text-2xl font-display font-semibold text-text-secondary">
                {config.label}
              </span>
            </div>
            <h3 className="text-xl font-display font-semibold text-text-primary">
              {draft.title}
              {draft.version > 1 && (
                <span className="ml-3 text-sm text-text-muted font-mono">v{draft.version}</span>
              )}
            </h3>
          </div>
        </div>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-3 sm:grid-cols-6 gap-4 mb-6">
        {/* Total Claims */}
        <div className="bg-bg-elevated/50 rounded-xl p-4 border border-border-base">
          <div className="flex items-center gap-2 mb-2">
            <DocumentTextIcon className="h-5 w-5 text-accent-teal" />
            <span className="text-xs text-text-muted font-mono uppercase tracking-wide">Claims</span>
          </div>
          <p className="text-3xl font-display font-bold text-text-primary mb-1">{metrics.claims_count}</p>
          {metrics.claims_needing_citation > 0 && (
            <p className="text-xs text-warning font-medium">{metrics.claims_needing_citation} need citation</p>
          )}
        </div>

        {/* Coverage Gaps */}
        <div className="bg-bg-elevated/50 rounded-xl p-4 border border-border-base">
          <div className="flex items-center gap-2 mb-2">
            <BeakerIcon className="h-5 w-5 text-accent-purple" />
            <span className="text-xs text-text-muted font-mono uppercase tracking-wide">Gaps</span>
          </div>
          <p className="text-3xl font-display font-bold text-text-primary mb-1">{metrics.gaps_count}</p>
          {metrics.critical_gaps > 0 && (
            <p className="text-xs text-error font-medium">{metrics.critical_gaps} critical</p>
          )}
        </div>

        {/* Feedback */}
        <div className="bg-bg-elevated/50 rounded-xl p-4 border border-border-base">
          <div className="flex items-center gap-2 mb-2">
            <ChatBubbleLeftRightIcon className="h-5 w-5 text-neon-pink" />
            <span className="text-xs text-text-muted font-mono uppercase tracking-wide">Feedback</span>
          </div>
          <p className="text-3xl font-display font-bold text-text-primary mb-1">{metrics.feedback_count}</p>
          {metrics.critical_feedback > 0 && (
            <p className="text-xs text-error font-medium">{metrics.critical_feedback} critical</p>
          )}
        </div>

        {/* Progress */}
        <div className="bg-bg-elevated/50 rounded-xl p-4 border border-border-base">
          <div className="flex items-center gap-2 mb-2">
            <CheckCircleIcon className="h-5 w-5 text-success" />
            <span className="text-xs text-text-muted font-mono uppercase tracking-wide">Progress</span>
          </div>
          <p className="text-3xl font-display font-bold text-text-primary mb-1">{metrics.progress_percent}%</p>
          <p className="text-xs text-text-secondary font-medium">{metrics.addressed_count}/{metrics.total_action_items} done</p>
        </div>

        {/* Total Action Items */}
        <div className="bg-bg-elevated/50 rounded-xl p-4 border border-border-base">
          <div className="flex items-center gap-2 mb-2">
            <ExclamationTriangleIcon className="h-5 w-5 text-warning" />
            <span className="text-xs text-text-muted font-mono uppercase tracking-wide">Actions</span>
          </div>
          <p className="text-3xl font-display font-bold text-text-primary mb-1">{metrics.total_action_items}</p>
          <p className="text-xs text-text-secondary font-medium">Total items</p>
        </div>

        {/* Last Analyzed */}
        <div className="bg-bg-elevated/50 rounded-xl p-4 border border-border-base">
          <div className="flex items-center gap-2 mb-2">
            <ClockIcon className="h-5 w-5 text-text-muted" />
            <span className="text-xs text-text-muted font-mono uppercase tracking-wide">Analyzed</span>
          </div>
          <p className="text-xl font-display font-bold text-text-primary mb-1">{timeSinceAnalysis}</p>
          <p className="text-xs text-text-secondary font-medium">Last update</p>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="bg-bg-elevated/30 rounded-xl p-4 border border-border-base">
        <div className="flex items-center justify-between mb-3">
          <span className="text-sm font-display font-semibold text-text-primary">Action Items Progress</span>
          <span className="text-sm font-mono font-bold text-neon-pink">
            {metrics.addressed_count} of {metrics.total_action_items} addressed
          </span>
        </div>
        <div className="h-3 bg-bg-void rounded-full overflow-hidden border border-border-base">
          <div
            className="h-full transition-all duration-500 ease-out"
            style={{
              width: `${metrics.progress_percent}%`,
              background: config.progressGradient
            }}
          />
        </div>
      </div>
    </div>
  )
}

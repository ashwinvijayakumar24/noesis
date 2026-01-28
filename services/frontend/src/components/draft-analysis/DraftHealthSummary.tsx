import { useMemo } from 'react'
import {
  CheckCircleIcon,
  ExclamationTriangleIcon,
  ExclamationCircleIcon,
  DocumentTextIcon,
  BeakerIcon,
  ChatBubbleLeftRightIcon,
  ArrowPathIcon,
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
  onReanalyze: () => void
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

  // Health status display config
  const healthConfig = {
    good: {
      bgColor: 'bg-emerald-900/20',
      borderColor: 'border-emerald-600/50',
      textColor: 'text-emerald-400',
      icon: <CheckCircleIcon className="h-8 w-8" />,
      label: 'Good Health'
    },
    needs_work: {
      bgColor: 'bg-amber-900/20',
      borderColor: 'border-amber-600/50',
      textColor: 'text-amber-400',
      icon: <ExclamationTriangleIcon className="h-8 w-8" />,
      label: 'Needs Work'
    },
    critical: {
      bgColor: 'bg-red-900/20',
      borderColor: 'border-red-600/50',
      textColor: 'text-red-400',
      icon: <ExclamationCircleIcon className="h-8 w-8" />,
      label: 'Critical Issues'
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
    <div className={`rounded-lg border ${config.borderColor} ${config.bgColor} p-4 mb-6`}>
      {/* Header Row */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-3">
          <span className={config.textColor}>{config.icon}</span>
          <div>
            <h2 className="text-lg font-serif font-semibold text-text-primary">
              {draft.title}
              {draft.version > 1 && (
                <span className="ml-2 text-sm text-text-muted font-mono">v{draft.version}</span>
              )}
            </h2>
            <p className={`text-sm ${config.textColor} font-medium`}>
              {config.label} • {metrics.health_score}%
            </p>
          </div>
        </div>
        <button
          onClick={onReanalyze}
          disabled={isReanalyzing}
          className="flex items-center gap-2 px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary bg-surface hover:bg-surface-hover rounded-lg border border-border-subtle transition-colors disabled:opacity-50"
        >
          <ArrowPathIcon className={`h-4 w-4 ${isReanalyzing ? 'animate-spin' : ''}`} />
          {isReanalyzing ? 'Analyzing...' : 'Re-analyze'}
        </button>
      </div>

      {/* Metrics Grid */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Overall Health */}
        <div className="bg-surface/50 rounded-lg p-3 border border-border-subtle">
          <div className="flex items-center gap-2 mb-1">
            <span className={config.textColor}>
              {metrics.health_status === 'good' ? (
                <CheckCircleIcon className="h-4 w-4" />
              ) : metrics.health_status === 'needs_work' ? (
                <ExclamationTriangleIcon className="h-4 w-4" />
              ) : (
                <ExclamationCircleIcon className="h-4 w-4" />
              )}
            </span>
            <span className="text-xs text-text-muted font-mono">Overall</span>
          </div>
          <p className={`text-2xl font-bold ${config.textColor}`}>{metrics.health_score}%</p>
          <p className="text-xs text-text-muted">{config.label}</p>
        </div>

        {/* Claims */}
        <div className="bg-surface/50 rounded-lg p-3 border border-border-subtle">
          <div className="flex items-center gap-2 mb-1">
            <DocumentTextIcon className="h-4 w-4 text-text-muted" />
            <span className="text-xs text-text-muted font-mono">Claims</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{metrics.claims_count}</p>
          {metrics.claims_needing_citation > 0 && (
            <p className="text-xs text-amber-500">{metrics.claims_needing_citation} need citation</p>
          )}
        </div>

        {/* Coverage Gaps */}
        <div className="bg-surface/50 rounded-lg p-3 border border-border-subtle">
          <div className="flex items-center gap-2 mb-1">
            <BeakerIcon className="h-4 w-4 text-text-muted" />
            <span className="text-xs text-text-muted font-mono">Gaps</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{metrics.gaps_count}</p>
          {metrics.critical_gaps > 0 && (
            <p className="text-xs text-red-400">{metrics.critical_gaps} critical</p>
          )}
        </div>

        {/* Feedback */}
        <div className="bg-surface/50 rounded-lg p-3 border border-border-subtle">
          <div className="flex items-center gap-2 mb-1">
            <ChatBubbleLeftRightIcon className="h-4 w-4 text-text-muted" />
            <span className="text-xs text-text-muted font-mono">Feedback</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{metrics.feedback_count}</p>
          {metrics.critical_feedback > 0 && (
            <p className="text-xs text-red-400">{metrics.critical_feedback} critical</p>
          )}
        </div>

        {/* Progress */}
        <div className="bg-surface/50 rounded-lg p-3 border border-border-subtle">
          <div className="flex items-center gap-2 mb-1">
            <CheckCircleIcon className="h-4 w-4 text-text-muted" />
            <span className="text-xs text-text-muted font-mono">Progress</span>
          </div>
          <p className="text-2xl font-bold text-text-primary">{metrics.progress_percent}%</p>
          <p className="text-xs text-text-muted">{metrics.addressed_count}/{metrics.total_action_items} done</p>
        </div>

        {/* Last Analyzed */}
        <div className="bg-surface/50 rounded-lg p-3 border border-border-subtle">
          <div className="flex items-center gap-2 mb-1">
            <ClockIcon className="h-4 w-4 text-text-muted" />
            <span className="text-xs text-text-muted font-mono">Analyzed</span>
          </div>
          <p className="text-lg font-semibold text-text-primary">{timeSinceAnalysis}</p>
          <p className="text-xs text-text-muted">Last update</p>
        </div>
      </div>

      {/* Progress Bar */}
      <div className="mt-4">
        <div className="flex items-center justify-between mb-1">
          <span className="text-xs text-text-muted">Action Items Progress</span>
          <span className="text-xs text-text-secondary font-mono">
            {metrics.addressed_count} of {metrics.total_action_items} addressed
          </span>
        </div>
        <div className="h-2 bg-surface rounded-full overflow-hidden">
          <div
            className={`h-full transition-all duration-500 ${
              metrics.progress_percent >= 70 ? 'bg-emerald-500' :
              metrics.progress_percent >= 40 ? 'bg-amber-500' : 'bg-red-500'
            }`}
            style={{ width: `${metrics.progress_percent}%` }}
          />
        </div>
      </div>
    </div>
  )
}

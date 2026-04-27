import { useState } from 'react'
import { ChevronDownIcon, ChevronUpIcon, ArrowsRightLeftIcon } from '@heroicons/react/24/outline'
import { useNavigate } from 'react-router-dom'

interface FeedbackTracked {
  feedback_text: string
  severity: string
  section_reference?: string
  resolution_status: 'resolved' | 'still_pending' | 'partially_addressed' | 'new_issue'
}

interface Narrative {
  evolution_summary?: string
  key_improvements?: string[]
  remaining_gaps?: string[]
  reviewer_readiness?: 'not_ready' | 'partially_ready' | 'ready'
}

interface VersionProgressCardProps {
  projectId: string
  comparisonId?: string
  improvementScore: number
  previousScore?: number
  feedbackTracked: FeedbackTracked[]
  narrative?: Narrative
  v1Id: string
  v2Id: string
}

const readinessColors = {
  not_ready: 'text-red-400 bg-red-400/10 border-red-400/30',
  partially_ready: 'text-amber-400 bg-amber-400/10 border-amber-400/30',
  ready: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30',
}

const readinessLabels = {
  not_ready: 'Not Ready',
  partially_ready: 'Partially Ready',
  ready: 'Reviewer Ready',
}

const resolutionConfig = {
  resolved: {
    label: 'Resolved',
    marker: '✓',
    markerClass: 'text-emerald-400',
    badgeClass: 'border-emerald-400/20 bg-emerald-400/10 text-emerald-400',
  },
  still_pending: {
    label: 'Carryover',
    marker: '○',
    markerClass: 'text-amber-400',
    badgeClass: 'border-amber-400/20 bg-amber-400/10 text-amber-400',
  },
  partially_addressed: {
    label: 'Partially Addressed',
    marker: '△',
    markerClass: 'text-accent-primary',
    badgeClass: 'border-accent-primary/20 bg-accent-primary/10 text-accent-primary',
  },
  new_issue: {
    label: 'New in v2',
    marker: '+',
    markerClass: 'text-text-secondary',
    badgeClass: 'border-border-default bg-bg-elevated text-text-secondary',
  },
}

export default function VersionProgressCard({
  projectId,
  improvementScore,
  previousScore,
  feedbackTracked,
  narrative,
  v1Id,
  v2Id,
}: VersionProgressCardProps) {
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()

  const scoreDelta = previousScore !== undefined ? improvementScore - previousScore : null
  const resolved = feedbackTracked.filter((item) => item.resolution_status === 'resolved').length
  const carryover = feedbackTracked.filter((item) => (
    item.resolution_status === 'still_pending' || item.resolution_status === 'partially_addressed'
  )).length
  const readiness = narrative?.reviewer_readiness ?? 'partially_ready'
  const canNavigate = Boolean(v1Id && v2Id)

  return (
    <div className="bg-bg-surface border border-border-default rounded-xl mb-3 overflow-hidden">
      <button
        onClick={() => setExpanded((value) => !value)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-3">
          <ArrowsRightLeftIcon className="h-4 w-4 text-text-tertiary shrink-0" />
          <span className="text-sm font-semibold text-text-primary">Changes from Previous Version</span>
          {scoreDelta !== null && (
            <span className={`text-xs font-semibold px-1.5 py-0.5 rounded ${scoreDelta >= 0 ? 'text-emerald-400 bg-emerald-400/10' : 'text-red-400 bg-red-400/10'}`}>
              {scoreDelta >= 0 ? '+' : ''}{scoreDelta} pts
            </span>
          )}
        </div>
        <div className="flex items-center gap-3">
          <div className="hidden sm:flex items-center gap-2 text-xs text-text-tertiary">
            <span className="text-emerald-400">{resolved} resolved</span>
            <span>·</span>
            <span className="text-amber-400">{carryover} carryover</span>
          </div>
          {expanded ? (
            <ChevronUpIcon className="h-4 w-4 text-text-tertiary" />
          ) : (
            <ChevronDownIcon className="h-4 w-4 text-text-tertiary" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="border-t border-border-default px-4 pb-4 pt-3 space-y-3">
          {narrative && (
            <>
              {narrative.reviewer_readiness && (
                <div className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg border text-xs font-semibold ${readinessColors[readiness]}`}>
                  {readinessLabels[readiness]}
                </div>
              )}
              {narrative.evolution_summary && (
                <p className="text-sm text-text-secondary leading-relaxed">{narrative.evolution_summary}</p>
              )}
            </>
          )}

          {feedbackTracked.length > 0 && (
            <div className="space-y-2">
              {feedbackTracked.slice(0, 6).map((item, index) => {
                const config = resolutionConfig[item.resolution_status] || resolutionConfig.still_pending
                return (
                  <div key={index} className="rounded-lg border border-border-default bg-bg-elevated p-3">
                    <div className="flex items-start gap-2">
                      <span className={`shrink-0 mt-0.5 font-semibold ${config.markerClass}`}>
                        {config.marker}
                      </span>
                      <div className="min-w-0 flex-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span className={`rounded-lg border px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide ${config.badgeClass}`}>
                            {config.label}
                          </span>
                          {item.section_reference && (
                            <span className="text-[11px] text-text-muted">{item.section_reference}</span>
                          )}
                        </div>
                        <p className="mt-2 text-xs text-text-tertiary leading-snug line-clamp-2">
                          {item.feedback_text}
                        </p>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}

          {canNavigate && (
            <button
              onClick={() => navigate(`/projects/${projectId}/compare/${v1Id}/${v2Id}`)}
              className="min-h-11 text-xs text-accent-primary hover:text-accent-primary/80 transition-colors font-medium"
            >
              View full comparison →
            </button>
          )}
        </div>
      )}
    </div>
  )
}

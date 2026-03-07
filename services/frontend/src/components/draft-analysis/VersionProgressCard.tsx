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
  comparisonId: string
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
  ready: 'text-emerald-400 bg-emerald-400/10 border-emerald-400/30'
}

const readinessLabels = {
  not_ready: 'Not Ready',
  partially_ready: 'Partially Ready',
  ready: 'Reviewer Ready'
}

export default function VersionProgressCard({
  projectId,
  comparisonId,
  improvementScore,
  previousScore,
  feedbackTracked,
  narrative,
  v1Id,
  v2Id
}: VersionProgressCardProps) {
  const [expanded, setExpanded] = useState(false)
  const navigate = useNavigate()

  const scoreDelta = previousScore !== undefined ? improvementScore - previousScore : null
  const resolved = feedbackTracked.filter(f => f.resolution_status === 'resolved').length
  const pending = feedbackTracked.filter(f => f.resolution_status === 'still_pending').length
  const readiness = narrative?.reviewer_readiness ?? 'partially_ready'

  return (
    <div className="bg-bg-surface border border-border-default rounded-xl mb-3 overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(e => !e)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-white/[0.02] transition-colors"
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
          <div className="flex items-center gap-2 text-xs text-text-tertiary">
            <span className="text-emerald-400">{resolved} resolved</span>
            <span>·</span>
            <span className="text-amber-400">{pending} pending</span>
          </div>
          {expanded ? (
            <ChevronUpIcon className="h-4 w-4 text-text-tertiary" />
          ) : (
            <ChevronDownIcon className="h-4 w-4 text-text-tertiary" />
          )}
        </div>
      </button>

      {/* Expanded content */}
      {expanded && (
        <div className="border-t border-border-default px-4 pb-4 pt-3 space-y-3">
          {/* Reviewer readiness + evolution summary */}
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

          {/* Feedback tracking list */}
          {feedbackTracked.length > 0 && (
            <div className="space-y-1.5">
              {feedbackTracked.slice(0, 6).map((item, i) => (
                <div key={i} className="flex items-start gap-2 text-xs">
                  <span className={`shrink-0 mt-0.5 font-semibold ${
                    item.resolution_status === 'resolved' ? 'text-emerald-400' : 'text-amber-400'
                  }`}>
                    {item.resolution_status === 'resolved' ? '✓' : '○'}
                  </span>
                  <span className="text-text-tertiary leading-snug line-clamp-2">{item.feedback_text}</span>
                </div>
              ))}
            </div>
          )}

          {/* Deep-dive link */}
          <button
            onClick={() => navigate(`/projects/${projectId}/compare/${v1Id}/${v2Id}`)}
            className="text-xs text-accent-primary hover:text-accent-primary/80 transition-colors font-medium"
          >
            View full comparison →
          </button>
        </div>
      )}
    </div>
  )
}

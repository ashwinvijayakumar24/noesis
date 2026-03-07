import { useNavigate } from 'react-router-dom'
import { DocumentTextIcon } from '@heroicons/react/24/outline'

interface TimelineEntry {
  draft_id: string
  title: string
  version: number
  created_at: string
  health_score: number
  score_delta: number | null
  critical_issues: number
  major_issues: number
  claim_count: number
  gap_count: number
}

interface VersionTimelineProps {
  projectId: string
  timeline: TimelineEntry[]
  onClose?: () => void
}

function ScoreSparkline({ entries }: { entries: TimelineEntry[] }) {
  if (entries.length < 2) return null

  const scores = entries.map(e => e.health_score)
  const min = Math.min(...scores)
  const max = Math.max(...scores)
  const range = max - min || 1
  const W = 120
  const H = 32

  const points = entries.map((e, i) => {
    const x = (i / (entries.length - 1)) * W
    const y = H - ((e.health_score - min) / range) * H
    return `${x},${y}`
  }).join(' ')

  return (
    <svg width={W} height={H} className="overflow-visible">
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        className="text-accent-primary"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {entries.map((e, i) => {
        const x = (i / (entries.length - 1)) * W
        const y = H - ((e.health_score - min) / range) * H
        return (
          <circle key={i} cx={x} cy={y} r="3" className="fill-accent-primary" />
        )
      })}
    </svg>
  )
}

export default function VersionTimeline({ projectId, timeline, onClose }: VersionTimelineProps) {
  const navigate = useNavigate()

  if (timeline.length === 0) {
    return (
      <div className="text-center py-8 text-text-tertiary text-sm">
        No analyzed drafts yet.
      </div>
    )
  }

  return (
    <div className="bg-bg-surface border border-border-default rounded-xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-text-primary">Version History</h3>
        <div className="flex items-center gap-4">
          {timeline.length >= 2 && (
            <ScoreSparkline entries={timeline} />
          )}
          {onClose && (
            <button onClick={onClose} className="text-xs text-text-tertiary hover:text-text-secondary transition-colors">
              Hide
            </button>
          )}
        </div>
      </div>

      <div className="relative">
        {/* Vertical line */}
        <div className="absolute left-4 top-0 bottom-0 w-px bg-border-default" />

        <div className="space-y-4 pl-10">
          {[...timeline].reverse().map((entry, i) => {
            const isLatest = i === 0
            return (
              <div key={entry.draft_id} className="relative">
                {/* Dot on timeline */}
                <div className={`absolute -left-10 top-2 w-3 h-3 rounded-full border-2 ${
                  isLatest
                    ? 'bg-accent-primary border-accent-primary'
                    : 'bg-bg-surface border-border-default'
                }`} />

                <div
                  onClick={() => navigate(`/projects/${projectId}/drafts/${entry.draft_id}`)}
                  className="bg-bg-base border border-border-default rounded-lg p-3 cursor-pointer hover:border-accent-primary/40 transition-colors"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0">
                      <DocumentTextIcon className="h-4 w-4 text-text-tertiary shrink-0" />
                      <span className="text-sm font-semibold text-text-primary truncate">
                        v{entry.version}
                        {isLatest && <span className="ml-1.5 text-xs text-accent-primary font-normal">latest</span>}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {entry.score_delta !== null && (
                        <span className={`text-xs font-semibold ${
                          entry.score_delta >= 0 ? 'text-emerald-400' : 'text-red-400'
                        }`}>
                          {entry.score_delta >= 0 ? '+' : ''}{entry.score_delta} pts
                        </span>
                      )}
                      <span className={`text-sm font-semibold ${
                        entry.health_score >= 75 ? 'text-emerald-400' :
                        entry.health_score >= 50 ? 'text-amber-400' : 'text-red-400'
                      }`}>
                        {entry.health_score}
                      </span>
                    </div>
                  </div>
                  <div className="flex items-center gap-3 mt-1.5 text-xs text-text-tertiary">
                    <span>{new Date(entry.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric' })}</span>
                    {entry.critical_issues > 0 && (
                      <span className="text-red-400">{entry.critical_issues} critical</span>
                    )}
                    {entry.major_issues > 0 && (
                      <span className="text-amber-400">{entry.major_issues} major</span>
                    )}
                    <span>{entry.claim_count} claims</span>
                  </div>
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

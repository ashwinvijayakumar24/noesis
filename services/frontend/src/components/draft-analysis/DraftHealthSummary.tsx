import { useMemo } from 'react'
import { ClockIcon } from '@heroicons/react/24/outline'

interface SectionCount {
  section_type: string
  new_count: number
  saved_count: number
  dismissed_count: number
  total_count: number
}

interface DraftHealthSummaryProps {
  draft: {
    id: string
    title: string
    version: number
    updated_at: string
  }
  sectionSummary: SectionCount[]
}

export default function DraftHealthSummary({ draft, sectionSummary }: DraftHealthSummaryProps) {
  const metrics = useMemo(() => {
    const totalNew = sectionSummary.reduce((s, sec) => s + sec.new_count, 0)
    const totalSaved = sectionSummary.reduce((s, sec) => s + sec.saved_count, 0)
    const totalDismissed = sectionSummary.reduce((s, sec) => s + sec.dismissed_count, 0)
    const totalItems = sectionSummary.reduce((s, sec) => s + sec.total_count, 0)
    const sectionsWithFeedback = sectionSummary.filter(s => s.total_count > 0).length

    const pctReviewed = totalItems > 0 ? (totalSaved + totalDismissed) / totalItems : 0

    const verdict =
      totalItems === 0 ? 'no-feedback' :
      totalNew === 0 ? 'looks-good' :
      pctReviewed >= 0.5 ? 'minor-revisions' :
      'major-revisions'

    return { totalNew, totalSaved, totalDismissed, totalItems, sectionsWithFeedback, verdict }
  }, [sectionSummary])

  // Plain text + dot — no background boxes
  const verdictConfig = {
    'major-revisions': { label: 'Needs Review', dotColor: 'bg-error', textColor: 'text-error' },
    'minor-revisions': { label: 'In Progress',  dotColor: 'bg-warning', textColor: 'text-warning' },
    'looks-good':      { label: 'All Reviewed', dotColor: 'bg-success', textColor: 'text-success' },
    'no-feedback':     { label: 'No Feedback',  dotColor: 'bg-text-muted', textColor: 'text-text-muted' },
  }

  const vc = verdictConfig[metrics.verdict]

  const timeSince = useMemo(() => {
    const diffMs = Date.now() - new Date(draft.updated_at).getTime()
    const mins = Math.floor(diffMs / 60000)
    const hrs = Math.floor(mins / 60)
    const days = Math.floor(hrs / 24)
    if (days > 0) return `${days}d ago`
    if (hrs > 0) return `${hrs}h ago`
    if (mins > 0) return `${mins}m ago`
    return 'just now'
  }, [draft.updated_at])

  return (
    <div className="bg-bg-surface border border-border-default rounded-xl p-4 mb-4">
      {/* Header */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex-1 min-w-0">
          {/* Verdict: dot + plain text, no box */}
          <div className="flex items-center gap-1.5 mb-1">
            <span className={`w-2 h-2 rounded-full shrink-0 ${vc.dotColor}`} />
            <span className={`text-xs font-semibold ${vc.textColor}`}>{vc.label}</span>
          </div>
          <h2 className="text-sm font-semibold text-text-primary truncate">
            {draft.title}
            {draft.version > 1 && (
              <span className="ml-2 text-xs font-normal text-text-tertiary">v{draft.version}</span>
            )}
          </h2>
        </div>
        <div className="flex items-center gap-1 text-xs text-text-tertiary ml-4 shrink-0 mt-1">
          <ClockIcon className="h-3.5 w-3.5" />
          <span>{timeSince}</span>
        </div>
      </div>

      {/* Metrics row — opaque dark fills, no translucent color */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-bg-void rounded-lg px-3 py-2.5">
          <p className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-1.5">To Review</p>
          <p className="text-xl font-semibold text-text-primary leading-none mb-1">
            {metrics.totalNew}
          </p>
          <p className={`text-xs font-medium ${metrics.totalNew > 0 ? 'text-warning' : 'text-success'}`}>
            {metrics.totalNew > 0 ? 'needs attention' : 'all clear'}
          </p>
        </div>

        <div className="bg-bg-void rounded-lg px-3 py-2.5">
          <p className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-1.5">Saved</p>
          <p className="text-xl font-semibold text-text-primary leading-none mb-1">
            {metrics.totalSaved}
          </p>
          <p className="text-xs text-text-muted font-medium">
            {metrics.totalDismissed > 0 ? `${metrics.totalDismissed} dismissed` : 'addressed items'}
          </p>
        </div>

        <div className="bg-bg-void rounded-lg px-3 py-2.5">
          <p className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-1.5">Sections</p>
          <p className="text-xl font-semibold text-text-primary leading-none mb-1">
            {metrics.sectionsWithFeedback}
          </p>
          <p className="text-xs text-text-muted font-medium">
            {metrics.totalItems} total items
          </p>
        </div>
      </div>
    </div>
  )
}

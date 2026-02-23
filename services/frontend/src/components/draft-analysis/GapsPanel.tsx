import { BeakerIcon } from '@heroicons/react/24/outline'
import { Badge, type BadgeVariant } from '../ui/Badge'

interface Gap {
  id: string
  gap_type: string
  description: string
  priority: string
  suggested_papers: any[]
}

interface GapsPanelProps {
  gaps: Gap[]
  onGapClick?: (gap: Gap) => void
}

export default function GapsPanel({ gaps, onGapClick }: GapsPanelProps) {
  const getPriorityVariant = (priority: string): BadgeVariant => {
    switch (priority) {
      case 'high':
        return 'error'
      case 'medium':
        return 'warning'
      case 'low':
        return 'success'
      default:
        return 'neutral'
    }
  }

  if (gaps.length === 0) {
    return (
      <div className="text-center py-12">
        <BeakerIcon className="h-12 w-12 text-text-muted mx-auto" />
        <p className="mt-4 text-text-secondary">No coverage gaps identified</p>
        <p className="mt-1 text-sm text-text-muted">
          Your draft appears to have comprehensive literature coverage
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {gaps
        .sort((a, b) => {
          const priorityOrder = { high: 0, medium: 1, low: 2 }
          return priorityOrder[a.priority as keyof typeof priorityOrder] -
                 priorityOrder[b.priority as keyof typeof priorityOrder]
        })
        .map((gap) => (
          <div
            key={gap.id}
            onClick={() => onGapClick?.(gap)}
            className={`border border-border-default rounded-lg p-4 bg-surface-hover transition-all ${
              onGapClick ? 'cursor-pointer hover:border-border-default hover:shadow-lg hover:shadow-red-600/20' : ''
            }`}
          >
            <div className="flex items-center gap-2 mb-2">
              <span className="text-xs font-medium text-text-tertiary font-mono uppercase">
                {gap.gap_type.replace('_', ' ')}
              </span>
              <Badge variant={getPriorityVariant(gap.priority)}>
                {gap.priority.toUpperCase()} PRIORITY
              </Badge>
            </div>
            <p className="text-sm text-text-secondary mb-3">{gap.description}</p>
            {gap.suggested_papers && gap.suggested_papers.length > 0 && (
              <div className="mt-3 border-t border-border-default pt-3">
                <p className="text-xs font-medium text-text-tertiary mb-2 font-mono">
                  Suggested papers from your literature:
                </p>
                <ul className="space-y-1">
                  {gap.suggested_papers.slice(0, 3).map((paper, idx) => (
                    <li key={idx} className="text-sm text-text-tertiary flex gap-2">
                      <span className="text-text-muted">•</span>
                      <span>{paper.title} ({paper.year})</span>
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        ))}
    </div>
  )
}

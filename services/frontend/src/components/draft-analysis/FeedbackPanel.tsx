import { ExclamationTriangleIcon, CheckCircleIcon, LightBulbIcon } from '@heroicons/react/24/outline'
import { Badge, type BadgeVariant } from '../ui/Badge'

interface Feedback {
  id: string
  feedback_type: string
  severity: string
  feedback_text: string
  suggestions: string[]
}

interface FeedbackPanelProps {
  feedback: Feedback[]
  onFeedbackClick?: (feedback: Feedback) => void
}

export default function FeedbackPanel({ feedback, onFeedbackClick }: FeedbackPanelProps) {
  const getSeverityVariant = (severity: string): BadgeVariant => {
    switch (severity) {
      case 'critical':
      case 'major':
        return 'error'
      case 'minor':
        return 'warning'
      case 'suggestion':
        return 'info'
      default:
        return 'neutral'
    }
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
      case 'major':
        return <ExclamationTriangleIcon className="h-5 w-5 text-text-tertiary" />
      case 'minor':
        return <LightBulbIcon className="h-5 w-5 text-text-tertiary" />
      case 'suggestion':
        return <CheckCircleIcon className="h-5 w-5 text-text-tertiary" />
      default:
        return null
    }
  }

  if (feedback.length === 0) {
    return (
      <div className="text-center py-12">
        <ExclamationTriangleIcon className="h-12 w-12 text-text-muted mx-auto" />
        <p className="mt-4 text-text-secondary">No feedback available yet</p>
        <p className="mt-1 text-sm text-text-muted">
          Your draft will receive expert reviewer feedback after analysis
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {feedback
        .sort((a, b) => {
          const severityOrder = { critical: 0, major: 1, minor: 2, suggestion: 3 }
          return severityOrder[a.severity as keyof typeof severityOrder] -
                 severityOrder[b.severity as keyof typeof severityOrder]
        })
        .map((item) => (
          <div
            key={item.id}
            onClick={() => onFeedbackClick?.(item)}
            className={`border border-border-base rounded-lg p-4 bg-surface-hover transition-all ${
              onFeedbackClick ? 'cursor-pointer hover:border-border-subtle hover:shadow-lg hover:shadow-red-600/20' : ''
            }`}
          >
            <div className="flex items-start gap-3">
              {getSeverityIcon(item.severity)}
              <div className="flex-1">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-text-tertiary font-mono uppercase">
                    {item.feedback_type}
                  </span>
                  <Badge variant={getSeverityVariant(item.severity)}>
                    {item.severity.toUpperCase()}
                  </Badge>
                </div>
                <p className="text-sm text-text-secondary mb-3">{item.feedback_text}</p>
                {item.suggestions && item.suggestions.length > 0 && (
                  <div className="mt-3 border-t border-border-subtle pt-3">
                    <p className="text-xs font-medium text-text-tertiary mb-2 font-mono">
                      Suggested improvements:
                    </p>
                    <ul className="space-y-1 text-sm text-text-tertiary">
                      {item.suggestions.map((improvement, idx) => (
                        <li key={idx} className="text-sm flex gap-2">
                          <span className="text-text-muted">•</span>
                          <span>{improvement}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
    </div>
  )
}

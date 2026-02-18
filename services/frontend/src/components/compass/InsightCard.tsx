import { type ReactNode } from 'react'
import ConfidenceBar from './ConfidenceBar'

type InsightType = 'gap' | 'conflict' | 'pattern' | 'general'

interface InsightCardProps {
  /** Card title */
  title: string
  /** Type of insight for color coding */
  type: InsightType
  /** Priority level (1-5, where 5 is highest) */
  priority?: number
  /** Child content */
  children: ReactNode
  /** Optional metadata to display */
  metadata?: {
    sourceCount?: number
    confidence?: number
    actionable?: boolean
  }
  /** Additional class names */
  className?: string
}

export default function InsightCard({
  title,
  type,
  priority = 1,
  children,
  metadata,
  className = ''
}: InsightCardProps) {
  // Type-based color coding
  const getTypeStyles = () => {
    switch (type) {
      case 'gap':
        return {
          border: 'border-amber-700/50',
          bg: 'bg-amber-900/10',
          dot: 'bg-amber-500'
        }
      case 'conflict':
        return {
          border: 'border-red-700/50',
          bg: 'bg-red-900/10',
          dot: 'bg-red-500'
        }
      case 'pattern':
        return {
          border: 'border-blue-700/50',
          bg: 'bg-blue-900/10',
          dot: 'bg-blue-500'
        }
      case 'general':
      default:
        return {
          border: 'border-border-subtle',
          bg: 'bg-surface/50',
          dot: 'bg-slate-500'
        }
    }
  }

  const styles = getTypeStyles()

  // Render priority dots (filled based on priority level)
  const renderPriorityDots = () => {
    const dots = []
    for (let i = 1; i <= 5; i++) {
      dots.push(
        <div
          key={i}
          className={`h-1.5 w-1.5 rounded-full transition-colors ${
            i <= priority ? styles.dot : 'bg-surface-hover'
          }`}
        />
      )
    }
    return dots
  }

  return (
    <div
      className={`rounded-lg border ${styles.border} ${styles.bg} overflow-hidden ${className}`}
    >
      {/* Header */}
      <div className="p-3 border-b border-border-subtle/50">
        <div className="flex items-start justify-between gap-3">
          <h4 className="text-sm font-semibold text-text-primary flex-1">
            {title}
          </h4>

          {/* Priority dots */}
          {priority > 0 && (
            <div className="flex items-center gap-1 shrink-0">
              {renderPriorityDots()}
            </div>
          )}
        </div>
      </div>

      {/* Content */}
      <div className="p-3">
        {children}
      </div>

      {/* Metadata footer */}
      {metadata && (
        <div className="px-3 pb-3 flex items-center gap-3 text-xs text-text-muted">
          {metadata.sourceCount !== undefined && (
            <div className="flex items-center gap-1">
              <span className="font-mono">{metadata.sourceCount}</span>
              <span>sources</span>
            </div>
          )}

          {metadata.confidence !== undefined && (
            <div className="flex-1 min-w-0">
              <ConfidenceBar
                score={metadata.confidence}
                label="Confidence"
                showPercentage={false}
              />
            </div>
          )}

          {metadata.actionable && (
            <div className="px-2 py-0.5 rounded bg-green-900/20 text-green-400 border border-green-700/50 font-medium">
              Actionable
            </div>
          )}
        </div>
      )}
    </div>
  )
}

import { type ReactNode } from 'react'
import ConfidenceBar from './ConfidenceBar'

type InsightType = 'gap' | 'conflict' | 'pattern' | 'synthesis' | 'general'

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
  /** Optional click handler */
  onClick?: () => void
}

export default function InsightCard({
  title,
  type,
  priority = 1,
  children,
  metadata,
  className = '',
  onClick
}: InsightCardProps) {
  // Type-based color coding with neon-brutalist aesthetic
  const getTypeStyles = () => {
    switch (type) {
      case 'gap':
        return {
          accentBorder: 'border-l-4 border-l-warning',
          badge: 'bg-warning/10 text-warning border-warning/30',
          badgeLabel: 'GAP',
          icon: (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          )
        }
      case 'conflict':
        return {
          accentBorder: 'border-l-4 border-l-error',
          badge: 'bg-error/10 text-error border-error/30',
          badgeLabel: 'CONFLICT',
          icon: (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )
        }
      case 'pattern':
        return {
          accentBorder: 'border-l-4 border-l-accent-teal',
          badge: 'bg-accent-teal/10 text-accent-teal border-accent-teal/30',
          badgeLabel: 'PATTERN',
          icon: (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
            </svg>
          )
        }
      case 'synthesis':
        return {
          accentBorder: 'border-l-4 border-l-accent-purple',
          badge: 'bg-accent-purple/10 text-accent-purple border-accent-purple/30',
          badgeLabel: 'SYNTHESIS',
          icon: (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          )
        }
      case 'general':
      default:
        return {
          accentBorder: 'border-l-4 border-l-border-base',
          badge: 'bg-bg-elevated text-text-secondary border-border-default',
          badgeLabel: 'INSIGHT',
          icon: (
            <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          )
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
          className={`h-2 w-2 rounded-full transition-all duration-150 ${
            i <= priority ? 'bg-accent-primary scale-110' : 'bg-border-base'
          }`}
        />
      )
    }
    return dots
  }

  return (
    <div
      onClick={onClick}
      className={`group bg-bg-surface rounded-lg border border-border-default ${styles.accentBorder} p-6 transition-all duration-150 hover:border-accent-primary/30 hover:-translate-y-1 hover:shadow-card-lift ${
        onClick ? 'cursor-pointer' : ''
      } ${className}`}
    >
      {/* Header */}
      <div className="flex items-start justify-between gap-4 mb-4">
        <div className="flex items-start gap-3 flex-1 min-w-0">
          {/* Type Icon */}
          <div className={`shrink-0 p-2 rounded-lg border ${styles.badge}`}>
            {styles.icon}
          </div>

          {/* Title and Badge */}
          <div className="flex-1 min-w-0">
            <div className={`inline-flex items-center gap-2 px-2.5 py-1 rounded-md text-xs font-mono font-semibold uppercase border mb-2 ${styles.badge}`}>
              {styles.badgeLabel}
            </div>
            <h4 className="text-lg font-sans font-semibold text-text-primary group-hover:text-accent-primary transition-colors duration-150">
              {title}
            </h4>
          </div>
        </div>

        {/* Priority dots */}
        {priority > 0 && (
          <div className="flex items-center gap-1 shrink-0">
            {renderPriorityDots()}
          </div>
        )}
      </div>

      {/* Content */}
      <div className="text-text-secondary leading-relaxed mb-4">
        {children}
      </div>

      {/* Metadata footer */}
      {metadata && (
        <div className="flex items-center gap-4 pt-4 border-t border-border-default">
          {metadata.sourceCount !== undefined && (
            <div className="flex items-center gap-2 text-sm">
              <svg className="h-4 w-4 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              <span className="font-mono font-semibold text-text-primary">{metadata.sourceCount}</span>
              <span className="text-text-muted">sources</span>
            </div>
          )}

          {metadata.confidence !== undefined && (
            <div className="flex-1 min-w-0">
              <ConfidenceBar
                score={metadata.confidence}
                label="Confidence"
                showPercentage={true}
              />
            </div>
          )}

          {metadata.actionable && (
            <div className="px-3 py-1.5 rounded-lg bg-success/10 text-success border border-success/30 text-xs font-semibold uppercase">
              Actionable
            </div>
          )}
        </div>
      )}
    </div>
  )
}

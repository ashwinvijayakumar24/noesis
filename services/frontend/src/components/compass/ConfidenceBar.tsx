import { type ReactNode } from 'react'

interface ConfidenceBarProps {
  /** Confidence score between 0 and 1 */
  score: number
  /** Optional label to display */
  label?: string
  /** Whether to show percentage text */
  showPercentage?: boolean
  /** Additional class names */
  className?: string
}

export default function ConfidenceBar({
  score,
  label,
  showPercentage = true,
  className = ''
}: ConfidenceBarProps) {
  // Clamp score between 0 and 1
  const clampedScore = Math.max(0, Math.min(1, score))
  const percentage = Math.round(clampedScore * 100)

  // Color coding based on score
  const getColor = () => {
    if (percentage >= 70) return 'bg-green-600'
    if (percentage >= 40) return 'bg-amber-500'
    return 'bg-red-500'
  }

  const getBackgroundColor = () => {
    if (percentage >= 70) return 'bg-green-900/20'
    if (percentage >= 40) return 'bg-amber-900/20'
    return 'bg-red-900/20'
  }

  return (
    <div className={`flex items-center gap-2 ${className}`}>
      {label && (
        <span className="text-xs font-medium text-text-muted shrink-0">
          {label}
        </span>
      )}

      <div className="flex-1 min-w-0">
        <div className={`h-1.5 rounded-full overflow-hidden ${getBackgroundColor()}`}>
          <div
            className={`h-full ${getColor()} transition-all duration-300 ease-out`}
            style={{ width: `${percentage}%` }}
          />
        </div>
      </div>

      {showPercentage && (
        <span className="text-xs font-mono text-text-tertiary shrink-0 tabular-nums">
          {percentage}%
        </span>
      )}
    </div>
  )
}

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

  return (
    <div className={`flex items-center gap-3 ${className}`}>
      {label && (
        <span className="text-xs font-semibold text-text-secondary shrink-0 uppercase tracking-wide">
          {label}
        </span>
      )}

      <div className="flex-1 min-w-0">
        <div className="h-2 rounded-full overflow-hidden bg-bg-elevated border border-border-default">
          <div
            className="h-full transition-all duration-500 ease-out"
            style={{
              width: `${percentage}%`,
              background: percentage >= 70
                ? 'linear-gradient(90deg, #00d9ff 0%, #00d9ff 100%)' // Teal for high confidence
                : percentage >= 40
                ? 'linear-gradient(90deg, #F59E0B 0%, #00d9ff 100%)' // Orange to teal for medium
                : 'linear-gradient(90deg, #FF1F4C 0%, #F59E0B 100%)' // Pink to orange for low
            }}
          />
        </div>
      </div>

      {showPercentage && (
        <span className="text-sm font-mono font-bold text-accent-primary shrink-0 tabular-nums min-w-[3ch]">
          {percentage}%
        </span>
      )}
    </div>
  )
}

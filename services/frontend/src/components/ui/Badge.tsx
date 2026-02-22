import type { ReactNode } from 'react'

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'pink'

interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
}

export function Badge({ variant = 'neutral', children, className = '' }: BadgeProps) {
  const baseStyles = 'px-2.5 py-1 text-xs font-semibold rounded-md inline-flex items-center gap-1'

  const variantStyles = {
    success: 'bg-success/10 text-success border border-success/30',
    warning: 'bg-warning/10 text-warning border border-warning/30',
    error: 'bg-error/10 text-error border border-error/30',
    info: 'bg-info/10 text-info border border-info/30',
    neutral: 'bg-bg-elevated text-text-secondary border border-border-base',
    pink: 'bg-neon-pink/10 text-neon-pink border border-neon-pink/30'
  }

  return (
    <span className={`${baseStyles} ${variantStyles[variant]} ${className}`}>
      {children}
    </span>
  )
}

// Tag Component (for project tags)
interface TagProps {
  children: ReactNode
  className?: string
  onRemove?: () => void
}

export function Tag({ children, className = '', onRemove }: TagProps) {
  return (
    <span className={`px-2.5 py-1 text-xs font-medium bg-surface-hover text-text-tertiary border border-border-base rounded-md inline-flex items-center gap-1 ${className}`}>
      {children}
      {onRemove && (
        <button
          onClick={onRemove}
          className="ml-1 text-text-muted hover:text-text-primary transition-colors"
          aria-label="Remove tag"
        >
          ×
        </button>
      )}
    </span>
  )
}

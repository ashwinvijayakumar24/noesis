import type { ReactNode } from 'react'

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral' | 'primary' | 'teal' | 'indigo' | 'amber' | 'rose'

interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
}

export function Badge({ variant = 'neutral', children, className = '' }: BadgeProps) {
  const baseStyles = 'px-2.5 py-1 text-xs font-medium rounded-sm inline-flex items-center gap-1'

  const variantStyles = {
    success: 'bg-success-light text-success border border-success/30',
    warning: 'bg-amber-light text-amber-primary border border-amber-primary/30',
    error: 'bg-ruby-light text-ruby-primary border border-ruby-primary/30',
    info: 'bg-indigo-light text-indigo-primary border border-indigo-primary/30',
    neutral: 'bg-bg-elevated text-text-secondary border border-border-default',
    primary: 'bg-accent-light text-accent-primary border border-accent-primary/30',
    teal: 'bg-teal-light text-teal-primary border border-teal-primary/30',
    indigo: 'bg-indigo-light text-indigo-primary border border-indigo-primary/30',
    amber: 'bg-amber-light text-amber-primary border border-amber-primary/30',
    rose: 'bg-accent-light text-accent-primary border border-accent-primary/30'
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
    <span className={`px-2.5 py-1 text-xs font-medium bg-bg-elevated text-text-tertiary border border-border-default rounded-md inline-flex items-center gap-1 ${className}`}>
      {children}
      {onRemove && (
        <button
          onClick={onRemove}
          className="ml-1 text-text-muted hover:text-accent-primary transition-colors"
          aria-label="Remove tag"
        >
          ×
        </button>
      )}
    </span>
  )
}

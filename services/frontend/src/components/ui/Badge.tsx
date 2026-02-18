import type { ReactNode } from 'react'

export type BadgeVariant = 'success' | 'warning' | 'error' | 'info' | 'neutral'

interface BadgeProps {
  variant?: BadgeVariant
  children: ReactNode
  className?: string
}

export function Badge({ variant = 'neutral', children, className = '' }: BadgeProps) {
  const baseStyles = 'px-2.5 py-1 text-xs font-medium rounded-md inline-flex items-center gap-1'

  const variantStyles = {
    success: 'bg-green-900 text-green-100 border border-green-700',
    warning: 'bg-amber-800 text-amber-200 border border-amber-600',
    error: 'bg-red-800 text-red-200 border border-red-600',
    info: 'bg-slate-700 text-slate-200 border border-slate-500',
    neutral: 'bg-surface-hover text-text-tertiary border border-border-base'
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

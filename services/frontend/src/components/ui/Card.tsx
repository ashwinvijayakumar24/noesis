import type { ReactNode, HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  className?: string
  hover?: boolean
  clickable?: boolean
}

export function Card({ children, className = '', hover = false, clickable = false, ...props }: CardProps) {
  const baseStyles = 'bg-surface border border-border-base rounded-lg p-6 transition-all'
  const hoverStyles = hover ? 'hover:border-accent-primary hover:bg-surface-hover' : 'hover:border-border-subtle'
  const clickableStyles = clickable ? 'cursor-pointer' : ''

  return (
    <div className={`${baseStyles} ${hoverStyles} ${clickableStyles} ${className}`} {...props}>
      {children}
    </div>
  )
}

interface CardTitleProps {
  children: ReactNode
  className?: string
}

export function CardTitle({ children, className = '' }: CardTitleProps) {
  return (
    <h3 className={`text-2xl font-serif font-semibold text-text-primary mb-4 ${className}`}>
      {children}
    </h3>
  )
}

interface CardDescriptionProps {
  children: ReactNode
  className?: string
}

export function CardDescription({ children, className = '' }: CardDescriptionProps) {
  return (
    <p className={`text-sm text-text-secondary ${className}`}>
      {children}
    </p>
  )
}

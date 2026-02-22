import type { ReactNode, HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  className?: string
  hover?: boolean
  clickable?: boolean
}

export function Card({ children, className = '', hover = false, clickable = false, ...props }: CardProps) {
  const baseStyles = 'bg-bg-surface border border-border-base rounded-2xl p-6 transition-all duration-300'
  const hoverStyles = hover ? 'hover:border-neon-pink/30 hover:-translate-y-1 hover:shadow-card-lift' : ''
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
    <h3 className={`text-2xl font-display font-bold text-text-primary mb-4 ${className}`}>
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

import type { ReactNode, HTMLAttributes } from 'react'

interface CardProps extends HTMLAttributes<HTMLDivElement> {
  children: ReactNode
  className?: string
  hover?: boolean
  clickable?: boolean
}

export function Card({ children, className = '', hover = false, clickable = false, ...props }: CardProps) {
  const baseStyles = 'bg-bg-surface border border-border-default rounded-lg p-6 shadow-xs transition-all duration-150'
  const hoverStyles = hover ? 'hover:border-accent-primary/30 hover:-translate-y-0.5 hover:shadow-sm' : ''
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
    <h3 className={`text-xl font-sans font-semibold text-text-primary mb-3 leading-heading-4 tracking-normal ${className}`}>
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
    <p className={`text-sm text-text-secondary leading-body-small tracking-normal ${className}`}>
      {children}
    </p>
  )
}

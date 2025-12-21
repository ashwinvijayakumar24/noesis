import { ReactNode } from 'react'

interface HeadingProps {
  children: ReactNode
  className?: string
}

export function H1({ children, className = '' }: HeadingProps) {
  return (
    <h1 className={`text-5xl sm:text-6xl lg:text-7xl font-serif font-bold leading-[1.1] tracking-tight text-neutral-50 ${className}`}>
      {children}
    </h1>
  )
}

export function H2({ children, className = '' }: HeadingProps) {
  return (
    <h2 className={`text-4xl sm:text-5xl font-serif font-semibold text-neutral-50 ${className}`}>
      {children}
    </h2>
  )
}

export function H3({ children, className = '' }: HeadingProps) {
  return (
    <h3 className={`text-2xl font-serif font-semibold text-neutral-50 ${className}`}>
      {children}
    </h3>
  )
}

export function H4({ children, className = '' }: HeadingProps) {
  return (
    <h4 className={`text-xl font-serif font-medium text-neutral-50 ${className}`}>
      {children}
    </h4>
  )
}

interface TextProps {
  children: ReactNode
  className?: string
}

export function Text({ children, className = '' }: TextProps) {
  return (
    <p className={`text-neutral-300 ${className}`}>
      {children}
    </p>
  )
}

export function TextSecondary({ children, className = '' }: TextProps) {
  return (
    <p className={`text-neutral-400 ${className}`}>
      {children}
    </p>
  )
}

export function TextMuted({ children, className = '' }: TextProps) {
  return (
    <p className={`text-neutral-500 ${className}`}>
      {children}
    </p>
  )
}

export function TextMono({ children, className = '' }: TextProps) {
  return (
    <span className={`font-mono text-sm text-neutral-500 ${className}`}>
      {children}
    </span>
  )
}

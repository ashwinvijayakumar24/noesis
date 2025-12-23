import type { ReactNode } from 'react'

interface SectionProps {
  children: ReactNode
  className?: string
  background?: 'default' | 'subtle'
}

export function Section({ children, className = '', background = 'default' }: SectionProps) {
  const bgStyles = background === 'subtle' ? 'bg-neutral-900/30' : ''

  return (
    <section className={`py-32 px-6 sm:px-8 ${bgStyles} ${className}`}>
      <div className="max-w-6xl mx-auto">
        {children}
      </div>
    </section>
  )
}

interface SectionHeaderProps {
  title: string
  subtitle?: string
  className?: string
}

export function SectionHeader({ title, subtitle, className = '' }: SectionHeaderProps) {
  return (
    <div className={`mb-16 ${className}`}>
      <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-neutral-50 mb-4">
        {title}
      </h2>
      {subtitle && (
        <p className="text-xl text-neutral-400">
          {subtitle}
        </p>
      )}
    </div>
  )
}

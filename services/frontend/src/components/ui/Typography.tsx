import type { ReactNode } from 'react'
import { motion } from 'framer-motion'

interface HeadingProps {
  children: ReactNode
  className?: string
  gradient?: boolean
}

/**
 * H1 Display - 72px, Syne 800, for landing page hero
 */
export function H1({ children, className = '', gradient = false }: HeadingProps) {
  const baseClasses = 'text-6xl sm:text-7xl font-display font-extrabold leading-[1.1] tracking-tighter'
  const textClasses = gradient ? 'gradient-text' : 'text-text-primary'
  return (
    <h1 className={`${baseClasses} ${textClasses} ${className}`}>
      {children}
    </h1>
  )
}

/**
 * H2 Section - 48px, Syne 700, for section headings
 */
export function H2({ children, className = '' }: HeadingProps) {
  return (
    <h2 className={`text-4xl sm:text-5xl font-display font-bold leading-[1.2] tracking-tight text-text-primary ${className}`}>
      {children}
    </h2>
  )
}

/**
 * H3 Subsection - 32px, Syne 600, for subsections
 */
export function H3({ children, className = '' }: HeadingProps) {
  return (
    <h3 className={`text-2xl sm:text-3xl font-display font-semibold leading-[1.3] tracking-tight text-text-primary ${className}`}>
      {children}
    </h3>
  )
}

/**
 * H4 Card - 24px, Syne 600, for card titles
 */
export function H4({ children, className = '' }: HeadingProps) {
  return (
    <h4 className={`text-xl sm:text-2xl font-display font-semibold leading-[1.4] text-text-primary ${className}`}>
      {children}
    </h4>
  )
}

interface TextProps {
  children: ReactNode
  className?: string
}

/**
 * Body text - standard paragraph
 */
export function Text({ children, className = '' }: TextProps) {
  return (
    <p className={`text-base text-text-secondary leading-relaxed ${className}`}>
      {children}
    </p>
  )
}

/**
 * Secondary text - muted paragraphs
 */
export function TextSecondary({ children, className = '' }: TextProps) {
  return (
    <p className={`text-base text-text-tertiary leading-relaxed ${className}`}>
      {children}
    </p>
  )
}

/**
 * Muted text - very subtle text
 */
export function TextMuted({ children, className = '' }: TextProps) {
  return (
    <p className={`text-sm text-text-muted ${className}`}>
      {children}
    </p>
  )
}

/**
 * Monospace text - technical content
 */
export function TextMono({ children, className = '' }: TextProps) {
  return (
    <span className={`font-mono text-sm text-text-muted tracking-mono ${className}`}>
      {children}
    </span>
  )
}

/**
 * Large body text - emphasized paragraphs
 */
export function TextLarge({ children, className = '' }: TextProps) {
  return (
    <p className={`text-lg sm:text-xl text-text-secondary leading-relaxed ${className}`}>
      {children}
    </p>
  )
}

/**
 * Animated heading with fade-in effect
 */
export function AnimatedH1({ children, className = '', gradient = false, delay = 0 }: HeadingProps & { delay?: number }) {
  const baseClasses = 'text-6xl sm:text-7xl font-display font-extrabold leading-[1.1] tracking-tighter'
  const textClasses = gradient ? 'gradient-text' : 'text-text-primary'

  return (
    <motion.h1
      className={`${baseClasses} ${textClasses} ${className}`}
      initial={{ opacity: 0, y: 20, scale: 0.95 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.6, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.h1>
  )
}

/**
 * Animated H2 with scroll reveal
 */
export function AnimatedH2({ children, className = '', delay = 0 }: HeadingProps & { delay?: number }) {
  return (
    <motion.h2
      className={`text-4xl sm:text-5xl font-display font-bold leading-[1.2] tracking-tight text-text-primary ${className}`}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.5, delay }}
    >
      {children}
    </motion.h2>
  )
}

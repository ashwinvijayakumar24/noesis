import type { ReactNode } from 'react'
import { motion } from 'framer-motion'

interface HeadingProps {
  children: ReactNode
  className?: string
}

/**
 * H1 Display - 56px (Display-1), Inter 600 Semibold, for landing page hero
 */
export function H1({ children, className = '' }: HeadingProps) {
  return (
    <h1 className={`text-5xl sm:text-6xl font-sans font-semibold leading-tight tracking-tighter text-text-primary ${className}`}>
      {children}
    </h1>
  )
}

/**
 * H2 Section - 40px (Display-2), Inter 600 Semibold, for page titles
 */
export function H2({ children, className = '' }: HeadingProps) {
  return (
    <h2 className={`text-4xl sm:text-5xl font-sans font-semibold leading-heading-1 tracking-tighter text-text-primary ${className}`}>
      {children}
    </h2>
  )
}

/**
 * H3 Subsection - 32px (Heading-1), Inter 600 Semibold, for section headings
 */
export function H3({ children, className = '' }: HeadingProps) {
  return (
    <h3 className={`text-2xl sm:text-3xl font-sans font-semibold leading-heading-2 tracking-tight text-text-primary ${className}`}>
      {children}
    </h3>
  )
}

/**
 * H4 Card - 24px (Heading-2), Inter 600 Semibold, for subsection headings
 */
export function H4({ children, className = '' }: HeadingProps) {
  return (
    <h4 className={`text-xl sm:text-2xl font-sans font-semibold leading-heading-3 tracking-snug text-text-primary ${className}`}>
      {children}
    </h4>
  )
}

interface TextProps {
  children: ReactNode
  className?: string
}

/**
 * Body text - standard paragraph, Inter 400, line-height 1.6 (spacious!)
 */
export function Text({ children, className = '' }: TextProps) {
  return (
    <p className={`text-base text-text-secondary leading-body tracking-normal ${className}`}>
      {children}
    </p>
  )
}

/**
 * Secondary text - muted paragraphs
 */
export function TextSecondary({ children, className = '' }: TextProps) {
  return (
    <p className={`text-base text-text-tertiary leading-body tracking-normal ${className}`}>
      {children}
    </p>
  )
}

/**
 * Muted text - very subtle text, line-height 1.5
 */
export function TextMuted({ children, className = '' }: TextProps) {
  return (
    <p className={`text-sm text-text-muted leading-body-small tracking-normal ${className}`}>
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
 * Large body text - emphasized paragraphs, line-height 1.6
 */
export function TextLarge({ children, className = '' }: TextProps) {
  return (
    <p className={`text-lg sm:text-xl text-text-secondary leading-body-large tracking-normal ${className}`}>
      {children}
    </p>
  )
}

/**
 * Animated heading with fade-in effect - Inter 600 Semibold
 */
export function AnimatedH1({ children, className = '', delay = 0 }: HeadingProps & { delay?: number }) {
  return (
    <motion.h1
      className={`text-5xl sm:text-6xl font-sans font-semibold leading-tight tracking-tighter text-text-primary ${className}`}
      initial={{ opacity: 0, y: 20, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      transition={{ duration: 0.3, delay, ease: [0.16, 1, 0.3, 1] }}
    >
      {children}
    </motion.h1>
  )
}

/**
 * Animated H2 with scroll reveal - Inter 600 Semibold
 */
export function AnimatedH2({ children, className = '', delay = 0 }: HeadingProps & { delay?: number }) {
  return (
    <motion.h2
      className={`text-4xl sm:text-5xl font-sans font-semibold leading-heading-1 tracking-tighter text-text-primary ${className}`}
      initial={{ opacity: 0, y: 12 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ duration: 0.3, delay }}
    >
      {children}
    </motion.h2>
  )
}

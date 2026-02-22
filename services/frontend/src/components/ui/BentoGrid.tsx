import { motion } from 'framer-motion'
import { type ReactNode } from 'react'

interface BentoGridProps {
  children: ReactNode
  columns?: 2 | 3 | 4
  gap?: 'sm' | 'md' | 'lg'
  className?: string
}

/**
 * BentoGrid - Asymmetric grid layout system
 *
 * Usage:
 * <BentoGrid columns={2} gap="lg">
 *   <BentoCard size="large">...</BentoCard>
 *   <BentoCard>...</BentoCard>
 * </BentoGrid>
 */
export function BentoGrid({
  children,
  columns = 2,
  gap = 'md',
  className = ''
}: BentoGridProps) {
  const gapClasses = {
    sm: 'gap-4',
    md: 'gap-6 lg:gap-8',
    lg: 'gap-8 lg:gap-12'
  }

  const columnClasses = {
    2: 'grid-cols-1 md:grid-cols-2',
    3: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-3',
    4: 'grid-cols-1 md:grid-cols-2 lg:grid-cols-4'
  }

  return (
    <div className={`grid ${columnClasses[columns]} ${gapClasses[gap]} ${className}`}>
      {children}
    </div>
  )
}

interface BentoCardProps {
  children: ReactNode
  size?: 'small' | 'medium' | 'large' | 'wide' | 'tall'
  icon?: ReactNode
  title?: string
  description?: string
  className?: string
  onClick?: () => void
  delay?: number
}

/**
 * BentoCard - Individual card component for BentoGrid
 *
 * Features:
 * - Hover lift effect
 * - Pink border glow on hover
 * - Gradient overlay
 * - Optional icon badge
 * - Responsive sizing
 */
export function BentoCard({
  children,
  size = 'medium',
  icon,
  title,
  description,
  className = '',
  onClick,
  delay = 0
}: BentoCardProps) {
  const sizeClasses = {
    small: '',
    medium: '',
    large: 'md:col-span-2 md:row-span-2',
    wide: 'md:col-span-2',
    tall: 'md:row-span-2'
  }

  const hasInteraction = !!onClick

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true }}
      transition={{ delay, duration: 0.5 }}
      className={`
        group relative
        bg-bg-surface
        border border-border-base
        rounded-2xl p-8
        transition-all duration-300
        hover:border-neon-pink/30
        hover:-translate-y-2
        ${sizeClasses[size]}
        ${hasInteraction ? 'cursor-pointer' : ''}
        ${className}
      `}
      onClick={onClick}
      style={{
        boxShadow: '0 4px 24px rgba(0, 0, 0, 0.1)'
      }}
    >
      {/* Gradient Overlay on Hover */}
      <div className="absolute inset-0 bg-gradient-to-br from-neon-pink/5 to-transparent rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

      <div className="relative z-10 space-y-6">
        {/* Icon Badge */}
        {icon && (
          <div className="w-14 h-14 rounded-xl bg-bg-void/50 border border-border-base flex items-center justify-center group-hover:border-neon-pink/50 transition-all duration-300">
            <div className="text-text-tertiary group-hover:text-neon-pink transition-colors">
              {icon}
            </div>
          </div>
        )}

        {/* Title & Description */}
        {(title || description) && (
          <div className="space-y-3">
            {title && (
              <h3 className="text-2xl sm:text-3xl font-display font-semibold text-text-primary leading-tight">
                {title}
              </h3>
            )}
            {description && (
              <p className="text-text-secondary leading-relaxed">
                {description}
              </p>
            )}
          </div>
        )}

        {/* Custom Content */}
        {children}
      </div>

      {/* Subtle Border Glow Effect */}
      <div
        className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
        style={{
          boxShadow: '0 0 0 1px rgba(255, 31, 76, 0.1), 0 8px 32px rgba(255, 31, 76, 0.1)'
        }}
      />
    </motion.div>
  )
}

/**
 * Compact BentoCard variant for smaller content
 */
export function BentoCardCompact({
  icon,
  title,
  value,
  className = '',
  delay = 0
}: {
  icon?: ReactNode
  title: string
  value: string | number
  className?: string
  delay?: number
}) {
  return (
    <motion.div
      initial={{ opacity: 0, scale: 0.95 }}
      whileInView={{ opacity: 1, scale: 1 }}
      viewport={{ once: true }}
      transition={{ delay, duration: 0.4 }}
      className={`
        bg-bg-surface
        border border-border-base
        rounded-xl p-6
        hover:border-neon-pink/30
        transition-all duration-300
        ${className}
      `}
    >
      <div className="flex items-center justify-between">
        <div className="space-y-2">
          <p className="text-xs font-mono text-text-muted uppercase tracking-wider">
            {title}
          </p>
          <p className="text-2xl sm:text-3xl font-display font-bold text-text-primary">
            {value}
          </p>
        </div>
        {icon && (
          <div className="text-neon-pink opacity-20">
            {icon}
          </div>
        )}
      </div>
    </motion.div>
  )
}

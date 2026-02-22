import { motion, useMotionValue, useSpring } from 'framer-motion'
import { useRef, type ReactNode, type MouseEvent } from 'react'

interface MagneticButtonProps {
  children: ReactNode
  className?: string
  onClick?: () => void
  variant?: 'primary' | 'secondary' | 'ghost'
  size?: 'sm' | 'md' | 'lg'
  disabled?: boolean
  type?: 'button' | 'submit' | 'reset'
  icon?: ReactNode
}

/**
 * MagneticButton - Interactive button that follows mouse movement with spring physics
 *
 * Features:
 * - Subtle magnetic effect (follows mouse within button bounds)
 * - Spring-based animation (stiffness 150, damping 15)
 * - Neon pink glow on hover
 * - Scale feedback on tap
 * - Accessible (keyboard navigation, focus states)
 */
export function MagneticButton({
  children,
  className = '',
  onClick,
  variant = 'primary',
  size = 'md',
  disabled = false,
  type = 'button',
  icon
}: MagneticButtonProps) {
  const ref = useRef<HTMLButtonElement>(null)

  // Motion values for magnetic effect
  const x = useMotionValue(0)
  const y = useMotionValue(0)

  // Spring physics for smooth follow
  const springConfig = { stiffness: 150, damping: 15 }
  const springX = useSpring(x, springConfig)
  const springY = useSpring(y, springConfig)

  const handleMouseMove = (e: MouseEvent<HTMLButtonElement>) => {
    if (!ref.current || disabled) return

    const rect = ref.current.getBoundingClientRect()
    const centerX = rect.left + rect.width / 2
    const centerY = rect.top + rect.height / 2

    // Calculate distance from center
    const distanceX = e.clientX - centerX
    const distanceY = e.clientY - centerY

    // Apply magnetic effect (30% of distance)
    x.set(distanceX * 0.3)
    y.set(distanceY * 0.3)
  }

  const handleMouseLeave = () => {
    x.set(0)
    y.set(0)
  }

  // Variant styles
  const variantClasses = {
    primary: 'bg-neon-pink text-white hover:shadow-neon-glow focus:ring-neon-pink',
    secondary: 'border-2 border-neon-pink text-neon-pink hover:bg-neon-pink/10 focus:ring-neon-pink',
    ghost: 'text-text-secondary hover:text-text-primary hover:bg-bg-surface focus:ring-text-primary'
  }

  // Size styles
  const sizeClasses = {
    sm: 'px-4 py-2 text-sm',
    md: 'px-8 py-4 text-base',
    lg: 'px-10 py-5 text-lg'
  }

  const baseClasses = 'font-semibold rounded-lg transition-all duration-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-bg-void disabled:opacity-50 disabled:cursor-not-allowed'

  return (
    <motion.button
      ref={ref}
      type={type}
      className={`${baseClasses} ${variantClasses[variant]} ${sizeClasses[size]} ${className} ${icon ? 'flex items-center gap-2' : ''}`}
      style={{ x: springX, y: springY }}
      onClick={onClick}
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      disabled={disabled}
      whileHover={{ scale: disabled ? 1 : 1.02 }}
      whileTap={{ scale: disabled ? 1 : 0.98 }}
      transition={{ duration: 0.2 }}
    >
      {icon && <span>{icon}</span>}
      {children}
    </motion.button>
  )
}

/**
 * MagneticButtonGroup - Container for button groups with proper spacing
 */
export function MagneticButtonGroup({ children, className = '' }: { children: ReactNode; className?: string }) {
  return (
    <div className={`flex flex-col sm:flex-row items-start sm:items-center gap-4 ${className}`}>
      {children}
    </div>
  )
}

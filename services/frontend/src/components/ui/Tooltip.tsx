/**
 * Tooltip Component
 *
 * Provides contextual help and explanations for UI elements.
 * Lightweight and accessible implementation using CSS and HTML.
 */

import { QuestionMarkCircleIcon, InformationCircleIcon } from '@heroicons/react/24/outline'
import { ReactNode, useState } from 'react'

interface TooltipProps {
  /**
   * Content to display in the tooltip
   */
  content: string | ReactNode

  /**
   * Position of the tooltip relative to the trigger
   */
  position?: 'top' | 'bottom' | 'left' | 'right'

  /**
   * Children element that triggers the tooltip
   */
  children: ReactNode

  /**
   * Additional class name for the wrapper
   */
  className?: string

  /**
   * Delay before showing tooltip (ms)
   */
  delay?: number
}

/**
 * Tooltip component with customizable position
 */
export function Tooltip({
  content,
  position = 'top',
  children,
  className = '',
  delay = 200
}: TooltipProps) {
  const [isVisible, setIsVisible] = useState(false)
  const [timeoutId, setTimeoutId] = useState<NodeJS.Timeout | null>(null)

  const handleMouseEnter = () => {
    const id = setTimeout(() => setIsVisible(true), delay)
    setTimeoutId(id)
  }

  const handleMouseLeave = () => {
    if (timeoutId) {
      clearTimeout(timeoutId)
      setTimeoutId(null)
    }
    setIsVisible(false)
  }

  const positionClasses = {
    top: 'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left: 'right-full top-1/2 -translate-y-1/2 mr-2',
    right: 'left-full top-1/2 -translate-y-1/2 ml-2'
  }

  const arrowClasses = {
    top: 'top-full left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-b-transparent border-t-gray-800',
    bottom: 'bottom-full left-1/2 -translate-x-1/2 border-l-transparent border-r-transparent border-t-transparent border-b-gray-800',
    left: 'left-full top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-r-transparent border-l-gray-800',
    right: 'right-full top-1/2 -translate-y-1/2 border-t-transparent border-b-transparent border-l-transparent border-r-gray-800'
  }

  return (
    <div
      className={`relative inline-flex ${className}`}
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      onFocus={handleMouseEnter}
      onBlur={handleMouseLeave}
    >
      {children}

      {/* Tooltip */}
      {isVisible && (
        <div
          className={`absolute z-50 ${positionClasses[position]} pointer-events-none`}
          role="tooltip"
        >
          {/* Tooltip content */}
          <div className="relative bg-gray-800 text-white text-sm rounded-lg px-3 py-2 max-w-xs shadow-lg">
            {content}

            {/* Arrow */}
            <div
              className={`absolute w-0 h-0 border-4 ${arrowClasses[position]}`}
            />
          </div>
        </div>
      )}
    </div>
  )
}

/**
 * Info icon with tooltip - common pattern for help text
 */
export function InfoTooltip({
  content,
  position = 'top',
  className = ''
}: {
  content: string | ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}) {
  return (
    <Tooltip content={content} position={position} className={className}>
      <InformationCircleIcon className="h-4 w-4 text-text-tertiary hover:text-text-secondary cursor-help transition-colors" />
    </Tooltip>
  )
}

/**
 * Question mark icon with tooltip - for more explicit help
 */
export function HelpTooltip({
  content,
  position = 'top',
  className = ''
}: {
  content: string | ReactNode
  position?: 'top' | 'bottom' | 'left' | 'right'
  className?: string
}) {
  return (
    <Tooltip content={content} position={position} className={className}>
      <QuestionMarkCircleIcon className="h-4 w-4 text-text-tertiary hover:text-text-secondary cursor-help transition-colors" />
    </Tooltip>
  )
}

/**
 * Inline text with tooltip - for terms that need explanation
 */
export function TooltipText({
  children,
  tooltip,
  className = ''
}: {
  children: ReactNode
  tooltip: string | ReactNode
  className?: string
}) {
  return (
    <Tooltip content={tooltip} className={className}>
      <span className="border-b border-dotted border-text-tertiary cursor-help">
        {children}
      </span>
    </Tooltip>
  )
}

/**
 * Feature badge with tooltip - for new or beta features
 */
export function FeatureBadge({
  label,
  tooltip,
  variant = 'beta'
}: {
  label?: string
  tooltip: string | ReactNode
  variant?: 'beta' | 'new' | 'experimental'
}) {
  const variantStyles = {
    beta: 'bg-blue-500/20 text-blue-300 border-blue-500/50',
    new: 'bg-green-500/20 text-green-300 border-green-500/50',
    experimental: 'bg-purple-500/20 text-purple-300 border-purple-500/50'
  }

  const labelText = label || variant.toUpperCase()

  return (
    <Tooltip content={tooltip} position="top">
      <span
        className={`inline-flex items-center px-2 py-0.5 text-xs font-medium rounded border ${variantStyles[variant]} cursor-help`}
      >
        {labelText}
      </span>
    </Tooltip>
  )
}

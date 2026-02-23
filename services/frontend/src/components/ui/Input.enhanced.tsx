import { forwardRef, type InputHTMLAttributes } from 'react'
import { motion } from 'framer-motion'

interface EnhancedInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
  hint?: string
  icon?: React.ReactNode
}

/**
 * EnhancedInput - Form input with pink glow focus state
 *
 * Features:
 * - Pink glow on focus (neon aesthetic)
 * - Bottom border animation
 * - Error state with shake animation
 * - Optional icon support
 * - Label animation
 * - Accessible (proper ARIA attributes)
 */
export const EnhancedInput = forwardRef<HTMLInputElement, EnhancedInputProps>(
  ({ label, error, hint, icon, className = '', ...props }, ref) => {
    return (
      <div className="w-full">
        {/* Label */}
        {label && (
          <label
            htmlFor={props.id}
            className="block text-sm font-medium text-text-secondary mb-2"
          >
            {label}
            {props.required && <span className="text-accent-primary ml-1">*</span>}
          </label>
        )}

        {/* Input Container */}
        <div className="relative">
          {/* Icon */}
          {icon && (
            <div className="absolute left-4 top-1/2 -translate-y-1/2 text-text-muted pointer-events-none">
              {icon}
            </div>
          )}

          {/* Input Field */}
          <input
            ref={ref}
            className={`
              w-full px-4 py-3
              ${icon ? 'pl-12' : ''}
              bg-bg-surface
              border border-border-default
              rounded-lg
              text-text-primary placeholder:text-text-muted
              transition-all duration-300

              /* Focus State - Pink Glow */
              focus:outline-none
              focus:border-accent-primary
              focus:shadow-focus-pink
              focus:bg-bg-elevated

              /* Hover State */
              hover:border-border-focus

              /* Error State */
              ${error ? 'border-error focus:border-error focus:shadow-[0_0_0_4px_rgba(239,68,68,0.1)]' : ''}

              /* Disabled State */
              disabled:opacity-50
              disabled:cursor-not-allowed
              disabled:bg-bg-surface

              ${className}
            `}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={
              error ? `${props.id}-error` : hint ? `${props.id}-hint` : undefined
            }
            {...props}
          />

          {/* Bottom Indicator Line (Animates on Focus) */}
          <motion.div
            className="absolute bottom-0 left-0 h-0.5 bg-gradient-to-r from-accent-primary to-accent-teal"
            initial={{ scaleX: 0 }}
            whileFocus={{ scaleX: 1 }}
            transition={{ duration: 0.3 }}
            style={{ transformOrigin: 'left' }}
          />
        </div>

        {/* Error Message */}
        {error && (
          <motion.p
            id={`${props.id}-error`}
            className="mt-2 text-sm text-error flex items-center gap-2"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0, x: [-2, 2, -2, 0] }}
            transition={{
              opacity: { duration: 0.2 },
              y: { duration: 0.2 },
              x: { duration: 0.4, times: [0, 0.33, 0.66, 1] }
            }}
            role="alert"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            {error}
          </motion.p>
        )}

        {/* Hint Text */}
        {hint && !error && (
          <p
            id={`${props.id}-hint`}
            className="mt-2 text-sm text-text-muted font-mono"
          >
            {hint}
          </p>
        )}
      </div>
    )
  }
)

EnhancedInput.displayName = 'EnhancedInput'

/**
 * Textarea variant with same styling
 */
interface EnhancedTextareaProps extends InputHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
  hint?: string
  rows?: number
}

export const EnhancedTextarea = forwardRef<HTMLTextAreaElement, EnhancedTextareaProps>(
  ({ label, error, hint, rows = 4, className = '', ...props }, ref) => {
    return (
      <div className="w-full">
        {label && (
          <label
            htmlFor={props.id}
            className="block text-sm font-medium text-text-secondary mb-2"
          >
            {label}
            {props.required && <span className="text-accent-primary ml-1">*</span>}
          </label>
        )}

        <div className="relative">
          <textarea
            ref={ref}
            rows={rows}
            className={`
              w-full px-4 py-3
              bg-bg-surface
              border border-border-default
              rounded-lg
              text-text-primary placeholder:text-text-muted
              transition-all duration-300
              resize-y

              focus:outline-none
              focus:border-accent-primary
              focus:shadow-focus-pink
              focus:bg-bg-elevated

              hover:border-border-focus

              ${error ? 'border-error focus:border-error focus:shadow-[0_0_0_4px_rgba(239,68,68,0.1)]' : ''}

              disabled:opacity-50
              disabled:cursor-not-allowed

              ${className}
            `}
            aria-invalid={error ? 'true' : 'false'}
            aria-describedby={
              error ? `${props.id}-error` : hint ? `${props.id}-hint` : undefined
            }
            {...props}
          />
        </div>

        {error && (
          <motion.p
            id={`${props.id}-error`}
            className="mt-2 text-sm text-error flex items-center gap-2"
            initial={{ opacity: 0, y: -4 }}
            animate={{ opacity: 1, y: 0 }}
            role="alert"
          >
            <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 20 20">
              <path fillRule="evenodd" d="M18 10a8 8 0 11-16 0 8 8 0 0116 0zm-7 4a1 1 0 11-2 0 1 1 0 012 0zm-1-9a1 1 0 00-1 1v4a1 1 0 102 0V6a1 1 0 00-1-1z" clipRule="evenodd" />
            </svg>
            {error}
          </motion.p>
        )}

        {hint && !error && (
          <p id={`${props.id}-hint`} className="mt-2 text-sm text-text-muted font-mono">
            {hint}
          </p>
        )}
      </div>
    )
  }
)

EnhancedTextarea.displayName = 'EnhancedTextarea'

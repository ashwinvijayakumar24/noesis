import type { InputHTMLAttributes, TextareaHTMLAttributes, SelectHTMLAttributes, ReactNode } from 'react'

// Text Input Component
interface TextInputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string
  error?: string
}

export function TextInput({ label, error, className = '', ...props }: TextInputProps) {
  const baseStyles = 'w-full px-4 py-3 bg-bg-base border border-border-base rounded-md text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors'
  const errorStyles = error ? 'border-error focus:ring-error focus:border-error' : ''

  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-text-secondary mb-2">
          {label}
        </label>
      )}
      <input
        className={`${baseStyles} ${errorStyles} ${className}`}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm text-error">{error}</p>
      )}
    </div>
  )
}

// Textarea Component
interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: string
  error?: string
}

export function Textarea({ label, error, className = '', ...props }: TextareaProps) {
  const baseStyles = 'w-full px-4 py-3 bg-bg-base border border-border-base rounded-md text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors resize-none'
  const errorStyles = error ? 'border-error focus:ring-error focus:border-error' : ''

  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-text-secondary mb-2">
          {label}
        </label>
      )}
      <textarea
        className={`${baseStyles} ${errorStyles} ${className}`}
        {...props}
      />
      {error && (
        <p className="mt-1 text-sm text-error">{error}</p>
      )}
    </div>
  )
}

// Select Component
interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: string
  error?: string
  children: ReactNode
}

export function Select({ label, error, children, className = '', ...props }: SelectProps) {
  const baseStyles = 'w-full px-4 py-3 bg-bg-base border border-border-base rounded-md text-text-primary focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors'
  const errorStyles = error ? 'border-error focus:ring-error focus:border-error' : ''

  return (
    <div className="w-full">
      {label && (
        <label className="block text-sm font-medium text-text-secondary mb-2">
          {label}
        </label>
      )}
      <select
        className={`${baseStyles} ${errorStyles} ${className}`}
        {...props}
      >
        {children}
      </select>
      {error && (
        <p className="mt-1 text-sm text-error">{error}</p>
      )}
    </div>
  )
}

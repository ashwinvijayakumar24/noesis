import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'icon'
export type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children: ReactNode
}

export function Button({ variant = 'primary', size = 'md', children, className = '', ...props }: ButtonProps) {
  const baseStyles = 'font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center'

  const variantStyles = {
    primary: 'bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover',
    secondary: 'bg-surface border border-border-base text-text-secondary rounded-lg hover:bg-surface-hover hover:border-accent-primary',
    ghost: 'text-text-tertiary rounded-md hover:text-text-primary hover:bg-surface-hover',
    icon: 'text-text-tertiary rounded-md hover:text-text-primary hover:bg-surface-hover'
  }

  const sizeStyles = {
    sm: variant === 'icon' ? 'p-1.5' : 'px-4 py-2 text-sm',
    md: variant === 'icon' ? 'p-2' : 'px-6 py-3 text-base',
    lg: variant === 'icon' ? 'p-3' : 'px-8 py-4 text-lg'
  }

  return (
    <button
      className={`${baseStyles} ${variantStyles[variant]} ${sizeStyles[size]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

import type { ButtonHTMLAttributes, ReactNode } from 'react'

export type ButtonVariant = 'primary' | 'secondary' | 'ghost' | 'icon'
export type ButtonSize = 'sm' | 'md' | 'lg'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant
  size?: ButtonSize
  children: ReactNode
}

export function Button({ variant = 'primary', size = 'md', children, className = '', ...props }: ButtonProps) {
  const baseStyles = 'font-medium transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2'

  const variantStyles = {
    primary: 'bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px focus:ring-2 focus:ring-accent-primary',
    secondary: 'bg-bg-surface border border-border-default text-text-primary rounded-md hover:bg-bg-hover hover:border-accent-primary/30 hover:shadow-sm hover:-translate-y-px focus:ring-2 focus:ring-accent-primary',
    ghost: 'text-text-secondary rounded-md hover:text-accent-primary hover:bg-accent-light focus:ring-2 focus:ring-accent-primary',
    icon: 'text-text-secondary rounded-md hover:text-accent-primary hover:bg-accent-light focus:ring-2 focus:ring-accent-primary'
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

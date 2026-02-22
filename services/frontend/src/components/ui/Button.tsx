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
    primary: 'bg-neon-pink text-white font-semibold rounded-xl hover:bg-neon-pink-bright hover:shadow-neon-glow transition-all duration-200',
    secondary: 'bg-bg-surface border-2 border-neon-pink text-neon-pink rounded-xl hover:bg-neon-pink/10 hover:border-neon-pink-bright transition-all duration-200',
    ghost: 'text-text-secondary rounded-lg hover:text-neon-pink hover:bg-neon-pink/10 transition-all duration-200',
    icon: 'text-text-secondary rounded-lg hover:text-neon-pink hover:bg-neon-pink/10 transition-all duration-200'
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

import { ButtonHTMLAttributes, ReactNode } from 'react'

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'ghost'
  children: ReactNode
}

export function Button({ variant = 'primary', children, className = '', ...props }: ButtonProps) {
  const baseStyles = 'font-semibold transition-colors rounded-lg'

  const variants = {
    primary: 'px-8 py-4 bg-accent-primary text-white hover:bg-accent-hover',
    secondary: 'px-8 py-4 border border-neutral-700 text-neutral-300 font-medium hover:border-neutral-600 hover:text-neutral-50',
    ghost: 'px-4 py-2 text-neutral-400 font-medium hover:text-neutral-50'
  }

  return (
    <button
      className={`${baseStyles} ${variants[variant]} ${className}`}
      {...props}
    >
      {children}
    </button>
  )
}

interface NoesisLogoProps {
  size?: 'sm' | 'md' | 'lg' | 'xl'
  className?: string
}

const sizeClasses = {
  sm: 'text-base',
  md: 'text-xl',
  lg: 'text-2xl',
  xl: 'text-3xl',
}

export function NoesisLogo({ size = 'md', className = '' }: NoesisLogoProps) {
  return (
    <span className={`font-heading font-bold tracking-tight text-text-primary ${sizeClasses[size]} ${className}`}>
      Noesis<span className="text-accent-primary">.</span>
    </span>
  )
}

import type { ReactNode } from 'react'
import { XMarkIcon } from '@heroicons/react/24/outline'

// Main Modal Container
interface ModalProps {
  isOpen: boolean
  onClose: () => void
  children: ReactNode
  size?: 'sm' | 'md' | 'lg' | 'xl' | 'full'
  className?: string
}

export function Modal({ isOpen, onClose, children, size = 'xl', className = '' }: ModalProps) {
  if (!isOpen) return null

  const sizeStyles = {
    sm: 'max-w-md',
    md: 'max-w-2xl',
    lg: 'max-w-4xl',
    xl: 'max-w-7xl',
    full: 'max-w-[95vw]'
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-md animate-fade-in"
      onClick={onClose}
    >
      <div
        className={`w-full ${sizeStyles[size]} h-[90vh] bg-bg-surface border-2 border-neon-pink/20 rounded-3xl shadow-neon-glow-lg flex flex-col animate-scale-in ${className}`}
        onClick={(e) => e.stopPropagation()}
      >
        {children}
      </div>
    </div>
  )
}

// Modal Header
interface ModalHeaderProps {
  children: ReactNode
  onClose?: () => void
  className?: string
}

export function ModalHeader({ children, onClose, className = '' }: ModalHeaderProps) {
  return (
    <div className={`px-8 py-6 border-b border-border-base flex items-center justify-between shrink-0 bg-bg-elevated/50 ${className}`}>
      <div className="flex-1">{children}</div>
      {onClose && (
        <button
          onClick={onClose}
          className="p-2 text-text-secondary hover:text-neon-pink hover:bg-neon-pink/10 rounded-lg transition-all duration-200 hover:rotate-90"
          aria-label="Close modal"
        >
          <XMarkIcon className="h-6 w-6" />
        </button>
      )}
    </div>
  )
}

// Modal Title
interface ModalTitleProps {
  children: ReactNode
  className?: string
}

export function ModalTitle({ children, className = '' }: ModalTitleProps) {
  return (
    <h2 className={`text-3xl font-display font-bold bg-gradient-to-r from-neon-pink to-accent-teal bg-clip-text text-transparent ${className}`}>
      {children}
    </h2>
  )
}

// Modal Content
interface ModalContentProps {
  children: ReactNode
  className?: string
}

export function ModalContent({ children, className = '' }: ModalContentProps) {
  return (
    <div className={`flex-1 overflow-y-auto px-6 py-6 ${className}`}>
      {children}
    </div>
  )
}

// Modal Footer
interface ModalFooterProps {
  children: ReactNode
  className?: string
}

export function ModalFooter({ children, className = '' }: ModalFooterProps) {
  return (
    <div className={`px-6 py-5 border-t border-border-subtle flex items-center justify-end gap-4 shrink-0 ${className}`}>
      {children}
    </div>
  )
}

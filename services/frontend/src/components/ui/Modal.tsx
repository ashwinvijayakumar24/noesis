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
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/50 backdrop-blur-sm"
      onClick={onClose}
    >
      <div
        className={`w-full ${sizeStyles[size]} h-[90vh] bg-surface border border-border-base rounded-xl shadow-2xl flex flex-col ${className}`}
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
    <div className={`px-6 py-5 border-b border-border-subtle flex items-center justify-between shrink-0 ${className}`}>
      <div className="flex-1">{children}</div>
      {onClose && (
        <button
          onClick={onClose}
          className="p-2 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded-md transition-colors"
          aria-label="Close modal"
        >
          <XMarkIcon className="h-5 w-5" />
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
    <h2 className={`text-2xl font-serif font-semibold text-text-primary ${className}`}>
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

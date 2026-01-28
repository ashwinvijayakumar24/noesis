import { useEffect } from 'react'
import { CheckCircleIcon, XCircleIcon, InformationCircleIcon, ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'

interface ToastProps {
  type: 'success' | 'error' | 'info' | 'warning'
  title: string
  message?: string
  onClose: () => void
  duration?: number
}

export default function Toast({ type, title, message, onClose, duration = 5000 }: ToastProps) {
  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        onClose()
      }, duration)
      return () => clearTimeout(timer)
    }
  }, [duration, onClose])

  const icons = {
    success: <CheckCircleIcon className="h-6 w-6 text-green-500" />,
    error: <XCircleIcon className="h-6 w-6 text-red-500" />,
    info: <InformationCircleIcon className="h-6 w-6 text-blue-500" />,
    warning: <ExclamationTriangleIcon className="h-6 w-6 text-yellow-500" />
  }

  const borderColors = {
    success: 'border-l-green-500',
    error: 'border-l-red-500',
    info: 'border-l-blue-500',
    warning: 'border-l-yellow-500'
  }

  return (
    <div className={`fixed top-4 right-4 z-50 w-96 bg-surface border border-border-base ${borderColors[type]} border-l-4 rounded-lg shadow-lg animate-slide-in`}>
      <div className="p-4">
        <div className="flex items-start gap-3">
          <div className="shrink-0">
            {icons[type]}
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-sm font-semibold text-text-primary mb-1">
              {title}
            </h4>
            {message && (
              <p className="text-sm text-text-secondary">
                {message}
              </p>
            )}
          </div>
          <button
            onClick={onClose}
            className="shrink-0 p-1 rounded hover:bg-surface-hover transition-colors"
            aria-label="Close notification"
          >
            <XMarkIcon className="h-4 w-4 text-text-tertiary" />
          </button>
        </div>
      </div>
    </div>
  )
}

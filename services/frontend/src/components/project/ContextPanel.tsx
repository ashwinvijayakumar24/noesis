import { useState } from 'react'
import { XMarkIcon as _XMarkIcon, ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline'

interface ContextPanelProps {
  // Will be expanded in Phase 4
}

export default function ContextPanel({}: ContextPanelProps) {
  const [isCollapsed, setIsCollapsed] = useState(false)

  if (isCollapsed) {
    return (
      <div className="w-12 border-l border-border-base bg-surface flex items-start justify-center pt-4">
        <button
          onClick={() => setIsCollapsed(false)}
          className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
          aria-label="Expand context panel"
        >
          <ChevronLeftIcon className="h-5 w-5 text-text-tertiary" />
        </button>
      </div>
    )
  }

  return (
    <div className="w-80 border-l border-border-base bg-surface flex flex-col">
      {/* Header */}
      <div className="flex-shrink-0 p-4 border-b border-border-subtle flex items-center justify-between">
        <h3 className="text-sm font-semibold text-text-primary">Context</h3>
        <button
          onClick={() => setIsCollapsed(true)}
          className="p-1 hover:bg-surface-hover rounded transition-colors"
          aria-label="Collapse context panel"
        >
          <ChevronRightIcon className="h-5 w-5 text-text-tertiary" />
        </button>
      </div>

      {/* Content - Placeholder for Phase 4 */}
      <div className="flex-1 overflow-y-auto p-4">
        <div className="text-center py-12">
          <div className="p-3 bg-surface-hover rounded-lg inline-block mb-3">
            <svg className="h-10 w-10 text-text-muted" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <h4 className="text-sm font-semibold text-text-primary mb-2">
            Smart Context Panel
          </h4>
          <p className="text-xs text-text-tertiary">
            This panel will show relevant information based on your current activity.
          </p>
          <div className="mt-6 text-left bg-bg-base p-3 rounded-lg border border-border-base">
            <h5 className="text-xs font-semibold text-text-secondary mb-2">Phase 4 Features:</h5>
            <ul className="text-xs text-text-tertiary space-y-1">
              <li>• Document details & analysis</li>
              <li>• Chat history & sources</li>
              <li>• Related papers for sections</li>
              <li>• Draft analysis metrics</li>
            </ul>
          </div>
        </div>
      </div>
    </div>
  )
}

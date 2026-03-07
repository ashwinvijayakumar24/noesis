import { useState, useMemo } from 'react'
import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import UnifiedFeedbackCard from './UnifiedFeedbackCard'

interface PriorityGroupProps {
  items: Array<{
    id: string
    type: 'claim' | 'gap' | 'feedback'
    priority: 'high' | 'medium' | 'low'
    content: any
  }>
  onStatusChange: (feedbackId: string, feedbackType: 'claim' | 'gap' | 'feedback', newStatus: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument?: (lineNumber: number) => void
  currentStatus: 'new' | 'saved' | 'dismissed'
}

// Priority configuration for group headers
const PRIORITY_HEADER_CONFIG = {
  high: {
    bg: 'bg-error/5',
    border: 'border-error/20',
    text: 'text-error',
    label: 'High Priority'
  },
  medium: {
    bg: 'bg-warning/5',
    border: 'border-warning/20',
    text: 'text-warning',
    label: 'Medium Priority'
  },
  low: {
    bg: 'bg-bg-elevated',
    border: 'border-border-default',
    text: 'text-text-secondary',
    label: 'Low Priority'
  }
}

export default function PriorityGroup({
  items,
  onStatusChange,
  onViewInDocument,
  currentStatus
}: PriorityGroupProps) {
  // Group items by priority
  const groupedItems = useMemo(() => {
    const groups = {
      high: items.filter(item => item.priority === 'high'),
      medium: items.filter(item => item.priority === 'medium'),
      low: items.filter(item => item.priority === 'low')
    }
    return groups
  }, [items])

  // Collapse state: HIGH expanded by default, MEDIUM/LOW collapsed
  const [collapsed, setCollapsed] = useState({
    high: false,
    medium: true,
    low: true
  })

  const toggleCollapse = (priority: 'high' | 'medium' | 'low') => {
    setCollapsed(prev => ({
      ...prev,
      [priority]: !prev[priority]
    }))
  }

  // Render a priority group
  const renderPriorityGroup = (
    priority: 'high' | 'medium' | 'low',
    items: typeof groupedItems.high
  ) => {
    if (items.length === 0) return null

    const config = PRIORITY_HEADER_CONFIG[priority]
    const isCollapsed = collapsed[priority]

    return (
      <div key={priority} className="mb-4">
        {/* Group Header */}
        <button
          onClick={() => toggleCollapse(priority)}
          className={`
            w-full flex items-center justify-between
            px-4 py-3 rounded-lg border ${config.border} ${config.bg}
            hover:bg-opacity-30 transition-all duration-150
          `}
        >
          <div className="flex items-center space-x-3">
            {/* Expand/Collapse Icon */}
            {isCollapsed ? (
              <ChevronRightIcon className={`w-5 h-5 ${config.text}`} />
            ) : (
              <ChevronDownIcon className={`w-5 h-5 ${config.text}`} />
            )}

            {/* Priority Label */}
            <span className={`text-sm font-sans font-semibold ${config.text}`}>
              {config.label}
            </span>

            {/* Count Badge */}
            <span className={`
              px-2 py-0.5 rounded-full text-xs font-semibold
              bg-bg-void ${config.text} border ${config.border}
            `}>
              {items.length} {items.length === 1 ? 'item' : 'items'}
            </span>
          </div>

          {/* Collapse hint */}
          <span className="text-xs text-text-muted">
            {isCollapsed ? 'Expand' : 'Collapse'}
          </span>
        </button>

        {/* Group Items */}
        {!isCollapsed && (
          <div className="mt-3 space-y-3">
            {items.map(item => (
              <UnifiedFeedbackCard
                key={item.id}
                item={item}
                onStatusChange={onStatusChange}
                onViewInDocument={onViewInDocument}
                currentStatus={currentStatus}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* HIGH priority items (expanded by default) */}
      {renderPriorityGroup('high', groupedItems.high)}

      {/* MEDIUM priority items (collapsed by default) */}
      {renderPriorityGroup('medium', groupedItems.medium)}

      {/* LOW priority items (collapsed by default) */}
      {renderPriorityGroup('low', groupedItems.low)}

      {/* Empty state */}
      {items.length === 0 && (
        <div className="text-center py-8 text-slate-400">
          <p className="text-sm">No feedback items to display</p>
        </div>
      )}
    </div>
  )
}

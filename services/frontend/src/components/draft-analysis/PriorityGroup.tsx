import { useState, useMemo } from 'react'
import { ChevronDownIcon, ChevronRightIcon } from '@heroicons/react/24/outline'
import UnifiedFeedbackCard from './UnifiedFeedbackCard'
import type { PdfCoordinates } from '../DocumentViewer'

interface PriorityGroupProps {
  items: Array<{
    id: string
    type: 'claim' | 'gap' | 'feedback' | 'task'
    priority: 'high' | 'medium' | 'low'
    content: any
  }>
  onStatusChange: (feedbackId: string, feedbackType: 'claim' | 'gap' | 'feedback' | 'task', newStatus: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument?: (payload: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
    pdf_coordinates?: PdfCoordinates
    page_number?: number
    match_confidence?: number
  }) => void
  currentStatus: 'new' | 'saved' | 'dismissed'
  fileType: string
}

// Plain text divider headers — no colored fills, no borders
const PRIORITY_HEADER_CONFIG = {
  high:   { dot: 'bg-error',          text: 'text-error',        label: 'High Priority' },
  medium: { dot: 'bg-warning',        text: 'text-warning',      label: 'Medium Priority' },
  low:    { dot: 'bg-text-muted',     text: 'text-text-muted',   label: 'Low Priority' },
}

export default function PriorityGroup({
  items,
  onStatusChange,
  onViewInDocument,
  currentStatus,
  fileType,
}: PriorityGroupProps) {
  const groupedItems = useMemo(() => ({
    high:   items.filter(item => item.priority === 'high'),
    medium: items.filter(item => item.priority === 'medium'),
    low:    items.filter(item => item.priority === 'low'),
  }), [items])

  // All groups expanded by default
  const [collapsed, setCollapsed] = useState({ high: false, medium: false, low: false })

  const toggleCollapse = (priority: 'high' | 'medium' | 'low') => {
    setCollapsed(prev => ({ ...prev, [priority]: !prev[priority] }))
  }

  const renderPriorityGroup = (priority: 'high' | 'medium' | 'low', groupItems: typeof groupedItems.high) => {
    if (groupItems.length === 0) return null

    const config = PRIORITY_HEADER_CONFIG[priority]
    const isCollapsed = collapsed[priority]

    return (
      <div key={priority} className="mb-5">
        {/* Group header: dot + text divider, fully opaque, no colored background */}
        <button
          onClick={() => toggleCollapse(priority)}
          className="w-full flex items-center gap-2 py-1 mb-3 group"
        >
          <span className={`w-1.5 h-1.5 rounded-full shrink-0 ${config.dot}`} />
          <span className={`text-xs font-semibold uppercase tracking-wider ${config.text}`}>
            {config.label}
          </span>
          <span className="text-xs text-text-muted ml-1">
            {groupItems.length}
          </span>
          <div className="flex-1 h-px bg-border-default ml-1" />
          {isCollapsed
            ? <ChevronRightIcon className="w-3.5 h-3.5 text-text-muted group-hover:text-text-secondary transition-colors" />
            : <ChevronDownIcon className="w-3.5 h-3.5 text-text-muted group-hover:text-text-secondary transition-colors" />
          }
        </button>

        {!isCollapsed && (
          <div className="space-y-2">
            {groupItems.map(item => (
              <UnifiedFeedbackCard
                key={item.id}
                item={item}
                onStatusChange={onStatusChange}
                onViewInDocument={onViewInDocument}
                currentStatus={currentStatus}
                fileType={fileType}
              />
            ))}
          </div>
        )}
      </div>
    )
  }

  return (
    <div>
      {renderPriorityGroup('high', groupedItems.high)}
      {renderPriorityGroup('medium', groupedItems.medium)}
      {renderPriorityGroup('low', groupedItems.low)}

      {items.length === 0 && (
        <div className="text-center py-8">
          <p className="text-sm text-text-muted">No feedback items to display</p>
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import {
  CheckIcon,
  XMarkIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ArrowTopRightOnSquareIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  BeakerIcon
} from '@heroicons/react/24/outline'

interface UnifiedFeedbackCardProps {
  item: {
    id: string
    type: 'claim' | 'gap' | 'feedback'
    priority: 'high' | 'medium' | 'low'
    content: any
  }
  onStatusChange: (feedbackId: string, feedbackType: 'claim' | 'gap' | 'feedback', newStatus: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument?: (lineNumber: number) => void
  currentStatus: 'new' | 'saved' | 'dismissed'
}

// Priority configuration (neon-brutalist)
const PRIORITY_CONFIG = {
  high: {
    accentBorder: 'border-l-4 border-l-accent-primary',
    badge: 'bg-accent-primary/10 text-accent-primary border-accent-primary/30',
    label: 'HIGH PRIORITY'
  },
  medium: {
    accentBorder: 'border-l-4 border-l-warning',
    badge: 'bg-warning/10 text-warning border-warning/30',
    label: 'MEDIUM'
  },
  low: {
    accentBorder: 'border-l-4 border-l-accent-teal',
    badge: 'bg-accent-teal/10 text-accent-teal border-accent-teal/30',
    label: 'LOW'
  }
}

// Type configuration (neon-brutalist)
const TYPE_CONFIG = {
  claim: {
    icon: InformationCircleIcon,
    label: 'CLAIM',
    badge: 'bg-accent-purple/10 text-accent-purple border-accent-purple/30'
  },
  gap: {
    icon: ExclamationTriangleIcon,
    label: 'GAP',
    badge: 'bg-warning/10 text-warning border-warning/30'
  },
  feedback: {
    icon: BeakerIcon,
    label: 'FEEDBACK',
    badge: 'bg-info/10 text-info border-info/30'
  }
}

export default function UnifiedFeedbackCard({
  item,
  onStatusChange,
  onViewInDocument,
  currentStatus
}: UnifiedFeedbackCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const priorityConfig = PRIORITY_CONFIG[item.priority]
  const typeConfig = TYPE_CONFIG[item.type]
  const TypeIcon = typeConfig.icon

  // Extract content based on type
  const getContentText = () => {
    if (item.type === 'claim') {
      return item.content.claim_text
    } else if (item.type === 'gap') {
      return item.content.description
    } else {
      return item.content.feedback_text
    }
  }

  const getSuggestions = () => {
    if (item.type === 'claim') {
      return item.content.existing_citations || []
    } else if (item.type === 'gap') {
      return item.content.suggested_papers || []
    } else {
      return item.content.suggestions || []
    }
  }

  const getMetadata = () => {
    if (item.type === 'claim') {
      return {
        type: item.content.claim_type,
        requiresCitation: item.content.requires_citation,
        importance: item.content.importance_score
      }
    } else if (item.type === 'gap') {
      return {
        gapType: item.content.gap_type,
        hasLiterature: item.content.has_relevant_literature
      }
    } else {
      return {
        feedbackType: item.content.feedback_type,
        severity: item.content.severity
      }
    }
  }

  const contentText = getContentText()
  const suggestions = getSuggestions()
  const metadata = getMetadata()
  const hasLongContent = contentText.length > 200 || suggestions.length > 3

  const handleSave = () => {
    onStatusChange(item.id, item.type, 'saved')
  }

  const handleDismiss = () => {
    onStatusChange(item.id, item.type, 'dismissed')
  }

  const handleViewInDocument = () => {
    const lineNumber = item.content.line_number
    if (lineNumber && onViewInDocument) {
      onViewInDocument(lineNumber)
    }
  }

  return (
    <div className={`group bg-bg-surface rounded-lg border border-border-default ${priorityConfig.accentBorder} p-5 transition-all duration-150 hover:border-accent-primary/30 hover:-translate-y-1 hover:shadow-card-lift`}>
      {/* Header: Type Badge + Priority Badge */}
      <div className="flex items-start justify-between mb-4">
        <div className="flex items-center gap-2">
          {/* Type Badge */}
          <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-semibold uppercase border ${typeConfig.badge}`}>
            <TypeIcon className="w-4 h-4" />
            {typeConfig.label}
          </span>

          {/* Priority Badge */}
          <span className={`px-2.5 py-1 rounded-md text-xs font-mono font-semibold uppercase border ${priorityConfig.badge}`}>
            {priorityConfig.label}
          </span>
        </div>

        {/* View in Document Link */}
        {item.content.line_number && (
          <button
            onClick={handleViewInDocument}
            className="text-xs text-accent-primary hover:text-accent-primary-bright flex items-center gap-1 font-medium transition-colors duration-200"
          >
            <span>Line {item.content.line_number}</span>
            <ArrowTopRightOnSquareIcon className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Content Text */}
      <div className="mb-4">
        <p className={`text-text-primary leading-relaxed ${!isExpanded && hasLongContent ? 'line-clamp-3' : ''}`}>
          {contentText}
        </p>
      </div>

      {/* Metadata */}
      <div className="flex flex-wrap gap-2 mb-4">
        {item.type === 'claim' && (
          <>
            <span className="text-xs font-mono text-text-secondary bg-bg-elevated px-2 py-1 rounded-md border border-border-default">
              Type: {metadata.type}
            </span>
            <span className="text-xs font-mono text-text-secondary bg-bg-elevated px-2 py-1 rounded-md border border-border-default">
              Importance: {(metadata.importance * 100).toFixed(0)}%
            </span>
            {metadata.requiresCitation && (
              <span className="text-xs font-semibold text-warning bg-warning/10 px-2 py-1 rounded-md border border-warning/30">
                Needs Citation
              </span>
            )}
          </>
        )}

        {item.type === 'gap' && (
          <>
            <span className="text-xs font-mono text-text-secondary bg-bg-elevated px-2 py-1 rounded-md border border-border-default">
              Type: {metadata.gapType}
            </span>
            {metadata.hasLiterature && (
              <span className="text-xs font-semibold text-success bg-success/10 px-2 py-1 rounded-md border border-success/30">
                Literature Available
              </span>
            )}
          </>
        )}

        {item.type === 'feedback' && (
          <>
            <span className="text-xs font-mono text-text-secondary bg-bg-elevated px-2 py-1 rounded-md border border-border-default">
              Type: {metadata.feedbackType}
            </span>
            <span className="text-xs font-mono text-text-secondary bg-bg-elevated px-2 py-1 rounded-md border border-border-default">
              Severity: {metadata.severity}
            </span>
          </>
        )}
      </div>

      {/* Suggestions/Citations (Collapsible if long) */}
      {suggestions.length > 0 && (
        <div className="mb-4">
          <div
            className="flex items-center justify-between cursor-pointer group/header"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            <h4 className="text-sm font-sans font-semibold text-text-primary">
              {item.type === 'claim' ? 'Existing Citations' : 'Suggestions'}
              <span className="ml-2 text-text-muted font-mono text-xs">({suggestions.length})</span>
            </h4>
            {hasLongContent && (
              <button className="text-text-secondary group-hover/header:text-accent-primary transition-colors duration-200">
                {isExpanded ? (
                  <ChevronUpIcon className="w-5 h-5" />
                ) : (
                  <ChevronDownIcon className="w-5 h-5" />
                )}
              </button>
            )}
          </div>

          {(isExpanded || !hasLongContent) && (
            <ul className="mt-3 space-y-2">
              {suggestions.slice(0, isExpanded ? undefined : 3).map((suggestion: any, idx: number) => (
                <li key={idx} className="text-sm text-text-secondary pl-4 border-l-2 border-accent-primary/30 hover:border-accent-primary transition-colors duration-200">
                  {typeof suggestion === 'string' ? suggestion : suggestion.title || suggestion.citation_string || JSON.stringify(suggestion)}
                </li>
              ))}
              {!isExpanded && suggestions.length > 3 && (
                <li className="text-sm text-text-muted pl-4 italic">
                  +{suggestions.length - 3} more...
                </li>
              )}
            </ul>
          )}
        </div>
      )}

      {/* Expand/Collapse for long content */}
      {hasLongContent && !suggestions.length && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-sm text-accent-primary hover:text-accent-primary-bright mb-4 flex items-center gap-1.5 font-medium transition-colors duration-200"
        >
          <span>{isExpanded ? 'Show less' : 'Show more'}</span>
          {isExpanded ? (
            <ChevronUpIcon className="w-4 h-4" />
          ) : (
            <ChevronDownIcon className="w-4 h-4" />
          )}
        </button>
      )}

      {/* Action Buttons (only show for 'new' status) */}
      {currentStatus === 'new' && (
        <div className="flex items-center gap-3 pt-4 border-t border-border-default opacity-0 group-hover:opacity-100 transition-opacity duration-150">
          <button
            onClick={handleSave}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-success/10 text-success border border-success/30 hover:bg-success/20 hover:border-success/50 transition-all duration-200"
          >
            <CheckIcon className="w-5 h-5" />
            <span>Mark as Addressed</span>
          </button>

          <button
            onClick={handleDismiss}
            className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg text-sm font-semibold bg-bg-elevated text-text-secondary border border-border-default hover:bg-bg-hover hover:text-text-primary transition-all duration-200"
          >
            <XMarkIcon className="w-5 h-5" />
            <span>Dismiss</span>
          </button>
        </div>
      )}

      {/* Status indicator for saved/dismissed */}
      {currentStatus !== 'new' && (
        <div className="pt-4 border-t border-border-default">
          <span className={`text-sm font-semibold ${currentStatus === 'saved' ? 'text-success' : 'text-text-muted'}`}>
            {currentStatus === 'saved' ? '✓ Addressed' : '✕ Dismissed'}
          </span>
        </div>
      )}
    </div>
  )
}

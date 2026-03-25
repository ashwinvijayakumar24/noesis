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

// Left border accent — the card border communicates priority, no colored box needed
const PRIORITY_CONFIG = {
  high:   { accentBorder: 'border-l-2 border-l-error',         label: 'High',   labelColor: 'text-error' },
  medium: { accentBorder: 'border-l-2 border-l-warning',       label: 'Medium', labelColor: 'text-warning' },
  low:    { accentBorder: 'border-l-2 border-l-border-subtle', label: 'Low',    labelColor: 'text-text-muted' },
}

// Type indicator — icon + plain text label, no colored background
const TYPE_CONFIG = {
  claim:    { icon: InformationCircleIcon, label: 'Claim',    color: 'text-text-secondary' },
  gap:      { icon: ExclamationTriangleIcon, label: 'Gap',    color: 'text-text-secondary' },
  feedback: { icon: BeakerIcon,            label: 'Feedback', color: 'text-text-secondary' },
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

  const getContentText = () => {
    if (item.type === 'claim') return item.content.claim_text
    if (item.type === 'gap') return item.content.description
    return item.content.feedback_text
  }

  const getSuggestions = () => {
    if (item.type === 'claim') return item.content.existing_citations || []
    if (item.type === 'gap') return item.content.suggested_papers || []
    return item.content.suggestions || []
  }

  const getMetadata = () => {
    if (item.type === 'claim') return {
      type: item.content.claim_type,
      requiresCitation: item.content.requires_citation,
      importance: item.content.importance_score,
    }
    if (item.type === 'gap') return {
      gapType: item.content.gap_type,
      hasLiterature: item.content.has_relevant_literature,
    }
    return {
      feedbackType: item.content.feedback_type,
      severity: item.content.severity,
    }
  }

  const contentText = getContentText()
  const suggestions = getSuggestions()
  const metadata = getMetadata()
  const hasLongContent = contentText.length > 200 || suggestions.length > 3

  return (
    <div className={`bg-bg-surface rounded-lg border border-border-default ${priorityConfig.accentBorder} p-4 transition-colors duration-150 hover:border-border-subtle`}>

      {/* Header: type + priority as plain text, no colored boxes */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <TypeIcon className={`w-3.5 h-3.5 ${typeConfig.color} shrink-0`} />
          <span className="text-xs font-semibold text-text-secondary">{typeConfig.label}</span>
          <span className="text-text-muted text-xs">·</span>
          <span className={`text-xs font-medium ${priorityConfig.labelColor}`}>{priorityConfig.label}</span>
        </div>

        {item.content.line_number && (
          <button
            onClick={() => item.content.line_number && onViewInDocument?.(item.content.line_number)}
            className="text-xs text-text-muted hover:text-text-primary flex items-center gap-1 transition-colors duration-150"
          >
            <span>Line {item.content.line_number}</span>
            <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" />
          </button>
        )}
      </div>

      {/* Content text */}
      <div className="mb-3">
        <p className={`text-sm text-text-primary leading-relaxed ${!isExpanded && hasLongContent ? 'line-clamp-3' : ''}`}>
          {contentText}
        </p>
      </div>

      {/* Metadata — inline plain text, no chip boxes */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-xs text-text-muted">
        {item.type === 'claim' && (
          <>
            <span>Type: <span className="text-text-secondary">{metadata.type}</span></span>
            <span className="text-border-subtle">·</span>
            <span>Importance: <span className="text-text-secondary">{((metadata.importance ?? 0) * 100).toFixed(0)}%</span></span>
            {metadata.requiresCitation && (
              <>
                <span className="text-border-subtle">·</span>
                <span className="text-warning font-medium">Needs citation</span>
              </>
            )}
          </>
        )}

        {item.type === 'gap' && (
          <>
            <span>Type: <span className="text-text-secondary">{metadata.gapType}</span></span>
            {metadata.hasLiterature && (
              <>
                <span className="text-border-subtle">·</span>
                <span className="text-success font-medium">Literature available</span>
              </>
            )}
          </>
        )}

        {item.type === 'feedback' && (
          <>
            <span>Type: <span className="text-text-secondary">{metadata.feedbackType}</span></span>
            <span className="text-border-subtle">·</span>
            <span>Severity: <span className="text-text-secondary">{metadata.severity}</span></span>
          </>
        )}
      </div>

      {/* Citation needed hint — shown when claim requires citation but has none */}
      {item.type === 'claim' && metadata.requiresCitation && suggestions.length === 0 && (
        <div className="mb-3 pl-3 border-l border-warning text-xs text-text-muted">
          <span className="text-warning font-medium">Citation needed</span>
          {' '}— Search your library or use Paper Discovery to find supporting references for this claim.
        </div>
      )}

      {/* Suggestions / Citations */}
      {suggestions.length > 0 && (
        <div className="mb-3">
          <button
            className="flex items-center gap-1.5 mb-2 group/toggle"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            <h4 className="text-xs font-semibold text-text-secondary group-hover/toggle:text-text-primary transition-colors">
              {item.type === 'claim' ? 'Existing citations' : 'Suggestions'}
            </h4>
            <span className="text-text-muted text-xs">({suggestions.length})</span>
            {hasLongContent && (
              isExpanded
                ? <ChevronUpIcon className="w-3.5 h-3.5 text-text-muted" />
                : <ChevronDownIcon className="w-3.5 h-3.5 text-text-muted" />
            )}
          </button>

          {(isExpanded || !hasLongContent) && (
            <ul className="space-y-2">
              {suggestions.slice(0, isExpanded ? undefined : 3).map((suggestion: any, idx: number) => (
                <li key={idx} className="pl-3 border-l border-border-subtle">
                  {typeof suggestion === 'string' ? (
                    <span className="text-xs text-text-secondary">{suggestion}</span>
                  ) : (
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-start gap-1.5 flex-wrap">
                        <span className="text-xs text-text-primary font-medium leading-snug">
                          {suggestion.title || suggestion.citation_string || 'Untitled'}
                        </span>
                        {suggestion.external && (
                          <span className={`text-xs px-1.5 py-0.5 rounded font-medium shrink-0 ${
                            suggestion.source === 'semantic_scholar'
                              ? 'bg-indigo-500/15 text-indigo-400'
                              : 'bg-teal-500/15 text-teal-400'
                          }`}>
                            {suggestion.source === 'semantic_scholar' ? 'Semantic Scholar' : 'OpenAlex'}
                          </span>
                        )}
                      </div>
                      {(suggestion.authors || suggestion.year) && (
                        <span className="text-xs text-text-muted">
                          {suggestion.authors
                            ? (Array.isArray(suggestion.authors) ? suggestion.authors.slice(0, 2).join(', ') + (suggestion.authors.length > 2 ? ' et al.' : '') : suggestion.authors)
                            : ''}
                          {suggestion.authors && suggestion.year ? ' · ' : ''}
                          {suggestion.year}
                        </span>
                      )}
                      {(suggestion.open_access_url || suggestion.url) && (
                        <a
                          href={suggestion.open_access_url || suggestion.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-accent-primary hover:underline flex items-center gap-1 mt-0.5 w-fit"
                        >
                          <span>{suggestion.open_access_url ? 'View PDF' : 'View paper'}</span>
                          <ArrowTopRightOnSquareIcon className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                  )}
                </li>
              ))}
              {!isExpanded && suggestions.length > 3 && (
                <li className="text-xs text-text-muted pl-3 italic">+{suggestions.length - 3} more</li>
              )}
            </ul>
          )}
        </div>
      )}

      {/* Expand/collapse for long content without suggestions */}
      {hasLongContent && !suggestions.length && (
        <button
          onClick={() => setIsExpanded(!isExpanded)}
          className="text-xs text-text-muted hover:text-text-primary mb-3 flex items-center gap-1 transition-colors duration-150"
        >
          {isExpanded ? <ChevronUpIcon className="w-3.5 h-3.5" /> : <ChevronDownIcon className="w-3.5 h-3.5" />}
          <span>{isExpanded ? 'Show less' : 'Show more'}</span>
        </button>
      )}

      {/* Action buttons — solid, opaque, no translucent fills */}
      {currentStatus === 'new' && (
        <div className="flex items-center gap-2 pt-3 border-t border-border-default">
          <button
            onClick={() => onStatusChange(item.id, item.type, 'saved')}
            className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-success text-white hover:opacity-90 transition-opacity duration-150"
          >
            <CheckIcon className="w-3.5 h-3.5" />
            <span>Mark addressed</span>
          </button>

          <button
            onClick={() => onStatusChange(item.id, item.type, 'dismissed')}
            className="flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-bg-elevated text-text-secondary hover:text-text-primary border border-border-default hover:border-border-subtle transition-colors duration-150"
          >
            <XMarkIcon className="w-3.5 h-3.5" />
            <span>Dismiss</span>
          </button>
        </div>
      )}

      {/* Status indicator for saved/dismissed */}
      {currentStatus !== 'new' && (
        <div className="pt-3 border-t border-border-default">
          <span className={`text-xs font-semibold ${currentStatus === 'saved' ? 'text-success' : 'text-text-muted'}`}>
            {currentStatus === 'saved' ? '✓ Addressed' : '✕ Dismissed'}
          </span>
        </div>
      )}
    </div>
  )
}

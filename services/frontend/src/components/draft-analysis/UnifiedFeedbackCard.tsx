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

// Left border accent — the card border communicates priority
const PRIORITY_CONFIG = {
  high:   { accentBorder: 'border-l-2 border-l-error',         label: 'High',   labelColor: 'text-error' },
  medium: { accentBorder: 'border-l-2 border-l-warning',       label: 'Medium', labelColor: 'text-warning' },
  low:    { accentBorder: 'border-l-2 border-l-border-subtle', label: 'Low',    labelColor: 'text-text-muted' },
}

const TYPE_CONFIG = {
  claim:    { icon: InformationCircleIcon, label: 'Claim',    color: 'text-text-secondary' },
  gap:      { icon: ExclamationTriangleIcon, label: 'Gap',    color: 'text-text-secondary' },
  feedback: { icon: BeakerIcon,            label: 'Feedback', color: 'text-text-secondary' },
}

// A1: Human-readable labels for feedback_type (strength → null = don't show type chip)
const FEEDBACK_TYPE_LABEL: Record<string, string | null> = {
  strength:   null,
  weakness:   'Needs Work',
  question:   'Question from Reviewer',
  suggestion: 'Suggestion',
  structural: 'Structural Issue',
  general:    'Feedback',
}

// A1: Human-readable labels for severity
const SEVERITY_CONFIG: Record<string, { label: string; className: string } | null> = {
  critical:   { label: 'Critical', className: 'text-error font-semibold' },
  major:      { label: 'Major',    className: 'text-warning font-semibold' },
  minor:      { label: 'Minor',    className: 'text-info' },
  suggestion: null,  // omit — already conveyed by type label
}

// A4: Parse suggested citations from supporting_literature JSONB
// Handles both old array format and new { top_match, suggested_citations } object format
function parseSuggestedCitations(content: any): Array<{ display: string; source: string }> {
  const supLit = content?.supporting_literature
  console.log('[CitationChips] supporting_literature raw:', supLit)

  if (!supLit) {
    console.log('[CitationChips] No supporting_literature field — claim_id:', content?.id)
    return []
  }

  if (Array.isArray(supLit)) {
    // Old format: array of library citation matches
    const results = supLit
      .filter((s: any) => s.similarity >= 0.5 && (s.display || s.document_title))
      .map((s: any) => ({
        display: s.display || s.document_title,
        source: 'library',
      }))
    console.log('[CitationChips] Old array format, parsed:', results.length, 'citations')
    return results
  }

  // New format (after B2): { top_match: {...}, suggested_citations: [...] }
  const suggestedCits = (supLit.suggested_citations || []).map((s: any) => ({
    display: s.display || `${s.title} (${s.year || ''})`.trim(),
    source: s.source || 'library',
  }))
  // Fallback: if no suggested_citations but top_match has a display, show it as a library chip
  if (suggestedCits.length === 0 && supLit.top_match?.display) {
    console.log('[CitationChips] New format, using top_match fallback:', supLit.top_match.display)
    return [{ display: supLit.top_match.display, source: 'library' }]
  }
  console.log('[CitationChips] New format, suggested_citations:', suggestedCits.length)
  return suggestedCits
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

  // A2: Detect strength items — they get special treatment
  const isStrength = item.type === 'feedback' && item.content.feedback_type === 'strength'

  // A2: Strengths get green left border instead of priority-based border
  const borderAccentClass = isStrength
    ? 'border-l-2 border-l-success'
    : priorityConfig.accentBorder

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
      type: item.content.claim_type as string,
      requiresCitation: item.content.requires_citation as boolean,
      importance: item.content.importance_score as number,
    }
    if (item.type === 'gap') return {
      gapType: item.content.gap_type as string,
      hasLiterature: item.content.has_relevant_literature as boolean,
    }
    return {
      feedbackType: item.content.feedback_type as string,
      severity: item.content.severity as string,
    }
  }

  const contentText = getContentText()
  const suggestions = getSuggestions()
  const metadata = getMetadata()
  const hasLongContent = contentText.length > 200 || suggestions.length > 3

  // A4: Get citation chips from supporting_literature
  const suggestedCitations = item.type === 'claim' ? parseSuggestedCitations(item.content) : []

  return (
    <div className={`bg-bg-surface rounded-lg border border-border-default ${borderAccentClass} p-4 transition-colors duration-150 hover:border-border-subtle`}>

      {/* Header: type + priority */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2">
          <TypeIcon className={`w-3.5 h-3.5 ${typeConfig.color} shrink-0`} />
          <span className="text-xs font-semibold text-text-secondary">{typeConfig.label}</span>
          {!isStrength && (
            <>
              <span className="text-text-muted text-xs">·</span>
              <span className={`text-xs font-medium ${priorityConfig.labelColor}`}>{priorityConfig.label}</span>
            </>
          )}
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

      {/* Metadata — plain text, no debug enum labels */}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mb-3 text-xs text-text-muted">
        {item.type === 'claim' && (
          <>
            <span className="capitalize text-text-secondary">{metadata.type}</span>
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

        {/* A1: Feedback type/severity shown as human-readable labels, not raw enums */}
        {item.type === 'feedback' && (() => {
          const typeLabel = FEEDBACK_TYPE_LABEL[metadata.feedbackType as string] ?? metadata.feedbackType
          const severityInfo = metadata.severity ? SEVERITY_CONFIG[metadata.severity as string] : null
          if (!typeLabel && !severityInfo) return null
          return (
            <>
              {typeLabel && <span className="text-text-secondary">{typeLabel}</span>}
              {typeLabel && severityInfo && <span className="text-border-subtle">·</span>}
              {severityInfo && <span className={severityInfo.className}>{severityInfo.label}</span>}
            </>
          )
        })()}
      </div>

      {/* A4: Citation needed — show specific paper chips instead of generic text */}
      {item.type === 'claim' && metadata.requiresCitation && suggestions.length === 0 && (
        <div className="mb-3 pl-3 border-l border-warning">
          <span className="text-xs text-warning font-medium block mb-1.5">Citation needed</span>
          {suggestedCitations.length > 0 ? (
            <div className="flex flex-wrap gap-1.5">
              {suggestedCitations.slice(0, 4).map((cit, i) => (
                <span
                  key={i}
                  className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                    cit.source === 'library'
                      ? 'bg-teal-500/15 text-teal-400'
                      : 'bg-indigo-500/15 text-indigo-400'
                  }`}
                >
                  {cit.display}
                </span>
              ))}
            </div>
          ) : (
            <span className="text-xs text-text-muted italic">
              No citation match found in your library.
            </span>
          )}
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

      {/* A2: Action buttons — not shown for strength items (they're informational, not actionable) */}
      {currentStatus === 'new' && !isStrength && (
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

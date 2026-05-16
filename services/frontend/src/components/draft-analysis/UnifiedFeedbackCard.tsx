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
import type { PdfCoordinates } from '../DocumentViewer'
import MarkdownText from './MarkdownText'

interface UnifiedFeedbackCardProps {
  item: {
    id: string
    type: 'claim' | 'gap' | 'feedback'
    priority: 'high' | 'medium' | 'low'
    issueCategory?: string
    content: any
  }
  onStatusChange: (feedbackId: string, feedbackType: 'claim' | 'gap' | 'feedback', newStatus: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument?: (payload: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
    pdf_coordinates?: PdfCoordinates
    match_confidence?: number
  }) => void
  currentStatus: 'new' | 'saved' | 'dismissed'
  fileType: string
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

// Human-readable labels for feedback_type
const FEEDBACK_TYPE_LABEL: Record<string, string | null> = {
  strength:   null,
  weakness:   'Needs Work',
  question:   'Question from Reviewer',
  suggestion: 'Suggestion',
  structural: 'Structural Issue',
  general:    'Feedback',
}

// Human-readable labels for severity
const SEVERITY_CONFIG: Record<string, { label: string; className: string; badgeClass: string } | null> = {
  critical:   { label: 'Critical', className: 'text-error font-semibold', badgeClass: 'bg-error/10 text-error border-error/20' },
  major:      { label: 'Major',    className: 'text-warning font-semibold', badgeClass: 'bg-warning/10 text-warning border-warning/20' },
  minor:      { label: 'Minor',    className: 'text-info', badgeClass: 'bg-info/10 text-info border-info/20' },
  suggestion: null,
}

// Citation source color coding
const CITATION_SOURCE_CONFIG: Record<string, { bg: string; text: string; label: string }> = {
  library:           { bg: 'bg-teal-500/15',   text: 'text-teal-400',   label: 'Library' },
  manual_upload:     { bg: 'bg-teal-500/15',   text: 'text-teal-400',   label: 'Library' },
  bibtex_import:     { bg: 'bg-violet-500/15',  text: 'text-violet-400', label: 'BibTeX' },
  semantic_scholar:  { bg: 'bg-indigo-500/15', text: 'text-indigo-400', label: 'Semantic Scholar' },
  openalex:          { bg: 'bg-amber-500/15',  text: 'text-amber-400',  label: 'OpenAlex' },
}

const META_LABEL_CLASS = 'text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted'
const META_VALUE_CLASS = 'text-xs font-medium text-text-secondary'
const META_STATUS_READY_CLASS = 'text-xs font-medium text-accent-primary hover:text-accent-primary/80'

// Parse suggested citations from supporting_literature JSONB
function parseSuggestedCitations(content: any): Array<{ display: string; source: string; similarity?: number }> {
  const supLit = content?.supporting_literature
  if (!supLit) return []

  if (Array.isArray(supLit)) {
    return supLit
      .filter((s: any) => s.similarity >= 0.5 && (s.display || s.document_title))
      .map((s: any) => ({
        display: s.display || s.document_title,
        source: s.source || 'library',
        similarity: s.similarity,
      }))
  }

  // New format: { top_match: {...}, suggested_citations: [...] }
  const suggestedCits = (supLit.suggested_citations || []).map((s: any) => ({
    display: s.display || `${s.title} (${s.year || ''})`.trim(),
    source: s.source || 'library',
    similarity: s.similarity,
  }))
  if (suggestedCits.length === 0 && supLit.top_match?.display) {
    return [{ display: supLit.top_match.display, source: 'library', similarity: supLit.top_match.similarity }]
  }
  return suggestedCits
}

export default function UnifiedFeedbackCard({
  item,
  onStatusChange,
  onViewInDocument,
  currentStatus,
  fileType,
}: UnifiedFeedbackCardProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const priorityConfig = PRIORITY_CONFIG[item.priority]
  const typeConfig = TYPE_CONFIG[item.type]
  const TypeIcon = typeConfig.icon

  // Detect strength items — they get special treatment
  const isStrength = item.type === 'feedback' && item.content.feedback_type === 'strength'

  // Strengths get green left border instead of priority-based border
  const borderAccentClass = isStrength
    ? 'border-l-2 border-l-success'
    : priorityConfig.accentBorder

  // Detect unsupported claims
  const isUnsupportedClaim = item.type === 'claim' &&
    item.content.requires_citation &&
    item.content.importance_score >= 0.65

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

  // Citation chips from supporting_literature
  const suggestedCitations = item.type === 'claim' ? parseSuggestedCitations(item.content) : []
  const isPdf = fileType === 'application/pdf' || fileType === 'pdf'
  const hasReliablePdfAnchor = Boolean(item.content.pdf_coordinates)
  const canOpenDocument = Boolean(onViewInDocument) && (isPdf ? hasReliablePdfAnchor : Boolean(item.content.line_number))
  const viewPayload = {
    line_number: item.content.line_number,
    content_text: contentText,
    text_snippet: item.content.text_snippet,
    section_type: item.content.section_type ?? item.content.section_reference,
    section_location: item.content.section_location,
    pdf_coordinates: item.content.pdf_coordinates,
    match_confidence: item.content.match_confidence,
  }

  return (
    <div className={`bg-bg-surface rounded-lg border border-border-default ${borderAccentClass} p-4 transition-colors duration-150 hover:border-border-subtle`}>

      {/* Header: type badge + severity badge + priority */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Type badge */}
          {isUnsupportedClaim ? (
            <span className="px-2 py-0.5 rounded text-xs font-semibold bg-error/10 text-error border border-error/20">
              Unsupported Claim
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <TypeIcon className={`w-3.5 h-3.5 ${typeConfig.color} shrink-0`} />
              <span className="text-xs font-semibold text-text-secondary">{typeConfig.label}</span>
            </span>
          )}

          {/* Severity badge for feedback */}
          {item.type === 'feedback' && !isStrength && (() => {
            const severityInfo = metadata.severity ? SEVERITY_CONFIG[metadata.severity as string] : null
            if (!severityInfo) return null
            return (
              <span className={`px-2 py-0.5 rounded text-xs font-semibold border ${severityInfo.badgeClass}`}>
                {severityInfo.label}
              </span>
            )
          })()}

          {/* Priority (for non-unsupported claims) */}
          {!isStrength && !isUnsupportedClaim && (
            <>
              <span className="text-text-muted text-xs">·</span>
              <span className={`text-xs font-medium ${priorityConfig.labelColor}`}>{priorityConfig.label}</span>
            </>
          )}
        </div>

        {/* Metadata summary */}
        <div className="flex items-start gap-4 shrink-0 ml-3 border-l border-border-default pl-4">
          {item.content.section_type && (
            <div className="min-w-[92px]">
              <div className={META_LABEL_CLASS}>Section</div>
              <div className={`${META_VALUE_CLASS} mt-1 capitalize`}>
                {(item.content.section_type || '').replace(/_/g, ' ')}
              </div>
            </div>
          )}
          {canOpenDocument && (
            <div className="min-w-[148px]">
              <div className={META_LABEL_CLASS}>Location</div>
              <div className="mt-1">
                <button
                  onClick={() => onViewInDocument?.(viewPayload)}
                  className={`inline-flex items-center gap-1 ${META_STATUS_READY_CLASS} transition-colors duration-150`}
                >
                  <span>
                    {isPdf
                      ? `Page ${item.content.pdf_coordinates?.page}`
                      : `Line ${item.content.line_number}`}
                  </span>
                  <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Content text */}
      <div className="mb-3">
        <MarkdownText
          as="p"
          text={contentText}
          className={`text-sm text-text-primary leading-relaxed ${!isExpanded && hasLongContent ? 'line-clamp-3' : ''}`}
        />
      </div>

      {/* Metadata row */}
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
            {metadata.hasLiterature && (
              <>
                <span className="text-success font-medium">Literature available</span>
              </>
            )}
          </>
        )}

        {item.type === 'feedback' && (() => {
          const typeLabel = FEEDBACK_TYPE_LABEL[metadata.feedbackType as string] ?? metadata.feedbackType
          if (!typeLabel) return null
          return <span className="text-text-secondary">{typeLabel}</span>
        })()}
      </div>

      {/* Citation chips with source color coding */}
      {item.type === 'claim' && suggestedCitations.length > 0 && (
        <div className="mb-3 pl-3 border-l border-accent-primary/30">
          <span className="text-xs text-accent-primary font-medium block mb-1.5">Recommended support</span>
          <div className="space-y-2">
            {suggestedCitations.slice(0, 2).map((cit, i) => {
              const sourceConfig = CITATION_SOURCE_CONFIG[cit.source] || CITATION_SOURCE_CONFIG['library']
              return (
                <div
                  key={i}
                  className="flex items-start justify-between gap-3 rounded-md border border-border-default bg-bg-elevated px-3 py-2"
                  title={`${sourceConfig.label}${cit.similarity ? ` · ${Math.round(cit.similarity * 100)}% match` : ''}`}
                >
                  <span className="text-xs font-medium leading-snug text-text-primary">{cit.display}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {cit.similarity && cit.similarity >= 0.7 && (
                      <span className="text-[11px] font-medium text-text-muted">{Math.round(cit.similarity * 100)}%</span>
                    )}
                    <span className={`text-[11px] font-semibold uppercase tracking-wide ${sourceConfig.text}`}>
                      {sourceConfig.label}
                    </span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      )}

      {item.type === 'claim' && metadata.requiresCitation && suggestions.length === 0 && suggestedCitations.length === 0 && (
        <div className="mb-3 pl-3 border-l border-warning">
          <span className="text-xs text-warning font-medium block mb-1.5">Citation needed</span>
          <span className="text-xs text-text-muted italic">
            No citation match found in your library.
          </span>
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
              {suggestions.slice(0, isExpanded ? undefined : 2).map((suggestion: any, idx: number) => (
                <li key={idx} className="pl-3 border-l border-border-subtle">
                  {typeof suggestion === 'string' ? (
                    <MarkdownText text={suggestion} className="text-xs text-text-secondary" />
                  ) : (
                    <div className="flex flex-col gap-0.5">
                      <div className="flex items-start gap-1.5 flex-wrap">
                        <span className="text-xs text-text-primary font-medium leading-snug">
                          {suggestion.title || suggestion.citation_string || 'Untitled'}
                        </span>
                        {suggestion.external && (() => {
                          const source = suggestion.source || 'semantic_scholar'
                          const sourceConfig = CITATION_SOURCE_CONFIG[source] || CITATION_SOURCE_CONFIG['library']
                          return (
                            <span className={`text-[11px] font-semibold uppercase tracking-wide shrink-0 ${sourceConfig.text}`}>
                              {sourceConfig.label}
                            </span>
                          )
                        })()}
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
              {!isExpanded && suggestions.length > 2 && (
                <li className="text-xs text-text-muted pl-3 italic">+{suggestions.length - 2} more</li>
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

      {/* Action buttons — not shown for strength items */}
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

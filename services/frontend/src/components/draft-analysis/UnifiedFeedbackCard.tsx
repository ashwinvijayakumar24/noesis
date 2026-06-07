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
    type: 'claim' | 'gap' | 'feedback' | 'task'
    priority: 'high' | 'medium' | 'low'
    issueCategory?: string
    content: any
  }
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

const PRIORITY_CONFIG = {
  high:   { label: 'High',   labelColor: 'text-error' },
  medium: { label: 'Medium', labelColor: 'text-warning' },
  low:    { label: 'Low',    labelColor: 'text-text-muted' },
}

const TYPE_CONFIG = {
  claim:    { icon: InformationCircleIcon, label: 'Claim',    color: 'text-text-secondary' },
  gap:      { icon: ExclamationTriangleIcon, label: 'Gap',    color: 'text-text-secondary' },
  feedback: { icon: BeakerIcon,            label: 'Feedback', color: 'text-text-secondary' },
  task:     { icon: BeakerIcon,            label: 'Revision Task', color: 'text-text-secondary' },
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
  critical:   { label: 'Critical', className: 'text-error font-semibold', badgeClass: 'border-border-strong text-error' },
  major:      { label: 'Major',    className: 'text-warning font-semibold', badgeClass: 'border-border-strong text-warning' },
  minor:      { label: 'Minor',    className: 'text-info', badgeClass: 'border-border-default text-text-secondary' },
  suggestion: null,
}

// Source labels stay neutral; provenance matters more than decorative color here.
const CITATION_SOURCE_CONFIG: Record<string, { text: string; label: string }> = {
  library:           { text: 'text-text-secondary', label: 'Library' },
  manual_upload:     { text: 'text-text-secondary', label: 'Library' },
  bibtex_import:     { text: 'text-text-secondary', label: 'BibTeX' },
  semantic_scholar:  { text: 'text-text-secondary', label: 'Semantic Scholar' },
  openalex:          { text: 'text-text-secondary', label: 'OpenAlex' },
  pubmed:            { text: 'text-text-secondary', label: 'PubMed' },
  arxiv:             { text: 'text-text-secondary', label: 'arXiv' },
}

function citationSourceConfig(source?: string) {
  const sourceKey = String(source || 'library').trim().toLowerCase()
  return CITATION_SOURCE_CONFIG[sourceKey] || CITATION_SOURCE_CONFIG['library']
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
  const [isExpanded, setIsExpanded] = useState(item.type === 'task')

  const priorityConfig = PRIORITY_CONFIG[item.priority]
  const typeConfig = TYPE_CONFIG[item.type]
  const TypeIcon = typeConfig.icon

  // Detect strength items — they get special treatment
  const isStrength = item.type === 'feedback' && item.content.feedback_type === 'strength'

  // Detect unsupported claims
  const isUnsupportedClaim = item.type === 'claim' &&
    item.content.requires_citation &&
    item.content.importance_score >= 0.65

  const getContentText = () => {
    if (item.type === 'claim') return item.content.claim_text
    if (item.type === 'gap') return item.content.description
    if (item.type === 'task') return item.content.problem
    return item.content.feedback_text
  }

  const getSuggestions = () => {
    if (item.type === 'claim') return item.content.existing_citations || []
    if (item.type === 'gap') return item.content.suggested_papers || []
    if (item.type === 'task') return []
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
    if (item.type === 'task') return {
      feedbackType: item.content.task_type as string,
      severity: item.content.severity as string,
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
  const suggestedSources = item.type === 'task' && Array.isArray(item.content.suggested_sources)
    ? item.content.suggested_sources
    : []
  const isPdf = fileType === 'application/pdf' || fileType === 'pdf'
  const hasReliablePdfAnchor = Boolean(item.content.pdf_coordinates || item.content.page_number)
  const canOpenDocument = Boolean(onViewInDocument) && (isPdf ? hasReliablePdfAnchor : Boolean(item.content.line_number))
  const viewPayload = {
    line_number: item.content.line_number,
    content_text: contentText,
    text_snippet: item.content.text_snippet ?? item.content.anchor_text,
    section_type: item.content.section_type ?? item.content.section_reference ?? item.content.section,
    section_location: item.content.section_location,
    pdf_coordinates: item.content.pdf_coordinates,
    page_number: item.content.page_number,
    match_confidence: item.content.match_confidence,
  }
  const locationLabel = isPdf
    ? item.content.pdf_coordinates?.page || item.content.page_number
      ? `Page ${item.content.pdf_coordinates?.page ?? item.content.page_number}`
      : null
    : item.content.line_number
      ? `Line ${item.content.line_number}`
      : null
  const anchorText = item.content.anchor_text ?? item.content.text_snippet

  const renderLocationButton = (className = META_STATUS_READY_CLASS) => {
    if (!canOpenDocument || !locationLabel) return null
    return (
      <button
        onClick={() => onViewInDocument?.(viewPayload)}
        className={`inline-flex items-center gap-1 ${className} transition-colors duration-150`}
      >
        <span>{locationLabel}</span>
        <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" />
      </button>
    )
  }

  return (
    <div className="rounded-lg border border-border-default bg-bg-surface p-4 transition-colors duration-150 hover:border-border-strong">

      {/* Header: type badge + severity badge + priority */}
      <div className="flex items-start justify-between mb-3">
        <div className="flex items-center gap-2 flex-wrap">
          {/* Type badge */}
          {isUnsupportedClaim ? (
            <span className="rounded border border-border-strong px-2 py-0.5 text-xs font-semibold text-error">
              Unsupported Claim
            </span>
          ) : (
            <span className="flex items-center gap-1">
              <TypeIcon className={`w-3.5 h-3.5 ${typeConfig.color} shrink-0`} />
              <span className="text-xs font-semibold text-text-secondary">{typeConfig.label}</span>
            </span>
          )}

          {/* Severity badge for feedback */}
          {(item.type === 'feedback' || item.type === 'task') && !isStrength && (() => {
            const severityInfo = metadata.severity ? SEVERITY_CONFIG[metadata.severity as string] : null
            if (!severityInfo) return null
            return (
              <span className={`rounded border px-2 py-0.5 text-xs font-semibold ${severityInfo.badgeClass}`}>
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
          {(item.content.section_type || item.content.section) && (
            <div className="min-w-[92px]">
              <div className={META_LABEL_CLASS}>Section</div>
              <div className={`${META_VALUE_CLASS} mt-1 capitalize`}>
                {(item.content.section_type || item.content.section || '').replace(/_/g, ' ')}
              </div>
            </div>
          )}
          {canOpenDocument && (
            <div className="min-w-[148px]">
              <div className={META_LABEL_CLASS}>Location</div>
              <div className="mt-1">
                {renderLocationButton()}
              </div>
            </div>
          )}
        </div>
      </div>

      {item.type === 'task' ? (
        <div className="mb-3 space-y-3">
          <div>
            <div className={META_LABEL_CLASS}>Problem</div>
            <MarkdownText
              as="p"
              text={item.content.problem || contentText}
              className="mt-1 text-sm text-text-primary leading-relaxed"
            />
          </div>

          {item.content.why_it_matters && (
            <div>
              <div className={META_LABEL_CLASS}>Why it matters</div>
              <MarkdownText
                as="p"
                text={item.content.why_it_matters}
                className="mt-1 text-sm text-text-secondary leading-relaxed"
              />
            </div>
          )}

          {item.content.suggested_action && (
            <div className="border-t border-border-default pt-3">
              <div className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-secondary">
                Suggested Action
              </div>
              <MarkdownText
                as="p"
                text={item.content.suggested_action}
                className="mt-1 text-sm text-text-primary leading-relaxed"
              />
            </div>
          )}

          <div className="grid gap-3 border-t border-border-default pt-3 sm:grid-cols-2">
            {anchorText && (
              <div>
                <div className={META_LABEL_CLASS}>Anchor</div>
                <MarkdownText
                  as="p"
                  text={anchorText}
                  className="mt-1 text-xs text-text-secondary leading-relaxed line-clamp-4"
                />
              </div>
            )}
            <div>
              <div className={META_LABEL_CLASS}>Location</div>
              <div className="mt-1">
                {renderLocationButton('text-xs font-medium text-accent-primary hover:text-accent-primary/80') ?? (
                  <span className="text-xs text-text-muted">Location unavailable</span>
                )}
              </div>
              {typeof item.content.match_confidence === 'number' && (
                <p className="mt-1 text-[11px] text-text-muted">
                  Anchor confidence: {Math.round(item.content.match_confidence * 100)}%
                </p>
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="mb-3">
          <MarkdownText
            as="p"
            text={contentText}
            className={`text-sm text-text-primary leading-relaxed ${!isExpanded && hasLongContent ? 'line-clamp-3' : ''}`}
          />
        </div>
      )}

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

      {/* Citation support */}
      {item.type === 'claim' && suggestedCitations.length > 0 && (
        <div className="mb-3 border-t border-border-default pt-3">
          <span className="mb-1.5 block text-xs font-medium text-text-secondary">Recommended support</span>
          <div className="space-y-2">
            {suggestedCitations.slice(0, 2).map((cit, i) => {
              const sourceConfig = citationSourceConfig(cit.source)
              return (
                <div
                  key={i}
                  className="flex items-start justify-between gap-3 rounded-md border border-border-default px-3 py-2"
                  title={`${sourceConfig.label}${cit.similarity ? ` · ${Math.round(cit.similarity * 100)}% match` : ''}`}
                >
                  <span className="text-xs font-medium leading-snug text-text-primary">{cit.display}</span>
                  <div className="flex items-center gap-2 shrink-0">
                    {cit.similarity && cit.similarity >= 0.7 && (
                      <span className="text-[11px] font-medium text-text-muted">{Math.round(cit.similarity * 100)}%</span>
                    )}
                    <span className={`text-[11px] font-semibold tracking-wide ${sourceConfig.text}`}>
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
        <div className="mb-3 border-t border-border-default pt-3">
          <span className="mb-1.5 block text-xs font-medium text-warning">Citation needed</span>
          <span className="text-xs text-text-muted italic">
            No citation match found in your library.
          </span>
        </div>
      )}

      {/* Suggestions / Citations */}
      {item.type !== 'task' && suggestions.length > 0 && (
        <div className="mb-3">
          <button
            className="flex items-center gap-1.5 mb-2 group/toggle"
            onClick={() => setIsExpanded(!isExpanded)}
          >
            <h4 className="text-xs font-semibold text-text-secondary group-hover/toggle:text-text-primary transition-colors">
              {item.type === 'claim' ? 'Existing citations' : 'Action'}
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
                <li key={idx} className="border-t border-border-subtle pt-2 first:border-t-0 first:pt-0">
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
                          const sourceConfig = citationSourceConfig(source)
                          return (
                            <span className={`text-[11px] font-semibold tracking-wide shrink-0 ${sourceConfig.text}`}>
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

      {suggestedSources.length > 0 && (
        <div className="mb-3 border-t border-border-default pt-3">
          <div className={META_LABEL_CLASS}>Suggested Sources</div>
          <ul className="mt-2 space-y-2">
          {suggestedSources.slice(0, 3).map((source: any, idx: number) => (
            <li key={`${source.document_id || source.doi || source.url || idx}`} className="text-xs text-text-secondary">
              <span className="font-medium text-text-primary">
                {source.display || source.document_title || source.title || 'Source'}
              </span>
              {(source.source || source.provider) && (() => {
                const sourceKey = source.source || source.provider
                const sourceConfig = citationSourceConfig(sourceKey)
                return (
                  <span className={`ml-2 text-[11px] font-semibold tracking-wide ${sourceConfig.text}`}>
                    {sourceConfig.label}
                  </span>
                )
              })()}
                {typeof source.similarity === 'number' && (
                  <span className="ml-1 text-text-muted">({Math.round(source.similarity * 100)}% match)</span>
                )}
                {(source.open_access_url || source.url || source.external_url) && (
                  <a
                    href={source.open_access_url || source.url || source.external_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="ml-2 inline-flex items-center gap-1 text-accent-primary hover:underline"
                  >
                    View
                    <ArrowTopRightOnSquareIcon className="h-3 w-3" />
                  </a>
                )}
            </li>
          ))}
        </ul>
        </div>
      )}

      {/* Expand/collapse for long content without suggestions */}
      {item.type !== 'task' && hasLongContent && !suggestions.length && (
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

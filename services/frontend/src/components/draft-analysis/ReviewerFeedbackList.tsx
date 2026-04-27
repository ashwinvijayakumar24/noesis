import { useState, useMemo } from 'react'
import { CheckIcon, XMarkIcon, ChevronDownIcon, BookOpenIcon } from '@heroicons/react/24/outline'

// ---------------------------------------------------------------------------
// Types (mirrors DraftAnalysis.tsx interfaces)
// ---------------------------------------------------------------------------

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  section_location: string
  section_type?: string
  importance_score: number
  requires_citation: boolean
  existing_citations: string[]
  line_number?: number
  text_snippet?: string
  status: 'new' | 'saved' | 'dismissed'
}

interface Gap {
  id: string
  gap_type: string
  description: string
  priority: 'high' | 'medium' | 'low'
  section_type?: string
  suggested_papers: any[]
  has_relevant_literature?: boolean
  line_number?: number
  text_snippet?: string
  status: 'new' | 'saved' | 'dismissed'
}

interface FeedbackItem {
  id: string
  feedback_type: string
  severity: string
  priority: 'high' | 'medium' | 'low'
  reviewer_persona?: string
  section_type?: string
  feedback_text: string
  suggestions: string[]
  section_reference?: string
  line_number?: number
  text_snippet?: string
  status: 'new' | 'saved' | 'dismissed'
}

type ItemType = 'claim' | 'gap' | 'feedback'
type Priority = 'high' | 'medium' | 'low'
type FilterKey = 'all' | 'claims' | 'gaps' | 'feedback'

interface ListItem {
  type: ItemType
  content: Claim | Gap | FeedbackItem
  priority: Priority
}

interface ReviewerFeedbackListProps {
  claims: Claim[]
  gaps: Gap[]
  feedback: FeedbackItem[]
  readinessScore: number | null
  onStatusChange: (id: string, type: ItemType, status: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument: (item: { line_number?: number; content_text?: string; text_snippet?: string; section_type?: string; section_location?: string }) => void
  fileType: string
  onOpenEditingReview?: () => void
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

const PRIORITY_ORDER: Record<Priority, number> = { high: 0, medium: 1, low: 2 }

function claimPriority(c: Claim): Priority {
  return c.importance_score >= 0.7 ? 'high' : c.importance_score >= 0.4 ? 'medium' : 'low'
}

function feedbackPriority(f: FeedbackItem): Priority {
  if (f.severity === 'critical') return 'high'
  if (f.severity === 'major') return 'medium'
  return 'low'
}

function getContentText(item: ListItem): string {
  if (item.type === 'claim') return (item.content as Claim).claim_text
  if (item.type === 'gap') return (item.content as Gap).description
  return (item.content as FeedbackItem).feedback_text
}

function capitalize(s: string): string {
  return s.charAt(0).toUpperCase() + s.slice(1)
}

function buildViewLabel(content: any, fileType: string): string | null {
  const section = content.section_type ?? content.section_location ?? content.section_reference
  const lineNum = content.line_number
  const isPdf = fileType === 'application/pdf' || fileType === 'pdf'

  if (isPdf && lineNum) return `View on Page ~${Math.ceil(lineNum / 55)}`
  if (section) return `View in ${capitalize((section as string).replace(/_/g, ' '))}`
  if (!isPdf && lineNum) return `View on Line ${lineNum}`
  return null
}

// ---------------------------------------------------------------------------
// FeedbackListItem
// ---------------------------------------------------------------------------

interface FeedbackListItemProps {
  number: number
  item: ListItem
  fileType: string
  onStatusChange: ReviewerFeedbackListProps['onStatusChange']
  onViewInDocument: ReviewerFeedbackListProps['onViewInDocument']
}

function FeedbackListItem({ number, item, fileType, onStatusChange, onViewInDocument }: FeedbackListItemProps) {
  const [papersExpanded, setPapersExpanded] = useState(false)
  const isAddressed = item.content.status === 'saved'
  const text = getContentText(item)
  const viewLabel = buildViewLabel(item.content, fileType)
  const suggestedPapers: any[] = item.type === 'gap' ? ((item.content as Gap).suggested_papers ?? []) : []

  const priorityBorder =
    item.priority === 'high'
      ? 'border-l-2 border-l-error'
      : item.priority === 'medium'
        ? 'border-l-2 border-l-warning'
        : 'border-l-2 border-l-border-subtle'

  const viewPayload = {
    line_number: (item.content as any).line_number,
    content_text: text,
    text_snippet: (item.content as any).text_snippet,
    // feedback items use section_reference; claims/gaps use section_type/section_location
    section_type: (item.content as any).section_type
      ?? (item.content as any).section_reference
      ?? (item.content as any).section_location,
    section_location: (item.content as any).section_location,
  }

  return (
    <div
      onClick={() => onViewInDocument(viewPayload)}
      className={`px-4 py-4 hover:bg-bg-hover/30 transition-colors duration-150 cursor-pointer ${priorityBorder} ${isAddressed ? 'opacity-50' : ''}`}
    >
      <div className="flex gap-3">
        {/* Number badge */}
        <span className="shrink-0 mt-0.5 w-5 h-5 rounded-full border border-border-default bg-bg-elevated text-[10px] font-semibold text-text-muted flex items-center justify-center">
          {number}
        </span>

        <div className="flex-1 min-w-0">
          <p className="text-sm text-text-primary leading-relaxed line-clamp-4">{text}</p>

          {/* Bottom row: location hint + action buttons */}
          <div className="flex items-center justify-between mt-2.5">
            {viewLabel ? (
              <span className="text-xs text-text-muted">{viewLabel} →</span>
            ) : (
              <span />
            )}

            <div className="flex items-center gap-0.5">
              {suggestedPapers.length > 0 && (
                <button
                  onClick={e => { e.stopPropagation(); setPapersExpanded(p => !p) }}
                  className="h-8 px-2 rounded-lg flex items-center gap-1 text-xs text-text-muted hover:text-text-primary hover:bg-bg-elevated transition-colors duration-150"
                  title="Suggested papers"
                >
                  <BookOpenIcon className="h-3.5 w-3.5" />
                  {suggestedPapers.length}
                  <ChevronDownIcon className={`h-3 w-3 transition-transform duration-150 ${papersExpanded ? 'rotate-180' : ''}`} />
                </button>
              )}
              <button
                onClick={e => { e.stopPropagation(); onStatusChange(item.content.id, item.type, isAddressed ? 'new' : 'saved') }}
                title={isAddressed ? 'Mark unaddressed' : 'Mark addressed'}
                className={`h-8 w-8 rounded-lg flex items-center justify-center transition-colors duration-150 ${
                  isAddressed
                    ? 'bg-success/10 text-success'
                    : 'text-text-muted hover:text-success hover:bg-success/10'
                }`}
              >
                <CheckIcon className="h-4 w-4" />
              </button>
              <button
                onClick={e => { e.stopPropagation(); onStatusChange(item.content.id, item.type, 'dismissed') }}
                title="Dismiss"
                className="h-8 w-8 rounded-lg flex items-center justify-center text-text-muted hover:text-error hover:bg-error/10 transition-colors duration-150"
              >
                <XMarkIcon className="h-4 w-4" />
              </button>
            </div>
          </div>

          {/* Suggested papers for gap items */}
          {papersExpanded && suggestedPapers.length > 0 && (
            <div className="mt-3 space-y-2">
              {suggestedPapers.slice(0, 5).map((paper: any, idx: number) => (
                <div key={idx} className="rounded-lg border border-border-default bg-bg-elevated px-3 py-2">
                  <p className="text-xs font-semibold text-text-primary leading-snug line-clamp-2">
                    {paper.title ?? paper.paper_title ?? 'Unknown title'}
                  </p>
                  {(paper.authors || paper.year) && (
                    <p className="text-[11px] text-text-muted mt-0.5">
                      {[paper.authors?.slice?.(0, 2)?.join?.(', '), paper.year].filter(Boolean).join(' · ')}
                    </p>
                  )}
                  {paper.relevance_reason && (
                    <p className="text-[11px] text-text-secondary mt-1 leading-relaxed">{paper.relevance_reason}</p>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// FilterChips
// ---------------------------------------------------------------------------

interface FilterChipsProps {
  filter: FilterKey
  onChange: (f: FilterKey) => void
  counts: { claims: number; gaps: number; feedback: number }
}

function FilterChips({ filter, onChange, counts }: FilterChipsProps) {
  const chips: Array<{ key: FilterKey; label: string; count: number }> = [
    { key: 'all', label: 'All', count: counts.claims + counts.gaps + counts.feedback },
    { key: 'claims', label: 'Claims', count: counts.claims },
    { key: 'gaps', label: 'Gaps', count: counts.gaps },
    { key: 'feedback', label: 'Feedback', count: counts.feedback },
  ]

  return (
    <div className="flex gap-1">
      {chips.map(chip => (
        <button
          key={chip.key}
          onClick={() => onChange(chip.key)}
          className={`px-2.5 py-1 rounded-lg text-xs font-semibold transition-colors duration-150 ${
            filter === chip.key
              ? 'bg-accent-primary/10 text-accent-primary'
              : 'text-text-muted hover:text-text-primary hover:bg-bg-elevated'
          }`}
        >
          {chip.label}
          {chip.count > 0 && (
            <span className="ml-1 opacity-60">{chip.count}</span>
          )}
        </button>
      ))}
    </div>
  )
}

// ---------------------------------------------------------------------------
// ReviewerFeedbackList
// ---------------------------------------------------------------------------

export default function ReviewerFeedbackList({
  claims,
  gaps,
  feedback,
  readinessScore,
  onStatusChange,
  onViewInDocument,
  fileType,
  onOpenEditingReview,
}: ReviewerFeedbackListProps) {
  const [filter, setFilter] = useState<FilterKey>('all')

  const allItems = useMemo<ListItem[]>(() => {
    return [
      ...claims
        .filter(c => c.status !== 'dismissed')
        .map(c => ({ type: 'claim' as const, content: c, priority: claimPriority(c) })),
      ...gaps
        .filter(g => g.status !== 'dismissed')
        .map(g => ({ type: 'gap' as const, content: g, priority: g.priority })),
      ...feedback
        .filter(f => f.status !== 'dismissed' && f.feedback_type !== 'strength')
        .map(f => ({ type: 'feedback' as const, content: f, priority: feedbackPriority(f) })),
    ].sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
  }, [claims, gaps, feedback])

  const filtered = useMemo<ListItem[]>(() => {
    if (filter === 'all') return allItems
    const typeMap: Record<Exclude<FilterKey, 'all'>, ItemType> = {
      claims: 'claim',
      gaps: 'gap',
      feedback: 'feedback',
    }
    return allItems.filter(i => i.type === typeMap[filter as Exclude<FilterKey, 'all'>])
  }, [allItems, filter])

  const addressedCount = useMemo(
    () => [...claims, ...gaps, ...feedback].filter(i => i.status === 'saved').length,
    [claims, gaps, feedback],
  )
  const totalCount = useMemo(
    () => [...claims, ...gaps, ...feedback.filter(f => f.feedback_type !== 'strength')].length,
    [claims, gaps, feedback],
  )

  const claimsCount = claims.filter(c => c.status !== 'dismissed').length
  const gapsCount = gaps.filter(g => g.status !== 'dismissed').length
  const feedbackCount = feedback.filter(f => f.status !== 'dismissed' && f.feedback_type !== 'strength').length

  return (
    <div className="flex flex-col h-full">
      {/* Score + filter strip */}
      <div className="shrink-0 border-b border-border-default bg-bg-surface">
        <div className="flex items-center justify-between px-4 py-3">
          <div className="flex items-center gap-3">
            {readinessScore !== null && (
              <div className="flex items-baseline gap-1">
                <span className="text-base font-semibold text-text-primary tabular-nums">
                  {Math.round(readinessScore * 100)}/100
                </span>
                <span className="text-[10px] text-text-muted uppercase tracking-wide">readiness</span>
              </div>
            )}
            <span className="text-xs text-text-muted">
              {addressedCount} of {totalCount} addressed
            </span>
          </div>
          <FilterChips
            filter={filter}
            onChange={setFilter}
            counts={{ claims: claimsCount, gaps: gapsCount, feedback: feedbackCount }}
          />
        </div>

        {onOpenEditingReview && (
          <div className="px-4 pb-2">
            <button
              onClick={onOpenEditingReview}
              className="text-xs text-text-muted hover:text-accent-primary transition-colors duration-150"
            >
              Editing Review →
            </button>
          </div>
        )}
      </div>

      {/* Numbered list */}
      <div className="flex-1 overflow-y-auto divide-y divide-border-default">
        {filtered.length > 0 ? (
          filtered.map((item, idx) => (
            <FeedbackListItem
              key={item.content.id}
              number={idx + 1}
              item={item}
              fileType={fileType}
              onStatusChange={onStatusChange}
              onViewInDocument={onViewInDocument}
            />
          ))
        ) : (
          <div className="flex flex-col items-center justify-center py-16 text-center px-6">
            <p className="text-sm text-text-secondary">No items to review</p>
            <p className="text-xs text-text-muted mt-1">
              {filter !== 'all' ? 'Try switching the filter above.' : 'Analysis results will appear here.'}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

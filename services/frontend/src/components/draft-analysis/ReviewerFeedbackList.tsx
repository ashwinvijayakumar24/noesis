import { useMemo, useState } from 'react'
import { ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import type { PdfCoordinates } from '../DocumentViewer'
import UnifiedFeedbackCard from './UnifiedFeedbackCard'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  section_location: string
  section_type?: string
  importance_score: number
  confidence_score?: number
  requires_citation: boolean
  existing_citations: string[]
  supporting_literature?: any
  line_number?: number
  text_snippet?: string
  pdf_coordinates?: PdfCoordinates
  match_confidence?: number
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
  pdf_coordinates?: PdfCoordinates
  match_confidence?: number
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
  pdf_coordinates?: PdfCoordinates
  match_confidence?: number
  status: 'new' | 'saved' | 'dismissed'
}

type ItemType = 'claim' | 'gap' | 'feedback'
type Priority = 'high' | 'medium' | 'low'
type StatusFilter = 'new' | 'saved' | 'dismissed'
type CategoryKey =
  | 'all'
  | 'missing_citations'
  | 'weak_arguments'
  | 'coverage_gaps'
  | 'methodology'
  | 'reviewer_questions'

interface ListItem {
  id: string
  type: ItemType
  priority: Priority
  issueCategory: CategoryKey
  content: Claim | Gap | FeedbackItem
}

interface ReviewerFeedbackListProps {
  claims: Claim[]
  gaps: Gap[]
  feedback: FeedbackItem[]
  readinessScore: number | null
  loading?: boolean
  statusFilter: StatusFilter
  onStatusFilterChange: (status: StatusFilter) => void
  onStatusChange: (id: string, type: ItemType, status: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument: (item: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
    pdf_coordinates?: PdfCoordinates
    match_confidence?: number
  }) => void
  fileType: string
  onOpenEditingReview?: () => void
}

const PRIORITY_ORDER: Record<Priority, number> = { high: 0, medium: 1, low: 2 }

const PRIORITY_HEADER_CONFIG = {
  high: { dot: 'bg-error', text: 'text-error', label: 'High priority' },
  medium: { dot: 'bg-warning', text: 'text-warning', label: 'Medium priority' },
  low: { dot: 'bg-text-muted', text: 'text-text-muted', label: 'Low priority' },
} as const

const CATEGORY_CONFIG: Record<CategoryKey, { label: string }> = {
  all: { label: 'All issues' },
  missing_citations: { label: 'Missing citations' },
  weak_arguments: { label: 'Weak arguments' },
  coverage_gaps: { label: 'Coverage gaps' },
  methodology: { label: 'Methodology' },
  reviewer_questions: { label: 'Reviewer questions' },
}

function claimPriority(claim: Claim): Priority {
  if (claim.importance_score >= 0.8) return 'high'
  if (claim.importance_score >= 0.5) return 'medium'
  return 'low'
}

function feedbackPriority(item: FeedbackItem): Priority {
  if (item.priority) return item.priority
  if (item.severity === 'critical') return 'high'
  if (item.severity === 'major') return 'medium'
  return 'low'
}

function classifyClaim(claim: Claim): CategoryKey {
  if (claim.requires_citation) return 'missing_citations'
  if (claim.claim_type === 'methodological') return 'methodology'
  return 'weak_arguments'
}

function classifyGap(gap: Gap): CategoryKey {
  if ((gap.gap_type || '').toLowerCase().includes('method')) return 'methodology'
  return 'coverage_gaps'
}

function classifyFeedback(item: FeedbackItem): CategoryKey {
  if (item.feedback_type === 'question') return 'reviewer_questions'
  if (
    item.feedback_type === 'structural'
    || item.section_type === 'methodology'
    || /method|evaluation|ablation|baseline|implementation/i.test(item.feedback_text)
  ) {
    return 'methodology'
  }
  return 'weak_arguments'
}

function buildItems(
  claims: Claim[],
  gaps: Gap[],
  feedback: FeedbackItem[],
): ListItem[] {
  return [
    ...claims
      .map((item) => ({
        id: item.id,
        type: 'claim' as const,
        priority: claimPriority(item),
        issueCategory: classifyClaim(item),
        content: item,
      })),
    ...gaps
      .map((item) => ({
        id: item.id,
        type: 'gap' as const,
        priority: item.priority,
        issueCategory: classifyGap(item),
        content: item,
      })),
    ...feedback
      .filter((item) => item.feedback_type !== 'strength')
      .map((item) => ({
        id: item.id,
        type: 'feedback' as const,
        priority: feedbackPriority(item),
        issueCategory: classifyFeedback(item),
        content: item,
      })),
  ].sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
}

export default function ReviewerFeedbackList({
  claims,
  gaps,
  feedback,
  readinessScore,
  loading = false,
  statusFilter,
  onStatusFilterChange,
  onStatusChange,
  onViewInDocument,
  fileType,
  onOpenEditingReview,
}: ReviewerFeedbackListProps) {
  const [category, setCategory] = useState<CategoryKey>('all')

  const allItems = useMemo(() => buildItems(claims, gaps, feedback), [claims, gaps, feedback])

  const statusFilteredItems = useMemo(
    () => allItems.filter((item) => item.content.status === statusFilter),
    [allItems, statusFilter],
  )

  const visibleItems = useMemo(
    () => (category === 'all'
      ? statusFilteredItems
      : statusFilteredItems.filter((item) => item.issueCategory === category)),
    [statusFilteredItems, category],
  )

  const addressedCount = useMemo(
    () => [...claims, ...gaps, ...feedback].filter((item) => item.status === 'saved').length,
    [claims, gaps, feedback],
  )
  const totalCount = useMemo(
    () => buildItems(claims, gaps, feedback).length,
    [claims, gaps, feedback],
  )

  const statusCounts = useMemo(() => ({
    new: buildItems(
      claims.filter((item) => item.status === 'new'),
      gaps.filter((item) => item.status === 'new'),
      feedback.filter((item) => item.status === 'new'),
    ).length,
    saved: buildItems(
      claims.filter((item) => item.status === 'saved'),
      gaps.filter((item) => item.status === 'saved'),
      feedback.filter((item) => item.status === 'saved'),
    ).length,
    dismissed: claims.filter((item) => item.status === 'dismissed').length
      + gaps.filter((item) => item.status === 'dismissed').length
      + feedback.filter((item) => item.status === 'dismissed' && item.feedback_type !== 'strength').length,
  }), [claims, gaps, feedback])

  const categoryCounts = useMemo(() => {
    const counts: Record<CategoryKey, number> = {
      all: statusFilteredItems.length,
      missing_citations: 0,
      weak_arguments: 0,
      coverage_gaps: 0,
      methodology: 0,
      reviewer_questions: 0,
    }
    statusFilteredItems.forEach((item) => {
      counts[item.issueCategory] += 1
    })
    return counts
  }, [statusFilteredItems])

  const groupedItems = useMemo(() => ({
    high: visibleItems.filter((item) => item.priority === 'high'),
    medium: visibleItems.filter((item) => item.priority === 'medium'),
    low: visibleItems.filter((item) => item.priority === 'low'),
  }), [visibleItems])

  return (
    <div className="flex h-full flex-col">
      <div className="shrink-0 border-b border-border-default bg-bg-surface">
        <div className="flex items-center justify-between gap-4 px-4 py-3">
          <div className="flex items-center gap-3">
            {readinessScore !== null && (
              <div className="flex items-baseline gap-1">
                <span className="text-base font-semibold text-text-primary tabular-nums">
                  {Math.round(readinessScore)}/100
                </span>
                <span className="text-[10px] uppercase tracking-wide text-text-muted">readiness</span>
              </div>
            )}
            <span className="text-xs text-text-muted">
              {addressedCount} of {totalCount} addressed
            </span>
          </div>
          {onOpenEditingReview && (
            <button
              onClick={onOpenEditingReview}
              className="text-xs text-text-muted hover:text-accent-primary transition-colors duration-150"
            >
              Editing Review →
            </button>
          )}
        </div>

        <div className="px-4 pb-3">
          <div className="flex flex-wrap gap-1.5">
            {(Object.keys(CATEGORY_CONFIG) as CategoryKey[]).map((key) => (
              <button
                key={key}
                onClick={() => setCategory(key)}
                className={`min-h-10 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors duration-150 ${
                  category === key
                    ? 'border-accent-primary/20 bg-accent-primary/10 text-accent-primary'
                    : 'border-border-default bg-bg-elevated text-text-secondary hover:text-text-primary'
                }`}
              >
                {CATEGORY_CONFIG[key].label}
                {categoryCounts[key] > 0 && <span className="ml-1.5 opacity-70">{categoryCounts[key]}</span>}
              </button>
            ))}
          </div>
        </div>

        <div className="flex space-x-1 border-t border-border-default px-4">
          {(['new', 'saved', 'dismissed'] as StatusFilter[]).map((status) => {
            const isActive = statusFilter === status
            return (
              <button
                key={status}
              onClick={() => onStatusFilterChange(status)}
                className={`min-h-11 border-b-2 px-4 py-2 text-sm font-semibold transition-all duration-150 ${
                  isActive
                    ? 'border-accent-primary text-text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary'
                }`}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)}
                {statusCounts[status] > 0 && (
                  <span className={`ml-1.5 rounded-full border px-2 py-0.5 text-xs ${
                    isActive
                      ? 'border-accent-primary/20 bg-accent-primary/10 text-accent-primary'
                      : 'border-border-default bg-bg-elevated text-text-muted'
                  }`}>
                    {statusCounts[status]}
                  </span>
                )}
              </button>
            )
          })}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-4 py-4">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-solid border-accent-primary border-r-transparent mb-3" />
            <p className="text-sm text-text-secondary">Loading issue list...</p>
          </div>
        ) : visibleItems.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-center">
            <p className="text-sm text-text-secondary">No issues in this bucket</p>
            <p className="mt-1 text-xs text-text-muted">
              Try another issue category or status filter.
            </p>
          </div>
        ) : (
          <div className="space-y-5">
            {(['high', 'medium', 'low'] as const).map((priority) => {
              const group = groupedItems[priority]
              if (group.length === 0) return null
              const config = PRIORITY_HEADER_CONFIG[priority]
              return (
                <div key={priority}>
                  <div className="mb-3 flex items-center gap-2 py-1">
                    <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
                    <span className={`text-xs font-semibold uppercase tracking-wider ${config.text}`}>
                      {config.label}
                    </span>
                    <span className="text-xs text-text-muted">{group.length}</span>
                    <div className="ml-1 h-px flex-1 bg-border-default" />
                  </div>
                  <div className="space-y-3">
                    {group.map((item) => (
                      <UnifiedFeedbackCard
                        key={item.id}
                        item={item}
                        onStatusChange={onStatusChange}
                        onViewInDocument={onViewInDocument}
                        currentStatus={statusFilter}
                        fileType={fileType}
                      />
                    ))}
                  </div>
                </div>
              )
            })}

            {statusFilter === 'new' && categoryCounts.missing_citations === 0 && (
              <div className="rounded-lg border border-border-default bg-bg-elevated/40 p-3">
                <div className="flex items-start gap-2">
                  <ExclamationTriangleIcon className="mt-0.5 h-4 w-4 text-text-muted" />
                  <p className="text-xs text-text-secondary">
                    Recommendation papers only appear when the analysis found a concrete citation issue or gap with candidate support.
                  </p>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

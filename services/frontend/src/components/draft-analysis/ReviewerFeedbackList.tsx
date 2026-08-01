import { useEffect, useMemo, useRef, useState } from 'react'
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline'
import type { PdfCoordinates } from '../DocumentViewer'
import UnifiedFeedbackCard from './UnifiedFeedbackCard'
import EditorDecisionCard from './EditorDecisionCard'
import MetaReviewCard from './MetaReviewCard'
import ReviewerPanelTabs from './ReviewerPanelTabs'

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

interface RevisionTask {
  id: string
  source_type: string
  task_type: string
  severity: string
  priority: Priority
  section?: string
  anchor_text?: string
  problem: string
  why_it_matters?: string
  suggested_action: string
  source_ids?: string[]
  line_number?: number
  page_number?: number
  paragraph_index?: number
  suggested_sources?: any[]
  text_snippet?: string
  pdf_coordinates?: PdfCoordinates
  match_confidence?: number
  status: 'new' | 'saved' | 'dismissed'
}

type ItemType = 'claim' | 'gap' | 'feedback' | 'task'
type Priority = 'high' | 'medium' | 'low'
export type StatusFilter = 'new' | 'saved' | 'dismissed'
export type CategoryKey =
  | 'all'
  | 'missing_citations'
  | 'weak_arguments'
  | 'coverage_gaps'
  | 'methodology'
  | 'clarity_limits'
  | 'reviewer_questions'

interface ListItem {
  id: string
  type: ItemType
  priority: Priority
  issueCategory: CategoryKey
  content: Claim | Gap | FeedbackItem | RevisionTask
}

interface ReviewerFeedbackListProps {
  claims: Claim[]
  gaps: Gap[]
  feedback: FeedbackItem[]
  revisionTasks?: RevisionTask[]
  readinessScore: number | null
  loading?: boolean
  statusFilter: StatusFilter
  onStatusFilterChange: (status: StatusFilter) => void
  onStatusChange: (id: string, type: ItemType, status: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument?: (item: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
    pdf_coordinates?: PdfCoordinates
    page_number?: number
    match_confidence?: number
  }) => void
  fileType: string
  initialCategory?: CategoryKey
  maxVisibleItems?: number
  compactPreview?: boolean
  editorDecision?: {
    proceed_to_review: boolean
    fatal_flaws: string[]
    scope_appropriate: boolean
    writing_quality: 'publishable' | 'needs_revision' | 'major_revision'
    notes: string
  } | null
  reviewerPanel?: any[]
  metaReview?: any | null
}

const PRIORITY_ORDER: Record<Priority, number> = { high: 0, medium: 1, low: 2 }

const PRIORITY_HEADER_CONFIG = {
  high: { dot: 'bg-error', text: 'text-error', label: 'High priority' },
  medium: { dot: 'bg-warning', text: 'text-warning', label: 'Medium priority' },
  low: { dot: 'bg-text-muted', text: 'text-text-muted', label: 'Low priority' },
} as const

const CATEGORY_CONFIG: Record<CategoryKey, { label: string }> = {
  all: { label: 'Revision queue' },
  missing_citations: { label: 'Missing citations' },
  weak_arguments: { label: 'Claims & evidence' },
  coverage_gaps: { label: 'Literature & positioning' },
  methodology: { label: 'Methods & evaluation' },
  clarity_limits: { label: 'Clarity & limits' },
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

function classifyTask(item: RevisionTask): CategoryKey {
  const taskType = (item.task_type || '').toLowerCase()
  const problemText = `${item.problem || ''} ${item.why_it_matters || ''} ${item.suggested_action || ''}`
  if (taskType === 'citation') return 'missing_citations'
  if (taskType === 'literature_positioning') return 'coverage_gaps'
  if (taskType === 'causal_claim') return 'weak_arguments'
  if (['methodology', 'evaluation', 'framework_validation', 'deployment', 'reproducibility', 'baseline', 'ablation', 'runtime', 'scalability'].includes(taskType)) {
    return 'methodology'
  }
  if (['clarity', 'structural', 'limitations', 'presentation'].includes(taskType)) return 'clarity_limits'
  if (/question|clarify|could you|can you/i.test(problemText)) return 'reviewer_questions'
  return 'weak_arguments'
}

function recommendationLabel(value?: string) {
  return String(value || 'major_revision')
    .replace(/_/g, ' ')
    .replace(/\b\w/g, (char) => char.toUpperCase())
}

function getMetaReviewPayload(metaReview: any | null) {
  if (!metaReview) return null
  if (metaReview.meta_review && typeof metaReview.meta_review === 'object') return metaReview.meta_review
  return metaReview
}

function ReviewSummaryStrip({
  readinessScore,
  revisionTasks,
  editorDecision,
  reviewerPanel,
  metaReview,
}: {
  readinessScore: number | null
  revisionTasks: RevisionTask[]
  editorDecision?: ReviewerFeedbackListProps['editorDecision']
  reviewerPanel?: any[]
  metaReview?: any | null
}) {
  const meta = getMetaReviewPayload(metaReview)
  const mustAddressCount = Array.isArray(meta?.must_address) ? meta.must_address.length : revisionTasks.filter((task) => task.priority === 'high').length
  const reviewerCount = reviewerPanel?.length || 0
  const agreement = meta?.reviewer_agreement_level ? String(meta.reviewer_agreement_level) : reviewerCount > 0 ? 'panel' : 'pending'
  const recommendation = recommendationLabel(meta?.overall_recommendation)
  const deskStatus = editorDecision
    ? editorDecision.proceed_to_review
      ? 'passed desk check'
      : 'desk check blocked'
    : 'desk check pending'

  return (
    <div className="border-b border-border-default bg-bg-surface px-4 py-3">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <div className="rounded-lg border border-border-default bg-bg-elevated px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">Readiness</p>
          <p className="mt-1 text-sm font-semibold text-text-primary">
            {readinessScore !== null ? `${Math.round(readinessScore)}/100` : 'Pending'}
          </p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">Recommendation</p>
          <p className="mt-1 text-sm font-semibold capitalize text-text-primary">{recommendation}</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">Must address</p>
          <p className="mt-1 text-sm font-semibold text-text-primary">{mustAddressCount} issue{mustAddressCount === 1 ? '' : 's'}</p>
        </div>
        <div className="rounded-lg border border-border-default bg-bg-elevated px-3 py-2">
          <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">Review panel</p>
          <p className="mt-1 text-sm font-semibold capitalize text-text-primary">
            {reviewerCount > 0 ? `${reviewerCount} reviewers, ${agreement} agreement` : deskStatus}
          </p>
        </div>
      </div>
    </div>
  )
}

function buildItems(
  claims: Claim[],
  gaps: Gap[],
  feedback: FeedbackItem[],
  revisionTasks: RevisionTask[] = [],
): ListItem[] {
  if (revisionTasks.length > 0) {
    return revisionTasks
      .map((item) => ({
        id: item.id,
        type: 'task' as const,
        priority: item.priority,
        issueCategory: classifyTask(item),
        content: item,
      }))
      .sort((a, b) => PRIORITY_ORDER[a.priority] - PRIORITY_ORDER[b.priority])
  }

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
  revisionTasks = [],
  readinessScore,
  loading = false,
  statusFilter,
  onStatusFilterChange,
  onStatusChange,
  onViewInDocument,
  fileType,
  initialCategory = 'all',
  maxVisibleItems,
  compactPreview = false,
  editorDecision,
  reviewerPanel,
  metaReview,
}: ReviewerFeedbackListProps) {
  const [category, setCategory] = useState<CategoryKey>(initialCategory)
  const [summaryCollapsed, setSummaryCollapsed] = useState(true)
  const feedbackScrollRef = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    setCategory(initialCategory)
  }, [initialCategory])

  const allItems = useMemo(() => buildItems(claims, gaps, feedback, revisionTasks), [claims, gaps, feedback, revisionTasks])

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
    () => revisionTasks.length > 0
      ? revisionTasks.filter((item) => item.status === 'saved').length
      : [...claims, ...gaps, ...feedback].filter((item) => item.status === 'saved').length,
    [claims, gaps, feedback, revisionTasks],
  )
  const totalCount = useMemo(
    () => buildItems(claims, gaps, feedback, revisionTasks).length,
    [claims, gaps, feedback, revisionTasks],
  )

  const statusCounts = useMemo(() => ({
    new: revisionTasks.length > 0 ? revisionTasks.filter((item) => item.status === 'new').length : buildItems(
      claims.filter((item) => item.status === 'new'),
      gaps.filter((item) => item.status === 'new'),
      feedback.filter((item) => item.status === 'new'),
    ).length,
    saved: revisionTasks.length > 0 ? revisionTasks.filter((item) => item.status === 'saved').length : buildItems(
      claims.filter((item) => item.status === 'saved'),
      gaps.filter((item) => item.status === 'saved'),
      feedback.filter((item) => item.status === 'saved'),
    ).length,
    dismissed: revisionTasks.length > 0 ? revisionTasks.filter((item) => item.status === 'dismissed').length : claims.filter((item) => item.status === 'dismissed').length
      + gaps.filter((item) => item.status === 'dismissed').length
      + feedback.filter((item) => item.status === 'dismissed' && item.feedback_type !== 'strength').length,
  }), [claims, gaps, feedback, revisionTasks])

  const categoryCounts = useMemo(() => {
    const counts: Record<CategoryKey, number> = {
      all: statusFilteredItems.length,
      missing_citations: 0,
      weak_arguments: 0,
      coverage_gaps: 0,
      methodology: 0,
      clarity_limits: 0,
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

  const renderedItems = useMemo(() => {
    if (!maxVisibleItems) return groupedItems

    let remaining = maxVisibleItems
    const take = (items: ListItem[]) => {
      if (remaining <= 0) return []
      const next = items.slice(0, remaining)
      remaining -= next.length
      return next
    }

    return {
      high: take(groupedItems.high),
      medium: take(groupedItems.medium),
      low: take(groupedItems.low),
    }
  }, [groupedItems, maxVisibleItems])

  const visibleCategories = useMemo(
    () => (Object.keys(CATEGORY_CONFIG) as CategoryKey[])
      .filter((key) => key === 'all' || categoryCounts[key] > 0),
    [categoryCounts],
  )

  useEffect(() => {
    if (!visibleCategories.includes(category)) {
      setCategory('all')
    }
  }, [category, visibleCategories])

  useEffect(() => {
    feedbackScrollRef.current?.scrollTo({ top: 0, behavior: 'smooth' })
  }, [category, statusFilter])

  const hasDecisionContext = !compactPreview && (editorDecision || metaReview || (reviewerPanel && reviewerPanel.length > 0))
  const compactStatusSummary = `${Math.round(readinessScore ?? 0)}/100 · ${statusCounts.new} open · ${addressedCount}/${totalCount} addressed`

  return (
    <div className="flex h-full flex-col">
      {!compactPreview && (
        <div className="shrink-0 border-b border-border-default bg-bg-surface">
          {summaryCollapsed ? (
            <div className="flex items-center justify-between gap-3 border-b border-border-default px-4 py-2.5">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold text-text-primary">
                  {recommendationLabel(getMetaReviewPayload(metaReview)?.overall_recommendation)}
                </p>
                <p className="mt-0.5 truncate font-mono text-xs text-text-muted">
                  {readinessScore !== null ? compactStatusSummary : `${statusCounts.new} open · ${addressedCount}/${totalCount} addressed`}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setSummaryCollapsed(false)}
                className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border-default px-2.5 py-1.5 text-xs font-semibold text-text-secondary transition-colors duration-150 hover:bg-bg-elevated hover:text-text-primary active:translate-y-px"
                aria-expanded="false"
                aria-label="Show review summary"
              >
                <ChevronDownIcon className="h-4 w-4" aria-hidden="true" />
                Summary
              </button>
            </div>
          ) : (
            <>
              <ReviewSummaryStrip
                readinessScore={readinessScore}
                revisionTasks={revisionTasks}
                editorDecision={editorDecision}
                reviewerPanel={reviewerPanel}
                metaReview={metaReview}
              />
              <div className="flex items-center justify-between gap-4 px-4 py-3">
                <div className="flex min-w-0 items-center gap-3">
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
                <button
                  type="button"
                  onClick={() => setSummaryCollapsed(true)}
                  className="inline-flex shrink-0 items-center gap-1.5 rounded-md border border-border-default px-2.5 py-1.5 text-xs font-semibold text-text-secondary transition-colors duration-150 hover:bg-bg-elevated hover:text-text-primary active:translate-y-px"
                  aria-expanded="true"
                  aria-label="Hide review summary"
                >
                  <ChevronUpIcon className="h-4 w-4" aria-hidden="true" />
                  Collapse
                </button>
              </div>

              <div className="px-4 pb-3">
                <div className="flex flex-wrap gap-1.5">
                  {visibleCategories.map((key) => (
                    <button
                      key={key}
                      onClick={() => setCategory(key)}
                      className={`min-h-10 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors duration-150 ${
                        category === key
                          ? 'border-border-strong bg-bg-surface text-text-primary'
                          : 'border-transparent bg-transparent text-text-secondary hover:border-border-default hover:bg-bg-surface hover:text-text-primary'
                      }`}
                    >
                      {CATEGORY_CONFIG[key].label}
                      {categoryCounts[key] > 0 && <span className="ml-1.5 text-text-muted">{categoryCounts[key]}</span>}
                    </button>
                  ))}
                </div>
              </div>
            </>
          )}

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
                        ? 'border-border-strong text-text-secondary'
                        : 'border-border-default text-text-muted'
                    }`}>
                      {statusCounts[status]}
                    </span>
                  )}
                </button>
              )
            })}
          </div>
        </div>
      )}

      <div ref={feedbackScrollRef} className={`flex-1 overflow-y-auto px-4 ${compactPreview ? 'py-3' : 'py-4'}`}>
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
              const group = renderedItems[priority]
              if (group.length === 0) return null
              const config = PRIORITY_HEADER_CONFIG[priority]
              const label = priority === 'high' ? 'Top priorities' : config.label
              return (
                <div key={priority}>
                  <div className="mb-3 flex items-center gap-2 py-1">
                    <span className={`h-1.5 w-1.5 rounded-full ${config.dot}`} />
                    <span className={`text-xs font-semibold uppercase tracking-wider ${config.text}`}>
                      {label}
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

            {hasDecisionContext && (
              <div className="space-y-3 border-t border-border-default pt-5">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-wider text-text-muted">
                    Decision Letter & Reviewer Context
                  </p>
                  <p className="mt-1 text-xs text-text-muted">
                    Supporting reviewer detail is collapsed here so the revision queue stays primary.
                  </p>
                </div>
                {editorDecision && <EditorDecisionCard decision={editorDecision} />}
                {metaReview && <MetaReviewCard metaReview={metaReview} />}
                {reviewerPanel && reviewerPanel.length > 0 && <ReviewerPanelTabs reviewers={reviewerPanel} />}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

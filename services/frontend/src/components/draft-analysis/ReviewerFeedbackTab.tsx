import { useState, useMemo, useEffect } from 'react'
import { CheckIcon, ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import UnifiedFeedbackCard from './UnifiedFeedbackCard'
import EditorDecisionCard from './EditorDecisionCard'
import MetaReviewCard from './MetaReviewCard'
import ReviewerPanelTabs from './ReviewerPanelTabs'
import MarkdownText from './MarkdownText'
import type { PdfCoordinates } from '../DocumentViewer'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  section_type?: string
  importance_score: number
  confidence_score?: number
  requires_citation: boolean
  existing_citations: string[]
  supporting_literature?: any
  line_number?: number
  status: 'new' | 'saved' | 'dismissed'
}

interface Gap {
  id: string
  gap_type: string
  description: string
  priority: 'high' | 'medium' | 'low'
  section_type?: string
  suggested_papers?: any[]
  has_relevant_literature?: boolean
  line_number?: number
  status: 'new' | 'saved' | 'dismissed'
}

interface Feedback {
  id: string
  feedback_type: string
  feedback_text: string
  severity: string
  priority: 'high' | 'medium' | 'low'
  reviewer_persona?: string
  section_type?: string
  section_reference?: string
  suggestions?: string[]
  line_number?: number
  status: 'new' | 'saved' | 'dismissed'
}

interface ReviewerFeedbackTabProps {
  claims: Claim[]
  gaps: Gap[]
  feedback: Feedback[]
  carryoverBadges?: Record<string, { label: string; tone: 'warning' | 'accent' }>
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
  fileType: string
  // Phase 3 peer review panel (optional — gracefully absent on older drafts)
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

type StatusFilter = 'new' | 'saved' | 'dismissed'
type ReviewerTab = 'r1' | 'r2'

const SECTION_LABELS: Record<string, string> = {
  abstract: 'Abstract',
  introduction: 'Introduction',
  literature_review: 'Literature Review',
  methodology: 'Methods',
  results: 'Results',
  discussion: 'Discussion',
  conclusion: 'Conclusion',
  references: 'References',
}

const PRIORITY_HEADER_CONFIG = {
  high: { dot: 'bg-error', text: 'text-error', label: 'High Priority' },
  medium: { dot: 'bg-warning', text: 'text-warning', label: 'Medium Priority' },
  low: { dot: 'bg-text-muted', text: 'text-text-muted', label: 'Low Priority' },
}

const PAGE_SIZE = 10

function claimToPriority(claim: Claim): 'high' | 'medium' | 'low' {
  return claim.importance_score >= 0.8 ? 'high' : claim.importance_score >= 0.5 ? 'medium' : 'low'
}

function getReviewerPersona(item: Feedback): ReviewerTab {
  return item.reviewer_persona === 'reviewer_1' ? 'r1' : 'r2'
}

export default function ReviewerFeedbackTab({
  claims,
  gaps,
  feedback,
  carryoverBadges = {},
  onStatusChange,
  onViewInDocument,
  fileType,
  editorDecision,
  reviewerPanel,
  metaReview,
}: ReviewerFeedbackTabProps) {
  const r1Items = useMemo(
    () => feedback.filter((item) => getReviewerPersona(item) === 'r1'),
    [feedback],
  )
  const r2Feedback = useMemo(
    () => feedback.filter((item) => getReviewerPersona(item) === 'r2' && item.feedback_type !== 'strength'),
    [feedback],
  )

  const [reviewerTab, setReviewerTab] = useState<ReviewerTab>(r1Items.length > 0 ? 'r1' : 'r2')
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('new')
  const [activeSection, setActiveSection] = useState<string | null>(null)
  const [visibleCount, setVisibleCount] = useState(PAGE_SIZE)

  useEffect(() => {
    if (r1Items.length === 0 && reviewerTab === 'r1') {
      setReviewerTab('r2')
    }
  }, [r1Items.length, reviewerTab])

  const currentSections = useMemo(() => {
    const sectionOrder = [
      'abstract',
      'introduction',
      'literature_review',
      'methodology',
      'results',
      'discussion',
      'conclusion',
      'references',
    ]
    const set = new Set<string>()

    if (reviewerTab === 'r1') {
      r1Items.forEach((item) => item.section_type && set.add(item.section_type))
    } else {
      claims.forEach((item) => item.section_type && set.add(item.section_type))
      gaps.forEach((item) => item.section_type && set.add(item.section_type))
      r2Feedback.forEach((item) => item.section_type && set.add(item.section_type))
    }

    return sectionOrder.filter((section) => set.has(section))
  }, [reviewerTab, r1Items, claims, gaps, r2Feedback])

  const sectionsWithCritical = useMemo(() => {
    const critical = new Set<string>()
    if (reviewerTab !== 'r2') return critical

    claims.forEach((item) => {
      if (item.section_type && item.requires_citation && item.importance_score >= 0.8) critical.add(item.section_type)
    })
    gaps.forEach((item) => {
      if (item.section_type && item.priority === 'high') critical.add(item.section_type)
    })
    r2Feedback.forEach((item) => {
      if (item.section_type && (item.severity === 'critical' || item.severity === 'major')) critical.add(item.section_type)
    })
    return critical
  }, [reviewerTab, claims, gaps, r2Feedback])

  const statusCounts = useMemo(() => {
    if (reviewerTab === 'r1') {
      return {
        new: r1Items.filter((item) => item.status === 'new').length,
        saved: r1Items.filter((item) => item.status === 'saved').length,
        dismissed: r1Items.filter((item) => item.status === 'dismissed').length,
      }
    }

    return {
      new:
        claims.filter((item) => item.status === 'new').length +
        gaps.filter((item) => item.status === 'new').length +
        r2Feedback.filter((item) => item.status === 'new').length,
      saved:
        claims.filter((item) => item.status === 'saved').length +
        gaps.filter((item) => item.status === 'saved').length +
        r2Feedback.filter((item) => item.status === 'saved').length,
      dismissed:
        claims.filter((item) => item.status === 'dismissed').length +
        gaps.filter((item) => item.status === 'dismissed').length +
        r2Feedback.filter((item) => item.status === 'dismissed').length,
    }
  }, [reviewerTab, r1Items, claims, gaps, r2Feedback])

  const filteredR1Items = useMemo(() => {
    const byStatus = r1Items.filter((item) => item.status === statusFilter)
    return activeSection ? byStatus.filter((item) => item.section_type === activeSection) : byStatus
  }, [r1Items, statusFilter, activeSection])

  const r2VisibleItems = useMemo(() => {
    const filteredClaims = claims.filter((item) => item.status === statusFilter)
    const filteredGaps = gaps.filter((item) => item.status === statusFilter)
    const filteredFeedback = r2Feedback.filter((item) => item.status === statusFilter)

    const sectionClaims = activeSection
      ? filteredClaims.filter((item) => item.section_type === activeSection)
      : filteredClaims
    const sectionGaps = activeSection
      ? filteredGaps.filter((item) => item.section_type === activeSection)
      : filteredGaps
    const sectionFeedback = activeSection
      ? filteredFeedback.filter((item) => item.section_type === activeSection)
      : filteredFeedback

    const items: Array<{
      id: string
      type: 'claim' | 'gap' | 'feedback'
      priority: 'high' | 'medium' | 'low'
      content: Claim | Gap | Feedback
    }> = []

    sectionClaims.forEach((item) => items.push({ id: item.id, type: 'claim', priority: claimToPriority(item), content: item }))
    sectionGaps.forEach((item) => items.push({ id: item.id, type: 'gap', priority: item.priority, content: item }))
    sectionFeedback.forEach((item) => items.push({ id: item.id, type: 'feedback', priority: item.priority, content: item }))

    return items
  }, [claims, gaps, r2Feedback, statusFilter, activeSection])

  const visibleR2Items = useMemo(
    () => r2VisibleItems.slice(0, visibleCount),
    [r2VisibleItems, visibleCount],
  )

  const visibleR1Subset = useMemo(
    () => filteredR1Items.slice(0, visibleCount),
    [filteredR1Items, visibleCount],
  )

  const hasMore = reviewerTab === 'r1'
    ? filteredR1Items.length > visibleCount
    : r2VisibleItems.length > visibleCount

  const handleReviewerTabChange = (nextTab: ReviewerTab) => {
    setReviewerTab(nextTab)
    setActiveSection(null)
    setStatusFilter('new')
    setVisibleCount(PAGE_SIZE)
  }

  const handleStatusChange = (nextStatus: StatusFilter) => {
    setStatusFilter(nextStatus)
    setVisibleCount(PAGE_SIZE)
  }

  const handleSectionChange = (section: string | null) => {
    setActiveSection(section)
    setVisibleCount(PAGE_SIZE)
  }

  return (
    <div className="space-y-4">
      {editorDecision && <EditorDecisionCard decision={editorDecision} />}
      {metaReview && <MetaReviewCard metaReview={metaReview} />}
      {reviewerPanel && reviewerPanel.length > 0 && <ReviewerPanelTabs reviewers={reviewerPanel} />}
      <div className="flex flex-wrap gap-1.5">
        <button
          onClick={() => handleReviewerTabChange('r1')}
          className={`min-h-11 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors duration-fast ${
            reviewerTab === 'r1'
              ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/25'
              : 'text-text-muted border-border-default hover:text-text-secondary'
          }`}
        >
          Reviewer 1 - Strengths ({r1Items.length})
        </button>
        <button
          onClick={() => handleReviewerTabChange('r2')}
          className={`min-h-11 px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors duration-fast ${
            reviewerTab === 'r2'
              ? 'bg-accent-primary/10 text-accent-primary border-accent-primary/20'
              : 'text-text-muted border-border-default hover:text-text-secondary'
          }`}
        >
          Reviewer 2 - Critiques ({claims.length + gaps.length + r2Feedback.length})
        </button>
      </div>

      {currentSections.length > 1 && (
        <div className="flex flex-wrap gap-1.5">
          <button
            onClick={() => handleSectionChange(null)}
            className={`min-h-10 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors duration-150 ${
              activeSection === null
                ? 'bg-accent-primary/10 text-accent-primary border border-accent-primary/20'
                : 'bg-bg-elevated text-text-secondary border border-border-default hover:text-text-primary'
            }`}
          >
            All
          </button>
          {currentSections.map((section) => (
            <button
              key={section}
              onClick={() => handleSectionChange(section)}
              className={`min-h-10 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors duration-150 flex items-center gap-1.5 ${
                activeSection === section
                  ? 'bg-accent-primary/10 text-accent-primary border border-accent-primary/20'
                  : 'bg-bg-elevated text-text-secondary border border-border-default hover:text-text-primary'
              }`}
            >
              {reviewerTab === 'r2' && sectionsWithCritical.has(section) && (
                <ExclamationTriangleIcon className="w-3 h-3 text-warning" />
              )}
              {SECTION_LABELS[section] || section}
            </button>
          ))}
        </div>
      )}

      <div className="flex space-x-1 border-b border-border-default">
        {(['new', 'saved', 'dismissed'] as StatusFilter[]).map((status) => {
          const count = statusCounts[status]
          const isActive = statusFilter === status

          return (
            <button
              key={status}
              onClick={() => handleStatusChange(status)}
              className={`
                min-h-11 px-4 py-2 text-sm font-semibold border-b-2 transition-all duration-150
                ${isActive
                  ? 'border-accent-primary text-text-primary'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
                }
              `}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
              {count > 0 && (
                <span className={`ml-1.5 px-2 py-0.5 rounded-full text-xs border ${
                  isActive
                    ? 'bg-accent-primary/10 text-accent-primary border-accent-primary/20'
                    : 'bg-bg-elevated text-text-muted border-border-default'
                }`}>
                  {count}
                </span>
              )}
            </button>
          )
        })}
      </div>

      {reviewerTab === 'r1' ? (
      <StrengthList
        items={visibleR1Subset}
        hasMore={hasMore}
        statusFilter={statusFilter}
        onLoadMore={() => setVisibleCount((count) => count + PAGE_SIZE)}
        onStatusChange={onStatusChange}
        onViewInDocument={onViewInDocument}
      />
      ) : (
        <CritiqueList
          items={visibleR2Items}
          hasMore={hasMore}
          statusFilter={statusFilter}
          carryoverBadges={carryoverBadges}
          fileType={fileType}
          onLoadMore={() => setVisibleCount((count) => count + PAGE_SIZE)}
          onStatusChange={onStatusChange}
          onViewInDocument={onViewInDocument}
        />
      )}
    </div>
  )
}

function StrengthList({
  items,
  hasMore,
  statusFilter,
  onLoadMore,
  onStatusChange,
  onViewInDocument,
}: {
  items: Feedback[]
  hasMore: boolean
  statusFilter: StatusFilter
  onLoadMore: () => void
  onStatusChange: ReviewerFeedbackTabProps['onStatusChange']
  onViewInDocument?: (payload: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
    pdf_coordinates?: PdfCoordinates
    match_confidence?: number
  }) => void
}) {
  if (items.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-text-secondary">
          {statusFilter === 'new' && 'No Reviewer 1 strengths available yet'}
          {statusFilter === 'saved' && 'No saved Reviewer 1 strengths'}
          {statusFilter === 'dismissed' && 'No dismissed Reviewer 1 strengths'}
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-3">
      {items.map((item) => (
        <div
          key={item.id}
          className="rounded-lg border border-emerald-500/20 bg-emerald-500/5 p-4"
        >
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="rounded text-xs font-semibold border border-emerald-500/25 bg-emerald-500/10 px-2 py-0.5 text-emerald-400">
                Strength
              </span>
              {item.section_type && (
                <span className="text-xs text-text-muted px-1.5 py-0.5 rounded bg-bg-elevated">
                  § {(item.section_type || '').replace(/_/g, ' ')}
                </span>
              )}
            </div>
            {item.line_number && (
              <button
                onClick={() => onViewInDocument?.({ line_number: item.line_number })}
                className="text-xs text-text-muted hover:text-text-primary transition-colors duration-150"
              >
                Line {item.line_number}
              </button>
            )}
          </div>

          <MarkdownText
            as="p"
            text={item.feedback_text}
            className="mt-3 text-sm text-text-primary leading-relaxed"
          />

          {item.section_reference && (
            <p className="mt-2 text-xs text-text-secondary">
              <span className="font-semibold text-text-primary">Reference:</span> {item.section_reference}
            </p>
          )}

          {statusFilter === 'new' ? (
            <div className="mt-4 flex flex-col gap-2 sm:flex-row">
              <button
                onClick={() => onStatusChange(item.id, 'feedback', 'saved')}
                className="min-h-11 flex-1 flex items-center justify-center gap-1.5 rounded-lg bg-success px-3 py-2 text-xs font-semibold text-white hover:opacity-90 transition-opacity duration-150"
              >
                <CheckIcon className="w-3.5 h-3.5" />
                Save
              </button>
              <button
                onClick={() => onStatusChange(item.id, 'feedback', 'dismissed')}
                className="min-h-11 flex items-center justify-center gap-1.5 rounded-lg border border-border-default bg-bg-elevated px-3 py-2 text-xs font-semibold text-text-secondary hover:text-text-primary hover:border-border-subtle transition-colors duration-150"
              >
                <XMarkIcon className="w-3.5 h-3.5" />
                Dismiss
              </button>
            </div>
          ) : (
            <p className={`mt-4 text-xs font-semibold ${statusFilter === 'saved' ? 'text-success' : 'text-text-muted'}`}>
              {statusFilter === 'saved' ? 'Saved for later' : 'Dismissed'}
            </p>
          )}
        </div>
      ))}

      {hasMore && (
        <button
          onClick={onLoadMore}
          className="w-full min-h-11 rounded-lg border border-border-default px-4 py-3 text-sm font-semibold text-text-secondary hover:text-text-primary hover:border-border-subtle transition-colors duration-150"
        >
          Show more strengths
        </button>
      )}
    </div>
  )
}

function CritiqueList({
  items,
  hasMore,
  statusFilter,
  carryoverBadges,
  onLoadMore,
  onStatusChange,
  onViewInDocument,
  fileType,
}: {
  items: Array<{
    id: string
    type: 'claim' | 'gap' | 'feedback'
    priority: 'high' | 'medium' | 'low'
    content: Claim | Gap | Feedback
  }>
  hasMore: boolean
  statusFilter: StatusFilter
  carryoverBadges: ReviewerFeedbackTabProps['carryoverBadges']
  onLoadMore: () => void
  onStatusChange: ReviewerFeedbackTabProps['onStatusChange']
  onViewInDocument?: (payload: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
    pdf_coordinates?: PdfCoordinates
    match_confidence?: number
  }) => void
  fileType: string
}) {
  const groupedItems = useMemo(() => ({
    high: items.filter((item) => item.priority === 'high'),
    medium: items.filter((item) => item.priority === 'medium'),
    low: items.filter((item) => item.priority === 'low'),
  }), [items])

  if (items.length === 0) {
    return (
      <div className="text-center py-8">
        <p className="text-sm text-text-secondary">
          {statusFilter === 'new' && 'No Reviewer 2 critiques to display'}
          {statusFilter === 'saved' && 'No saved Reviewer 2 critiques'}
          {statusFilter === 'dismissed' && 'No dismissed Reviewer 2 critiques'}
        </p>
      </div>
    )
  }

  return (
    <div>
      {(['high', 'medium', 'low'] as const).map((priority) => {
        const config = PRIORITY_HEADER_CONFIG[priority]
        const group = groupedItems[priority]
        if (group.length === 0) return null

        return (
          <div key={priority} className="mb-5">
            <div className="mb-3 flex items-center gap-2 py-1">
              <span className={`h-1.5 w-1.5 rounded-full shrink-0 ${config.dot}`} />
              <span className={`text-xs font-semibold uppercase tracking-wider ${config.text}`}>
                {config.label}
              </span>
              <span className="text-xs text-text-muted ml-1">{group.length}</span>
              <div className="ml-1 h-px flex-1 bg-border-default" />
            </div>

            <div className="space-y-3">
              {group.map((item) => {
                const badge = item.type === 'feedback' ? carryoverBadges?.[item.id] : undefined
                return (
                  <div key={item.id}>
                    {badge && (
                      <span className={`mb-2 inline-flex rounded-lg border px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide ${
                        badge.tone === 'warning'
                          ? 'border-warning/20 bg-warning/10 text-warning'
                          : 'border-accent-primary/20 bg-accent-primary/10 text-accent-primary'
                      }`}>
                        {badge.label}
                      </span>
                    )}
                    <UnifiedFeedbackCard
                      item={item}
                      onStatusChange={onStatusChange}
                      onViewInDocument={onViewInDocument}
                      currentStatus={statusFilter}
                      fileType={fileType}
                    />
                  </div>
                )
              })}
            </div>
          </div>
        )
      })}

      {hasMore && (
        <button
          onClick={onLoadMore}
          className="w-full min-h-11 rounded-lg border border-border-default px-4 py-3 text-sm font-semibold text-text-secondary hover:text-text-primary hover:border-border-subtle transition-colors duration-150"
        >
          Show more critiques
        </button>
      )}
    </div>
  )
}

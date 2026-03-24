import { useState, useMemo } from 'react'
import PriorityGroup from './PriorityGroup'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  importance_score: number
  confidence_score?: number
  requires_citation: boolean
  existing_citations: string[]
  line_number?: number
  status: 'new' | 'saved' | 'dismissed'
}

interface Gap {
  id: string
  gap_type: string
  description: string
  priority: 'high' | 'medium' | 'low'
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
  section_reference?: string
  suggestions?: string[]
  line_number?: number
  status: 'new' | 'saved' | 'dismissed'
}

interface SectionFeedbackTabsProps {
  sectionType: string
  claims: Claim[]
  gaps: Gap[]
  feedback: Feedback[]
  onStatusChange: (feedbackId: string, feedbackType: 'claim' | 'gap' | 'feedback', newStatus: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument?: (lineNumber: number) => void
}

type StatusFilter = 'new' | 'saved' | 'dismissed'

export default function SectionFeedbackTabs({
  sectionType: _sectionType,
  claims,
  gaps,
  feedback,
  onStatusChange,
  onViewInDocument
}: SectionFeedbackTabsProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('new')

  // Filter feedback by status
  const filteredClaims = useMemo(() =>
    claims.filter(c => c.status === statusFilter),
    [claims, statusFilter]
  )

  const filteredGaps = useMemo(() =>
    gaps.filter(g => g.status === statusFilter),
    [gaps, statusFilter]
  )

  const filteredFeedback = useMemo(() =>
    feedback.filter(f => f.status === statusFilter),
    [feedback, statusFilter]
  )

  // Combine all items with priority
  const allFeedbackItems = useMemo(() => {
    const items: Array<{
      id: string
      type: 'claim' | 'gap' | 'feedback'
      priority: 'high' | 'medium' | 'low'
      content: any
    }> = []

    filteredClaims.forEach(claim => {
      items.push({
        id: claim.id,
        type: 'claim',
        priority: claim.importance_score >= 0.8 ? 'high' : claim.importance_score >= 0.5 ? 'medium' : 'low',
        content: claim
      })
    })

    filteredGaps.forEach(gap => {
      items.push({
        id: gap.id,
        type: 'gap',
        priority: gap.priority,
        content: gap
      })
    })

    filteredFeedback.forEach(fb => {
      items.push({
        id: fb.id,
        type: 'feedback',
        priority: fb.priority,
        content: fb
      })
    })

    return items
  }, [filteredClaims, filteredGaps, filteredFeedback])

  // Count by status
  const statusCounts = useMemo(() => ({
    new: claims.filter(c => c.status === 'new').length +
         gaps.filter(g => g.status === 'new').length +
         feedback.filter(f => f.status === 'new').length,
    saved: claims.filter(c => c.status === 'saved').length +
           gaps.filter(g => g.status === 'saved').length +
           feedback.filter(f => f.status === 'saved').length,
    dismissed: claims.filter(c => c.status === 'dismissed').length +
               gaps.filter(g => g.status === 'dismissed').length +
               feedback.filter(f => f.status === 'dismissed').length
  }), [claims, gaps, feedback])

  return (
    <div className="space-y-4">
      {/* Status Tabs */}
      <div className="flex space-x-1 border-b border-border-default">
        <button
          onClick={() => setStatusFilter('new')}
          className={`
            px-4 py-2 text-sm font-semibold border-b-2 transition-all duration-fast
            ${statusFilter === 'new'
              ? 'border-accent-primary text-text-primary'
              : 'border-transparent text-text-secondary hover:text-text-primary'
            }
          `}
        >
          New {statusCounts.new > 0 && (
            <span className={`ml-1.5 px-2 py-0.5 rounded-full text-xs border ${
              statusFilter === 'new'
                ? 'bg-accent-primary/10 text-accent-primary border-accent-primary/20'
                : 'bg-bg-elevated text-text-muted border-border-default'
            }`}>
              {statusCounts.new}
            </span>
          )}
        </button>

        <button
          onClick={() => setStatusFilter('saved')}
          className={`
            px-4 py-2 text-sm font-semibold border-b-2 transition-all duration-fast
            ${statusFilter === 'saved'
              ? 'border-success text-text-primary'
              : 'border-transparent text-text-secondary hover:text-text-primary'
            }
          `}
        >
          Saved {statusCounts.saved > 0 && (
            <span className={`ml-1.5 px-2 py-0.5 rounded-full text-xs border ${
              statusFilter === 'saved'
                ? 'bg-success/10 text-success border-success/20'
                : 'bg-bg-elevated text-text-muted border-border-default'
            }`}>
              {statusCounts.saved}
            </span>
          )}
        </button>

        <button
          onClick={() => setStatusFilter('dismissed')}
          className={`
            px-4 py-2 text-sm font-semibold border-b-2 transition-all duration-fast
            ${statusFilter === 'dismissed'
              ? 'border-border-subtle text-text-primary'
              : 'border-transparent text-text-secondary hover:text-text-primary'
            }
          `}
        >
          Dismissed {statusCounts.dismissed > 0 && (
            <span className="ml-1.5 px-2 py-0.5 rounded-full text-xs bg-bg-elevated text-text-muted border border-border-default">
              {statusCounts.dismissed}
            </span>
          )}
        </button>
      </div>

      {/* Feedback items */}
      {allFeedbackItems.length > 0 ? (
        <PriorityGroup
          items={allFeedbackItems}
          onStatusChange={onStatusChange}
          onViewInDocument={onViewInDocument}
          currentStatus={statusFilter}
        />
      ) : (
        <div className="text-center py-12">
          <p className="text-sm text-text-secondary">
            {statusFilter === 'new' && 'No new feedback items'}
            {statusFilter === 'saved' && 'No saved feedback items'}
            {statusFilter === 'dismissed' && 'No dismissed feedback items'}
          </p>
          <p className="text-xs mt-1 text-text-muted">
            {statusFilter === 'new' && 'Great work! All items have been reviewed.'}
            {statusFilter === 'saved' && 'Save useful feedback to review later.'}
            {statusFilter === 'dismissed' && "Dismissed items won't appear in the New tab."}
          </p>
        </div>
      )}
    </div>
  )
}

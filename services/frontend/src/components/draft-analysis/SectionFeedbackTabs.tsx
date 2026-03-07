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

// Section-specific tab configuration
const SECTION_TAB_CONFIG: Record<string, { label: string; category: string }[]> = {
  abstract: [
    { label: 'Positioning', category: 'positioning' },
    { label: 'Coverage', category: 'coverage' },
    { label: 'Clarity', category: 'clarity' }
  ],
  introduction: [
    { label: 'Positioning', category: 'positioning' },
    { label: 'Gap Identification', category: 'gap_identification' },
    { label: 'Motivation', category: 'motivation' }
  ],
  literature_review: [
    { label: 'Coverage Gaps', category: 'coverage_gaps' },
    { label: 'Synthesis Quality', category: 'synthesis_quality' },
    { label: 'Missing Works', category: 'missing_works' }
  ],
  methodology: [
    { label: 'Rigor', category: 'rigor' },
    { label: 'Reproducibility', category: 'reproducibility' },
    { label: 'Alternatives', category: 'alternatives' },
    { label: 'Detail', category: 'detail' }
  ],
  results: [
    { label: 'Evidence Strength', category: 'evidence_strength' },
    { label: 'Analysis Depth', category: 'analysis_depth' },
    { label: 'Limitations', category: 'limitations' }
  ],
  discussion: [
    { label: 'Positioning', category: 'positioning' },
    { label: 'Limitations', category: 'limitations' },
    { label: 'Future Work', category: 'future_work' }
  ],
  conclusion: [
    { label: 'Contribution Clarity', category: 'contribution_clarity' },
    { label: 'Scope', category: 'scope' }
  ],
  references: [
    { label: 'Completeness', category: 'completeness' },
    { label: 'Format', category: 'format' }
  ]
}

type StatusFilter = 'new' | 'saved' | 'dismissed'

export default function SectionFeedbackTabs({
  sectionType,
  claims,
  gaps,
  feedback,
  onStatusChange,
  onViewInDocument
}: SectionFeedbackTabsProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('new')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')

  // Get section-specific tabs
  const sectionTabs = SECTION_TAB_CONFIG[sectionType] || [
    { label: 'All Feedback', category: 'all' }
  ]

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

  // Further filter by category if not 'all'
  // Map category to feedback_type patterns
  const categoryMap: Record<string, string[]> = {
    positioning: ['positioning'],
    coverage: ['coverage'],
    coverage_gaps: ['coverage', 'gap'],
    gap_identification: ['gap', 'positioning'],
    motivation: ['motivation', 'argumentation'],
    synthesis_quality: ['synthesis', 'argumentation'],
    missing_works: ['coverage', 'missing'],
    rigor: ['methodology', 'rigor'],
    reproducibility: ['methodology', 'reproducibility'],
    alternatives: ['methodology', 'alternatives'],
    detail: ['methodology', 'detail'],
    evidence_strength: ['evidence', 'argumentation'],
    analysis_depth: ['analysis', 'argumentation'],
    limitations: ['limitation'],
    future_work: ['future'],
    contribution_clarity: ['contribution', 'positioning'],
    scope: ['scope'],
    completeness: ['completeness'],
    format: ['format'],
    clarity: ['clarity']
  }

  const categoryFilteredClaims = useMemo(() => {
    if (categoryFilter === 'all') {
      return filteredClaims
    }

    const patterns = categoryMap[categoryFilter] || []
    return filteredClaims.filter(c => {
      const type = c.claim_type.toLowerCase()
      return patterns.some(pattern => type.includes(pattern))
    })
  }, [filteredClaims, categoryFilter])

  const categoryFilteredGaps = useMemo(() => {
    if (categoryFilter === 'all') {
      return filteredGaps
    }

    const patterns = categoryMap[categoryFilter] || []
    return filteredGaps.filter(g => {
      const type = g.gap_type.toLowerCase()
      return patterns.some(pattern => type.includes(pattern))
    })
  }, [filteredGaps, categoryFilter])

  const categoryFilteredFeedback = useMemo(() => {
    if (categoryFilter === 'all') {
      return filteredFeedback
    }

    const patterns = categoryMap[categoryFilter] || []
    return filteredFeedback.filter(f => {
      const type = f.feedback_type.toLowerCase()
      return patterns.some(pattern => type.includes(pattern))
    })
  }, [filteredFeedback, categoryFilter])

  // Combine all feedback items for display
  const allFeedbackItems = useMemo(() => {
    const items: Array<{
      id: string
      type: 'claim' | 'gap' | 'feedback'
      priority: 'high' | 'medium' | 'low'
      content: any
    }> = []

    // Add claims (priority based on importance_score)
    categoryFilteredClaims.forEach(claim => {
      items.push({
        id: claim.id,
        type: 'claim',
        priority: claim.importance_score >= 0.8 ? 'high' : claim.importance_score >= 0.5 ? 'medium' : 'low',
        content: claim
      })
    })

    // Add gaps (priority from gap.priority)
    categoryFilteredGaps.forEach(gap => {
      items.push({
        id: gap.id,
        type: 'gap',
        priority: gap.priority,
        content: gap
      })
    })

    // Add feedback (priority from feedback.priority)
    categoryFilteredFeedback.forEach(fb => {
      items.push({
        id: fb.id,
        type: 'feedback',
        priority: fb.priority,
        content: fb
      })
    })

    return items
  }, [categoryFilteredClaims, categoryFilteredGaps, categoryFilteredFeedback])

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
      {/* Status Tabs (New / Saved / Dismissed) */}
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

      {/* Category Tabs (Section-specific) */}
      <div className="flex flex-wrap gap-2">
        <button
          onClick={() => setCategoryFilter('all')}
          className={`
            px-3 py-1.5 rounded-lg text-sm font-semibold border transition-all duration-fast
            ${categoryFilter === 'all'
              ? 'bg-bg-elevated text-text-primary border-border-subtle'
              : 'bg-bg-surface text-text-secondary border-border-default hover:text-text-primary hover:border-border-subtle'
            }
          `}
        >
          All
        </button>

        {sectionTabs.map(tab => (
          <button
            key={tab.category}
            onClick={() => setCategoryFilter(tab.category)}
            className={`
              px-3 py-1.5 rounded-lg text-sm font-semibold border transition-all duration-fast
              ${categoryFilter === tab.category
                ? 'bg-bg-elevated text-text-primary border-border-subtle'
                : 'bg-bg-surface text-text-secondary border-border-default hover:text-text-primary hover:border-border-subtle'
              }
            `}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* Feedback Display with Priority Grouping */}
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

import { useState, useMemo } from 'react'
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline'
import PriorityGroup from './PriorityGroup'
import UnifiedFeedbackCard from './UnifiedFeedbackCard'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  importance_score: number
  confidence_score?: number
  requires_citation: boolean
  existing_citations: string[]
  supporting_literature?: any  // JSONB: array (old) or { top_match, suggested_citations } (new)
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

type FeedbackItem = {
  id: string
  type: 'claim' | 'gap' | 'feedback'
  priority: 'high' | 'medium' | 'low'
  content: any
}

function claimToPriority(claim: Claim): 'high' | 'medium' | 'low' {
  return claim.importance_score >= 0.8 ? 'high' : claim.importance_score >= 0.5 ? 'medium' : 'low'
}

export default function SectionFeedbackTabs({
  sectionType: _sectionType,
  claims,
  gaps,
  feedback,
  onStatusChange,
  onViewInDocument
}: SectionFeedbackTabsProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('new')
  const [strengthsExpanded, setStrengthsExpanded] = useState(false)
  const [allClaimsExpanded, setAllClaimsExpanded] = useState(false)

  // Filter by status
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

  // A3: Split claims — actionable (needs citation or high importance) vs informational
  const actionableClaims = useMemo(() =>
    filteredClaims.filter(c => c.requires_citation === true || c.importance_score >= 0.65),
    [filteredClaims]
  )

  const informationalClaims = useMemo(() =>
    filteredClaims.filter(c => c.requires_citation !== true && c.importance_score < 0.65),
    [filteredClaims]
  )

  // A2: Separate strengths (read-only accordion) from actionable feedback
  const strengthItems = useMemo(() =>
    filteredFeedback.filter(f => f.feedback_type === 'strength'),
    [filteredFeedback]
  )

  const actionableFeedback = useMemo(() =>
    filteredFeedback.filter(f => f.feedback_type !== 'strength'),
    [filteredFeedback]
  )

  // Main actionable list: actionable claims + gaps + non-strength feedback
  const allFeedbackItems = useMemo((): FeedbackItem[] => {
    const items: FeedbackItem[] = []

    actionableClaims.forEach(claim => {
      items.push({ id: claim.id, type: 'claim', priority: claimToPriority(claim), content: claim })
    })

    filteredGaps.forEach(gap => {
      items.push({ id: gap.id, type: 'gap', priority: gap.priority, content: gap })
    })

    actionableFeedback.forEach(fb => {
      items.push({ id: fb.id, type: 'feedback', priority: fb.priority, content: fb })
    })

    return items
  }, [actionableClaims, filteredGaps, actionableFeedback])

  // A2+A3: Status counts — exclude strengths and informational claims from 'new'
  const statusCounts = useMemo(() => {
    const actionableNew =
      claims.filter(c => c.status === 'new' && (c.requires_citation === true || c.importance_score >= 0.65)).length +
      gaps.filter(g => g.status === 'new').length +
      feedback.filter(f => f.status === 'new' && f.feedback_type !== 'strength').length

    return {
      new: actionableNew,
      saved: claims.filter(c => c.status === 'saved').length +
             gaps.filter(g => g.status === 'saved').length +
             feedback.filter(f => f.status === 'saved').length,
      dismissed: claims.filter(c => c.status === 'dismissed').length +
                 gaps.filter(g => g.status === 'dismissed').length +
                 feedback.filter(f => f.status === 'dismissed').length,
    }
  }, [claims, gaps, feedback])

  // Collapsed accordion items
  const strengthCardItems = useMemo((): FeedbackItem[] =>
    strengthItems.map(fb => ({ id: fb.id, type: 'feedback' as const, priority: fb.priority, content: fb })),
    [strengthItems]
  )

  const informationalCardItems = useMemo((): FeedbackItem[] =>
    informationalClaims.map(claim => ({
      id: claim.id,
      type: 'claim' as const,
      priority: claimToPriority(claim),
      content: claim,
    })),
    [informationalClaims]
  )

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

      {/* Main actionable feedback items */}
      {allFeedbackItems.length > 0 ? (
        <PriorityGroup
          items={allFeedbackItems}
          onStatusChange={onStatusChange}
          onViewInDocument={onViewInDocument}
          currentStatus={statusFilter}
        />
      ) : (
        <div className="text-center py-8">
          <p className="text-sm text-text-secondary">
            {statusFilter === 'new' && 'No new items requiring action'}
            {statusFilter === 'saved' && 'No saved feedback items'}
            {statusFilter === 'dismissed' && 'No dismissed feedback items'}
          </p>
          <p className="text-xs mt-1 text-text-muted">
            {statusFilter === 'new' && informationalClaims.length > 0 && 'All claims are well-supported — see below.'}
            {statusFilter === 'saved' && 'Save useful feedback to review later.'}
            {statusFilter === 'dismissed' && "Dismissed items won't appear in the New tab."}
          </p>
        </div>
      )}

      {/* A3: Well-supported / informational claims accordion */}
      {statusFilter === 'new' && informationalCardItems.length > 0 && (
        <div className="border border-border-default rounded-lg overflow-hidden">
          <button
            onClick={() => setAllClaimsExpanded(!allClaimsExpanded)}
            className="w-full flex items-center justify-between px-4 py-3 bg-bg-elevated hover:bg-bg-surface transition-colors duration-150"
          >
            <span className="text-xs font-semibold text-text-secondary">
              {informationalCardItems.length} well-supported claim{informationalCardItems.length !== 1 ? 's' : ''} — no action needed
            </span>
            {allClaimsExpanded
              ? <ChevronUpIcon className="w-4 h-4 text-text-muted" />
              : <ChevronDownIcon className="w-4 h-4 text-text-muted" />
            }
          </button>
          {allClaimsExpanded && (
            <div className="p-3 space-y-2">
              {informationalCardItems.map(item => (
                <UnifiedFeedbackCard
                  key={item.id}
                  item={item}
                  onStatusChange={onStatusChange}
                  onViewInDocument={onViewInDocument}
                  currentStatus={statusFilter}
                />
              ))}
            </div>
          )}
        </div>
      )}

      {/* A2: Strengths accordion — read-only, no action buttons */}
      {statusFilter === 'new' && strengthCardItems.length > 0 && (
        <div className="border border-success/20 rounded-lg overflow-hidden">
          <button
            onClick={() => setStrengthsExpanded(!strengthsExpanded)}
            className="w-full flex items-center justify-between px-4 py-3 bg-success/5 hover:bg-success/10 transition-colors duration-150"
          >
            <span className="text-xs font-semibold text-success">
              ✓ {strengthCardItems.length} strength{strengthCardItems.length !== 1 ? 's' : ''} — what's working
            </span>
            {strengthsExpanded
              ? <ChevronUpIcon className="w-4 h-4 text-success/70" />
              : <ChevronDownIcon className="w-4 h-4 text-success/70" />
            }
          </button>
          {strengthsExpanded && (
            <div className="p-3 space-y-2">
              {strengthCardItems.map(item => (
                <UnifiedFeedbackCard
                  key={item.id}
                  item={item}
                  onStatusChange={onStatusChange}
                  onViewInDocument={onViewInDocument}
                  currentStatus={statusFilter}
                />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  )
}

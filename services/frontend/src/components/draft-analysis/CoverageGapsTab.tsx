import { useState, useMemo, useEffect } from 'react'
import {
  ArrowTopRightOnSquareIcon,
  BookmarkIcon,
  CheckIcon,
  ExclamationTriangleIcon,
  MagnifyingGlassIcon,
  XMarkIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { ApiError, api } from '../../lib/api'
import { handleError } from '../../lib/errorHandler'

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

interface CoverageGapsTabProps {
  gaps: Gap[]
  projectId?: string
  token?: string
  onStatusChange: (feedbackId: string, feedbackType: 'claim' | 'gap' | 'feedback', newStatus: 'new' | 'saved' | 'dismissed') => void
  onViewInDocument?: (lineNumber: number) => void
}

type StatusFilter = 'new' | 'saved' | 'dismissed'

const GAP_TYPE_LABELS: Record<string, string> = {
  missing_citation: 'Missing Citation',
  missing_methodology: 'Missing Methodology',
  theoretical_gap: 'Theoretical Gap',
  empirical_gap: 'Empirical Gap',
  literature_gap: 'Literature Gap',
  comparison_gap: 'Missing Comparison',
  replication_gap: 'Replication Gap',
}

const PRIORITY_CONFIG = {
  high: { border: 'border-l-error', badge: 'bg-error/10 text-error border-error/20', label: 'Critical' },
  medium: { border: 'border-l-warning', badge: 'bg-warning/10 text-warning border-warning/20', label: 'High' },
  low: { border: 'border-l-border-subtle', badge: 'bg-bg-elevated text-text-muted border-border-default', label: 'Medium' },
}

export default function CoverageGapsTab({
  gaps,
  projectId,
  token,
  onStatusChange,
  onViewInDocument,
}: CoverageGapsTabProps) {
  const [statusFilter, setStatusFilter] = useState<StatusFilter>('new')
  const [searchingGapId, setSearchingGapId] = useState<string | null>(null)
  const [savingRecommendationId, setSavingRecommendationId] = useState<string | null>(null)
  const [inlineRecommendations, setInlineRecommendations] = useState<Record<string, any[]>>({})
  const [quota, setQuota] = useState<{
    actions_used: number
    actions_limit: number | null
    total_held: number
    max_pool: number | null
  } | null>(null)

  useEffect(() => {
    if (!token || !projectId) return
    api.discover.getQuotaStatus(token, projectId)
      .then((response) => setQuota(response))
      .catch(() => {})
  }, [token, projectId])

  const filteredGaps = useMemo(() => (
    gaps.filter((gap) => gap.status === statusFilter)
  ), [gaps, statusFilter])

  const sortedGaps = useMemo(() => (
    [...filteredGaps].sort((a, b) => {
      const order = { high: 0, medium: 1, low: 2 }
      return (order[a.priority] ?? 2) - (order[b.priority] ?? 2)
    })
  ), [filteredGaps])

  const criticalCount = useMemo(() => (
    gaps.filter((gap) => gap.priority === 'high' && gap.status === 'new').length
  ), [gaps])

  const statusCounts = useMemo(() => ({
    new: gaps.filter((gap) => gap.status === 'new').length,
    saved: gaps.filter((gap) => gap.status === 'saved').length,
    dismissed: gaps.filter((gap) => gap.status === 'dismissed').length,
  }), [gaps])

  const discoverExhausted = quota?.actions_limit !== null && quota?.actions_used !== undefined
    ? quota.actions_used >= quota.actions_limit
    : false

  const handleFindPapers = async (gap: Gap) => {
    if (!token || !projectId) return
    try {
      setSearchingGapId(gap.id)
      const response = await api.discover.search(token, projectId, gap.description)
      setInlineRecommendations((current) => ({
        ...current,
        [gap.id]: response.recommendations || [],
      }))
      if (response.quota) {
        setQuota({
          actions_used: response.quota.used,
          actions_limit: response.quota.limit,
          total_held: quota?.total_held ?? 0,
          max_pool: quota?.max_pool ?? null,
        })
      } else if (token && projectId) {
        const quotaResponse = await api.discover.getQuotaStatus(token, projectId)
        setQuota(quotaResponse)
      }
    } catch (error) {
      if (error instanceof ApiError && error.status === 429) {
        toast.error('Discover search limit reached for today')
      } else {
        handleError(error, 'finding gap papers')
      }
    } finally {
      setSearchingGapId(null)
    }
  }

  const handleSaveRecommendation = async (gapId: string, recommendationId: string) => {
    if (!token || !projectId) return
    try {
      setSavingRecommendationId(recommendationId)
      await api.discover.saveToLiterature(token, projectId, recommendationId)
      setInlineRecommendations((current) => ({
        ...current,
        [gapId]: (current[gapId] || []).map((paper) => (
          paper.id === recommendationId ? { ...paper, bib_saved: true } : paper
        )),
      }))
      toast.success('Paper saved to Literature')
    } catch (error) {
      handleError(error, 'saving discovered paper')
    } finally {
      setSavingRecommendationId(null)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h3 className="text-sm font-semibold text-text-primary">Coverage Analysis</h3>
          <p className="mt-1 text-xs text-text-secondary">
            Review the highest-risk gaps first, then pull external papers into Literature when coverage is thin.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {criticalCount > 0 && (
            <span className="flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-error/10 text-error border border-error/20">
              <ExclamationTriangleIcon className="w-3.5 h-3.5" />
              {criticalCount} Critical Gap{criticalCount !== 1 ? 's' : ''}
            </span>
          )}
          {quota && (
            <span className="rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary">
              {quota.actions_limit === null
                ? 'Unlimited discover searches'
                : `${quota.actions_used}/${quota.actions_limit} discover searches today`}
            </span>
          )}
        </div>
      </div>

      <div className="flex space-x-1 border-b border-border-default">
        {(['new', 'saved', 'dismissed'] as StatusFilter[]).map((status) => {
          const count = statusCounts[status]
          const isActive = statusFilter === status
          return (
            <button
              key={status}
              onClick={() => setStatusFilter(status)}
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

      {sortedGaps.length > 0 ? (
        <div className="space-y-3">
          {sortedGaps.map((gap) => {
            const config = PRIORITY_CONFIG[gap.priority]
            const typeLabel = GAP_TYPE_LABELS[gap.gap_type] || gap.gap_type?.replace(/_/g, ' ')
            const suggestedPapers = gap.suggested_papers || []
            const recommendations = inlineRecommendations[gap.id] || []

            return (
              <div
                key={gap.id}
                className={`bg-bg-surface rounded-lg border border-border-default border-l-2 ${config.border} p-4 transition-colors duration-150 hover:border-border-subtle`}
              >
                <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between mb-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className={`px-2 py-0.5 rounded text-xs font-semibold border ${config.badge}`}>
                      {config.label}
                    </span>
                    {typeLabel && (
                      <span className="text-xs text-text-muted capitalize">{typeLabel}</span>
                    )}
                  </div>
                  {gap.line_number && (
                    <button
                      onClick={() => onViewInDocument?.(gap.line_number!)}
                      className="min-h-10 text-xs text-text-muted hover:text-text-primary flex items-center gap-1 transition-colors duration-150"
                    >
                      <span>Line {gap.line_number}</span>
                      <ArrowTopRightOnSquareIcon className="w-3.5 h-3.5" />
                    </button>
                  )}
                </div>

                <p className="text-sm text-text-primary leading-relaxed mb-3">
                  {gap.description}
                </p>

                {suggestedPapers.length > 0 && (
                  <div className="mb-3">
                    <h4 className="text-xs font-semibold text-text-secondary mb-2">
                      Existing suggested papers ({suggestedPapers.length})
                    </h4>
                    <div className="space-y-1.5">
                      {suggestedPapers.slice(0, 4).map((paper: any, idx: number) => (
                        <div key={idx} className="pl-3 border-l border-border-subtle">
                          {typeof paper === 'string' ? (
                            <span className="text-xs text-accent-primary">{paper}</span>
                          ) : (
                            <div>
                              <span className="text-xs text-accent-primary font-medium">
                                {paper.title || paper.citation_string || 'Untitled'}
                              </span>
                              {(paper.authors || paper.year) && (
                                <span className="text-xs text-text-muted ml-1.5">
                                  {paper.authors
                                    ? (Array.isArray(paper.authors)
                                      ? `${paper.authors.slice(0, 2).join(', ')}${paper.authors.length > 2 ? ' et al.' : ''}`
                                      : paper.authors)
                                    : ''}
                                  {paper.authors && paper.year ? ' · ' : ''}
                                  {paper.year}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {statusFilter === 'new' && token && projectId && (
                  <div className="mb-3 rounded-lg border border-border-default bg-bg-elevated p-3">
                    <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div>
                        <p className="text-xs font-semibold text-text-primary">External paper lookup</p>
                        <p className="mt-1 text-xs text-text-secondary">
                          Search Discover with this gap description and save relevant papers directly into Literature.
                        </p>
                      </div>
                      <button
                        onClick={() => handleFindPapers(gap)}
                        disabled={searchingGapId === gap.id || discoverExhausted}
                        className="min-h-11 inline-flex items-center justify-center gap-1.5 rounded-lg border border-border-default px-3 py-2 text-xs font-semibold text-text-secondary hover:text-text-primary hover:border-border-subtle disabled:opacity-50 disabled:cursor-not-allowed transition-colors duration-150"
                      >
                        <MagnifyingGlassIcon className="w-3.5 h-3.5" />
                        {searchingGapId === gap.id ? 'Searching...' : 'Find relevant papers'}
                      </button>
                    </div>

                    {recommendations.length > 0 && (
                      <div className="mt-3 space-y-2">
                        {recommendations.slice(0, 5).map((paper) => (
                          <div
                            key={paper.id}
                            className="rounded-lg border border-border-default bg-bg-surface px-3 py-2"
                          >
                            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
                              <div className="min-w-0">
                                <p className="text-sm font-semibold text-text-primary">{paper.title}</p>
                                <p className="mt-1 text-xs text-text-secondary">
                                  {Array.isArray(paper.authors)
                                    ? `${paper.authors.slice(0, 3).join(', ')}${paper.authors.length > 3 ? ' et al.' : ''}`
                                    : paper.authors || 'Authors unavailable'}
                                  {paper.year ? ` · ${paper.year}` : ''}
                                </p>
                              </div>
                              <button
                                onClick={() => handleSaveRecommendation(gap.id, paper.id)}
                                disabled={paper.bib_saved || savingRecommendationId === paper.id}
                                className={`min-h-11 shrink-0 rounded-lg px-3 py-2 text-xs font-semibold transition-colors duration-150 ${
                                  paper.bib_saved
                                    ? 'border border-emerald-500/20 bg-emerald-500/10 text-emerald-400'
                                    : 'border border-border-default bg-bg-elevated text-text-secondary hover:text-text-primary hover:border-border-subtle'
                                }`}
                              >
                                <span className="inline-flex items-center gap-1.5">
                                  <BookmarkIcon className="w-3.5 h-3.5" />
                                  {paper.bib_saved
                                    ? 'Saved to Literature'
                                    : savingRecommendationId === paper.id
                                      ? 'Saving...'
                                      : 'Save to Literature'}
                                </span>
                              </button>
                            </div>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {statusFilter === 'new' && (
                  <div className="flex flex-col gap-2 pt-3 border-t border-border-default sm:flex-row">
                    <button
                      onClick={() => onStatusChange(gap.id, 'gap', 'saved')}
                      className="min-h-11 flex-1 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-success text-white hover:opacity-90 transition-opacity duration-150"
                    >
                      <CheckIcon className="w-3.5 h-3.5" />
                      Mark addressed
                    </button>
                    <button
                      onClick={() => onStatusChange(gap.id, 'gap', 'dismissed')}
                      className="min-h-11 flex items-center justify-center gap-1.5 px-3 py-2 rounded-lg text-xs font-semibold bg-bg-elevated text-text-secondary hover:text-text-primary border border-border-default hover:border-border-subtle transition-colors duration-150"
                    >
                      <XMarkIcon className="w-3.5 h-3.5" />
                      Dismiss
                    </button>
                  </div>
                )}

                {statusFilter !== 'new' && (
                  <div className="pt-3 border-t border-border-default">
                    <span className={`text-xs font-semibold ${statusFilter === 'saved' ? 'text-success' : 'text-text-muted'}`}>
                      {statusFilter === 'saved' ? 'Addressed' : 'Dismissed'}
                    </span>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      ) : (
        <div className="text-center py-8">
          <p className="text-sm text-text-secondary">
            {statusFilter === 'new' && 'No coverage gaps found'}
            {statusFilter === 'saved' && 'No addressed gaps'}
            {statusFilter === 'dismissed' && 'No dismissed gaps'}
          </p>
          <p className="text-xs mt-1 text-text-muted">
            {statusFilter === 'new' && 'Your literature coverage looks solid.'}
          </p>
        </div>
      )}
    </div>
  )
}

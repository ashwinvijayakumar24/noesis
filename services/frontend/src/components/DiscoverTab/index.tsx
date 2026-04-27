import { useState, useEffect, useRef } from 'react'
import { useAuthStore } from '../../stores/authStore'
import { api, ApiError } from '../../lib/api'
import toast from 'react-hot-toast'
import {
  MagnifyingGlassIcon,
  BookOpenIcon,
  XMarkIcon,
  ArrowTopRightOnSquareIcon,
  DocumentTextIcon,
  PlusIcon,
  LightBulbIcon,
  LockClosedIcon,
} from '@heroicons/react/24/outline'

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface DiscoveredPaper {
  id: string
  title: string
  abstract: string | null
  authors: string[]
  year: number | null
  doi: string | null
  arxiv_id: string | null
  pubmed_id: string | null
  source: 'semantic_scholar' | 'arxiv' | 'pubmed'
  paper_url: string | null
  pdf_url: string | null
  citation_count: number | null
  journal_name: string | null
  relevance_score: number
  relevance_reason: string | null
  discovery_type: 'recommended' | 'searched'
  search_query: string | null
  bib_saved: boolean
  status: 'new' | 'added' | 'dismissed'
}

interface QuotaStatus {
  actions_used: number
  actions_limit: number
  total_held: number
  max_pool: number
}

interface DiscoverTabProps {
  projectId: string
  documentCount?: number
  analyzedDocCount: number
  onDocumentSaved?: () => void
  insightsAnalyzed?: boolean
  onTabChange?: (tab: string) => void
}

// ---------------------------------------------------------------------------
// Source badge helper
// ---------------------------------------------------------------------------

function SourceBadge({ source }: { source: DiscoveredPaper['source'] }) {
  if (source === 'semantic_scholar') {
    return (
      <span className="text-xs font-mono px-1.5 py-0.5 rounded border border-border-default bg-bg-elevated text-text-muted shrink-0">
        SS
      </span>
    )
  }
  if (source === 'arxiv') {
    return (
      <span className="text-xs font-mono px-1.5 py-0.5 rounded border border-border-default bg-bg-elevated text-text-muted shrink-0">
        arXiv
      </span>
    )
  }
  // pubmed
  return (
    <span className="text-xs font-mono px-1.5 py-0.5 rounded border border-border-default bg-bg-elevated text-text-muted shrink-0">
      PM
    </span>
  )
}

// ---------------------------------------------------------------------------
// DiscoverPaperCard (inline)
// ---------------------------------------------------------------------------

interface DiscoverPaperCardProps {
  paper: DiscoveredPaper
  savingIds: Set<string>
  dismissingIds: Set<string>
  onSave: (paperId: string) => void
  onDismiss: (paperId: string) => void
}

function DiscoverPaperCard({
  paper,
  savingIds,
  dismissingIds,
  onSave,
  onDismiss,
}: DiscoverPaperCardProps) {
  const isSaving = savingIds.has(paper.id)
  const isDismissing = dismissingIds.has(paper.id)

  // Build author/year/journal line
  const authorLine = (() => {
    if (!paper.authors || paper.authors.length === 0) return null
    const shown = paper.authors.slice(0, 2).join(', ')
    const suffix = paper.authors.length > 2 ? ' et al.' : ''
    const parts = [shown + suffix]
    if (paper.year) parts.push(String(paper.year))
    if (paper.journal_name) parts.push(paper.journal_name)
    return parts.join(' · ')
  })()

  return (
    <div className="bg-bg-surface border border-border-default rounded-xl p-4 hover:bg-bg-hover hover:border-accent-primary/20 transition-colors duration-150 group">
      {/* Top row: source badge + title + dismiss */}
      <div className="flex items-start gap-3">
        <div className="flex-1 flex items-start gap-2 min-w-0">
          <SourceBadge source={paper.source} />
          <h4 className="font-semibold text-text-primary text-sm leading-snug line-clamp-2 min-w-0">
            {paper.title}
          </h4>
        </div>
        <button
          onClick={() => onDismiss(paper.id)}
          disabled={isDismissing}
          title="Dismiss paper"
          className="shrink-0 inline-flex h-11 w-11 items-center justify-center rounded-xl text-text-muted hover:bg-bg-elevated hover:text-text-secondary transition-colors duration-150 ml-1 -mt-1 disabled:opacity-40"
        >
          <XMarkIcon className="h-4 w-4" />
        </button>
      </div>

      {/* Author / year / journal */}
      {authorLine && (
        <p className="text-sm text-text-secondary mt-2 leading-snug">{authorLine}</p>
      )}

      {/* Relevance bar (recommended only) */}
      {paper.discovery_type === 'recommended' && (
        <div className="flex items-center gap-2 mt-3">
          <span className="text-xs text-text-tertiary shrink-0">Relevance</span>
          <div className="flex-1 h-1.5 bg-bg-subtle rounded-full overflow-hidden">
            <div
              className="h-full bg-accent-primary rounded-full transition-all duration-150"
              style={{ width: `${Math.round(paper.relevance_score * 100)}%` }}
            />
          </div>
          <span className="text-xs text-text-tertiary shrink-0">
            {Math.round(paper.relevance_score * 100)}%
          </span>
          {paper.citation_count != null && paper.citation_count > 0 && (
            <span className="text-xs text-text-muted shrink-0">
              · {paper.citation_count.toLocaleString()} citations
            </span>
          )}
        </div>
      )}

      {/* Abstract preview */}
      {paper.abstract && (
        <p className="text-sm text-text-tertiary mt-2 line-clamp-2 leading-relaxed">
          {paper.abstract}
        </p>
      )}

      {/* Action row */}
      <div className="flex flex-wrap items-center gap-2 mt-3">
        {/* View Paper */}
        {paper.paper_url && (
          <a
            href={paper.paper_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center gap-1.5 text-xs text-text-secondary border border-border-default rounded-lg px-3 py-2 hover:text-text-primary hover:border-text-tertiary/30 transition-colors duration-150"
          >
            <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" />
            View Paper
          </a>
        )}

        {/* PDF */}
        {paper.pdf_url ? (
          <a
            href={paper.pdf_url}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex min-h-11 items-center gap-1.5 border border-border-default text-text-secondary hover:text-text-primary rounded-lg px-3 py-2 text-xs transition-colors duration-150"
          >
            <DocumentTextIcon className="h-3.5 w-3.5" />
            PDF
          </a>
        ) : (
          <button
            disabled
            title="No open-access PDF available"
            className="inline-flex min-h-11 items-center gap-1.5 border border-border-default text-text-muted opacity-40 cursor-not-allowed rounded-lg px-3 py-2 text-xs"
          >
            <DocumentTextIcon className="h-3.5 w-3.5" />
            PDF
          </button>
        )}

        {/* Save to Literature */}
        {paper.bib_saved ? (
          <span className="inline-flex min-h-11 items-center gap-1.5 text-xs text-text-muted border border-border-default rounded-lg px-3 py-2 cursor-default">
            Saved ✓
          </span>
        ) : (
          <button
            onClick={() => onSave(paper.id)}
            disabled={isSaving}
            className="inline-flex min-h-11 items-center gap-1.5 text-xs bg-accent-primary text-white hover:bg-accent-hover rounded-lg px-3 py-2 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSaving ? (
              <span className="h-3.5 w-3.5 border border-white/40 border-t-white rounded-full animate-spin" />
            ) : (
              <PlusIcon className="h-3.5 w-3.5" />
            )}
            {isSaving ? 'Saving…' : 'Save to Literature'}
          </button>
        )}
      </div>
    </div>
  )
}

// ---------------------------------------------------------------------------
// Main DiscoverTab component
// ---------------------------------------------------------------------------

function normalizePaperListResponse(data: unknown): {
  papers: DiscoveredPaper[]
  totalNew: number
} {
  if (Array.isArray(data)) {
    return { papers: data as DiscoveredPaper[], totalNew: data.length }
  }

  if (data && typeof data === 'object') {
    const payload = data as {
      papers?: DiscoveredPaper[]
      recommendations?: DiscoveredPaper[]
      total_new?: number
    }
    const papers = payload.papers ?? payload.recommendations ?? []
    return {
      papers,
      totalNew: payload.total_new ?? papers.length,
    }
  }

  return { papers: [], totalNew: 0 }
}

export default function DiscoverTab({
  projectId,
  documentCount = 0,
  analyzedDocCount,
  onDocumentSaved,
  insightsAnalyzed,
  onTabChange,
}: DiscoverTabProps) {
  const { session } = useAuthStore()
  const token = session?.access_token ?? ''

  const [papers, setPapers] = useState<DiscoveredPaper[]>([])
  const [quota, setQuota] = useState<QuotaStatus>({
    actions_used: 0,
    actions_limit: 5,
    total_held: 0,
    max_pool: 30,
  })
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [finding, setFinding] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [offset, setOffset] = useState(0)
  const [totalNew, setTotalNew] = useState(0)
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set())
  const [dismissingIds, setDismissingIds] = useState<Set<string>>(new Set())

  const searchInputRef = useRef<HTMLInputElement>(null)

  // ------------------------------------------------------------------
  // Data fetching
  // ------------------------------------------------------------------

  const loadQuota = async () => {
    if (!token) return

    try {
      const data = await api.discover.getQuotaStatus(token, projectId)
      setQuota(data)
    } catch {
      // Silent on background quota refresh failures
    }
  }

  const loadPapers = async (nextOffset: number, append: boolean) => {
    if (!token) return

    const data = await api.discover.list(token, projectId, nextOffset)
    const normalized = normalizePaperListResponse(data)

    setPapers(prev =>
      append ? [...prev, ...normalized.papers] : normalized.papers,
    )
    setTotalNew(normalized.totalNew)
    setOffset(nextOffset)
  }

  const loadInitial = async () => {
    if (!token || analyzedDocCount === 0) {
      setLoading(false)
      setPapers([])
      setTotalNew(0)
      setOffset(0)
      return
    }

    setLoading(true)
    try {
      await Promise.all([
        loadPapers(0, false),
        loadQuota(),
      ])
    } catch {
      // Silent on mount failure — don't interrupt the user
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    void loadInitial()
  }, [projectId, token, analyzedDocCount]) // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------
  // Find Papers (generate)
  // ------------------------------------------------------------------

  const handleFindPapers = async () => {
    if (!token || finding || quota.actions_used >= quota.actions_limit) return
    setFinding(true)
    try {
      await api.discover.findForProject(token, projectId)
      await Promise.all([loadInitial(), loadQuota()])
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 429) {
        toast.error('Daily discover limit reached. Come back tomorrow.')
      } else {
        toast.error(err.message || 'Failed to find papers.')
      }
    } finally {
      setFinding(false)
    }
  }

  const handleShowMore = async () => {
    if (!token || loadingMore || papers.length >= totalNew) return

    const nextOffset = offset + 5
    setLoadingMore(true)
    try {
      await loadPapers(nextOffset, true)
    } catch (err: any) {
      toast.error(err.message || 'Failed to load more papers.')
    } finally {
      setLoadingMore(false)
    }
  }

  // ------------------------------------------------------------------
  // Search
  // ------------------------------------------------------------------

  const handleSearch = async () => {
    const q = searchQuery.trim()
    if (!q || !token || searching || quota.actions_used >= quota.actions_limit) return
    setSearching(true)
    try {
      await api.discover.search(token, projectId, q)
      await Promise.all([loadInitial(), loadQuota()])
    } catch (err: any) {
      if (err instanceof ApiError && err.status === 429) {
        toast.error('Daily discover limit reached. Resets tomorrow.')
      } else {
        toast.error(err.message || 'Search failed.')
      }
    } finally {
      setSearching(false)
    }
  }

  // ------------------------------------------------------------------
  // Save to Literature
  // ------------------------------------------------------------------

  const handleSave = async (paperId: string) => {
    if (!token) return
    setSavingIds(prev => new Set(prev).add(paperId))
    try {
      await api.discover.saveToLiterature(token, projectId, paperId)
      setPapers(prev =>
        prev.map(p => (p.id === paperId ? { ...p, bib_saved: true } : p)),
      )
      toast.success('Paper saved to your literature library.')
      onDocumentSaved?.()
      await loadQuota()
    } catch (err: any) {
      toast.error(err.message || 'Failed to save paper.')
    } finally {
      setSavingIds(prev => {
        const next = new Set(prev)
        next.delete(paperId)
        return next
      })
    }
  }

  // ------------------------------------------------------------------
  // Dismiss
  // ------------------------------------------------------------------

  const handleDismiss = async (paperId: string) => {
    if (!token) return
    setDismissingIds(prev => new Set(prev).add(paperId))
    try {
      await api.discover.dismiss(token, paperId)
      setPapers(prev => prev.filter(p => p.id !== paperId))
      setTotalNew(prev => Math.max(prev - 1, 0))
      await loadQuota()
    } catch (err: any) {
      toast.error(err.message || 'Failed to dismiss paper.')
    } finally {
      setDismissingIds(prev => {
        const next = new Set(prev)
        next.delete(paperId)
        return next
      })
    }
  }

  // ------------------------------------------------------------------
  // Derived state
  // ------------------------------------------------------------------

  const refreshDisabled =
    quota.actions_used >= quota.actions_limit || finding
  const searchDisabled =
    quota.actions_used >= quota.actions_limit || searching || !searchQuery.trim()
  const discoverQuotaExhausted = quota.actions_used >= quota.actions_limit
  const refreshTooltip =
    discoverQuotaExhausted ? 'Daily discover limit reached' : undefined

  const poolBadgeClass =
    quota.total_held >= quota.max_pool
      ? 'bg-bg-elevated text-error border-border-default'
      : quota.total_held >= quota.max_pool * 0.8
        ? 'bg-bg-elevated text-warning border-border-default'
        : 'bg-bg-elevated text-text-muted border-border-default'

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  if (analyzedDocCount === 0) {
    return (
      <div className="flex flex-col items-center justify-center py-24 text-center">
        <LockClosedIcon className="h-10 w-10 text-text-muted mb-4" />
        <p className="text-text-primary font-semibold mb-2">Upload a paper first</p>
        <p className="text-text-muted text-sm max-w-xs leading-relaxed">
          Discover works best when it can match papers to your existing literature.
          Upload and analyze at least one PDF to unlock discovery.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header row */}
      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
        <div>
          <h3 className="text-2xl font-semibold text-text-primary tracking-tight">
            Discover
          </h3>
          <p className="text-sm text-text-secondary mt-1">
            Find open-access papers relevant to your project
          </p>
        </div>
        {/* Pool badge */}
        <span
          className={`inline-flex items-center text-xs font-semibold px-2.5 py-1 rounded-lg border ${poolBadgeClass} shrink-0`}
        >
          {quota.total_held} / {quota.max_pool} papers
        </span>
      </div>

      {/* Soft nudge when insights haven't been generated yet */}
      {documentCount > 0 && !insightsAnalyzed && (
        <div className="flex items-start gap-3 px-3.5 py-3 rounded-xl border border-border-default bg-bg-elevated text-sm">
          <LightBulbIcon className="h-4 w-4 text-text-muted shrink-0 mt-0.5" />
          <p className="text-text-secondary leading-snug flex-1">
            Results will improve after you{' '}
            <button
              onClick={() => onTabChange?.('insights')}
              className="text-accent-primary hover:text-accent-hover font-semibold transition-colors duration-150 underline underline-offset-2"
            >
              build your Literature Map
            </button>
            {' '} - Discover uses your research gaps and themes as search seeds.
          </p>
        </div>
      )}

      {/* Action row */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Find Papers button */}
        <div className="flex flex-col gap-1">
          <button
            onClick={handleFindPapers}
            disabled={refreshDisabled}
            title={refreshTooltip}
            className="inline-flex min-h-11 items-center gap-2 px-4 py-2.5 rounded-xl bg-accent-primary text-white text-sm font-semibold hover:bg-accent-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            {finding && (
              <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {finding ? 'Finding…' : 'Find Papers for My Project'}
          </button>
          {discoverQuotaExhausted && (
            <p className="text-xs text-text-muted pl-1">Daily discover limit reached</p>
          )}
        </div>

        {/* Search input */}
        <div className="flex-1 flex flex-col gap-1">
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <input
                ref={searchInputRef}
                type="text"
                value={searchQuery}
                onChange={e => setSearchQuery(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleSearch()}
                disabled={searching || discoverQuotaExhausted}
                placeholder="Search any topic…"
                className="w-full min-h-11 bg-bg-surface border border-border-default rounded-xl px-4 py-2.5 pr-10 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-primary/50 transition-colors duration-150 disabled:opacity-50"
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={searchDisabled}
              className="inline-flex min-h-11 min-w-11 items-center justify-center px-3 py-2 rounded-xl bg-bg-surface border border-border-default text-text-secondary hover:text-text-primary hover:border-text-tertiary/30 transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
            >
              {searching ? (
                <span className="h-4 w-4 border-2 border-text-muted/30 border-t-text-secondary rounded-full animate-spin" />
              ) : (
                <MagnifyingGlassIcon className="h-4 w-4" />
              )}
            </button>
          </div>
          <span className="text-xs text-text-muted pl-1">
            {quota.actions_used}/{quota.actions_limit} searches today
          </span>
        </div>
      </div>

      {/* Paper list / empty states */}
      {loading ? (
        // Loading skeleton
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div
              key={i}
              className="bg-bg-surface border border-border-default rounded-xl p-4 animate-pulse"
            >
              <div className="flex gap-2 mb-3">
                <div className="h-5 w-8 bg-bg-subtle rounded" />
                <div className="h-5 flex-1 bg-bg-subtle rounded" />
              </div>
              <div className="h-4 w-1/3 bg-bg-subtle rounded mb-2" />
              <div className="h-3 w-full bg-bg-subtle rounded mb-1" />
              <div className="h-3 w-4/5 bg-bg-subtle rounded" />
            </div>
          ))}
        </div>
      ) : papers.length === 0 ? (
        // Empty state
        <div className="flex flex-col items-center justify-center py-16 text-center">
          {documentCount === 0 ? (
            <>
              <BookOpenIcon className="h-10 w-10 text-text-muted mb-4" />
              <h4 className="text-base font-semibold text-text-secondary mb-2">
                Start discovering papers
              </h4>
              <p className="text-sm text-text-tertiary max-w-sm leading-relaxed">
                Upload a paper to get personalized recommendations, or use the
                search bar to find papers on any topic.
              </p>
            </>
          ) : (
            <>
              <MagnifyingGlassIcon className="h-10 w-10 text-text-muted mb-4" />
              <h4 className="text-base font-semibold text-text-secondary mb-2">
                Ready to explore
              </h4>
              <p className="text-sm text-text-tertiary max-w-sm leading-relaxed">
                Click &ldquo;Find Papers for My Project&rdquo; to get 5 papers
                tailored to your research, or search any topic above.
              </p>
            </>
          )}
        </div>
      ) : (
        <div className="space-y-3">
          {papers.map(paper => (
            <DiscoverPaperCard
              key={paper.id}
              paper={paper}
              savingIds={savingIds}
              dismissingIds={dismissingIds}
              onSave={handleSave}
              onDismiss={handleDismiss}
            />
          ))}
          {papers.length < totalNew && (
            <button
              onClick={handleShowMore}
              disabled={loadingMore}
              className="w-full mt-3 min-h-11 py-2 text-sm text-text-secondary border border-border-default rounded-xl hover:border-border-subtle hover:text-text-primary transition-colors duration-fast disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {loadingMore ? 'Loading…' : `Show more (${totalNew - papers.length} remaining)`}
            </button>
          )}
        </div>
      )}
    </div>
  )
}

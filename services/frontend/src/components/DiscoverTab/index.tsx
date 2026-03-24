import { useState, useEffect, useRef } from 'react'
import { useAuthStore } from '../../stores/authStore'
import toast from 'react-hot-toast'
import {
  MagnifyingGlassIcon,
  BookOpenIcon,
  XMarkIcon,
  ArrowTopRightOnSquareIcon,
  DocumentTextIcon,
  PlusIcon,
  LightBulbIcon,
} from '@heroicons/react/24/outline'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

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
  refresh_used: number
  refresh_limit: number
  search_used: number
  search_limit: number
  bib_save_used: number
  bib_save_limit: number
  total_held: number
  max_pool: number
}

interface DiscoverTabProps {
  projectId: string
  documentCount?: number
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
  quota: QuotaStatus
  savingIds: Set<string>
  dismissingIds: Set<string>
  onSave: (paperId: string) => void
  onDismiss: (paperId: string) => void
}

function DiscoverPaperCard({
  paper,
  quota,
  savingIds,
  dismissingIds,
  onSave,
  onDismiss,
}: DiscoverPaperCardProps) {
  const isSaving = savingIds.has(paper.id)
  const isDismissing = dismissingIds.has(paper.id)
  const saveAtLimit = quota.bib_save_used >= quota.bib_save_limit

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
          className="shrink-0 text-text-muted hover:text-text-secondary transition-colors duration-150 ml-1 mt-0.5 disabled:opacity-40"
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
            className="inline-flex items-center gap-1.5 text-xs text-text-secondary border border-border-default rounded-lg px-3 py-1.5 hover:text-text-primary hover:border-text-tertiary/30 transition-colors duration-150"
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
            className="inline-flex items-center gap-1.5 border border-border-default text-text-secondary hover:text-text-primary rounded-lg px-3 py-1.5 text-xs transition-colors duration-150"
          >
            <DocumentTextIcon className="h-3.5 w-3.5" />
            PDF
          </a>
        ) : (
          <button
            disabled
            title="No open-access PDF available"
            className="inline-flex items-center gap-1.5 border border-border-default text-text-muted opacity-40 cursor-not-allowed rounded-lg px-3 py-1.5 text-xs"
          >
            <DocumentTextIcon className="h-3.5 w-3.5" />
            PDF
          </button>
        )}

        {/* Save to Literature */}
        {paper.bib_saved ? (
          <span className="inline-flex items-center gap-1.5 text-xs text-text-muted border border-border-default rounded-lg px-3 py-1.5 cursor-default">
            Saved ✓
          </span>
        ) : saveAtLimit ? (
          <button
            disabled
            title="Daily save limit reached"
            className="inline-flex items-center gap-1.5 text-xs text-text-muted border border-border-default rounded-lg px-3 py-1.5 cursor-not-allowed opacity-50"
          >
            <PlusIcon className="h-3.5 w-3.5" />
            Save to Literature
          </button>
        ) : (
          <button
            onClick={() => onSave(paper.id)}
            disabled={isSaving}
            className="inline-flex items-center gap-1.5 text-xs bg-accent-primary text-white hover:bg-accent-hover rounded-lg px-3 py-1.5 transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
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

export default function DiscoverTab({ projectId, documentCount = 0, onDocumentSaved, insightsAnalyzed, onTabChange }: DiscoverTabProps) {
  const { session } = useAuthStore()
  const token = session?.access_token ?? ''

  const [papers, setPapers] = useState<DiscoveredPaper[]>([])
  const [quota, setQuota] = useState<QuotaStatus>({
    refresh_used: 0,
    refresh_limit: 1,
    search_used: 0,
    search_limit: 3,
    bib_save_used: 0,
    bib_save_limit: 3,
    total_held: 0,
    max_pool: 20,
  })
  const [loading, setLoading] = useState(false)
  const [finding, setFinding] = useState(false)
  const [searching, setSearching] = useState(false)
  const [searchQuery, setSearchQuery] = useState('')
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set())
  const [dismissingIds, setDismissingIds] = useState<Set<string>>(new Set())

  const searchInputRef = useRef<HTMLInputElement>(null)

  // ------------------------------------------------------------------
  // Data fetching
  // ------------------------------------------------------------------

  const fetchPapersAndQuota = async () => {
    if (!token) return
    setLoading(true)
    try {
      const [papersRes, quotaRes] = await Promise.all([
        fetch(`${API_BASE}/paper-recommendations/projects/${projectId}`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
        fetch(`${API_BASE}/paper-recommendations/projects/${projectId}/quota-status`, {
          headers: { Authorization: `Bearer ${token}` },
        }),
      ])

      if (papersRes.ok) {
        const data = await papersRes.json()
        // API may return array directly or { recommendations: [...] }
        setPapers(Array.isArray(data) ? data : (data.recommendations ?? []))
      }

      if (quotaRes.ok) {
        const data = await quotaRes.json()
        setQuota(data)
      }
    } catch (err) {
      // Silent on mount failure — don't interrupt the user
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchPapersAndQuota()
  }, [projectId, token]) // eslint-disable-line react-hooks/exhaustive-deps

  // ------------------------------------------------------------------
  // Find Papers (generate)
  // ------------------------------------------------------------------

  const handleFindPapers = async () => {
    if (!token || finding) return
    setFinding(true)
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 60000) // 60s timeout
    try {
      const res = await fetch(
        `${API_BASE}/paper-recommendations/projects/${projectId}/generate`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` }, signal: controller.signal },
      )
      clearTimeout(timeoutId)
      if (res.status === 429) {
        toast.error('Already used your daily refresh. Come back tomorrow.')
        return
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Request failed (${res.status})`)
      }
      const data = await res.json()
      const newPapers: DiscoveredPaper[] = Array.isArray(data)
        ? data
        : (data.recommendations ?? [])
      setPapers(prev => {
        // Merge: keep existing, append new by id
        const existingIds = new Set(prev.map(p => p.id))
        const appended = newPapers.filter(p => !existingIds.has(p.id))
        return [...prev, ...appended]
      })
      // Refresh quota
      const qRes = await fetch(
        `${API_BASE}/paper-recommendations/projects/${projectId}/quota-status`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (qRes.ok) setQuota(await qRes.json())
    } catch (err: any) {
      clearTimeout(timeoutId)
      if (err.name === 'AbortError') {
        toast.error('Request timed out. Try again in a moment.')
      } else {
        toast.error(err.message || 'Failed to find papers.')
      }
    } finally {
      setFinding(false)
    }
  }

  // ------------------------------------------------------------------
  // Search
  // ------------------------------------------------------------------

  const handleSearch = async () => {
    const q = searchQuery.trim()
    if (!q || !token || searching) return
    setSearching(true)
    try {
      const res = await fetch(
        `${API_BASE}/paper-recommendations/projects/${projectId}/search`,
        {
          method: 'POST',
          headers: {
            Authorization: `Bearer ${token}`,
            'Content-Type': 'application/json',
          },
          body: JSON.stringify({ query: q }),
        },
      )
      if (res.status === 429) {
        toast.error('Search limit reached (3/day). Resets tomorrow.')
        return
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Request failed (${res.status})`)
      }
      const data = await res.json()
      const newPapers: DiscoveredPaper[] = Array.isArray(data)
        ? data
        : (data.recommendations ?? [])
      setPapers(prev => {
        const existingIds = new Set(prev.map(p => p.id))
        const appended = newPapers.filter(p => !existingIds.has(p.id))
        return [...prev, ...appended]
      })
      // Refresh quota
      const qRes = await fetch(
        `${API_BASE}/paper-recommendations/projects/${projectId}/quota-status`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (qRes.ok) setQuota(await qRes.json())
    } catch (err: any) {
      toast.error(err.message || 'Search failed.')
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
      const res = await fetch(
        `${API_BASE}/paper-recommendations/projects/${projectId}/save-discovered/${paperId}`,
        { method: 'POST', headers: { Authorization: `Bearer ${token}` } },
      )
      if (res.status === 429) {
        toast.error('Save limit reached (3/day). Resets tomorrow.')
        return
      }
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Request failed (${res.status})`)
      }
      setPapers(prev =>
        prev.map(p => (p.id === paperId ? { ...p, bib_saved: true } : p)),
      )
      toast.success('Paper saved to your literature library.')
      onDocumentSaved?.()
      // Refresh quota
      const qRes = await fetch(
        `${API_BASE}/paper-recommendations/projects/${projectId}/quota-status`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (qRes.ok) setQuota(await qRes.json())
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
      const res = await fetch(`${API_BASE}/paper-recommendations/${paperId}`, {
        method: 'DELETE',
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) {
        const err = await res.json().catch(() => ({}))
        throw new Error(err.detail || `Request failed (${res.status})`)
      }
      setPapers(prev => prev.filter(p => p.id !== paperId))
      // Refresh quota (pool size decreases)
      const qRes = await fetch(
        `${API_BASE}/paper-recommendations/projects/${projectId}/quota-status`,
        { headers: { Authorization: `Bearer ${token}` } },
      )
      if (qRes.ok) setQuota(await qRes.json())
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
    documentCount === 0 || quota.refresh_used >= quota.refresh_limit || finding
  const refreshQuotaExhausted = quota.refresh_used >= quota.refresh_limit
  const refreshTooltip =
    documentCount === 0
      ? 'Upload a paper first to get personalized recommendations'
      : refreshQuotaExhausted
        ? 'Refresh used today'
        : undefined

  const poolBadgeClass =
    quota.total_held >= quota.max_pool
      ? 'bg-bg-elevated text-error border-border-default'
      : quota.total_held >= quota.max_pool * 0.8
        ? 'bg-bg-elevated text-warning border-border-default'
        : 'bg-bg-elevated text-text-muted border-border-default'

  // ------------------------------------------------------------------
  // Render
  // ------------------------------------------------------------------

  if (documentCount > 0 && !insightsAnalyzed) {
    return (
      <div className="flex flex-col items-center justify-center py-16 px-6 text-center">
        <div className="w-12 h-12 rounded-full bg-bg-surface border border-border-default flex items-center justify-center mb-4">
          <LightBulbIcon className="h-6 w-6 text-text-muted" />
        </div>
        <h3 className="text-text-primary font-semibold text-lg mb-2">Generate Insights First</h3>
        <p className="text-text-secondary text-sm max-w-sm mb-6">
          Discover uses your project's research gaps and themes as search seeds.
          Analyze your literature first to get targeted paper recommendations.
        </p>
        <button
          onClick={() => onTabChange?.('insights')}
          className="px-4 py-2 bg-accent-primary hover:bg-accent-hover text-white text-sm font-semibold rounded-xl transition-colors duration-150"
        >
          Go to Insights →
        </button>
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

      {/* Action row */}
      <div className="flex flex-col sm:flex-row gap-3">
        {/* Find Papers button */}
        <div className="flex flex-col gap-1">
          <button
            onClick={handleFindPapers}
            disabled={refreshDisabled}
            title={refreshTooltip}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-xl bg-accent-primary text-white text-sm font-semibold hover:bg-accent-hover transition-colors duration-150 disabled:opacity-50 disabled:cursor-not-allowed shrink-0"
          >
            {finding && (
              <span className="h-4 w-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
            )}
            {finding ? 'Finding…' : 'Find Papers for My Project'}
          </button>
          {refreshQuotaExhausted && (
            <p className="text-xs text-text-muted pl-1">Refresh used today</p>
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
                disabled={searching}
                placeholder="Search any topic…"
                className="w-full bg-bg-surface border border-border-default rounded-xl px-4 py-2 pr-10 text-sm text-text-primary placeholder-text-muted focus:outline-none focus:border-accent-primary/50 transition-colors duration-150 disabled:opacity-50"
              />
            </div>
            <button
              onClick={handleSearch}
              disabled={searching || !searchQuery.trim()}
              className="inline-flex items-center justify-center px-3 py-2 rounded-xl bg-bg-surface border border-border-default text-text-secondary hover:text-text-primary hover:border-text-tertiary/30 transition-colors duration-150 disabled:opacity-40 disabled:cursor-not-allowed shrink-0"
            >
              {searching ? (
                <span className="h-4 w-4 border-2 border-text-muted/30 border-t-text-secondary rounded-full animate-spin" />
              ) : (
                <MagnifyingGlassIcon className="h-4 w-4" />
              )}
            </button>
          </div>
          {quota.search_used >= 1 && (
            <p className="text-xs text-text-muted pl-1">
              {quota.search_used} of {quota.search_limit} searches used today
            </p>
          )}
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
              quota={quota}
              savingIds={savingIds}
              dismissingIds={dismissingIds}
              onSave={handleSave}
              onDismiss={handleDismiss}
            />
          ))}
        </div>
      )}
    </div>
  )
}

import { useState, useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'
import { Badge } from './ui/Badge'
import {
  AcademicCapIcon,
  ArrowDownTrayIcon,
  ArrowTopRightOnSquareIcon,
  PlusCircleIcon,
  XMarkIcon,
  TrashIcon
} from '@heroicons/react/24/outline'

const MAX_PAPER_RECOMMENDATIONS = 30

interface PaperRecommendation {
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
  publication_type: string | null
  fields_of_study: string[]
  relevance_score: number
  relevance_reason: string
  matched_keywords: string[]
  addresses_gaps: string[]
  status: 'new' | 'added' | 'dismissed'
}

interface PaperRecommendationsProps {
  projectId: string
  insightsStatus?: string
}

const SOURCE_COLORS = {
  semantic_scholar: 'bg-[#1e40af] text-white border-[#1e40af]',
  arxiv: 'bg-[#6b21a8] text-white border-[#6b21a8]',
  pubmed: 'bg-[#166534] text-white border-[#166534]',
}

const SOURCE_NAMES = {
  semantic_scholar: 'Semantic Scholar',
  arxiv: 'arXiv',
  pubmed: 'PubMed',
}

export default function PaperRecommendations({ projectId, insightsStatus: _insightsStatus }: PaperRecommendationsProps) {
  const { session } = useAuthStore()
  const [recommendations, setRecommendations] = useState<PaperRecommendation[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [activeTab, setActiveTab] = useState<'new' | 'accepted' | 'dismissed'>('new')
  const [selectedDismissed, setSelectedDismissed] = useState<Set<string>>(new Set())
  const [expandedPapers, setExpandedPapers] = useState<Set<string>>(new Set())
  const [currentPage, setCurrentPage] = useState(1)

  const PAPERS_PER_PAGE = 10

  useEffect(() => {
    fetchRecommendations()
  }, [projectId])

  const fetchRecommendations = async () => {
    if (!session?.access_token) return

    setLoading(true)
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/paper-recommendations/projects/${projectId}`,
        {
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!response.ok) throw new Error('Failed to fetch recommendations')

      const data = await response.json()
      setRecommendations(data.recommendations || [])
    } catch (error: any) {
      console.error('Failed to fetch recommendations:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    if (!session?.access_token) return

    // Check capacity before generating
    const isAtCapacity = recommendations.length >= MAX_PAPER_RECOMMENDATIONS
    const isNearCapacity = recommendations.length >= MAX_PAPER_RECOMMENDATIONS - 5

    if (isAtCapacity) {
      toast.error(`Maximum capacity reached (${MAX_PAPER_RECOMMENDATIONS}). Please delete some papers to generate more.`)
      return
    }

    if (isNearCapacity) {
      const confirmed = confirm(
        `You have ${recommendations.length}/${MAX_PAPER_RECOMMENDATIONS} papers. ` +
        `After generating 5 more, you'll be at capacity. Continue?`
      )
      if (!confirmed) return
    }

    setGenerating(true)
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/paper-recommendations/projects/${projectId}/generate`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || 'Failed to generate recommendations')
      }

      const data = await response.json()
      const newRecommendations = data.recommendations || []

      // Add new papers to existing ones (no replacement)
      setRecommendations(prev => [...prev, ...newRecommendations])
      toast.success(`Found ${newRecommendations.length} relevant papers!`)
    } catch (error: any) {
      console.error('Failed to generate recommendations:', error)
      toast.error(error.message || 'Failed to generate recommendations')
    } finally {
      setGenerating(false)
    }
  }

  const handlePermanentDelete = async () => {
    if (!session?.access_token) return
    if (selectedDismissed.size === 0) {
      toast.error('Please select papers to delete')
      return
    }

    const confirmed = confirm(`Permanently delete ${selectedDismissed.size} paper(s)? This will free up space in your quota.`)
    if (!confirmed) return

    try {
      const recommendationIds = Array.from(selectedDismissed)

      // Delete each recommendation
      await Promise.all(
        recommendationIds.map(id =>
          fetch(
            `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/paper-recommendations/${id}`,
            {
              method: 'DELETE',
              headers: {
                'Authorization': `Bearer ${session.access_token}`,
              },
            }
          )
        )
      )

      // Update local state
      setRecommendations(prev => prev.filter(r => !selectedDismissed.has(r.id)))
      setSelectedDismissed(new Set())
      toast.success(`Permanently deleted ${recommendationIds.length} paper(s)`)
    } catch (error: any) {
      console.error('Failed to delete papers:', error)
      toast.error('Failed to delete papers')
    }
  }

  const handleRestore = async () => {
    if (!session?.access_token) return
    if (selectedDismissed.size === 0) {
      toast.error('Please select papers to restore')
      return
    }

    try {
      const recommendationIds = Array.from(selectedDismissed)

      // Restore each recommendation to 'new' status
      await Promise.all(
        recommendationIds.map(id =>
          fetch(
            `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/paper-recommendations/${id}/status?status=new`,
            {
              method: 'PATCH',
              headers: {
                'Authorization': `Bearer ${session.access_token}`,
              },
            }
          )
        )
      )

      // Update local state
      setRecommendations(prev => prev.map(r =>
        selectedDismissed.has(r.id) ? { ...r, status: 'new' } : r
      ))
      setSelectedDismissed(new Set())
      toast.success(`Restored ${recommendationIds.length} paper(s) to New`)
    } catch (error: any) {
      console.error('Failed to restore papers:', error)
      toast.error('Failed to restore papers')
    }
  }

  const handleDismiss = async (recommendationId: string) => {
    if (!session?.access_token) return

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/paper-recommendations/${recommendationId}/status?status=dismissed`,
        {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!response.ok) throw new Error('Failed to dismiss')

      setRecommendations(prev => prev.map(r =>
        r.id === recommendationId ? { ...r, status: 'dismissed' } : r
      ))
      toast.success('Paper dismissed')
    } catch (error: any) {
      console.error('Failed to dismiss:', error)
      toast.error('Failed to dismiss paper')
    }
  }

  const handleKeepPaper = async (paper: PaperRecommendation) => {
    if (!session?.access_token) return

    try {
      // Update status to 'added'
      const statusResponse = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/paper-recommendations/${paper.id}/status?status=added`,
        {
          method: 'PATCH',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!statusResponse.ok) throw new Error('Failed to update status')

      setRecommendations(prev => prev.map(r =>
        r.id === paper.id ? { ...r, status: 'added' } : r
      ))

      toast.success('Paper saved to Accepted!')
    } catch (error: any) {
      console.error('Failed to keep paper:', error)
      toast.error('Failed to keep paper')
    }
  }

  const toggleExpanded = (paperId: string) => {
    setExpandedPapers(prev => {
      const newSet = new Set(prev)
      if (newSet.has(paperId)) {
        newSet.delete(paperId)
      } else {
        newSet.add(paperId)
      }
      return newSet
    })
  }

  const tabRecommendations = activeTab === 'new'
    ? recommendations.filter(r => r.status === 'new')
    : activeTab === 'accepted'
    ? recommendations.filter(r => r.status === 'added')
    : recommendations.filter(r => r.status === 'dismissed')

  // Count total papers (all statuses)
  const totalPapers = recommendations.length
  const isAtCapacity = totalPapers >= MAX_PAPER_RECOMMENDATIONS
  const isNearCapacity = totalPapers >= MAX_PAPER_RECOMMENDATIONS - 5

  // Pagination calculations
  const totalPages = Math.ceil(tabRecommendations.length / PAPERS_PER_PAGE)
  const startIndex = (currentPage - 1) * PAPERS_PER_PAGE
  const endIndex = startIndex + PAPERS_PER_PAGE
  const paginatedRecommendations = tabRecommendations.slice(startIndex, endIndex)

  // Reset to page 1 when tab changes
  useEffect(() => {
    setCurrentPage(1)
  }, [activeTab])

  // Adjust page if current page exceeds total pages
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(totalPages)
    }
  }, [totalPages, currentPage])

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-cyan-900/30 rounded-lg">
            <AcademicCapIcon className="h-6 w-6 text-cyan-300" />
          </div>
          <div>
            <h3 className="text-lg font-serif font-semibold text-text-primary">Discover Relevant Papers</h3>
            <div className="flex items-center gap-2">
              <Badge variant={isAtCapacity ? 'error' : isNearCapacity ? 'warning' : 'neutral'}>
                {totalPapers} / {MAX_PAPER_RECOMMENDATIONS}
              </Badge>
              {isAtCapacity && (
                <p className="text-sm text-text-tertiary">
                  ⚠️ At capacity - permanently delete dismissed papers to generate more
                </p>
              )}
            </div>
          </div>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating || isAtCapacity}
          className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {generating ? (
            <>
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
              Discovering Papers...
            </>
          ) : (
            <>
              Discover Papers
            </>
          )}
        </button>
      </div>

      {/* Tab Navigation */}
      {recommendations.length > 0 && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('new')}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
              activeTab === 'new'
                ? 'bg-cyan-800 text-cyan-100 border border-cyan-700'
                : 'bg-surface-hover text-text-secondary hover:bg-surface border border-border-base'
            }`}
          >
            New ({recommendations.filter(r => r.status === 'new').length})
          </button>
          <button
            onClick={() => setActiveTab('accepted')}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
              activeTab === 'accepted'
                ? 'bg-cyan-800 text-cyan-100 border border-cyan-700'
                : 'bg-surface-hover text-text-secondary hover:bg-surface border border-border-base'
            }`}
          >
            Accepted ({recommendations.filter(r => r.status === 'added').length})
          </button>
          <button
            onClick={() => setActiveTab('dismissed')}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
              activeTab === 'dismissed'
                ? 'bg-cyan-800 text-cyan-100 border border-cyan-700'
                : 'bg-surface-hover text-text-secondary hover:bg-surface border border-border-base'
            }`}
          >
            Dismissed ({recommendations.filter(r => r.status === 'dismissed').length})
          </button>
        </div>
      )}

      {/* Dismissed Tab Actions */}
      {activeTab === 'dismissed' && selectedDismissed.size > 0 && (
        <div className="flex gap-2">
          <button
            onClick={handleRestore}
            className="px-4 py-2 bg-cyan-800 text-cyan-100 font-semibold rounded-lg hover:bg-cyan-700 transition-colors flex items-center gap-2 border border-cyan-700"
          >
            Restore ({selectedDismissed.size})
          </button>
          <button
            onClick={handlePermanentDelete}
            className="px-4 py-2 bg-red-600 text-white font-semibold rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2"
          >
            <TrashIcon className="h-5 w-5" />
            Delete Permanently ({selectedDismissed.size})
          </button>
        </div>
      )}

      {/* Papers List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
        </div>
      ) : tabRecommendations.length === 0 ? (
        <div className="bg-surface/30 rounded-lg border border-border-subtle p-8 text-center">
          <AcademicCapIcon className="h-12 w-12 text-text-muted mx-auto mb-4" />
          <p className="text-text-tertiary">
            {recommendations.length === 0
              ? 'No paper recommendations yet. Click "Discover Papers" to find relevant research.'
              : activeTab === 'new'
              ? 'No new papers. Generate more or check other tabs.'
              : activeTab === 'accepted'
              ? 'No accepted papers yet. Keep papers from the New tab to see them here.'
              : 'No dismissed papers.'}
          </p>
        </div>
      ) : (
        <>
        <div className="space-y-3">
          {paginatedRecommendations.map((paper) => {
            const isExpanded = expandedPapers.has(paper.id)
            const scorePercentage = Math.round(paper.relevance_score * 100)

            return (
              <div key={paper.id} className="bg-surface/50 rounded-lg border border-border-base hover:border-border-subtle transition-colors">
                {/* Paper Header */}
                <div className="p-4">
                  <div className="flex items-start gap-3">
                    {/* Checkbox only for dismissed tab */}
                    {activeTab === 'dismissed' && (
                      <input
                        type="checkbox"
                        checked={selectedDismissed.has(paper.id)}
                        onChange={(e) => {
                          const newSelected = new Set(selectedDismissed)
                          if (e.target.checked) {
                            newSelected.add(paper.id)
                          } else {
                            newSelected.delete(paper.id)
                          }
                          setSelectedDismissed(newSelected)
                        }}
                        className="mt-1 h-4 w-4 text-accent-primary border-border-base rounded focus:ring-2 focus:ring-accent-primary shrink-0"
                      />
                    )}

                    <div className="flex items-start justify-between gap-4 flex-1">
                      <div className="flex-1 min-w-0">
                      {/* Title and metadata */}
                      <div className="flex items-center gap-2 mb-2 flex-wrap">
                        <span className={`text-xs px-2 py-1 rounded border font-mono ${SOURCE_COLORS[paper.source]}`}>
                          {SOURCE_NAMES[paper.source]}
                        </span>
                        {paper.year && (
                          <span className="text-xs text-text-tertiary font-mono">{paper.year}</span>
                        )}
                        {paper.citation_count && paper.citation_count > 0 && (
                          <span className="text-xs text-amber-600 font-mono">{paper.citation_count} citations</span>
                        )}
                        <div className="flex items-center gap-1">
                          <div className="h-2 w-24 bg-slate-800 rounded-full overflow-hidden">
                            <div
                              className="h-full bg-cyan-700"
                              style={{ width: `${scorePercentage}%` }}
                            />
                          </div>
                          <span className="text-xs text-cyan-600 font-mono">{scorePercentage}% match</span>
                        </div>
                      </div>

                      <h4
                        className="text-text-primary font-medium leading-relaxed mb-2 cursor-pointer hover:text-cyan-200 transition-colors"
                        onClick={() => toggleExpanded(paper.id)}
                      >
                        {paper.title}
                      </h4>

                      {/* Authors */}
                      {paper.authors && paper.authors.length > 0 && (
                        <p className="text-sm text-text-tertiary mb-2">
                          {paper.authors.slice(0, 3).join(', ')}
                          {paper.authors.length > 3 && ` +${paper.authors.length - 3} more`}
                        </p>
                      )}

                      {/* Relevance reason */}
                      <p className="text-xs text-text-muted">{paper.relevance_reason}</p>
                    </div>

                      {/* Actions */}
                      <div className="flex items-center gap-2 shrink-0">
                        {activeTab === 'new' && (
                          <>
                            <button
                              onClick={() => handleKeepPaper(paper)}
                              className="px-3 py-1.5 bg-green-800 text-green-100 text-sm font-semibold rounded hover:bg-green-700 transition-colors flex items-center gap-1 border border-green-700"
                            >
                              <PlusCircleIcon className="h-4 w-4" />
                              Keep Paper
                            </button>
                            <button
                              onClick={() => handleDismiss(paper.id)}
                              className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded transition-colors"
                              title="Dismiss paper"
                            >
                              <XMarkIcon className="h-5 w-5" />
                            </button>
                          </>
                        )}
                        {activeTab === 'accepted' && (
                          <>
                            <span className="px-3 py-1.5 bg-green-900/40 text-green-200 text-sm font-semibold rounded border border-green-800">
                              Kept
                            </span>
                            <button
                              onClick={() => handleDismiss(paper.id)}
                              className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded transition-colors"
                              title="Dismiss paper"
                            >
                              <XMarkIcon className="h-5 w-5" />
                            </button>
                          </>
                        )}
                        {activeTab === 'dismissed' && (
                          <span className="px-3 py-1.5 bg-surface-hover text-text-muted text-sm rounded">
                            Dismissed
                          </span>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* Expanded Details */}
                  {isExpanded && (
                    <div className="mt-4 pt-4 border-t border-border-subtle space-y-3">
                      {/* Abstract */}
                      {paper.abstract && (
                        <div>
                          <h5 className="text-sm font-semibold text-text-secondary mb-1">Abstract:</h5>
                          <p className="text-sm text-text-tertiary leading-relaxed">{paper.abstract}</p>
                        </div>
                      )}

                      {/* Additional metadata */}
                      <div className="grid grid-cols-2 gap-4 text-sm">
                        {paper.journal_name && (
                          <div>
                            <span className="text-text-muted font-mono">Journal:</span>{' '}
                            <span className="text-text-secondary">{paper.journal_name}</span>
                          </div>
                        )}
                        {paper.publication_type && (
                          <div>
                            <span className="text-text-muted font-mono">Type:</span>{' '}
                            <span className="text-text-secondary">{paper.publication_type}</span>
                          </div>
                        )}
                      </div>

                      {/* Links */}
                      <div className="flex gap-2">
                        {paper.paper_url && (
                          <a
                            href={paper.paper_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-3 py-1.5 bg-surface-hover text-text-secondary text-sm rounded hover:bg-surface transition-colors flex items-center gap-1"
                          >
                            <ArrowTopRightOnSquareIcon className="h-4 w-4" />
                            View Paper
                          </a>
                        )}
                        {paper.pdf_url && (
                          <a
                            href={paper.pdf_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="px-3 py-1.5 bg-red-600/20 text-red-400 text-sm rounded hover:bg-red-600/30 transition-colors flex items-center gap-1 border border-red-600/30"
                          >
                            <ArrowDownTrayIcon className="h-4 w-4" />
                            Download PDF
                          </a>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )
          })}
        </div>

        {/* Pagination Controls */}
        {tabRecommendations.length > PAPERS_PER_PAGE && (
          <div className="flex items-center justify-between pt-4 border-t border-border-subtle">
            <div className="text-sm text-text-tertiary">
              Showing {startIndex + 1}-{Math.min(endIndex, tabRecommendations.length)} of {tabRecommendations.length} papers
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
                disabled={currentPage === 1}
                className="px-3 py-1.5 text-sm bg-surface-hover text-text-secondary rounded hover:bg-surface transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Previous
              </button>
              <div className="flex items-center gap-1">
                {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                  <button
                    key={page}
                    onClick={() => setCurrentPage(page)}
                    className={`px-3 py-1.5 text-sm rounded transition-colors ${
                      currentPage === page
                        ? 'bg-accent-primary text-white font-semibold'
                        : 'bg-surface-hover text-text-secondary hover:bg-surface'
                    }`}
                  >
                    {page}
                  </button>
                ))}
              </div>
              <button
                onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
                disabled={currentPage === totalPages}
                className="px-3 py-1.5 text-sm bg-surface-hover text-text-secondary rounded hover:bg-surface transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Next
              </button>
            </div>
          </div>
        )}
        </>
      )}
    </div>
  )
}

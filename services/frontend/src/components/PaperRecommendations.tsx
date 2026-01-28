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
  FunnelIcon,
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
}

const SOURCE_COLORS = {
  semantic_scholar: 'bg-blue-600/20 text-blue-400 border-blue-600/30',
  arxiv: 'bg-purple-600/20 text-purple-400 border-purple-600/30',
  pubmed: 'bg-green-600/20 text-green-400 border-green-600/30',
}

const SOURCE_NAMES = {
  semantic_scholar: 'Semantic Scholar',
  arxiv: 'arXiv',
  pubmed: 'PubMed',
}

export default function PaperRecommendations({ projectId }: PaperRecommendationsProps) {
  const { session } = useAuthStore()
  const [recommendations, setRecommendations] = useState<PaperRecommendation[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [selectedRecommendations, setSelectedRecommendations] = useState<Set<string>>(new Set())
  const [filterStatus, setFilterStatus] = useState<'all' | 'new' | 'added' | 'dismissed'>('all')
  const [expandedPapers, setExpandedPapers] = useState<Set<string>>(new Set())

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

  const handleBulkDelete = async () => {
    if (!session?.access_token) return
    if (selectedRecommendations.size === 0) {
      toast.error('Please select papers to delete')
      return
    }

    const confirmed = confirm(`Delete ${selectedRecommendations.size} selected paper(s)?`)
    if (!confirmed) return

    try {
      const recommendationIds = Array.from(selectedRecommendations)

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
      setRecommendations(prev => prev.filter(r => !selectedRecommendations.has(r.id)))
      setSelectedRecommendations(new Set())
      toast.success(`Deleted ${recommendationIds.length} paper(s)`)
    } catch (error: any) {
      console.error('Failed to delete papers:', error)
      toast.error('Failed to delete papers')
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

  const handleAddToProject = async (paper: PaperRecommendation) => {
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

      toast.success('Paper marked as added! You can now manually upload the PDF.')
    } catch (error: any) {
      console.error('Failed to add paper:', error)
      toast.error('Failed to add paper to project')
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

  const filteredRecommendations = filterStatus === 'all'
    ? recommendations
    : recommendations.filter(r => r.status === filterStatus)

  const isAtCapacity = recommendations.length >= MAX_PAPER_RECOMMENDATIONS
  const isNearCapacity = recommendations.length >= MAX_PAPER_RECOMMENDATIONS - 5

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-cyan-600/20 rounded-lg">
            <AcademicCapIcon className="h-6 w-6 text-cyan-400" />
          </div>
          <div>
            <h3 className="text-lg font-serif font-semibold text-text-primary">Discover Relevant Papers</h3>
            <div className="flex items-center gap-2">
              <Badge variant={isAtCapacity ? 'error' : isNearCapacity ? 'warning' : 'neutral'}>
                {recommendations.length} / {MAX_PAPER_RECOMMENDATIONS}
              </Badge>
              {isAtCapacity && (
                <p className="text-sm text-text-tertiary">
                  ⚠️ At capacity - delete some to generate more
                </p>
              )}
            </div>
          </div>
        </div>
        <div className="flex gap-2">
          {selectedRecommendations.size > 0 && (
            <button
              onClick={handleBulkDelete}
              className="px-4 py-2 bg-red-600 text-white font-semibold rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2"
            >
              <TrashIcon className="h-5 w-5" />
              Delete Selected ({selectedRecommendations.size})
            </button>
          )}
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
      </div>

      {/* Filter */}
      {recommendations.length > 0 && (
        <div className="flex items-center gap-2 px-4 py-2 bg-surface/50 rounded-lg border border-border-base">
          <FunnelIcon className="h-4 w-4 text-text-tertiary" />
          <span className="text-sm text-text-tertiary font-mono">Filter:</span>
          <div className="flex gap-2">
            {['all', 'new', 'added', 'dismissed'].map((status) => (
              <button
                key={status}
                onClick={() => setFilterStatus(status as any)}
                className={`px-3 py-1 text-xs rounded transition-colors ${
                  filterStatus === status
                    ? 'bg-cyan-600 text-white font-semibold'
                    : 'bg-surface-hover text-text-secondary hover:bg-surface'
                }`}
              >
                {status.charAt(0).toUpperCase() + status.slice(1)}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Papers List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
        </div>
      ) : filteredRecommendations.length === 0 ? (
        <div className="bg-surface/30 rounded-lg border border-border-subtle p-8 text-center">
          <AcademicCapIcon className="h-12 w-12 text-text-muted mx-auto mb-4" />
          <p className="text-text-tertiary">
            {recommendations.length === 0
              ? 'No paper recommendations yet. Click "Discover Papers" to find relevant research.'
              : 'No papers match the selected filter.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {filteredRecommendations.map((paper) => {
            const isExpanded = expandedPapers.has(paper.id)
            const scorePercentage = Math.round(paper.relevance_score * 100)

            return (
              <div key={paper.id} className="bg-surface/50 rounded-lg border border-border-base hover:border-border-subtle transition-colors">
                {/* Paper Header */}
                <div className="p-4">
                  <div className="flex items-start gap-3">
                    {/* Checkbox for bulk selection */}
                    <input
                      type="checkbox"
                      checked={selectedRecommendations.has(paper.id)}
                      onChange={(e) => {
                        const newSelected = new Set(selectedRecommendations)
                        if (e.target.checked) {
                          newSelected.add(paper.id)
                        } else {
                          newSelected.delete(paper.id)
                        }
                        setSelectedRecommendations(newSelected)
                      }}
                      className="mt-1 h-4 w-4 text-accent-primary border-border-base rounded focus:ring-2 focus:ring-accent-primary shrink-0"
                    />

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
                          <span className="text-xs text-amber-400 font-mono">{paper.citation_count} citations</span>
                        )}
                        <div className="flex items-center gap-1">
                          <div className="h-2 w-24 bg-surface-hover rounded-full overflow-hidden">
                            <div
                              className="h-full bg-cyan-500"
                              style={{ width: `${scorePercentage}%` }}
                            />
                          </div>
                          <span className="text-xs text-cyan-400 font-mono">{scorePercentage}% match</span>
                        </div>
                      </div>

                      <h4
                        className="text-text-primary font-medium leading-relaxed mb-2 cursor-pointer hover:text-cyan-400 transition-colors"
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

                      {/* Matched keywords */}
                      {paper.matched_keywords && paper.matched_keywords.length > 0 && (
                        <div className="flex gap-1 mt-2 flex-wrap">
                          {paper.matched_keywords.map((keyword, i) => (
                            <span key={i} className="text-xs px-2 py-0.5 bg-cyan-900/30 text-cyan-300 rounded font-mono">
                              {keyword}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>

                      {/* Actions */}
                      <div className="flex items-center gap-2 shrink-0">
                        {paper.status === 'new' && (
                          <>
                            <button
                              onClick={() => handleAddToProject(paper)}
                              className="px-3 py-1.5 bg-cyan-600 text-white text-sm font-semibold rounded hover:bg-cyan-700 transition-colors flex items-center gap-1"
                            >
                              <PlusCircleIcon className="h-4 w-4" />
                              Add
                            </button>
                            <button
                              onClick={() => handleDismiss(paper.id)}
                              className="px-3 py-1.5 bg-surface-hover text-text-secondary text-sm rounded hover:bg-surface transition-colors"
                            >
                              <XMarkIcon className="h-4 w-4" />
                            </button>
                          </>
                        )}
                        {paper.status === 'added' && (
                          <span className="px-3 py-1.5 bg-emerald-600/20 text-emerald-400 text-sm font-semibold rounded border border-emerald-600/30">
                            Added
                          </span>
                        )}
                        {paper.status === 'dismissed' && (
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
      )}
    </div>
  )
}

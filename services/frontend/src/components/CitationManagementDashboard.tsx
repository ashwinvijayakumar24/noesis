import { useState, useEffect } from 'react'
import {
  BookOpenIcon,
  MagnifyingGlassIcon,
  ClipboardDocumentCheckIcon,
  ArrowPathIcon
} from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { handleError } from '../lib/errorHandler'
import { Badge } from './ui/Badge'

interface Citation {
  id: string
  title: string
  authors: string[]
  year: number | null
  journal_name: string | null
  doi: string | null
  url: string | null
  formatted_citations: {
    apa?: string
    ieee?: string
    mla?: string
    chicago?: string
  }
  citation_key: string | null
  is_from_project: boolean
  times_used: number
  created_at: string
}

interface CitationManagementDashboardProps {
  token: string
  projectId: string
}

const CITATION_STYLES = ['apa', 'ieee', 'mla', 'chicago']

export default function CitationManagementDashboard({ token, projectId }: CitationManagementDashboardProps) {
  const [citations, setCitations] = useState<Citation[]>([])
  const [loading, setLoading] = useState(true)
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedStyle, setSelectedStyle] = useState<string>('apa')
  const [filterSource, setFilterSource] = useState<'all' | 'project' | 'external'>('all')
  const [sortBy, setSortBy] = useState<'recent' | 'title' | 'year' | 'usage'>('recent')

  useEffect(() => {
    loadCitations()
  }, [projectId])

  const loadCitations = async () => {
    try {
      setLoading(true)
      const data = await api.citations.getProjectCitations(token, projectId)
      setCitations(data.citations || [])
    } catch (error: any) {
      console.error('Failed to load citations:', error)
      handleError(error, 'loading citations')
    } finally {
      setLoading(false)
    }
  }

  const copyFormattedCitation = (citation: Citation) => {
    const formatted = citation.formatted_citations[selectedStyle as keyof typeof citation.formatted_citations]
    if (formatted) {
      navigator.clipboard.writeText(formatted)
      toast.success(`${selectedStyle.toUpperCase()} citation copied!`)
    } else {
      toast.error('Citation format not available')
    }
  }

  const copyCitationKey = (key: string) => {
    navigator.clipboard.writeText(key)
    toast.success('Citation key copied!')
  }

  // Filter and sort citations
  const filteredAndSortedCitations = citations
    .filter((citation) => {
      // Search filter
      const matchesSearch = !searchQuery ||
        citation.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
        citation.authors.some(author => author.toLowerCase().includes(searchQuery.toLowerCase())) ||
        (citation.citation_key && citation.citation_key.toLowerCase().includes(searchQuery.toLowerCase()))

      // Source filter
      const matchesSource =
        filterSource === 'all' ||
        (filterSource === 'project' && citation.is_from_project) ||
        (filterSource === 'external' && !citation.is_from_project)

      return matchesSearch && matchesSource
    })
    .sort((a, b) => {
      switch (sortBy) {
        case 'recent':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        case 'title':
          return a.title.localeCompare(b.title)
        case 'year':
          return (b.year || 0) - (a.year || 0)
        case 'usage':
          return (b.times_used || 0) - (a.times_used || 0)
        default:
          return 0
      }
    })

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary mb-4"></div>
          <p className="text-text-tertiary text-sm">Loading citations...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-serif text-text-primary flex items-center gap-2">
            <BookOpenIcon className="h-7 w-7 text-accent-primary" />
            Citation Library
          </h2>
          <p className="text-sm text-text-tertiary mt-1">
            {citations.length} citation{citations.length !== 1 ? 's' : ''} in your project
          </p>
        </div>

        <button
          onClick={loadCitations}
          className="flex items-center gap-2 px-4 py-2 bg-accent-primary hover:bg-accent-secondary text-neutral-900 font-medium rounded-lg transition-colors"
        >
          <ArrowPathIcon className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* Controls */}
      <div className="bg-surface border border-border-base rounded-lg p-4">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          {/* Search */}
          <div className="relative">
            <MagnifyingGlassIcon className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-text-tertiary" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search citations..."
              className="w-full pl-10 pr-4 py-2 bg-bg-base border border-border-subtle rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent"
            />
          </div>

          {/* Citation Style */}
          <div>
            <label className="block text-xs font-medium text-text-tertiary mb-1">
              Citation Style
            </label>
            <select
              value={selectedStyle}
              onChange={(e) => setSelectedStyle(e.target.value)}
              className="w-full px-3 py-2 bg-bg-base border border-border-subtle rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent"
            >
              {CITATION_STYLES.map((style) => (
                <option key={style} value={style}>
                  {style.toUpperCase()}
                </option>
              ))}
            </select>
          </div>

          {/* Filter Source */}
          <div>
            <label className="block text-xs font-medium text-text-tertiary mb-1">
              Source
            </label>
            <select
              value={filterSource}
              onChange={(e) => setFilterSource(e.target.value as 'all' | 'project' | 'external')}
              className="w-full px-3 py-2 bg-bg-base border border-border-subtle rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent"
            >
              <option value="all">All Sources</option>
              <option value="project">Project Documents</option>
              <option value="external">External Papers</option>
            </select>
          </div>

          {/* Sort By */}
          <div>
            <label className="block text-xs font-medium text-text-tertiary mb-1">
              Sort By
            </label>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as 'recent' | 'title' | 'year' | 'usage')}
              className="w-full px-3 py-2 bg-bg-base border border-border-subtle rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent"
            >
              <option value="recent">Recently Added</option>
              <option value="title">Title (A-Z)</option>
              <option value="year">Year (Newest)</option>
              <option value="usage">Most Used</option>
            </select>
          </div>
        </div>
      </div>

      {/* Citations List */}
      <div className="space-y-3">
        {filteredAndSortedCitations.length === 0 ? (
          <div className="bg-surface border border-border-base rounded-lg p-12 text-center">
            <BookOpenIcon className="h-16 w-16 text-text-muted mx-auto mb-4" />
            <p className="text-text-tertiary text-lg mb-2">
              {searchQuery || filterSource !== 'all'
                ? 'No citations match your filters'
                : 'No citations in this project yet'
              }
            </p>
            <p className="text-text-muted text-sm">
              {searchQuery || filterSource !== 'all'
                ? 'Try adjusting your search or filters'
                : 'Upload papers or generate citation suggestions to build your library'
              }
            </p>
          </div>
        ) : (
          filteredAndSortedCitations.map((citation) => (
            <div
              key={citation.id}
              className="bg-surface-hover border border-border-base rounded-lg p-6 hover:border-border-subtle transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  {/* Title and Citation Key */}
                  <div className="flex items-start gap-3 mb-2">
                    <h3 className="text-base font-semibold text-text-primary flex-1">
                      {citation.title}
                    </h3>
                    {citation.citation_key && (
                      <button
                        onClick={() => copyCitationKey(citation.citation_key!)}
                        className="flex items-center gap-1 px-2 py-1 bg-surface hover:bg-surface-hover text-text-secondary text-xs font-mono rounded transition-colors"
                        title="Copy citation key"
                      >
                        {citation.citation_key}
                        <ClipboardDocumentCheckIcon className="h-3 w-3" />
                      </button>
                    )}
                  </div>

                  {/* Authors and Year */}
                  <p className="text-sm text-text-tertiary mb-2">
                    {citation.authors.slice(0, 3).join(', ')}
                    {citation.authors.length > 3 && ' et al.'}
                    {citation.year && ` (${citation.year})`}
                  </p>

                  {/* Journal */}
                  {citation.journal_name && (
                    <p className="text-sm text-text-muted mb-2">
                      {citation.journal_name}
                    </p>
                  )}

                  {/* Formatted Citation */}
                  <div className="bg-bg-base border border-border-subtle rounded-lg p-3 mb-3">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-sm text-text-secondary flex-1">
                        {citation.formatted_citations[selectedStyle as keyof typeof citation.formatted_citations] ||
                          'Citation format not available'}
                      </p>
                      <button
                        onClick={() => copyFormattedCitation(citation)}
                        className="flex-shrink-0 p-1.5 hover:bg-surface text-text-tertiary hover:text-text-secondary rounded transition-colors"
                        title="Copy citation"
                      >
                        <ClipboardDocumentCheckIcon className="h-5 w-5" />
                      </button>
                    </div>
                  </div>

                  {/* Metadata */}
                  <div className="flex flex-wrap items-center gap-3 text-xs text-text-muted">
                    {citation.is_from_project && (
                      <Badge variant="info">
                        FROM PROJECT
                      </Badge>
                    )}
                    {citation.times_used > 0 && (
                      <Badge variant="neutral">
                        USED {citation.times_used} TIME{citation.times_used !== 1 ? 'S' : ''}
                      </Badge>
                    )}
                    {citation.doi && (
                      <a
                        href={`https://doi.org/${citation.doi}`}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent-primary hover:text-accent-secondary underline"
                      >
                        DOI: {citation.doi}
                      </a>
                    )}
                    {citation.url && !citation.doi && (
                      <a
                        href={citation.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-accent-primary hover:text-accent-secondary underline"
                      >
                        View Paper
                      </a>
                    )}
                  </div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Summary Stats */}
      {citations.length > 0 && (
        <div className="bg-surface border border-border-base rounded-lg p-4">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-center">
            <div>
              <p className="text-2xl font-bold text-accent-primary">{citations.length}</p>
              <p className="text-xs text-text-tertiary">Total Citations</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-accent-primary">
                {citations.filter(c => c.is_from_project).length}
              </p>
              <p className="text-xs text-text-tertiary">From Project</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-accent-primary">
                {citations.filter(c => !c.is_from_project).length}
              </p>
              <p className="text-xs text-text-tertiary">External</p>
            </div>
            <div>
              <p className="text-2xl font-bold text-accent-primary">
                {citations.reduce((sum, c) => sum + (c.times_used || 0), 0)}
              </p>
              <p className="text-xs text-text-tertiary">Total Uses</p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

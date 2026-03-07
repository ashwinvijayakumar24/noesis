import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import {
  XMarkIcon,
  MagnifyingGlassIcon,
  DocumentCheckIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  ExclamationCircleIcon
} from '@heroicons/react/24/outline'
import { Button } from './ui/Button'

interface PaperDiscoveryModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
}

interface DiscoveredPaper {
  title: string
  authors: string[]
  year: number
  source: string
  download_status: 'success' | 'failed' | 'no_fulltext'
  pdf_url?: string
  error?: string
}

interface DiscoveryProgress {
  stage: 'searching' | 'filtering' | 'downloading' | 'processing' | 'complete' | 'error'
  message: string
  papers_found: number
  papers_downloaded: number
}

export default function PaperDiscoveryModal({ isOpen, onClose, projectId }: PaperDiscoveryModalProps) {
  const [query, setQuery] = useState('')
  const [maxPapers, setMaxPapers] = useState(10)
  const [isSearching, setIsSearching] = useState(false)
  const [progress, setProgress] = useState<DiscoveryProgress | null>(null)
  const [results, setResults] = useState<DiscoveredPaper[]>([])
  const [error, setError] = useState<string | null>(null)

  const handleSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!query.trim()) return

    setIsSearching(true)
    setError(null)
    setProgress({
      stage: 'searching',
      message: 'Searching PubMed, arXiv, and Semantic Scholar...',
      papers_found: 0,
      papers_downloaded: 0
    })

    try {
      const response = await fetch(`/api/projects/${projectId}/discover-papers`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${localStorage.getItem('access_token')}`
        },
        body: JSON.stringify({
          query,
          max_papers: maxPapers
        })
      })

      if (!response.ok) {
        throw new Error('Paper discovery failed')
      }

      const data = await response.json()

      setProgress({
        stage: 'complete',
        message: `Successfully discovered ${data.papers_discovered.length} papers`,
        papers_found: data.papers_discovered.length,
        papers_downloaded: data.papers_discovered.filter((p: DiscoveredPaper) => p.download_status === 'success').length
      })
      setResults(data.papers_discovered)
    } catch (err) {
      console.error('Paper discovery error:', err)
      setError(err instanceof Error ? err.message : 'Failed to discover papers')
      setProgress({
        stage: 'error',
        message: 'Discovery failed',
        papers_found: 0,
        papers_downloaded: 0
      })
    } finally {
      setIsSearching(false)
    }
  }

  const handleClose = () => {
    setQuery('')
    setMaxPapers(10)
    setProgress(null)
    setResults([])
    setError(null)
    onClose()
  }

  const getProgressIcon = () => {
    if (!progress) return null

    switch (progress.stage) {
      case 'searching':
      case 'filtering':
      case 'downloading':
      case 'processing':
        return <ArrowPathIcon className="h-6 w-6 text-accent-primary animate-spin" />
      case 'complete':
        return <CheckCircleIcon className="h-6 w-6 text-teal-primary" />
      case 'error':
        return <ExclamationCircleIcon className="h-6 w-6 text-ruby-primary" />
    }
  }

  return (
    <AnimatePresence>
      {isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="absolute inset-0 bg-black/70 backdrop-blur-sm"
            onClick={handleClose}
          />

          {/* Modal */}
          <motion.div
            initial={{ opacity: 0, scale: 0.95, y: 20 }}
            animate={{ opacity: 1, scale: 1, y: 0 }}
            exit={{ opacity: 0, scale: 0.95, y: 20 }}
            className="relative bg-bg-surface border border-border-default rounded-lg shadow-2xl max-w-2xl w-full max-h-[90vh] overflow-hidden flex flex-col"
          >
            {/* Header */}
            <div className="flex items-center justify-between p-6 border-b border-border-default">
              <div className="flex items-center gap-3">
                <div className="inline-flex items-center justify-center w-10 h-10 bg-accent-primary/10 rounded-lg">
                  <MagnifyingGlassIcon className="h-5 w-5 text-accent-primary" />
                </div>
                <div>
                  <h3 className="text-xl font-semibold text-text-primary">Discover Papers</h3>
                  <p className="text-sm text-text-secondary">Search and auto-download relevant papers</p>
                </div>
              </div>
              <button
                onClick={handleClose}
                className="text-text-muted hover:text-text-primary transition-colors"
              >
                <XMarkIcon className="h-6 w-6" />
              </button>
            </div>

            {/* Content */}
            <div className="flex-1 overflow-y-auto p-6 space-y-6">
              {/* Search Form */}
              <form onSubmit={handleSearch} className="space-y-4">
                <div>
                  <label htmlFor="query" className="block text-sm font-medium text-text-secondary mb-2">
                    Search Query
                  </label>
                  <input
                    id="query"
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="e.g., transformer architecture attention mechanisms"
                    className="w-full px-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent"
                    disabled={isSearching}
                    required
                  />
                </div>

                <div>
                  <label htmlFor="maxPapers" className="block text-sm font-medium text-text-secondary mb-2">
                    Maximum Papers
                  </label>
                  <select
                    id="maxPapers"
                    value={maxPapers}
                    onChange={(e) => setMaxPapers(Number(e.target.value))}
                    className="w-full px-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent"
                    disabled={isSearching}
                  >
                    <option value={5}>5 papers</option>
                    <option value={10}>10 papers</option>
                  </select>
                </div>

                <Button
                  type="submit"
                  variant="primary"
                  size="lg"
                  className="w-full"
                  disabled={isSearching}
                >
                  <MagnifyingGlassIcon className="h-5 w-5 mr-2" />
                  {isSearching ? 'Discovering Papers...' : 'Discover Papers'}
                </Button>
              </form>

              {/* Progress */}
              {progress && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 bg-bg-void border border-border-default rounded-lg"
                >
                  <div className="flex items-start gap-3">
                    {getProgressIcon()}
                    <div className="flex-1">
                      <p className="text-sm font-medium text-text-primary">{progress.message}</p>
                      {progress.papers_found > 0 && (
                        <p className="text-xs text-text-secondary mt-1">
                          Found {progress.papers_found} papers, downloaded {progress.papers_downloaded} successfully
                        </p>
                      )}
                    </div>
                  </div>
                </motion.div>
              )}

              {/* Error */}
              {error && (
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  className="p-4 bg-ruby-light border border-ruby-primary/30 rounded-lg"
                >
                  <div className="flex items-start gap-3">
                    <ExclamationCircleIcon className="h-5 w-5 text-ruby-primary flex-shrink-0" />
                    <p className="text-sm text-ruby-primary">{error}</p>
                  </div>
                </motion.div>
              )}

              {/* Results */}
              {results.length > 0 && (
                <div className="space-y-3">
                  <h4 className="text-sm font-semibold text-text-primary">Discovered Papers ({results.length})</h4>
                  <div className="space-y-2 max-h-64 overflow-y-auto">
                    {results.map((paper, index) => (
                      <motion.div
                        key={index}
                        initial={{ opacity: 0, x: -10 }}
                        animate={{ opacity: 1, x: 0 }}
                        transition={{ delay: index * 0.05 }}
                        className="p-3 bg-bg-void border border-border-default rounded-lg"
                      >
                        <div className="flex items-start gap-3">
                          <div className="flex-shrink-0">
                            {paper.download_status === 'success' ? (
                              <DocumentCheckIcon className="h-5 w-5 text-teal-primary" />
                            ) : (
                              <ExclamationCircleIcon className="h-5 w-5 text-amber-primary" />
                            )}
                          </div>
                          <div className="flex-1 min-w-0">
                            <p className="text-sm font-medium text-text-primary truncate">{paper.title}</p>
                            <p className="text-xs text-text-secondary mt-1">
                              {paper.authors.slice(0, 3).join(', ')}{paper.authors.length > 3 && ' et al.'} • {paper.year} • {paper.source}
                            </p>
                            {paper.download_status !== 'success' && (
                              <p className="text-xs text-amber-primary mt-1">
                                {paper.download_status === 'no_fulltext' ? 'No free full-text available' : 'Download failed'}
                              </p>
                            )}
                          </div>
                        </div>
                      </motion.div>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Footer */}
            <div className="p-6 border-t border-border-default">
              <p className="text-xs text-text-muted">
                Searches across PubMed, arXiv, and Semantic Scholar. Papers are auto-downloaded via Unpaywall when available.
              </p>
            </div>
          </motion.div>
        </div>
      )}
    </AnimatePresence>
  )
}

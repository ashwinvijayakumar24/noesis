import { Fragment, useState, useEffect, useCallback } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { MagnifyingGlassIcon, XMarkIcon, ClockIcon, FolderIcon, DocumentIcon, TableCellsIcon } from '@heroicons/react/24/outline'
import { useNavigate } from 'react-router-dom'
import { api } from '../lib/api'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

interface GlobalSearchProps {
  isOpen: boolean
  onClose: () => void
}

interface SearchResults {
  query: string
  projects: any[]
  documents: any[]
  datasets: any[]
  total: number
  has_more: {
    projects: boolean
    documents: boolean
    datasets: boolean
  }
}

export default function GlobalSearch({ isOpen, onClose }: GlobalSearchProps) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResults | null>(null)
  const [recentSearches, setRecentSearches] = useState<string[]>([])
  const [recentProjects, setRecentProjects] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const navigate = useNavigate()
  const { session } = useAuthStore()

  // Load recent searches from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('recent_searches')
    if (saved) {
      try {
        setRecentSearches(JSON.parse(saved))
      } catch (e) {
        console.error('Failed to parse recent searches', e)
      }
    }
  }, [])

  // Load recent projects when modal opens
  useEffect(() => {
    if (isOpen && session?.access_token) {
      loadRecentProjects()
    }
  }, [isOpen, session])

  const loadRecentProjects = async () => {
    if (!session?.access_token) return

    try {
      const recent = await api.search.recent(session.access_token)
      setRecentProjects(recent)
    } catch (error) {
      console.error('Failed to load recent projects:', error)
    }
  }

  // Save search to recent searches
  const saveRecentSearch = (searchQuery: string) => {
    const updated = [searchQuery, ...recentSearches.filter(s => s !== searchQuery)].slice(0, 5)
    setRecentSearches(updated)
    localStorage.setItem('recent_searches', JSON.stringify(updated))
  }

  // Debounced search function
  const performSearch = useCallback(
    async (searchQuery: string) => {
      if (!searchQuery || searchQuery.length < 2 || !session?.access_token) {
        setResults(null)
        return
      }

      setLoading(true)
      try {
        const searchResults = await api.search.global(session.access_token, searchQuery)
        setResults(searchResults)
        saveRecentSearch(searchQuery)
      } catch (error: any) {
        console.error('Search failed:', error)
        toast.error('Search failed')
      } finally {
        setLoading(false)
      }
    },
    [session]
  )

  // Debounce search input
  useEffect(() => {
    const timer = setTimeout(() => {
      performSearch(query)
    }, 300)

    return () => clearTimeout(timer)
  }, [query, performSearch])

  const handleResultClick = (type: 'project' | 'document' | 'dataset', item: any) => {
    if (type === 'project') {
      navigate(`/projects/${item.id}`)
    } else if (type === 'document') {
      navigate(`/projects/${item.project_id}`)
    } else if (type === 'dataset') {
      navigate(`/projects/${item.project_id}`)
    }
    onClose()
    setQuery('')
  }

  const handleRecentSearchClick = (recentQuery: string) => {
    setQuery(recentQuery)
  }

  const highlightMatch = (text: string, search: string) => {
    if (!search) return text

    const regex = new RegExp(`(${search})`, 'gi')
    const parts = text.split(regex)

    return parts.map((part, index) =>
      regex.test(part) ? (
        <span key={index} className="font-bold text-pink-400">
          {part}
        </span>
      ) : (
        part
      )
    )
  }

  const showEmptyState = !query && recentSearches.length === 0 && recentProjects.length === 0
  const showRecentState = !query && (recentSearches.length > 0 || recentProjects.length > 0)
  const showResults = query && query.length >= 2
  const hasResults = results && results.total > 0

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-start justify-center p-4 pt-[10vh]">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-2xl transform overflow-hidden rounded-xl bg-gray-900 border border-gray-700 shadow-2xl transition-all">
                {/* Search Input */}
                <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-800">
                  <MagnifyingGlassIcon className="h-5 w-5 text-gray-400" />
                  <input
                    type="text"
                    className="flex-1 bg-transparent text-white placeholder-gray-500 outline-none text-lg"
                    placeholder="Search projects, documents, and datasets..."
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    autoFocus
                  />
                  <button
                    onClick={onClose}
                    className="text-gray-400 hover:text-gray-200 transition"
                  >
                    <XMarkIcon className="h-5 w-5" />
                  </button>
                </div>

                {/* Results */}
                <div className="max-h-[60vh] overflow-y-auto">
                  {/* Empty State */}
                  {showEmptyState && (
                    <div className="px-4 py-12 text-center">
                      <MagnifyingGlassIcon className="h-12 w-12 mx-auto text-gray-600 mb-3" />
                      <p className="text-gray-400 text-sm">
                        Search across all your projects, documents, and datasets
                      </p>
                      <p className="text-gray-500 text-xs mt-2">
                        Use <kbd className="px-2 py-1 bg-gray-800 rounded text-xs">⌘K</kbd> or{' '}
                        <kbd className="px-2 py-1 bg-gray-800 rounded text-xs">Ctrl+K</kbd> to open search
                      </p>
                    </div>
                  )}

                  {/* Recent Searches & Projects */}
                  {showRecentState && (
                    <div className="px-4 py-3 space-y-4">
                      {recentSearches.length > 0 && (
                        <div>
                          <h3 className="text-xs font-medium text-gray-500 uppercase mb-2 px-2">Recent Searches</h3>
                          <div className="space-y-1">
                            {recentSearches.map((recentQuery, idx) => (
                              <button
                                key={idx}
                                onClick={() => handleRecentSearchClick(recentQuery)}
                                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-800 transition text-left"
                              >
                                <ClockIcon className="h-4 w-4 text-gray-500" />
                                <span className="text-gray-300 text-sm">{recentQuery}</span>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {recentProjects.length > 0 && (
                        <div>
                          <h3 className="text-xs font-medium text-gray-500 uppercase mb-2 px-2">Recently Viewed</h3>
                          <div className="space-y-1">
                            {recentProjects.map((project) => (
                              <button
                                key={project.id}
                                onClick={() => handleResultClick('project', project)}
                                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-800 transition text-left"
                              >
                                <FolderIcon className="h-4 w-4 text-pink-500" />
                                <div className="flex-1 min-w-0">
                                  <p className="text-gray-300 text-sm font-medium truncate">{project.title}</p>
                                  {project.description && (
                                    <p className="text-gray-500 text-xs truncate">{project.description}</p>
                                  )}
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}

                  {/* Loading */}
                  {loading && showResults && (
                    <div className="px-4 py-8 text-center">
                      <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-solid border-pink-600 border-r-transparent"></div>
                      <p className="text-gray-400 text-sm mt-2">Searching...</p>
                    </div>
                  )}

                  {/* Search Results */}
                  {!loading && showResults && results && (
                    <div className="px-4 py-3 space-y-4">
                      {/* No Results */}
                      {!hasResults && (
                        <div className="py-8 text-center">
                          <p className="text-gray-400 text-sm">No results found for "{query}"</p>
                        </div>
                      )}

                      {/* Projects */}
                      {results.projects.length > 0 && (
                        <div>
                          <div className="flex items-center justify-between mb-2 px-2">
                            <h3 className="text-xs font-medium text-gray-500 uppercase">
                              Projects ({results.projects.length})
                            </h3>
                            {results.has_more.projects && (
                              <span className="text-xs text-gray-500">+more</span>
                            )}
                          </div>
                          <div className="space-y-1">
                            {results.projects.map((project) => (
                              <button
                                key={project.id}
                                onClick={() => handleResultClick('project', project)}
                                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-800 transition text-left"
                              >
                                <FolderIcon className="h-5 w-5 text-pink-500" />
                                <div className="flex-1 min-w-0">
                                  <p className="text-gray-200 text-sm font-medium">
                                    {highlightMatch(project.title, query)}
                                  </p>
                                  {project.description && (
                                    <p className="text-gray-400 text-xs truncate">
                                      {highlightMatch(project.description, query)}
                                    </p>
                                  )}
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Documents */}
                      {results.documents.length > 0 && (
                        <div>
                          <div className="flex items-center justify-between mb-2 px-2">
                            <h3 className="text-xs font-medium text-gray-500 uppercase">
                              Documents ({results.documents.length})
                            </h3>
                            {results.has_more.documents && (
                              <span className="text-xs text-gray-500">+more</span>
                            )}
                          </div>
                          <div className="space-y-1">
                            {results.documents.map((doc) => (
                              <button
                                key={doc.id}
                                onClick={() => handleResultClick('document', doc)}
                                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-800 transition text-left"
                              >
                                <DocumentIcon className="h-5 w-5 text-blue-500" />
                                <div className="flex-1 min-w-0">
                                  <p className="text-gray-200 text-sm">
                                    {highlightMatch(doc.title, query)}
                                  </p>
                                  <p className="text-gray-500 text-xs truncate">
                                    in {doc.projects?.title || 'Unknown Project'}
                                  </p>
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}

                      {/* Datasets */}
                      {results.datasets.length > 0 && (
                        <div>
                          <div className="flex items-center justify-between mb-2 px-2">
                            <h3 className="text-xs font-medium text-gray-500 uppercase">
                              Datasets ({results.datasets.length})
                            </h3>
                            {results.has_more.datasets && (
                              <span className="text-xs text-gray-500">+more</span>
                            )}
                          </div>
                          <div className="space-y-1">
                            {results.datasets.map((dataset) => (
                              <button
                                key={dataset.id}
                                onClick={() => handleResultClick('dataset', dataset)}
                                className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-gray-800 transition text-left"
                              >
                                <TableCellsIcon className="h-5 w-5 text-green-500" />
                                <div className="flex-1 min-w-0">
                                  <p className="text-gray-200 text-sm">
                                    {highlightMatch(dataset.filename, query)}
                                  </p>
                                  <p className="text-gray-500 text-xs truncate">
                                    in {dataset.projects?.title || 'Unknown Project'}
                                  </p>
                                </div>
                              </button>
                            ))}
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>

                {/* Footer */}
                <div className="px-4 py-2 border-t border-gray-800 flex items-center justify-between">
                  <div className="flex items-center gap-2 text-xs text-gray-500">
                    <kbd className="px-2 py-1 bg-gray-800 rounded">↑↓</kbd>
                    <span>Navigate</span>
                    <kbd className="px-2 py-1 bg-gray-800 rounded">↵</kbd>
                    <span>Select</span>
                    <kbd className="px-2 py-1 bg-gray-800 rounded">Esc</kbd>
                    <span>Close</span>
                  </div>
                  <div className="text-xs text-gray-500">
                    {results && results.total > 0 && (
                      <span>{results.total} result{results.total !== 1 ? 's' : ''}</span>
                    )}
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

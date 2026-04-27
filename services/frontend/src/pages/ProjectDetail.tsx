import { useEffect, useState, useRef, lazy, Suspense } from 'react'
import type { ReactNode } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { motion, AnimatePresence } from 'framer-motion'
import { DocumentTextIcon, PencilIcon, CheckIcon, XMarkIcon, ArrowDownTrayIcon, PlusIcon, LightBulbIcon, MagnifyingGlassIcon, BookOpenIcon, InformationCircleIcon } from '@heroicons/react/24/outline'
import UploadDocumentModal from '../components/UploadDocumentModal'
import DeleteDocumentModal from '../components/DeleteDocumentModal'
import GlobalSearch from '../components/GlobalSearch'
import DraftsPanel from '../components/DraftsPanel'
import UploadDraftModal from '../components/UploadDraftModal'
import EmptyStateGuide from '../components/EmptyStateGuide'
import PageContainer from '../components/layout/PageContainer'
import { TabNavigation } from '../components/navigation/TabNavigation'
import { Button } from '../components/ui/Button'
import PaperCard from '../components/literature/PaperCard'
import type { PaperDocument } from '../components/literature/PaperCard'

// Lazy load heavy components for better performance
const InsightsTab = lazy(() => import('../components/InsightsTab'))
const DiscoverTab = lazy(() => import('../components/DiscoverTab'))

interface TabItem {
  id: string
  label: string
  icon?: ReactNode
  badgeCount?: number
  badgeVariant?: 'neutral' | 'primary' | 'warning' | 'success'
  isProcessing?: boolean
  colorScheme?: 'crimson' | 'amber' | 'emerald' | 'violet'
}

interface Project {
  id: string
  title: string
  description: string | null
  created_at: string
  updated_at: string
}

interface Document {
  id: string
  title: string
  file_url: string
  file_type?: string
  source_type?: string
  resolution_status?: string | null
  status: string
  created_at: string
  metadata?: {
    import_source?: string
    authors?: string[]
    year?: string
    journal?: string
    abstract?: string
    doi?: string
  }
}

type SourceFilter = 'all' | 'analyzed_pdf' | 'bibtex_import'
type SortBy = 'newest' | 'oldest' | 'status' | 'source'

type ActiveTab = 'literature' | 'discover' | 'insights' | 'drafts'

// Loading component for lazy-loaded sections
function ComponentLoader() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-solid border-accent-primary border-r-transparent"></div>
    </div>
  )
}

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { session } = useAuthStore()
  const [project, setProject] = useState<Project | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<ActiveTab>('literature')

  // Document modals
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  const [isImportModalOpen, setIsImportModalOpen] = useState(false)
  const [deleteDocument, setDeleteDocument] = useState<{ id: string; title: string } | null>(null)

  // Literature tab filter/sort
  const [sourceFilter, setSourceFilter] = useState<SourceFilter>('all')
  const [sortBy, setSortBy] = useState<SortBy>('newest')

  // Draft modals
  const [isUploadDraftModalOpen, setIsUploadDraftModalOpen] = useState(false)
  const [draftRefreshTrigger, setDraftRefreshTrigger] = useState(0)
  const [draftCount, setDraftCount] = useState(0)

  // Status legend popover
  const [showStatusLegend, setShowStatusLegend] = useState(false)

  // Banner dismissal state (persisted in localStorage)
  const [isDraftWarningDismissed, setIsDraftWarningDismissed] = useState(() => {
    if (!projectId) return false
    return localStorage.getItem(`noesis_draft_warning_dismissed_${projectId}`) === 'true'
  })

  // Search state
  const [isSearchOpen, setIsSearchOpen] = useState(false)

  // Track when each document first entered a stuck/analyzing state (for timeout)
  const analyzingStartTimes = useRef<Map<string, number>>(new Map())

  // Insights state (used by Compass and Insights tabs)
  const [_insights, setInsights] = useState<any | null>(null)
  const [insightsStatus, setInsightsStatus] = useState<'not_analyzed' | 'analyzing' | 'analyzed' | 'failed'>('not_analyzed')
  const [insightsPolling, setInsightsPolling] = useState<number | null>(null)

  // Project editing state
  const [isEditingProject, setIsEditingProject] = useState(false)
  const [editedTitle, setEditedTitle] = useState('')
  const [editedDescription, setEditedDescription] = useState('')

  // Load project details only on mount and when projectId changes
  useEffect(() => {
    if (session?.access_token && projectId) {
      loadProjectDetails()
      loadDraftCount()
    }
  }, [projectId])

  // Reload draft count when drafts are uploaded/deleted
  useEffect(() => {
    if (session?.access_token && projectId && draftRefreshTrigger > 0) {
      loadDraftCount()
    }
  }, [draftRefreshTrigger])

  // Update document title when project loads
  useEffect(() => {
    if (project?.title) {
      document.title = `${project.title} | Noesis`
    } else {
      document.title = 'Project | Noesis'
    }
  }, [project])

  // Poll for status updates every 3 seconds if there are processing or resolving documents
  useEffect(() => {
    if (!session?.access_token || !projectId) return

    const hasProcessingDocs = documents.some(
      (doc) => doc.status.toLowerCase() === 'processing' ||
               doc.status.toLowerCase() === 'uploaded' ||
               doc.status.toLowerCase() === 'ready' ||
               doc.status.toLowerCase() === 'analyzing' ||
               doc.resolution_status === 'resolving'
    )

    if (!hasProcessingDocs) return

    const STUCK_TIMEOUT_MS = 3 * 60 * 1000 // 3 minutes

    const pollInterval = setInterval(() => {
      api.projects.getBundle(session.access_token, projectId).then(data => {
        const { documents: updatedDocs } = data as { documents: any[] }
        const now = Date.now()

        const processedDocs = (updatedDocs || []).map((doc: any) => {
          const s = doc.status?.toLowerCase()
          const isStuck = s === 'analyzing' || s === 'processing' || s === 'uploaded' || s === 'ready' || doc.resolution_status === 'resolving'

          if (isStuck) {
            if (!analyzingStartTimes.current.has(doc.id)) {
              analyzingStartTimes.current.set(doc.id, now)
            } else if (now - analyzingStartTimes.current.get(doc.id)! > STUCK_TIMEOUT_MS) {
              analyzingStartTimes.current.delete(doc.id)
              api.documents.markFailed(session.access_token, doc.id).catch(() => {})
              return { ...doc, status: 'failed' }
            }
          } else {
            analyzingStartTimes.current.delete(doc.id)
          }
          return doc
        })

        setDocuments(processedDocs)
      }).catch(error => {
        console.error('Polling error:', error)
      })
    }, 3000) // Poll every 3 seconds

    return () => {
      clearInterval(pollInterval)
    }
  }, [documents, session, projectId])

  // Background polling for insights status (Phase 4.2)
  useEffect(() => {
    if (!session?.access_token || !projectId) return

    const checkInsightsStatus = async () => {
      try {
        const data = await api.projects.getInsights(session.access_token, projectId)
        const previousStatus = insightsStatus
        const newStatus = data.status

        setInsightsStatus(newStatus)

        // Phase 4.4: Show toast when auto-regeneration completes
        if (previousStatus === 'analyzing' && newStatus === 'analyzed') {
          toast.success('✓ Literature Map updated with latest documents', { duration: 4000 })
        }

        // Start polling if analyzing
        if (newStatus === 'analyzing' && !insightsPolling) {
          const interval = setInterval(() => checkInsightsStatus(), 5000) // Poll every 5 seconds
          setInsightsPolling(interval)
        }

        // Stop polling if not analyzing
        if (newStatus !== 'analyzing' && insightsPolling) {
          clearInterval(insightsPolling)
          setInsightsPolling(null)
        }

        // Update insights data if on insights/compass tab
        if (activeTab === 'insights' && data.insights) {
          setInsights(data.insights)
        }
      } catch (error: any) {
        console.error('Failed to check insights status:', error)
      }
    }

    // Initial check
    checkInsightsStatus()

    // Cleanup on unmount
    return () => {
      if (insightsPolling) {
        clearInterval(insightsPolling)
      }
    }
  }, [session, projectId, activeTab])

  // Load insights when navigating to insights or compass tabs
  useEffect(() => {
    if (!session?.access_token || !projectId) return
    if (activeTab !== 'insights') return

    const loadInsights = async () => {
      try {
        const data = await api.projects.getInsights(session.access_token, projectId)
        setInsights(data?.insights || null)
        setInsightsStatus(data.status)
      } catch (error: any) {
        console.error('Failed to load insights:', error)
        setInsights(null)
      }
    }

    loadInsights()
  }, [activeTab, session, projectId])

  const loadProjectDetails = async () => {
    if (!session?.access_token || !projectId) {
      return
    }

    try {
      setLoading(true)
      const data = await api.projects.getBundle(session.access_token, projectId)

      const { documents, ...projectData } = data
      setProject(projectData as Project)
      setDocuments(documents || [])
    } catch (error: any) {
      console.error('Failed to load project:', error)
      toast.error('Failed to load project details')
      navigate('/projects')
    } finally {
      setLoading(false)
    }
  }

  // Silent document refresh — no loading spinner, used for background updates
  const silentRefreshDocuments = async () => {
    if (!session?.access_token || !projectId) return
    try {
      const data = await api.projects.getBundle(session.access_token, projectId)
      setDocuments(data.documents || [])
    } catch {}
  }

  const loadDraftCount = async () => {
    if (!session?.access_token || !projectId) return

    try {
      const drafts = await api.drafts.list(session.access_token, projectId)
      setDraftCount(drafts?.length || 0)
    } catch (error: any) {
      console.error('Failed to load draft count:', error)
      // Silent fail - draft count not critical for page load
    }
  }

  const handleStartEditProject = () => {
    if (project) {
      setEditedTitle(project.title)
      setEditedDescription(project.description || '')
      setIsEditingProject(true)
    }
  }

  const handleCancelEditProject = () => {
    setIsEditingProject(false)
    setEditedTitle('')
    setEditedDescription('')
  }

  const handleSaveProject = async () => {
    if (!session?.access_token || !projectId) return

    if (!editedTitle.trim()) {
      toast.error('Project title cannot be empty')
      return
    }

    try {
      await api.projects.update(session.access_token, projectId, {
        title: editedTitle.trim(),
        description: editedDescription.trim() || null
      })

      if (project) {
        setProject({
          ...project,
          title: editedTitle.trim(),
          description: editedDescription.trim() || null
        })
      }

      setIsEditingProject(false)
      toast.success('Project updated successfully')
    } catch (error: any) {
      console.error('Failed to update project:', error)
      toast.error('Failed to update project')
    }
  }

  const handleDraftsLoaded = (count: number) => {
    setDraftCount(count)
  }

  const handleDismissDraftWarning = () => {
    if (!projectId) return
    localStorage.setItem(`noesis_draft_warning_dismissed_${projectId}`, 'true')
    setIsDraftWarningDismissed(true)
  }

  const handleExportBibTeX = async () => {
    if (documents.length === 0) {
      toast.error('No documents to export')
      return
    }

    try {
      toast.loading('Generating BibTeX file...')

      // Call the API endpoint
      const response = await fetch(
        `${import.meta.env.VITE_API_URL}/projects/${projectId}/export-bibtex`,
        {
          headers: {
            'Authorization': `Bearer ${session?.access_token}`
          }
        }
      )

      toast.dismiss()

      if (!response.ok) {
        throw new Error('Failed to generate BibTeX')
      }

      // Get the blob and download
      const blob = await response.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `${project?.title?.replace(/ /g, '_')}_citations.bib` || 'citations.bib'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      toast.success(`BibTeX file downloaded (${documents.length} entries)`)
    } catch (error: any) {
      toast.dismiss()
      toast.error(error.message || 'Failed to export BibTeX')
    }
  }

  if (loading && !project) {
    return (
      <div className="min-h-screen bg-bg-surface flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
          <p className="mt-4 text-text-tertiary">Loading project...</p>
        </div>
      </div>
    )
  }

  if (!project) {
    return null
  }

  const analyzedDocCount = documents.filter(doc => doc.status === 'analyzed').length

  // Prepare tabs for TabNavigation component
  // Order: Literature → Literature Map → Discover → Drafts
  const tabs: TabItem[] = [
    {
      id: 'literature',
      label: 'Literature',
      icon: <DocumentTextIcon className="h-5 w-5" />,
      badgeCount: documents.length > 0 ? documents.length : undefined,
      badgeVariant: 'neutral',
      colorScheme: 'crimson',
    },
    {
      id: 'insights',
      label: 'Literature Map',
      icon: <LightBulbIcon className="h-5 w-5" />,
      isProcessing: insightsStatus === 'analyzing',
      colorScheme: 'amber',
    },
    {
      id: 'discover',
      label: 'Discover',
      icon: <MagnifyingGlassIcon className="h-5 w-5" />,
      colorScheme: 'emerald',
    },
    {
      id: 'drafts',
      label: 'Drafts',
      icon: (
        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
      ),
      badgeCount: draftCount > 0 ? draftCount : undefined,
      badgeVariant: 'primary',
      colorScheme: 'violet',
    },
  ]

  return (
    <PageContainer
      breadcrumbs={[
        { label: 'Projects', href: '/projects' },
        { label: project.title || 'Loading...' },
      ]}
      backLink="/projects"
      backLabel="Back to Projects"
    >

      {/* Loading State */}
      {loading && (
        <div className="text-center py-12">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
          <p className="mt-4 text-text-tertiary">Loading project...</p>
        </div>
      )}

      {/* Project Content */}
      {!loading && project && (
        <>
          {/* Project Header */}
          <div className="bg-bg-bg-surfacerounded-lg border border-border-default p-6 mb-8">
            {isEditingProject ? (
              /* Edit Mode */
              <div className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2">Project Title</label>
                  <input
                    type="text"
                    value={editedTitle}
                    onChange={(e) => setEditedTitle(e.target.value)}
                    className="w-full px-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary text-2xl font-sans font-semibold focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-all duration-150 tracking-normal"
                    placeholder="Enter project title"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-text-secondary mb-2">Description <span className="text-text-muted font-mono text-xs">(optional)</span></label>
                  <textarea
                    value={editedDescription}
                    onChange={(e) => setEditedDescription(e.target.value)}
                    className="w-full px-4 py-3 bg-bg-void border border-border-default rounded-lg text-text-primary focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-all duration-150 tracking-normal"
                    placeholder="Enter project description"
                    rows={3}
                  />
                </div>
                <div className="flex items-center gap-3">
                  <Button
                    onClick={handleSaveProject}
                    variant="primary"
                  >
                    <CheckIcon className="h-4 w-4" />
                    Save Changes
                  </Button>
                  <button
                    onClick={handleCancelEditProject}
                    className="flex items-center gap-2 px-4 py-2 text-text-secondary hover:text-text-primary border-2 border-border-default rounded-lg hover:bg-bg-hover hover:border-accent-primary/30 transition-all duration-150"
                  >
                    <XMarkIcon className="h-4 w-4" />
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              /* View Mode */
              <>
                <div className="flex items-start justify-between mb-2">
                  <h2 className="text-3xl font-sans font-semibold text-text-primary tracking-normal">
                    {project.title}
                  </h2>
                  <button
                    onClick={handleStartEditProject}
                    className="flex items-center gap-2 px-3 py-1.5 text-sm text-text-secondary hover:text-accent-primary border border-border-default rounded-lg hover:bg-bg-hover hover:border-accent-primary/30 transition-all duration-150"
                    title="Edit project details"
                  >
                    <PencilIcon className="h-4 w-4" />
                    Edit
                  </button>
                </div>
                <p className="text-text-secondary mb-4 leading-relaxed">
                  {project.description || 'No description'}
                </p>
                <div className="flex items-center gap-4 text-sm font-mono text-text-muted">
                  <span>{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
                  <span>•</span>
                  <span>Created {new Date(project.created_at).toLocaleDateString()}</span>
                </div>
              </>
            )}
          </div>

          {/* Tabs Navigation */}
          <TabNavigation
            tabs={tabs}
            activeTab={activeTab}
            onTabChange={(tabId) => setActiveTab(tabId as ActiveTab)}
            className="mb-8"
          />

          {/* Tab Content with Animations */}
          <AnimatePresence mode="wait">
            {/* Literature Tab - Documents + Citation Network */}
            {activeTab === 'literature' && (
              <motion.div
                key="literature"
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0, y: -20 }}
                transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
                className="space-y-8"
              >
              {/* Literature Section — unified list */}
              <div>
                {/* Header */}
                <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-5">
                  <div>
                    <h3 className="text-2xl font-sans font-semibold text-text-primary tracking-normal">Literature</h3>
                    <p className="text-sm text-text-tertiary mt-1">
                      {(() => {
                        const analyzedCount = documents.filter(d => d.status === 'analyzed').length
                        const resolvingCount = documents.filter(d => d.resolution_status === 'resolving').length
                        const unresolvedCount = documents.filter(d => d.resolution_status === 'unresolved').length
                        const parts = []
                        if (analyzedCount) parts.push(`${analyzedCount} analyzed`)
                        if (resolvingCount) parts.push(`${resolvingCount} resolving`)
                        if (unresolvedCount) parts.push(`${unresolvedCount} metadata-only`)
                        return parts.length > 0 ? parts.join(' · ') : `${documents.length} papers`
                      })()}
                    </p>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    {/* Source filter pills + legend button */}
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-0.5 bg-bg-elevated/70 rounded-lg p-0.5 border border-border-default">
                        {(['all', 'analyzed_pdf', 'bibtex_import'] as SourceFilter[]).map(filter => {
                          const labels: Record<SourceFilter, string> = {
                            all: 'All',
                            analyzed_pdf: 'Analyzed PDFs',
                            bibtex_import: 'BibTeX Imports',
                          }
                          // A paper is a BibTeX import if source_type says so, OR file_type says so
                          // (fallback for docs inserted before migration 012 ran), OR resolution_status is set
                          const isBib = (d: Document) =>
                            d.source_type === 'bibtex_import' ||
                            d.source_type === 'zotero_import' ||
                            d.source_type === 'discovered' ||
                            d.file_type === 'bibtex_import' ||
                            (d.resolution_status != null && d.resolution_status !== '')
                          const filterCounts: Record<SourceFilter, number> = {
                            all: documents.length,
                            analyzed_pdf: documents.filter(d => !isBib(d) && d.status === 'analyzed').length,
                            bibtex_import: documents.filter(isBib).length,
                          }
                          const count = filterCounts[filter]
                          const isDisabled = filter !== 'all' && count === 0
                          const isActive = sourceFilter === filter
                          return (
                            <button
                              key={filter}
                              onClick={() => !isDisabled && setSourceFilter(filter)}
                              className={`px-2.5 py-1 text-xs font-semibold rounded-md transition-all duration-150 flex items-center gap-1.5 ${
                                isActive
                                  ? 'bg-accent-primary/12 text-accent-primary ring-1 ring-inset ring-accent-primary/25'
                                  : 'text-text-muted hover:text-text-secondary hover:bg-white/5'
                              } ${isDisabled ? 'opacity-35 pointer-events-none' : 'cursor-pointer'}`}
                            >
                              {labels[filter]}
                              {filter !== 'all' && (
                                <span className={`text-[10px] tabular-nums ${isActive ? 'text-accent-primary/70' : 'text-text-tertiary'}`}>
                                  {count}
                                </span>
                              )}
                            </button>
                          )
                        })}
                      </div>

                      {/* Status legend toggle */}
                      <div className="relative">
                        <button
                          onClick={() => setShowStatusLegend(prev => !prev)}
                          className="text-text-muted hover:text-text-secondary transition-colors duration-150 p-0.5 rounded"
                          title="Status legend"
                        >
                          <InformationCircleIcon className="h-4 w-4" />
                        </button>

                        {showStatusLegend && (
                          <div className="absolute right-0 top-7 z-20 w-80 bg-bg-elevated border border-border-default rounded-xl p-4 shadow-lg">
                            <div className="flex items-center justify-between mb-3">
                              <p className="text-xs font-semibold text-text-primary">Status Legend</p>
                              <button
                                onClick={() => setShowStatusLegend(false)}
                                className="text-text-muted hover:text-text-secondary transition-colors duration-150"
                              >
                                <XMarkIcon className="h-3.5 w-3.5" />
                              </button>
                            </div>
                            <div className="space-y-3">
                              <div className="flex items-start gap-2.5">
                                <span className="text-emerald-400 mt-0.5 shrink-0">●</span>
                                <div>
                                  <span className="text-xs font-semibold text-text-primary">Processed</span>
                                  <p className="text-xs text-text-tertiary mt-0.5 leading-relaxed">Full RAG analysis complete. This paper can be searched, cited, and used in draft analysis.</p>
                                </div>
                              </div>
                              <div className="flex items-start gap-2.5">
                                <span className="text-amber-400 mt-0.5 shrink-0">●</span>
                                <div>
                                  <span className="text-xs font-semibold text-text-primary">Analyzing</span>
                                  <p className="text-xs text-text-tertiary mt-0.5 leading-relaxed">Pipeline in progress. For PDFs: extracting text and generating embeddings. For .bib imports: searching for open-access PDF, downloading, and analyzing.</p>
                                </div>
                              </div>
                              <div className="flex items-start gap-2.5">
                                <span className="text-sky-400 mt-0.5 shrink-0">●</span>
                                <div>
                                  <span className="text-xs font-semibold text-text-primary">Imported</span>
                                  <p className="text-xs text-text-tertiary mt-0.5 leading-relaxed">.bib entry imported, but no open-access PDF was found. Metadata saved. Upload the PDF manually for full analysis.</p>
                                </div>
                              </div>
                              <div className="flex items-start gap-2.5">
                                <span className="text-red-400 mt-0.5 shrink-0">●</span>
                                <div>
                                  <span className="text-xs font-semibold text-text-primary">Failed</span>
                                  <p className="text-xs text-text-tertiary mt-0.5 leading-relaxed">Document analysis failed (PDF uploads only). Try re-uploading the file.</p>
                                </div>
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    </div>

                    {/* Sort dropdown */}
                    {documents.length > 1 && (
                      <select
                        value={sortBy}
                        onChange={e => setSortBy(e.target.value as SortBy)}
                        className="text-xs font-semibold bg-bg-elevated border border-border-default rounded-lg px-2.5 py-1.5 text-text-secondary focus:ring-1 focus:ring-accent-primary focus:border-accent-primary transition-colors"
                      >
                        <option value="newest">Newest</option>
                        <option value="oldest">Oldest</option>
                        <option value="status">By status</option>
                        <option value="source">By source</option>
                      </select>
                    )}

                    {/* Separator */}
                    <div className="h-5 w-px bg-border-default hidden sm:block" />

                    {/* Export BibTeX */}
                    {documents.length > 0 && (
                      <button
                        onClick={handleExportBibTeX}
                        className="px-3 py-1.5 border border-border-default text-text-secondary text-xs font-semibold rounded-lg hover:bg-bg-elevated hover:border-accent-teal hover:text-accent-teal transition-all duration-150 flex items-center gap-1.5"
                      >
                        <ArrowDownTrayIcon className="h-3.5 w-3.5" />
                        Export .bib
                      </button>
                    )}

                    {/* Import References (.bib / Zotero) */}
                    <button
                      onClick={() => setIsImportModalOpen(true)}
                      className="px-3 py-1.5 border border-border-default text-text-secondary text-xs font-semibold rounded-lg hover:bg-bg-elevated hover:border-violet-400/40 hover:text-violet-400 transition-all duration-150 flex items-center gap-1.5"
                    >
                      <BookOpenIcon className="h-3.5 w-3.5" />
                      Import .bib
                    </button>

                    {/* Upload PDF — same height as Import .bib */}
                    <button
                      onClick={() => setIsUploadModalOpen(true)}
                      className="px-3 py-1.5 bg-accent-primary text-white text-xs font-semibold rounded-lg hover:bg-accent-hover transition-all duration-150 flex items-center gap-1.5"
                    >
                      <PlusIcon className="h-3.5 w-3.5" />
                      Upload PDF
                    </button>
                  </div>
                </div>

                {/* Draft Warning Banner */}
                {draftCount > 0 && documents.length === 0 && !isDraftWarningDismissed && (
                  <div className="mb-5 bg-warning/10 border border-warning/40 rounded-xl p-4">
                    <div className="flex items-start gap-3">
                      <svg className="h-5 w-5 text-warning shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <div className="flex-1">
                        <p className="text-sm font-semibold text-warning">Add papers for citation suggestions</p>
                        <p className="text-xs text-text-secondary mt-0.5">
                          You have {draftCount} draft{draftCount > 1 ? 's' : ''} but no papers yet.
                          Citation suggestions require papers in your library.
                        </p>
                        <div className="flex gap-3 mt-2">
                          <button onClick={() => setIsUploadModalOpen(true)} className="text-xs font-semibold text-accent-primary underline">
                            Add Papers
                          </button>
                          <button onClick={handleDismissDraftWarning} className="text-xs text-text-muted hover:text-text-primary transition-colors">
                            Dismiss
                          </button>
                        </div>
                      </div>
                      <button onClick={handleDismissDraftWarning} className="text-text-muted hover:text-warning transition-colors">
                        <XMarkIcon className="h-4 w-4" />
                      </button>
                    </div>
                  </div>
                )}

                {/* Empty state */}
                {documents.length === 0 && (
                  <EmptyStateGuide onUploadClick={() => setIsUploadModalOpen(true)} />
                )}

                {/* Unified paper list */}
                {documents.length > 0 && (() => {
                  // Filter
                  const isBib = (d: Document) =>
                    d.source_type === 'bibtex_import' ||
                    d.source_type === 'zotero_import' ||
                    d.file_type === 'bibtex_import' ||
                    (d.resolution_status != null && d.resolution_status !== '')
                  let filtered = sourceFilter === 'all'
                    ? documents
                    : sourceFilter === 'bibtex_import'
                    ? documents.filter(isBib)
                    : documents.filter(d => !isBib(d) && d.status === 'analyzed')

                  // Sort
                  filtered = [...filtered].sort((a, b) => {
                    if (sortBy === 'oldest') return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
                    if (sortBy === 'status') {
                      const order: Record<string, number> = { analyzed: 0, analyzing: 1, processing: 2, uploaded: 2, ready: 2, imported: 3, failed: 4 }
                      return (order[a.status.toLowerCase()] ?? 9) - (order[b.status.toLowerCase()] ?? 9)
                    }
                    if (sortBy === 'source') {
                      const order: Record<string, number> = { manual_upload: 0, bibtex_import: 1, zotero_import: 1, discovered: 2 }
                      return (order[a.source_type || 'manual_upload'] ?? 9) - (order[b.source_type || 'manual_upload'] ?? 9)
                    }
                    // newest (default)
                    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
                  })

                  return (
                    <div className="space-y-2">
                      {filtered.map(doc => (
                        <PaperCard
                          key={doc.id}
                          document={doc as PaperDocument}
                          projectId={projectId!}
                          onDelete={(id, title) => setDeleteDocument({ id, title })}
                          token={session?.access_token}
                          onResolved={silentRefreshDocuments}
                        />
                      ))}
                      {filtered.length === 0 && (
                        <p className="text-sm text-text-muted text-center py-8">
                          No papers match this filter.
                        </p>
                      )}
                    </div>
                  )
                })()}
              </div>
            </motion.div>
          )}

          {/* Discover Tab */}
          {activeTab === 'discover' && projectId && (
            <motion.div
              key="discover"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <Suspense fallback={<ComponentLoader />}>
                <DiscoverTab
                  projectId={projectId}
                  documentCount={documents.length}
                  analyzedDocCount={analyzedDocCount}
                  onDocumentSaved={loadProjectDetails}
                  insightsAnalyzed={insightsStatus === 'analyzed'}
                  onTabChange={(tab) => setActiveTab(tab as ActiveTab)}
                />
              </Suspense>
            </motion.div>
          )}

          {/* Drafts Tab */}
          {activeTab === 'drafts' && session?.access_token && projectId && (
            <motion.div
              key="drafts"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
                <div>
                  <h3 className="text-2xl font-sans font-semibold text-text-primary tracking-normal">Research Drafts</h3>
                  <p className="text-sm text-text-secondary mt-1">
                    Get AI-powered feedback and citation suggestions
                  </p>
                </div>

                <Button
                  onClick={() => setIsUploadDraftModalOpen(true)}
                  variant="primary"
                >
                  <PlusIcon className="h-4 w-4" />
                  Upload Draft
                </Button>
              </div>
              <DraftsPanel
                token={session.access_token}
                projectId={projectId}
                refreshTrigger={draftRefreshTrigger}
                onDraftsLoaded={handleDraftsLoaded}
              />
            </motion.div>
          )}

          {/* Literature Map Tab */}
          {activeTab === 'insights' && projectId && (
            <motion.div
              key="insights"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <Suspense fallback={<ComponentLoader />}>
                <InsightsTab projectId={projectId} onDocumentSaved={loadProjectDetails} />
              </Suspense>
            </motion.div>
          )}
          </AnimatePresence>
        </>
      )}

      {/* Upload PDF Modal */}
      {session?.access_token && projectId && (
        <UploadDocumentModal
          isOpen={isUploadModalOpen}
          onClose={() => setIsUploadModalOpen(false)}
          onSuccess={loadProjectDetails}
          token={session.access_token}
          projectId={projectId}
          mode="pdf"
        />
      )}

      {/* Import References Modal (.bib / Zotero) */}
      {session?.access_token && projectId && (
        <UploadDocumentModal
          isOpen={isImportModalOpen}
          onClose={() => setIsImportModalOpen(false)}
          onSuccess={loadProjectDetails}
          token={session.access_token}
          projectId={projectId}
          mode="import"
        />
      )}

      {/* Upload Draft Modal */}
      {session?.access_token && projectId && (
        <UploadDraftModal
          isOpen={isUploadDraftModalOpen}
          onClose={() => setIsUploadDraftModalOpen(false)}
          onSuccess={() => {
            // Trigger draft panel refresh
            setDraftRefreshTrigger(prev => prev + 1)
          }}
          token={session.access_token}
          projectId={projectId}
        />
      )}

      {/* Delete Document Modal */}
      {session?.access_token && deleteDocument && (
        <DeleteDocumentModal
          isOpen={!!deleteDocument}
          onClose={() => setDeleteDocument(null)}
          onSuccess={loadProjectDetails}
          token={session.access_token}
          documentId={deleteDocument.id}
          documentTitle={deleteDocument.title}
        />
      )}

      {/* Global Search Modal */}
      <GlobalSearch
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
      />

    </PageContainer>
  )
}

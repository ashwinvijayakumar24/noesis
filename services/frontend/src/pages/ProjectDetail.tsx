import { useEffect, useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { motion, AnimatePresence } from 'framer-motion'
import { DocumentTextIcon, PencilIcon, CheckIcon, XMarkIcon, ArrowDownTrayIcon, PlusIcon, BookOpenIcon, InformationCircleIcon } from '@heroicons/react/24/outline'
import UploadDocumentModal from '../components/UploadDocumentModal'
import DeleteDocumentModal from '../components/DeleteDocumentModal'
import GlobalSearch from '../components/GlobalSearch'
import DraftsPanel from '../components/DraftsPanel'
import UploadDraftModal from '../components/UploadDraftModal'
import EmptyStateGuide from '../components/EmptyStateGuide'
import PageContainer from '../components/layout/PageContainer'
import { Button } from '../components/ui/Button'
import PaperCard from '../components/literature/PaperCard'
import type { PaperDocument } from '../components/literature/PaperCard'

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

type ProjectBundle = Project & {
  documents?: Document[]
}

type SourceFilter = 'all' | 'analyzed_pdf' | 'bibtex_import'
type SortBy = 'newest' | 'oldest' | 'status' | 'source'

type ActiveTab = 'literature' | 'drafts'

const formatProjectDate = (value: string) => new Date(value).toLocaleDateString('en-US', {
  month: 'short',
  day: 'numeric',
  year: 'numeric',
})

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

    const pollInterval = setInterval(() => {
      api.projects.getBundle(session.access_token, projectId).then(data => {
        const { documents: updatedDocs } = data as ProjectBundle
        setDocuments(updatedDocs || [])
      }).catch(error => {
        console.error('Polling error:', error)
      })
    }, 3000) // Poll every 3 seconds

    return () => {
      clearInterval(pollInterval)
    }
  }, [documents, session, projectId])

  const loadProjectDetails = async () => {
    if (!session?.access_token || !projectId) {
      return
    }

    try {
      setLoading(true)
      const data = await api.projects.getBundle(session.access_token, projectId) as ProjectBundle

      const { documents, ...projectData } = data
      setProject(projectData as Project)
      setDocuments(documents || [])
    } catch (error: unknown) {
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
      const data = await api.projects.getBundle(session.access_token, projectId) as ProjectBundle
      setDocuments(data.documents || [])
    } catch (error) {
      console.debug('Silent document refresh failed:', error)
    }
  }

  const loadDraftCount = async () => {
    if (!session?.access_token || !projectId) return

    try {
      const data = await api.drafts.list(session.access_token, projectId)
      setDraftCount(data?.drafts?.length || 0)
    } catch (error: unknown) {
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
    } catch (error: unknown) {
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
      const exportTitle = project?.title?.trim()
      a.download = exportTitle ? `${exportTitle.replace(/ /g, '_')}_citations.bib` : 'citations.bib'
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)

      toast.success(`BibTeX file downloaded (${documents.length} entries)`)
    } catch (error: unknown) {
      toast.dismiss()
      toast.error(error instanceof Error ? error.message : 'Failed to export BibTeX')
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

  const tabs = [
    {
      id: 'literature' as const,
      label: 'Literature',
      icon: <DocumentTextIcon className="h-4 w-4" />,
      count: documents.length,
    },
    {
      id: 'drafts' as const,
      label: 'Your Draft',
      icon: <PencilIcon className="h-4 w-4" />,
      count: undefined,
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
          <div className="mb-7 border-b border-border-default/70 pb-6">
            {isEditingProject ? (
              /* Edit Mode */
              <div className="rounded-xl border border-border-default bg-bg-surface/80 p-4">
                <div className="grid gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
                  <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.1em] text-text-secondary">Project Title</label>
                  <input
                    type="text"
                    value={editedTitle}
                    onChange={(e) => setEditedTitle(e.target.value)}
                    className="w-full rounded-lg border border-border-default bg-bg-void px-3 py-2.5 text-lg font-semibold text-text-primary outline-none transition-all duration-150 placeholder:text-text-muted focus:border-accent-primary focus:ring-1 focus:ring-accent-primary"
                    placeholder="Enter project title"
                  />
                </div>
                <div>
                  <label className="mb-1.5 block text-xs font-semibold uppercase tracking-[0.1em] text-text-secondary">Description <span className="font-mono text-[11px] normal-case tracking-normal text-text-secondary">(optional)</span></label>
                  <textarea
                    value={editedDescription}
                    onChange={(e) => setEditedDescription(e.target.value)}
                    className="min-h-[42px] w-full resize-none rounded-lg border border-border-default bg-bg-void px-3 py-2.5 text-sm text-text-primary outline-none transition-all duration-150 placeholder:text-text-muted focus:border-accent-primary focus:ring-1 focus:ring-accent-primary"
                    placeholder="Enter project description"
                    rows={2}
                  />
                </div>
                </div>
                <div className="mt-4 flex items-center gap-2">
                  <Button
                    onClick={handleSaveProject}
                    variant="primary"
                    size="sm"
                  >
                    <CheckIcon className="h-4 w-4" />
                    Save Changes
                  </Button>
                  <button
                    onClick={handleCancelEditProject}
                    className="inline-flex items-center gap-2 rounded-md border border-border-default px-3 py-2 text-sm font-semibold text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary active:translate-y-px"
                  >
                    <XMarkIcon className="h-4 w-4" />
                    Cancel
                  </button>
                </div>
              </div>
            ) : (
              /* View Mode */
              <div className="flex flex-col gap-5 sm:flex-row sm:items-start sm:justify-between">
                <div className="min-w-0">
                  <p className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-text-secondary">
                    Project
                  </p>
                  <h1 className="truncate text-3xl font-sans font-semibold leading-tight text-text-primary sm:text-4xl">
                    {project.title}
                  </h1>
                  <p className="mt-2 max-w-3xl text-sm leading-6 text-text-secondary">
                    {project.description || 'No description'}
                  </p>
                  <div className="mt-4 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs font-mono font-semibold text-text-secondary">
                    <span className="inline-flex items-center gap-1.5">
                      <DocumentTextIcon className="h-3.5 w-3.5" />
                      {documents.length} paper{documents.length === 1 ? '' : 's'}
                    </span>
                    <span className="inline-flex items-center gap-1.5">
                      <PencilIcon className="h-3.5 w-3.5" />
                      {draftCount > 0 ? 'Draft uploaded' : 'No draft'}
                    </span>
                    <span>Created {formatProjectDate(project.created_at)}</span>
                  </div>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={handleStartEditProject}
                    className="inline-flex items-center gap-2 rounded-md border border-border-default px-3 py-2 text-sm font-semibold text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary active:translate-y-px"
                    title="Edit project details"
                  >
                    <PencilIcon className="h-4 w-4" />
                    Edit
                  </button>
                </div>
              </div>
            )}
          </div>

          {/* Tabs Navigation */}
          <div className="mb-7 grid grid-cols-2 border-b border-border-default/70">
            {tabs.map(tab => {
              const isActive = activeTab === tab.id
              return (
                <button
                  key={tab.id}
                  onClick={() => setActiveTab(tab.id)}
                  className={`relative -mb-px inline-flex items-center justify-center gap-2 border-b px-4 py-3 text-sm font-semibold transition-colors duration-150 ${
                    isActive
                      ? 'border-accent-primary text-text-primary'
                      : 'border-transparent text-text-secondary hover:bg-bg-surface/40 hover:text-text-primary'
                  }`}
                >
                  <span className={isActive ? 'text-accent-primary' : 'text-text-secondary'}>
                    {tab.icon}
                  </span>
                  {tab.label}
                  {tab.count !== undefined && tab.count > 0 && (
                    <span className={`inline-flex h-5 min-w-5 items-center justify-center rounded-full px-1.5 text-[11px] font-bold tabular-nums ${
                      isActive ? 'bg-accent-primary/15 text-accent-primary' : 'bg-bg-elevated text-text-secondary'
                    }`}>
                      {tab.count}
                    </span>
                  )}
                </button>
              )
            })}
          </div>

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
                className="space-y-6"
              >
              {/* Literature Section — unified list */}
              <div>
                {/* Header */}
                <div className="mb-4 flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
                  <div>
                    <h2 className="text-xl font-sans font-semibold text-text-primary tracking-normal">Literature</h2>
                    <p className="mt-1 text-sm font-medium text-text-secondary">
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

                  <div className="flex flex-wrap items-center gap-2">
                    {/* Source filter pills + legend button */}
                    <div className="flex items-center gap-2">
                      <div className="flex items-center gap-0.5 rounded-lg border border-border-default bg-bg-surface/80 p-0.5">
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
                              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1 text-xs font-semibold transition-all duration-150 ${
                                isActive
                                  ? 'bg-bg-elevated text-text-primary ring-1 ring-inset ring-border-default'
                                  : 'text-text-secondary hover:bg-bg-hover hover:text-text-primary'
                              } ${isDisabled ? 'opacity-35 pointer-events-none' : 'cursor-pointer'}`}
                            >
                              {labels[filter]}
                              {filter !== 'all' && (
                                <span className={`text-[10px] tabular-nums ${isActive ? 'text-accent-primary' : 'text-text-secondary'}`}>
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
                          className="rounded-md border border-transparent p-1 text-text-secondary transition-colors duration-150 hover:border-border-default hover:bg-bg-hover hover:text-text-primary"
                          title="Status legend"
                        >
                          <InformationCircleIcon className="h-4 w-4" />
                        </button>

                        {showStatusLegend && (
                          <div className="absolute right-0 top-8 z-20 w-80 rounded-xl border border-border-default bg-bg-elevated p-3 shadow-xl">
                            <div className="mb-2 flex items-center justify-between">
                              <p className="text-xs font-bold uppercase tracking-[0.1em] text-text-secondary">Status Legend</p>
                              <button
                                onClick={() => setShowStatusLegend(false)}
                                className="rounded p-1 text-text-secondary transition-colors duration-150 hover:bg-bg-hover hover:text-text-primary"
                              >
                                <XMarkIcon className="h-3.5 w-3.5" />
                              </button>
                            </div>
                            <div className="space-y-2">
                              {[
                                {
                                  label: 'Processed',
                                  tone: 'text-emerald-300',
                                  copy: 'Full RAG analysis complete. This paper can be searched, cited, and used in draft analysis.',
                                },
                                {
                                  label: 'Analyzing',
                                  tone: 'text-amber-300',
                                  copy: 'Pipeline in progress for PDF extraction, embedding, or open-access PDF resolution.',
                                },
                                {
                                  label: 'Imported',
                                  tone: 'text-sky-300',
                                  copy: 'Metadata saved, but no open-access PDF was found. Upload the PDF manually for full analysis.',
                                },
                                {
                                  label: 'Failed',
                                  tone: 'text-red-300',
                                  copy: 'Document analysis failed. Try re-uploading or retrying the file.',
                                },
                              ].map(item => (
                                <div key={item.label} className="rounded-lg border border-border-default/70 bg-bg-surface/70 p-2.5">
                                  <span className={`text-xs font-semibold ${item.tone}`}>{item.label}</span>
                                  <p className="mt-0.5 text-xs leading-5 text-text-secondary">{item.copy}</p>
                                </div>
                              ))}
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
                        className="rounded-lg border border-border-default bg-bg-surface px-2.5 py-1.5 text-xs font-semibold text-text-secondary transition-colors focus:border-accent-primary focus:ring-1 focus:ring-accent-primary"
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
                        className="flex items-center gap-1.5 rounded-lg border border-border-default px-3 py-1.5 text-xs font-semibold text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary active:translate-y-px"
                      >
                        <ArrowDownTrayIcon className="h-3.5 w-3.5" />
                        Export .bib
                      </button>
                    )}

                    {/* Import References (.bib / Zotero) */}
                    <button
                      onClick={() => setIsImportModalOpen(true)}
                      className="flex items-center gap-1.5 rounded-lg border border-border-default px-3 py-1.5 text-xs font-semibold text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary active:translate-y-px"
                    >
                      <BookOpenIcon className="h-3.5 w-3.5" />
                      Import .bib
                    </button>

                    {/* Upload PDF — same height as Import .bib */}
                    <button
                      onClick={() => setIsUploadModalOpen(true)}
                      className="flex items-center gap-1.5 rounded-lg bg-accent-primary px-3 py-1.5 text-xs font-semibold text-white transition-all duration-150 hover:bg-accent-hover active:translate-y-px"
                    >
                      <PlusIcon className="h-3.5 w-3.5" />
                      Upload PDF
                    </button>
                  </div>
                </div>

                {/* Draft Warning Banner */}
                {draftCount > 0 && documents.length === 0 && !isDraftWarningDismissed && (
                  <div className="mb-5 rounded-xl border border-warning/35 bg-warning/10 p-3">
                    <div className="flex items-start gap-3">
                      <svg className="h-5 w-5 text-warning shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                      <div className="flex-1">
                        <p className="text-sm font-semibold text-warning">Add papers for citation suggestions</p>
                        <p className="mt-0.5 text-xs font-medium text-text-secondary">
                          Your draft has no papers yet. Citation suggestions require papers in your library.
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
                    <div className="overflow-hidden rounded-xl border border-border-default bg-bg-surface/80">
                      {filtered.map(doc => (
                        <PaperCard
                          key={doc.id}
                          document={doc as PaperDocument}
                          onDelete={(id, title) => setDeleteDocument({ id, title })}
                          token={session?.access_token}
                          onRefresh={silentRefreshDocuments}
                        />
                      ))}
                      {filtered.length === 0 && (
                        <p className="py-8 text-center text-sm font-medium text-text-secondary">
                          No papers match this filter.
                        </p>
                      )}
                    </div>
                  )
                })()}
              </div>
            </motion.div>
          )}

          {/* Your Draft Tab */}
          {activeTab === 'drafts' && session?.access_token && projectId && (
            <motion.div
              key="drafts"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <div className="mb-4 flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
                <div>
                  <h2 className="text-xl font-sans font-semibold text-text-primary tracking-normal">Your Draft</h2>
                  <p className="mt-1 text-sm font-medium text-text-secondary">
                    Analyze one manuscript against the literature in this project.
                  </p>
                </div>

                <Button
                  onClick={() => setIsUploadDraftModalOpen(true)}
                  variant="primary"
                  size="sm"
                >
                  <PlusIcon className="h-4 w-4" />
                  {draftCount > 0 ? 'Upload New Version' : 'Upload Draft'}
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
          hasExistingDraft={draftCount > 0}
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

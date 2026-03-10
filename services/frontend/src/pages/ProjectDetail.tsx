import { useEffect, useState, useRef, lazy, Suspense } from 'react'
import type { ReactNode } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { NoesisLogo } from '../components/ui/NoesisLogo'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { motion, AnimatePresence } from 'framer-motion'
import { DocumentTextIcon, PaperAirplaneIcon, TrashIcon as ClearIcon, PencilIcon, CheckIcon, XMarkIcon, ArrowsPointingOutIcon, ArrowsPointingInIcon, ArrowDownTrayIcon, PlusIcon, LightBulbIcon } from '@heroicons/react/24/outline'
import UploadDocumentModal from '../components/UploadDocumentModal'
import PaperDiscoveryModal from '../components/PaperDiscoveryModal'
import DeleteDocumentModal from '../components/DeleteDocumentModal'
import ChatMessage from '../components/ChatMessage'
import GlobalSearch from '../components/GlobalSearch'
import DraftsPanel from '../components/DraftsPanel'
import UploadDraftModal from '../components/UploadDraftModal'
import EmptyStateGuide from '../components/EmptyStateGuide'
import PageContainer from '../components/layout/PageContainer'
import { TabNavigation } from '../components/navigation/TabNavigation'
import { Button } from '../components/ui/Button'
import DocumentCard from '../components/literature/DocumentCard'

// Lazy load heavy components for better performance
const InsightsTab = lazy(() => import('../components/InsightsTab'))

interface TabItem {
  id: string
  label: string
  icon?: ReactNode
  badgeCount?: number
  badgeVariant?: 'neutral' | 'primary' | 'warning' | 'success'
  isProcessing?: boolean
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
  status: string
  created_at: string
}

interface ChatMessageType {
  id: string
  role: 'user' | 'assistant'
  content: string
  sources?: any[]
  created_at: string
}

type ActiveTab = 'literature' | 'insights' | 'drafts'

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
  const [isPaperDiscoveryModalOpen, setIsPaperDiscoveryModalOpen] = useState(false)
  const [deleteDocument, setDeleteDocument] = useState<{ id: string; title: string } | null>(null)

  // Draft modals
  const [isUploadDraftModalOpen, setIsUploadDraftModalOpen] = useState(false)
  const [draftRefreshTrigger, setDraftRefreshTrigger] = useState(0)
  const [draftCount, setDraftCount] = useState(0)

  // Banner dismissal state (persisted in localStorage)
  const [isDraftWarningDismissed, setIsDraftWarningDismissed] = useState(() => {
    if (!projectId) return false
    return localStorage.getItem(`noesis_draft_warning_dismissed_${projectId}`) === 'true'
  })

  // Chat state
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingMessage, setStreamingMessage] = useState('')
  const [streamingSources, setStreamingSources] = useState<any[]>([])
  const [isFullScreen, setIsFullScreen] = useState(false)
  const [includeDrafts, setIncludeDrafts] = useState(true)  // draft-aware chat always on by default
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)

  // Search state
  const [isSearchOpen, setIsSearchOpen] = useState(false)

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
      loadChatHistory()
      loadDraftCount()
    }
  }, [projectId])

  // Reload draft count when drafts are uploaded/deleted
  useEffect(() => {
    if (session?.access_token && projectId && draftRefreshTrigger > 0) {
      loadDraftCount()
    }
  }, [draftRefreshTrigger])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && isFullScreen) {
        setIsFullScreen(false)
        return
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [isFullScreen])

  // Update document title when project loads
  useEffect(() => {
    if (project?.title) {
      document.title = `${project.title} | Noesis`
    } else {
      document.title = 'Project | Noesis'
    }
  }, [project])

  // Auto-scroll to bottom when new messages arrive
  useEffect(() => {
    scrollToBottom()
  }, [messages, streamingMessage])

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }

  // Poll for status updates every 3 seconds if there are processing documents
  useEffect(() => {
    if (!session?.access_token || !projectId) return

    const hasProcessingDocs = documents.some(
      (doc) => doc.status.toLowerCase() === 'processing' ||
               doc.status.toLowerCase() === 'uploaded' ||
               doc.status.toLowerCase() === 'ready' ||
               doc.status.toLowerCase() === 'analyzing'
    )

    if (!hasProcessingDocs) return

    const pollInterval = setInterval(() => {
      // Silent reload - fetch updated documents without loading state
      api.projects.getBundle(session.access_token, projectId).then(data => {
        const { documents: updatedDocs } = data
        setDocuments(updatedDocs || [])
      }).catch(error => {
        console.error('Polling error:', error)
      })
    }, 2000) // Poll every 2 seconds for faster UI updates

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
          toast.success('✓ Insights updated with latest documents', { duration: 4000 })
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

  const loadChatHistory = async () => {
    if (!session?.access_token || !projectId) return

    try {
      const response = await api.chat.getHistory(session.access_token, projectId)
      // Backend returns {data: [...], pagination: {...}}
      // Extract the messages array from the data property
      const messagesArray = Array.isArray(response) ? response : (response?.data || [])
      setMessages(messagesArray)
    } catch (error: any) {
      console.error('Failed to load chat history:', error)
      // Set empty array on error to prevent map errors
      setMessages([])
    }
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

  const handleSendMessage = async () => {
    if (!input.trim() || !session?.access_token || !projectId || isStreaming) return

    const userMessage = input.trim()
    setInput('')

    const tempUserMessage: ChatMessageType = {
      id: Date.now().toString(),
      role: 'user',
      content: userMessage,
      created_at: new Date().toISOString(),
    }
    setMessages((prev) => [...prev, tempUserMessage])

    setIsStreaming(true)
    setStreamingMessage('')
    setStreamingSources([])

    try {
      const params = new URLSearchParams({
        query: userMessage,
        model: 'gpt-5.2-chat-latest',
        max_chunks: '5',
        include_drafts: includeDrafts.toString(),  // NEW: include drafts in search
      })

      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/chat/projects/${projectId}/query-stream?${params}`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!response.ok) {
        if (response.status === 429) {
          const parsed = await response.json().catch(() => null)
          const detail = parsed?.detail
          if (detail?.error === 'quota_exceeded') {
            const isDaily = detail.quota_type === 'daily_chat'
            toast.error(isDaily
              ? `Daily chat limit reached (${detail.limit} messages/day). Resets tomorrow.`
              : `Monthly chat limit reached. Upgrade to Pro for more.`
            )
            setIsStreaming(false)
            return
          }
        }
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      const decoder = new TextDecoder()

      if (!reader) {
        throw new Error('No reader available')
      }

      let buffer = ''
      while (true) {
        const { done, value } = await reader.read()

        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (!line.trim()) continue

          try {
            const data = JSON.parse(line)

            if (data.type === 'sources') {
              setStreamingSources(data.data)
            } else if (data.type === 'token') {
              setStreamingMessage((prev) => prev + data.data)
            } else if (data.type === 'done') {
              const assistantMessage: ChatMessageType = {
                id: (Date.now() + 1).toString(),
                role: 'assistant',
                content: data.data,
                sources: data.sources || streamingSources,
                created_at: new Date().toISOString(),
              }
              setMessages((prev) => [...prev, assistantMessage])
              setStreamingMessage('')
              setStreamingSources([])
              setIsStreaming(false)
            } else if (data.type === 'error') {
              toast.error(data.data || 'Failed to get response')
              setIsStreaming(false)
              setStreamingMessage('')
            }
          } catch (e) {
            console.error('Failed to parse line:', line, e)
          }
        }
      }
    } catch (error: any) {
      console.error('Streaming error:', error)
      toast.error('Failed to get response')
      setIsStreaming(false)
      setStreamingMessage('')
    }
  }

  const handleClearChat = async () => {
    if (!session?.access_token || !projectId) return

    if (!confirm('Are you sure you want to clear all chat messages?')) return

    try {
      await api.chat.clearHistory(session.access_token, projectId)
      setMessages([])
      toast.success('Chat history cleared')
    } catch (error: any) {
      console.error('Failed to clear chat:', error)
      toast.error('Failed to clear chat history')
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

  // Prepare tabs for TabNavigation component
  const tabs: TabItem[] = [
    {
      id: 'literature',
      label: 'Literature',
      icon: <DocumentTextIcon className="h-6 w-6 text-orange-400" />,
      badgeCount: documents.length > 0 ? documents.length : undefined,
      badgeVariant: 'neutral',
    },
    {
      id: 'insights',
      label: 'Insights',
      icon: <LightBulbIcon className="h-6 w-6 text-warning" />,
      isProcessing: insightsStatus === 'analyzing',
    },
    {
      id: 'drafts',
      label: 'Your Drafts',
      icon: (
        <svg className="h-6 w-6 text-accent-purple" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
        </svg>
      ),
      badgeCount: draftCount > 0 ? draftCount : undefined,
      badgeVariant: 'primary',
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
      onSearchOpen={() => setIsSearchOpen(true)}
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
              {/* Documents Section */}
              <div>
                <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-6">
                  <div>
                    <h3 className="text-2xl font-sans font-semibold text-text-primary tracking-normal">Research Papers</h3>
                    <p className="text-sm text-text-secondary mt-1">
                      Upload and analyze your literature collection
                    </p>
                  </div>

                  <div className="flex gap-2">
                    {/* Export BibTeX button */}
                    {documents.length > 0 && (
                      <button
                        onClick={handleExportBibTeX}
                        className="px-4 py-2 bg-bg-bg-surfaceborder-2 border-border-default text-text-primary font-semibold rounded-lg hover:bg-bg-elevated hover:border-accent-teal transition-all duration-150 flex items-center gap-2 group"
                      >
                        <ArrowDownTrayIcon className="h-4 w-4 group-hover:text-accent-teal transition-colors" />
                        <span>Export BibTeX</span>
                      </button>
                    )}

                    {/* Upload Document button */}
                    <Button
                      onClick={() => setIsUploadModalOpen(true)}
                      variant="primary"
                    >
                      <PlusIcon className="h-4 w-4" />
                      Upload Paper
                    </Button>

                    {/* Discover Papers — temporarily disabled, pending worktree implementation */}
                  </div>
                </div>

                {/* Draft Warning Banner - shown when draft uploaded without documents */}
                {draftCount > 0 && documents.length === 0 && !isDraftWarningDismissed && (
                  <div className="mb-6 bg-warning/10 border-2 border-warning/50 rounded-lg p-5">
                    <div className="flex items-start gap-3">
                      <div className="flex-shrink-0 mt-0.5">
                        <svg className="h-6 w-6 text-warning" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                        </svg>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-sm font-sans font-semibold text-warning mb-1">
                          Upload research papers to get citation suggestions
                        </h4>
                        <p className="text-sm text-text-secondary mb-3 leading-relaxed">
                          You have {draftCount} draft{draftCount > 1 ? 's' : ''} uploaded, but no research papers yet. Citation suggestions and coverage gap analysis require papers in your library.
                        </p>
                        <div className="flex items-center gap-3">
                          <button
                            onClick={() => setIsUploadModalOpen(true)}
                            className="text-sm font-semibold text-accent-primary hover:text-accent-primary-bright underline transition-colors"
                          >
                            Upload Research Papers
                          </button>
                          <button
                            onClick={handleDismissDraftWarning}
                            className="text-sm text-text-tertiary hover:text-text-primary transition-colors"
                          >
                            Dismiss
                          </button>
                        </div>
                      </div>
                      <button
                        onClick={handleDismissDraftWarning}
                        className="flex-shrink-0 text-text-tertiary hover:text-warning transition-colors"
                        aria-label="Dismiss warning"
                      >
                        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                        </svg>
                      </button>
                    </div>
                  </div>
                )}

              {/* Empty State */}
              {documents.length === 0 && (
                <EmptyStateGuide onUploadClick={() => setIsUploadModalOpen(true)} />
              )}

                {/* Documents List */}
                {documents.length > 0 && (
                  <motion.div
                    className="grid grid-cols-1 lg:grid-cols-2 gap-6"
                    initial="hidden"
                    whileInView="visible"
                    viewport={{ once: true, margin: "-100px" }}
                    variants={{
                      hidden: { opacity: 0 },
                      visible: {
                        opacity: 1,
                        transition: {
                          staggerChildren: 0.1
                        }
                      }
                    }}
                  >
                    {documents.map((doc) => (
                      <motion.div
                        key={doc.id}
                        variants={{
                          hidden: { opacity: 0, y: 20 },
                          visible: {
                            opacity: 1,
                            y: 0,
                            transition: {
                              duration: 0.5,
                              ease: [0.16, 1, 0.3, 1]
                            }
                          }
                        }}
                      >
                        <DocumentCard
                          document={doc}
                          projectId={projectId!}
                          onDelete={(id, title) => setDeleteDocument({ id, title })}
                        />
                      </motion.div>
                    ))}
                  </motion.div>
                )}
              </div>
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

        {/* Chat Tab - Disabled (use Research Assistant Panel instead) */}
        {/* {activeTab === 'chat' && !isFullScreen && (*/}
        {false && (
          <div className="flex flex-col h-[calc(100vh-280px)] min-h-125">
          {/* Chat Header */}
          <div className="bg-bg-surfaceborder border-border-default rounded-t-lg px-4 py-3 flex justify-between items-center">
            <div className="flex items-center gap-4 text-sm font-mono text-text-secondary">
              <div className="flex items-center gap-2">
                <DocumentTextIcon className="h-4 w-4" />
                <span>{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
              </div>
              {/* Draft-aware toggle */}
              <label className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={includeDrafts}
                  onChange={(e) => setIncludeDrafts(e.target.checked)}
                  className="w-4 h-4 rounded border-border-default bg-bg-surface text-accent-primary focus:ring-accent-primary focus:ring-offset-0"
                />
                <span className="text-xs">Include drafts 📄</span>
              </label>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setIsFullScreen(true)}
                className="text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2"
                title="Full screen mode"
              >
                <ArrowsPointingOutIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Expand</span>
              </button>
              {messages.length > 0 && (
                <button
                  onClick={handleClearChat}
                  className="text-sm text-text-secondary hover:text-red-400 transition-colors flex items-center gap-2"
                >
                  <ClearIcon className="h-4 w-4" />
                  Clear
                </button>
              )}
            </div>
          </div>

          {/* Messages Container */}
          <div
            ref={chatContainerRef}
            className="flex-1 overflow-y-auto bg-bg-surface border-x border-border-default"
          >
            <div className="max-w-3xl mx-auto px-4 py-8">
              {messages.length === 0 && !isStreaming && (
                <div className="flex items-center justify-center min-h-100">
                  <div className="text-center max-w-md">
                    <div className="h-16 w-16 mx-auto mb-4 rounded-full bg-accent-primary/10 flex items-center justify-center">
                      <svg className="h-8 w-8 text-accent-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                      </svg>
                    </div>
                    <h4 className="text-xl font-sans font-semibold text-text-primary mb-2">
                      How can I help you today?
                    </h4>
                    <p className="text-text-secondary text-sm">
                      Ask questions about your documents and get AI-powered answers with citations
                    </p>
                  </div>
                </div>
              )}

              <div className="space-y-8">
                {Array.isArray(messages) && messages.map((message) => (
                  <ChatMessage
                    key={message.id}
                    role={message.role}
                    content={message.content}
                    sources={message.sources}
                  />
                ))}

                {isStreaming && streamingMessage && (
                  <ChatMessage
                    role="assistant"
                    content={streamingMessage}
                    sources={streamingSources}
                    isStreaming={true}
                  />
                )}
              </div>

              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Container */}
          <div className="bg-bg-surfaceborder border-border-default rounded-b-lg">
            <div className="max-w-3xl mx-auto px-4 py-4">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  handleSendMessage()
                }}
                className="relative"
              >
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask anything about your documents..."
                  disabled={isStreaming}
                  className="w-full px-4 py-4 pr-24 bg-bg-surface border border-border-default rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors disabled:opacity-50"
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isStreaming}
                  className="absolute right-2 top-1/2 -translate-y-1/2 px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {isStreaming ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                    </>
                  ) : (
                    <PaperAirplaneIcon className="h-5 w-5" />
                  )}
                </button>
              </form>
            </div>
          </div>
          </div>
        )}

          {/* Insights Tab - Unified view with all insights + compass features */}
          {activeTab === 'insights' && projectId && (
            <motion.div
              key="insights"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
            >
              <Suspense fallback={<ComponentLoader />}>
                <InsightsTab projectId={projectId} />
              </Suspense>
            </motion.div>
          )}
          </AnimatePresence>
        </>
      )}

      {/* Full Screen Chat Mode */}
      {isFullScreen && (
        <div className="fixed inset-0 z-50 bg-bg-surface flex flex-col">
          {/* Full Screen Header */}
          <div className="bg-bg-surfaceborder-b border-border-default">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex justify-between items-center h-16">
                <div className="flex items-center gap-3">
                  <NoesisLogo size="sm" />
                  <div className="h-6 w-px bg-border-subtle"></div>
                  <div className="flex items-center gap-4 text-sm font-mono text-text-secondary">
                    <div className="flex items-center gap-2">
                      <DocumentTextIcon className="h-4 w-4" />
                      <span>{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
                    </div>
                    {/* Draft-aware toggle */}
                    <label className="flex items-center gap-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={includeDrafts}
                        onChange={(e) => setIncludeDrafts(e.target.checked)}
                        className="w-4 h-4 rounded border-border-default bg-bg-surface text-accent-primary focus:ring-accent-primary focus:ring-offset-0"
                      />
                      <span className="text-xs">Include drafts 📄</span>
                    </label>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {messages.length > 0 && (
                    <button
                      onClick={handleClearChat}
                      className="text-sm text-text-secondary hover:text-red-400 transition-colors flex items-center gap-2"
                    >
                      <ClearIcon className="h-4 w-4" />
                      <span className="hidden sm:inline">Clear</span>
                    </button>
                  )}
                  <button
                    onClick={() => setIsFullScreen(false)}
                    className="text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2 px-3 py-1.5 border border-border-default rounded-lg hover:bg-bg-hover"
                    title="Exit full screen"
                  >
                    <ArrowsPointingInIcon className="h-4 w-4" />
                    <span className="hidden sm:inline">Exit Full Screen</span>
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Messages Container */}
          <div
            ref={chatContainerRef}
            className="flex-1 overflow-y-auto bg-bg-surface"
          >
            <div className="max-w-4xl mx-auto px-4 py-8">
              {messages.length === 0 && !isStreaming && (
                <div className="flex items-center justify-center min-h-125">
                  <div className="text-center max-w-md">
                    <div className="h-20 w-20 mx-auto mb-6 rounded-full bg-accent-primary/10 flex items-center justify-center">
                      <svg className="h-10 w-10 text-accent-primary" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                      </svg>
                    </div>
                    <h4 className="text-2xl font-sans font-semibold text-text-primary mb-3">
                      How can I help you today?
                    </h4>
                    <p className="text-text-secondary">
                      Ask questions about your documents and get AI-powered answers with citations
                    </p>
                  </div>
                </div>
              )}

              <div className="space-y-8">
                {Array.isArray(messages) && messages.map((message) => (
                  <ChatMessage
                    key={message.id}
                    role={message.role}
                    content={message.content}
                    sources={message.sources}
                  />
                ))}

                {isStreaming && streamingMessage && (
                  <ChatMessage
                    role="assistant"
                    content={streamingMessage}
                    sources={streamingSources}
                    isStreaming={true}
                  />
                )}
              </div>

              <div ref={messagesEndRef} />
            </div>
          </div>

          {/* Input Container */}
          <div className="bg-bg-surfaceborder-t border-border-default">
            <div className="max-w-4xl mx-auto px-4 py-6">
              <form
                onSubmit={(e) => {
                  e.preventDefault()
                  handleSendMessage()
                }}
                className="relative"
              >
                <input
                  type="text"
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  placeholder="Ask anything about your documents..."
                  disabled={isStreaming}
                  className="w-full px-5 py-4 pr-28 bg-bg-surface border border-border-default rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors disabled:opacity-50 text-base"
                  autoFocus
                />
                <button
                  type="submit"
                  disabled={!input.trim() || isStreaming}
                  className="absolute right-2 top-1/2 -translate-y-1/2 px-5 py-2.5 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                >
                  {isStreaming ? (
                    <>
                      <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                    </>
                  ) : (
                    <PaperAirplaneIcon className="h-5 w-5" />
                  )}
                </button>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* Upload Document Modal */}
      {session?.access_token && projectId && (
        <UploadDocumentModal
          isOpen={isUploadModalOpen}
          onClose={() => setIsUploadModalOpen(false)}
          onSuccess={loadProjectDetails}
          token={session.access_token}
          projectId={projectId}
        />
      )}

      {/* Paper Discovery Modal */}
      {session?.access_token && projectId && (
        <PaperDiscoveryModal
          isOpen={isPaperDiscoveryModalOpen}
          onClose={() => setIsPaperDiscoveryModalOpen(false)}
          projectId={projectId}
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

      {/* Research Assistant Panel — temporarily hidden until chat is production-ready */}
      {/* {session?.access_token && projectId && !isFullScreen && (
        <ResearchAssistantPanel
          projectId={projectId}
          token={session.access_token}
          currentTab={activeTab}
          chatMessages={messages}
          chatInput={input}
          setChatInput={setInput}
          sendMessage={handleSendMessage}
          isLoading={isStreaming}
          clearChat={handleClearChat}
        />
      )} */}
    </PageContainer>
  )
}

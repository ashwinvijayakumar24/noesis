import { useEffect, useState, useRef, lazy, Suspense } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { ArrowLeftIcon, DocumentTextIcon, TrashIcon, PaperAirplaneIcon, TrashIcon as ClearIcon, MagnifyingGlassIcon, PencilIcon, CheckIcon, XMarkIcon, ArrowsPointingOutIcon, ArrowsPointingInIcon, ArrowDownTrayIcon } from '@heroicons/react/24/outline'
import UploadDocumentModal from '../components/UploadDocumentModal'
import DeleteDocumentModal from '../components/DeleteDocumentModal'
import ChatMessage from '../components/ChatMessage'
import GlobalSearch from '../components/GlobalSearch'
import DraftsPanel from '../components/DraftsPanel'
import UploadDraftModal from '../components/UploadDraftModal'
import EmptyStateGuide from '../components/EmptyStateGuide'
import ResearchAssistantPanel from '../components/ResearchAssistantPanel'
import { Badge, type BadgeVariant } from '../components/ui/Badge'

// Lazy load heavy components for better performance
const InsightsTab = lazy(() => import('../components/InsightsTab'))
const CitationNetwork = lazy(() => import('../components/CitationNetwork'))

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

type Tab = 'literature' | 'insights' | 'drafts'

// Loading component for lazy-loaded sections
function ComponentLoader() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-solid border-accent-primary border-r-transparent"></div>
    </div>
  )
}

// Helper function to get status badge variant and label
const getStatusBadge = (status: string): { variant: BadgeVariant; label: string; animate: boolean } => {
  const statusLower = status.toLowerCase()
  switch (statusLower) {
    case 'processing':
    case 'uploaded':
      return { variant: 'warning', label: 'Processing', animate: true }
    case 'analyzing':
      return { variant: 'warning', label: 'Analyzing', animate: true }
    case 'failed':
      return { variant: 'error', label: 'Failed', animate: false }
    case 'analyzed':
      return { variant: 'success', label: 'Processed', animate: false }
    default:
      // Capitalize first letter for any other status
      return { variant: 'neutral', label: status.charAt(0).toUpperCase() + status.slice(1).toLowerCase(), animate: false }
  }
}

// Helper function to get colored left border based on status
const getDocumentBorderColor = (status: string): string => {
  const statusLower = status.toLowerCase()
  switch (statusLower) {
    case 'ready':
      return 'border-l-4 border-l-slate-600'
    case 'processing':
    case 'uploaded':
    case 'analyzing':
      return 'border-l-4 border-l-amber-700'
    case 'failed':
      return 'border-l-4 border-l-red-600'
    case 'analyzed':
      return 'border-l-4 border-l-emerald-600'
    default:
      return 'border-l-4 border-l-slate-500'
  }
}

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { user, session, signOut } = useAuthStore()
  const [project, setProject] = useState<Project | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('literature')

  // Document modals
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
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
  const [includeDrafts, setIncludeDrafts] = useState(false)  // NEW: draft-aware chat toggle
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)

  // Search state
  const [isSearchOpen, setIsSearchOpen] = useState(false)

  // Insights state (used by Compass and Insights tabs)
  const [insights, setInsights] = useState<any | null>(null)
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
    }
  }, [projectId])

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
        model: 'gpt-4o',
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
            'Authorization': `Bearer ${session.access_token}`
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
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
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

  return (
    <div className="min-h-screen bg-bg-base">
      {/* Header */}
      <header className="bg-surface border-b border-border-base">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <img src="/noesis.png" alt="Noesis" className="h-10" />
              <span className="text-lg font-serif font-semibold text-text-primary">Noesis</span>
            </div>
            <div className="flex items-center gap-2 sm:gap-4">
              <button
                onClick={() => setIsSearchOpen(true)}
                className="flex items-center gap-2 px-2 sm:px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary bg-surface-hover hover:bg-surface-active rounded-lg border border-border-subtle transition-colors group"
              >
                <MagnifyingGlassIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Search</span>
              </button>
              <span className="text-sm text-text-secondary hidden md:inline font-mono">{user?.email}</span>
              <button
                onClick={() => signOut()}
                className="text-sm text-text-secondary hover:text-text-primary font-medium transition-colors"
              >
                Sign out
              </button>
            </div>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Back Button */}
        <Link
          to="/projects"
          className="inline-flex items-center gap-2 text-text-secondary hover:text-text-primary mb-6 transition-colors"
        >
          <ArrowLeftIcon className="h-5 w-5" />
          Back to Projects
        </Link>

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
        <div className="bg-surface rounded-lg border border-border-base p-6 mb-8">
          {isEditingProject ? (
            /* Edit Mode */
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">Project Title</label>
                <input
                  type="text"
                  value={editedTitle}
                  onChange={(e) => setEditedTitle(e.target.value)}
                  className="w-full px-4 py-3 bg-bg-base border border-border-subtle rounded-lg text-text-primary text-2xl font-serif font-bold focus:ring-2 focus:ring-accent-primary focus:border-transparent"
                  placeholder="Enter project title"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-text-secondary mb-2">Description <span className="text-text-muted font-mono text-xs">(optional)</span></label>
                <textarea
                  value={editedDescription}
                  onChange={(e) => setEditedDescription(e.target.value)}
                  className="w-full px-4 py-3 bg-bg-base border border-border-subtle rounded-lg text-text-primary focus:ring-2 focus:ring-accent-primary focus:border-transparent"
                  placeholder="Enter project description"
                  rows={3}
                />
              </div>
              <div className="flex items-center gap-3">
                <button
                  onClick={handleSaveProject}
                  className="flex items-center gap-2 px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
                >
                  <CheckIcon className="h-4 w-4" />
                  Save Changes
                </button>
                <button
                  onClick={handleCancelEditProject}
                  className="flex items-center gap-2 px-4 py-2 text-text-secondary hover:text-text-primary border border-border-subtle rounded-lg hover:bg-surface-hover transition-colors"
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
                <h2 className="text-3xl font-serif font-bold text-text-primary">
                  {project.title}
                </h2>
                <button
                  onClick={handleStartEditProject}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm text-text-secondary hover:text-text-primary border border-border-subtle rounded-lg hover:bg-surface-hover transition-colors"
                  title="Edit project details"
                >
                  <PencilIcon className="h-4 w-4" />
                  Edit
                </button>
              </div>
              <p className="text-text-secondary mb-4">
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
        <div className="mb-6">
          <div className="flex justify-center gap-4 border-b border-border-base overflow-x-auto scrollbar-hide">
            {/* Tab 1: Literature */}
            <button
              onClick={() => setActiveTab('literature')}
              className={`px-6 sm:px-8 py-4 text-base font-medium transition-colors border-b-2 whitespace-nowrap ${
                activeTab === 'literature'
                  ? 'border-accent-primary text-text-primary'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <div className="flex items-center gap-3">
                <DocumentTextIcon className="h-6 w-6 text-orange-400" />
                <span>Literature</span>
                {documents.length > 0 && (
                  <span className="ml-1 px-2 py-0.5 text-xs bg-surface-hover rounded-full font-mono">
                    {documents.length}
                  </span>
                )}
              </div>
            </button>

            {/* Tab 2: Insights */}
            <button
              onClick={() => setActiveTab('insights')}
              className={`px-6 sm:px-8 py-4 text-base font-medium transition-colors border-b-2 whitespace-nowrap ${
                activeTab === 'insights'
                  ? 'border-accent-primary text-text-primary'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <div className="flex items-center gap-3">
                <svg className="h-6 w-6 text-yellow-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                <span>Insights</span>
                {insightsStatus === 'analyzing' && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-slate-700/50 text-slate-300 border border-slate-600/50">
                    <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                    </svg>
                    Updating
                  </span>
                )}
              </div>
            </button>

            {/* Tab 3: Your Drafts (STAR FEATURE) */}
            <button
              onClick={() => setActiveTab('drafts')}
              className={`px-6 sm:px-8 py-4 text-base font-medium transition-colors border-b-2 whitespace-nowrap ${
                activeTab === 'drafts'
                  ? 'border-accent-primary text-text-primary'
                  : 'border-transparent text-text-secondary hover:text-text-primary'
              }`}
            >
              <div className="flex items-center gap-3">
                <svg className="h-6 w-6 text-purple-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M11 5H6a2 2 0 00-2 2v11a2 2 0 002 2h11a2 2 0 002-2v-5m-1.414-9.414a2 2 0 112.828 2.828L11.828 15H9v-2.828l8.586-8.586z" />
                </svg>
                <span>Your Drafts</span>
                {draftCount > 0 && (
                  <span className="ml-1 px-2 py-0.5 text-xs bg-purple-900/50 text-purple-300 rounded-full font-mono border border-purple-700/50">
                    {draftCount}
                  </span>
                )}
              </div>
            </button>
          </div>
        </div>

        {/* Literature Tab - Documents + Citation Network */}
        {activeTab === 'literature' && (
          <div className="mb-8 space-y-8">
            {/* Documents Section */}
            <div>
              <div className="flex justify-between items-center mb-4">
                <h3 className="text-xl font-serif font-semibold text-text-primary">Research Papers</h3>

                <div className="flex gap-2">
                  {/* Export BibTeX button */}
                  {documents.length > 0 && (
                    <button
                      onClick={handleExportBibTeX}
                      className="px-4 py-2 bg-slate-700 border border-slate-600 text-slate-200 font-semibold rounded-lg hover:bg-slate-600 hover:border-slate-500 transition-colors flex items-center gap-2"
                    >
                      <ArrowDownTrayIcon className="h-4 w-4" />
                      <span>Export BibTeX</span>
                    </button>
                  )}

                  {/* Upload Document button */}
                  <button
                    onClick={() => setIsUploadModalOpen(true)}
                    className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2"
                  >
                    <span>Upload Paper</span>
                  </button>
                </div>
              </div>

              {/* Draft Warning Banner - shown when draft uploaded without documents */}
              {draftCount > 0 && documents.length === 0 && !isDraftWarningDismissed && (
                <div className="mb-6 bg-amber-50 dark:bg-amber-900/20 border-2 border-amber-400 dark:border-amber-600 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <div className="flex-shrink-0 mt-0.5">
                      <svg className="h-6 w-6 text-amber-600 dark:text-amber-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                      </svg>
                    </div>
                    <div className="flex-1">
                      <h4 className="text-sm font-semibold text-amber-900 dark:text-amber-200 mb-1">
                        Upload research papers to get citation suggestions
                      </h4>
                      <p className="text-sm text-amber-800 dark:text-amber-300 mb-3">
                        You have {draftCount} draft{draftCount > 1 ? 's' : ''} uploaded, but no research papers yet. Citation suggestions and coverage gap analysis require papers in your library.
                      </p>
                      <div className="flex items-center gap-3">
                        <button
                          onClick={() => setIsUploadModalOpen(true)}
                          className="text-sm font-semibold text-amber-900 dark:text-amber-200 hover:text-amber-700 dark:hover:text-amber-100 underline"
                        >
                          Upload Research Papers
                        </button>
                        <button
                          onClick={handleDismissDraftWarning}
                          className="text-sm text-amber-700 dark:text-amber-400 hover:text-amber-900 dark:hover:text-amber-200"
                        >
                          Dismiss
                        </button>
                      </div>
                    </div>
                    <button
                      onClick={handleDismissDraftWarning}
                      className="flex-shrink-0 text-amber-600 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-200"
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
                <div className="space-y-3">
                  {documents.map((doc) => {
                    const statusBadge = getStatusBadge(doc.status)
                    const borderColor = getDocumentBorderColor(doc.status)
                    const isAnalyzed = doc.status.toLowerCase() === 'analyzed'
                    return (
                      <div
                        key={doc.id}
                        onClick={isAnalyzed ? () => navigate(`/projects/${projectId}/documents/${doc.id}`) : undefined}
                        className={`bg-surface rounded-lg border border-border-base p-5 transition-all group ${
                          isAnalyzed
                            ? 'hover:border-border-subtle hover:shadow-lg hover:shadow-red-600/20 cursor-pointer'
                            : 'cursor-default'
                        } ${borderColor}`}
                      >
                        <div className="flex items-start gap-4">
                          {/* PDF Icon */}
                          <div className="shrink-0">
                            <div className={`h-12 w-12 bg-surface-hover rounded-lg flex items-center justify-center border-2 ${
                              doc.status.toLowerCase() === 'failed' ? 'border-red-500/60' :
                              doc.status.toLowerCase() === 'processing' || doc.status.toLowerCase() === 'uploaded' ? 'border-amber-500/60' :
                              doc.status.toLowerCase() === 'ready' ? 'border-slate-500/60' :
                              'border-blue-500/60'
                            }`}>
                              <DocumentTextIcon className={`h-7 w-7 ${
                                doc.status.toLowerCase() === 'failed' ? 'text-red-400' :
                                doc.status.toLowerCase() === 'processing' || doc.status.toLowerCase() === 'uploaded' ? 'text-amber-400' :
                                doc.status.toLowerCase() === 'ready' ? 'text-slate-400' :
                                'text-blue-400'
                              }`} />
                            </div>
                          </div>

                          {/* Document Info */}
                          <div className="flex-1 min-w-0">
                            <div className="flex items-start justify-between gap-3">
                              <div className="flex-1 min-w-0">
                                <h4 className="font-serif font-semibold text-text-primary mb-1 truncate">
                                  {doc.title}
                                </h4>
                                <div className="flex items-center gap-3 text-sm font-mono text-text-muted">
                                  <span className="flex items-center gap-1">
                                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                                    </svg>
                                    {new Date(doc.created_at).toLocaleDateString('en-US', {
                                      year: 'numeric',
                                      month: 'short',
                                      day: 'numeric',
                                    })}
                                  </span>
                                </div>
                              </div>

                              {/* Status Badge & Delete Button */}
                              <div className="flex items-center gap-2">
                                {/* Status Badge */}
                                <Badge variant={statusBadge.variant}>
                                  {statusBadge.animate && (
                                    <span className="relative flex h-2 w-2">
                                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-700 opacity-75"></span>
                                      <span className="relative inline-flex rounded-full h-2 w-2 bg-amber-600"></span>
                                    </span>
                                  )}
                                  {statusBadge.label}
                                </Badge>

                                {/* Delete Button */}
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation()
                                    setDeleteDocument({ id: doc.id, title: doc.title })
                                  }}
                                  className="p-2 text-text-muted hover:text-red-400 hover:bg-red-950/30 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
                                  title="Delete document"
                                >
                                  <TrashIcon className="h-5 w-5" />
                                </button>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>

            {/* Citation Network Section - Collapsible */}
            {documents.length >= 2 && (
              <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
                <details className="group">
                  <summary className="flex items-center justify-between p-4 cursor-pointer hover:bg-surface-hover transition-colors">
                    <div className="flex items-center gap-3">
                      <div className="p-2 bg-slate-700/50 rounded-lg border-2 border-cyan-500/60">
                        <svg className="h-5 w-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                        </svg>
                      </div>
                      <div>
                        <h4 className="font-medium text-text-primary">Citation Network</h4>
                        <p className="text-sm text-text-muted">Interactive visualization of paper relationships</p>
                      </div>
                    </div>
                    <svg className="h-5 w-5 text-text-muted group-open:rotate-180 transition-transform" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                    </svg>
                  </summary>
                  <div className="border-t border-border-base p-4">
                    <Suspense fallback={<ComponentLoader />}>
                      <CitationNetwork projectId={projectId!} />
                    </Suspense>
                  </div>
                </details>
              </div>
            )}
          </div>
        )}

        {/* Drafts Tab */}
        {activeTab === 'drafts' && session?.access_token && projectId && (
          <div className="mb-8">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-serif font-semibold text-text-primary">Research Drafts</h3>

              <div className="flex gap-2">
                {/* Upload Draft button */}
                <button
                  onClick={() => setIsUploadDraftModalOpen(true)}
                  className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2"
                >
                  <span>Upload Draft</span>
                </button>
              </div>
            </div>
            <DraftsPanel
              token={session.access_token}
              projectId={projectId}
              refreshTrigger={draftRefreshTrigger}
              onDraftsLoaded={handleDraftsLoaded}
            />
          </div>
        )}

        {/* Chat Tab */}
        {activeTab === 'chat' && !isFullScreen && (
          <div className="flex flex-col h-[calc(100vh-280px)] min-h-125">
          {/* Chat Header */}
          <div className="bg-surface border border-border-base rounded-t-lg px-4 py-3 flex justify-between items-center">
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
                  className="w-4 h-4 rounded border-border-subtle bg-bg-base text-accent-primary focus:ring-accent-primary focus:ring-offset-0"
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
            className="flex-1 overflow-y-auto bg-bg-base border-x border-border-base"
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
                    <h4 className="text-xl font-serif font-semibold text-text-primary mb-2">
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
          <div className="bg-surface border border-border-base rounded-b-lg">
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
                  className="w-full px-4 py-4 pr-24 bg-bg-base border border-border-subtle rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors disabled:opacity-50"
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
          <div className="mb-8">
            <Suspense fallback={<ComponentLoader />}>
              <InsightsTab projectId={projectId} />
            </Suspense>
          </div>
        )}
          </>
        )}
      </main>

      {/* Full Screen Chat Mode */}
      {isFullScreen && (
        <div className="fixed inset-0 z-50 bg-bg-base flex flex-col">
          {/* Full Screen Header */}
          <div className="bg-surface border-b border-border-base">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex justify-between items-center h-16">
                <div className="flex items-center gap-3">
                  <img src="/noesis.png" alt="Noesis" className="h-10" />
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
                        className="w-4 h-4 rounded border-border-subtle bg-bg-base text-accent-primary focus:ring-accent-primary focus:ring-offset-0"
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
                    className="text-sm text-text-secondary hover:text-text-primary transition-colors flex items-center gap-2 px-3 py-1.5 border border-border-subtle rounded-lg hover:bg-surface-hover"
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
            className="flex-1 overflow-y-auto bg-bg-base"
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
                    <h4 className="text-2xl font-serif font-semibold text-text-primary mb-3">
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
          <div className="bg-surface border-t border-border-base">
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
                  className="w-full px-5 py-4 pr-28 bg-bg-base border border-border-subtle rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors disabled:opacity-50 text-base"
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

      {/* Research Assistant Panel (replaces Chat tab) */}
      {session?.access_token && projectId && !isFullScreen && (
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
      )}

    </div>
  )
}

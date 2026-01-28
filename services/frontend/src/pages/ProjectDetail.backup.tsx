import { useEffect, useState, useRef, lazy, Suspense } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { ArrowLeftIcon, DocumentTextIcon, TrashIcon, PaperAirplaneIcon, TrashIcon as ClearIcon, MagnifyingGlassIcon, Cog6ToothIcon, PencilIcon, CheckIcon, XMarkIcon, ArrowsPointingOutIcon, ArrowsPointingInIcon } from '@heroicons/react/24/outline'
import UploadDocumentModal from '../components/UploadDocumentModal'
import DeleteDocumentModal from '../components/DeleteDocumentModal'
import ChatMessage from '../components/ChatMessage'
import GlobalSearch from '../components/GlobalSearch'

// Lazy load heavy components for better performance
const DocumentDetailModal = lazy(() => import('../components/DocumentDetailModal'))
const RAGSettingsModal = lazy(() => import('../components/RAGSettingsModal'))
const ProjectInsights = lazy(() => import('../components/ProjectInsights'))
const LiteratureReviewModal = lazy(() => import('../components/LiteratureReviewModal'))
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

type Tab = 'documents' | 'chat' | 'insights' | 'analytics'

// Loading component for lazy-loaded sections
function ComponentLoader() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-solid border-accent-primary border-r-transparent"></div>
    </div>
  )
}

// Helper function to get status badge styling
const getStatusBadge = (status: string) => {
  const statusLower = status.toLowerCase()
  switch (statusLower) {
    case 'ready':
      return {
        bg: 'bg-green-500/20',
        text: 'text-green-300',
        label: 'Ready',
        animate: false,
      }
    case 'processing':
      return {
        bg: 'bg-yellow-500/20',
        text: 'text-yellow-300',
        label: 'Processing',
        animate: true,
      }
    case 'failed':
      return {
        bg: 'bg-red-500/20',
        text: 'text-red-300',
        label: 'Failed',
        animate: false,
      }
    default:
      return {
        bg: 'bg-neutral-700',
        text: 'text-neutral-300',
        label: 'Processed',
        animate: false,
      }
  }
}

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>()
  const navigate = useNavigate()
  const { user, session, signOut } = useAuthStore()
  const [project, setProject] = useState<Project | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('documents')

  // Document modals
  const [isUploadModalOpen, setIsUploadModalOpen] = useState(false)
  const [deleteDocument, setDeleteDocument] = useState<{ id: string; title: string } | null>(null)
  const [selectedDocument, setSelectedDocument] = useState<{ id: string; title: string; status: string } | null>(null)

  // Chat state
  const [messages, setMessages] = useState<ChatMessageType[]>([])
  const [input, setInput] = useState('')
  const [isStreaming, setIsStreaming] = useState(false)
  const [streamingMessage, setStreamingMessage] = useState('')
  const [streamingSources, setStreamingSources] = useState<any[]>([])
  const [isFullScreen, setIsFullScreen] = useState(false)
  const messagesEndRef = useRef<HTMLDivElement>(null)
  const chatContainerRef = useRef<HTMLDivElement>(null)

  // Search state
  const [isSearchOpen, setIsSearchOpen] = useState(false)

  // Literature review state
  const [isLitReviewOpen, setIsLitReviewOpen] = useState(false)

  // RAG Settings state
  const [isRAGSettingsOpen, setIsRAGSettingsOpen] = useState(false)

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
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setIsSearchOpen(true)
      }
      if ((e.metaKey || e.ctrlKey) && e.key === 'u') {
        e.preventDefault()
        setIsUploadModalOpen(true)
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

  // Poll for status updates every 5 seconds if there are processing documents
  useEffect(() => {
    if (!session?.access_token || !projectId) return

    const hasProcessingDocs = documents.some(
      (doc) => doc.status.toLowerCase() === 'processing' || doc.status.toLowerCase() === 'uploaded'
    )

    if (!hasProcessingDocs) return

    const pollInterval = setInterval(() => {
      loadProjectDetails()
    }, 5000)

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
      const history = await api.chat.getHistory(session.access_token, projectId)
      setMessages(history)
    } catch (error: any) {
      console.error('Failed to load chat history:', error)
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

  if (loading && !project) {
    return (
      <div className="min-h-screen bg-neutral-950 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
          <p className="mt-4 text-neutral-400">Loading project...</p>
        </div>
      </div>
    )
  }

  if (!project) {
    return null
  }

  return (
    <div className="min-h-screen bg-neutral-950">
      {/* Header */}
      <header className="bg-neutral-900 border-b border-neutral-800">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <img src="/noesis.png" alt="Noesis" className="h-10" />
              <span className="text-lg font-serif font-semibold text-neutral-50">Noesis</span>
            </div>
            <div className="flex items-center gap-2 sm:gap-4">
              <button
                onClick={() => setIsRAGSettingsOpen(true)}
                className="flex items-center gap-2 px-2 sm:px-3 py-1.5 text-sm text-neutral-400 hover:text-neutral-50 bg-neutral-800 hover:bg-neutral-700 rounded-lg border border-neutral-700 transition-colors"
                title="RAG Configuration"
              >
                <Cog6ToothIcon className="h-4 w-4" />
                <span className="hidden lg:inline">RAG Settings</span>
              </button>

              <button
                onClick={() => setIsSearchOpen(true)}
                className="flex items-center gap-2 px-2 sm:px-3 py-1.5 text-sm text-neutral-400 hover:text-neutral-50 bg-neutral-800 hover:bg-neutral-700 rounded-lg border border-neutral-700 transition-colors group"
              >
                <MagnifyingGlassIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Search</span>
                <kbd className="hidden md:inline-block px-1.5 py-0.5 text-xs bg-neutral-900 border border-neutral-700 rounded font-mono">
                  ⌘K
                </kbd>
              </button>
              <span className="text-sm text-neutral-400 hidden md:inline font-mono">{user?.email}</span>
              <button
                onClick={() => signOut()}
                className="text-sm text-neutral-400 hover:text-neutral-50 font-medium transition-colors"
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
          className="inline-flex items-center gap-2 text-neutral-400 hover:text-neutral-50 mb-6 transition-colors"
        >
          <ArrowLeftIcon className="h-5 w-5" />
          Back to Projects
        </Link>

        {/* Loading State */}
        {loading && (
          <div className="text-center py-12">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
            <p className="mt-4 text-neutral-400">Loading project...</p>
          </div>
        )}

        {/* Project Content */}
        {!loading && project && (
          <>
        {/* Project Header */}
        <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6 mb-8">
          {isEditingProject ? (
            /* Edit Mode */
            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-2">Project Title</label>
                <input
                  type="text"
                  value={editedTitle}
                  onChange={(e) => setEditedTitle(e.target.value)}
                  className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 text-2xl font-serif font-bold focus:ring-2 focus:ring-accent-primary focus:border-transparent"
                  placeholder="Enter project title"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-neutral-400 mb-2">Description <span className="text-neutral-500 font-mono text-xs">(optional)</span></label>
                <textarea
                  value={editedDescription}
                  onChange={(e) => setEditedDescription(e.target.value)}
                  className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 focus:ring-2 focus:ring-accent-primary focus:border-transparent"
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
                  className="flex items-center gap-2 px-4 py-2 text-neutral-400 hover:text-neutral-50 border border-neutral-700 rounded-lg hover:bg-neutral-800 transition-colors"
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
                <h2 className="text-3xl font-serif font-bold text-neutral-50">
                  {project.title}
                </h2>
                <button
                  onClick={handleStartEditProject}
                  className="flex items-center gap-2 px-3 py-1.5 text-sm text-neutral-400 hover:text-neutral-50 border border-neutral-700 rounded-lg hover:bg-neutral-800 transition-colors"
                  title="Edit project details"
                >
                  <PencilIcon className="h-4 w-4" />
                  Edit
                </button>
              </div>
              <p className="text-neutral-400 mb-4">
                {project.description || 'No description'}
              </p>
              <div className="flex items-center gap-4 text-sm font-mono text-neutral-500">
                <span>{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
                <span>•</span>
                <span>Created {new Date(project.created_at).toLocaleDateString()}</span>
              </div>
            </>
          )}
        </div>

        {/* Tabs Navigation */}
        <div className="mb-6">
          <div className="flex gap-2 border-b border-neutral-800 overflow-x-auto scrollbar-hide">
            <button
              onClick={() => setActiveTab('documents')}
              className={`px-4 sm:px-6 py-3 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${
                activeTab === 'documents'
                  ? 'border-accent-primary text-neutral-50'
                  : 'border-transparent text-neutral-400 hover:text-neutral-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <DocumentTextIcon className="h-5 w-5" />
                <span className="hidden sm:inline">Documents</span>
                <span className="sm:hidden">Docs</span>
                {documents.length > 0 && (
                  <span className="ml-1 px-2 py-0.5 text-xs bg-neutral-800 rounded-full font-mono">
                    {documents.length}
                  </span>
                )}
              </div>
            </button>
            <button
              onClick={() => setActiveTab('chat')}
              className={`px-4 sm:px-6 py-3 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${
                activeTab === 'chat'
                  ? 'border-accent-primary text-neutral-50'
                  : 'border-transparent text-neutral-400 hover:text-neutral-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
                </svg>
                <span>Chat</span>
              </div>
            </button>
            <button
              onClick={() => setActiveTab('insights')}
              className={`px-4 sm:px-6 py-3 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${
                activeTab === 'insights'
                  ? 'border-accent-primary text-neutral-50'
                  : 'border-transparent text-neutral-400 hover:text-neutral-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                <span>Insights</span>
              </div>
            </button>
            <button
              onClick={() => setActiveTab('analytics')}
              className={`px-4 sm:px-6 py-3 text-sm font-medium transition-colors border-b-2 whitespace-nowrap ${
                activeTab === 'analytics'
                  ? 'border-accent-primary text-neutral-50'
                  : 'border-transparent text-neutral-400 hover:text-neutral-300'
              }`}
            >
              <div className="flex items-center gap-2">
                <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                </svg>
                <span>Analytics</span>
              </div>
            </button>
          </div>
        </div>

        {/* Documents Tab */}
        {activeTab === 'documents' && (
          <div className="mb-8">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-serif font-semibold text-neutral-50">Documents</h3>
            <button
              onClick={() => setIsUploadModalOpen(true)}
              className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2"
            >
              <span>Upload Document</span>
              <kbd className="hidden sm:inline-block px-1.5 py-0.5 text-xs bg-accent-hover border border-accent-primary rounded font-mono">
                ⌘U
              </kbd>
            </button>
          </div>

          {/* Empty State */}
          {documents.length === 0 && (
            <div className="text-center py-12 bg-neutral-900 rounded-lg border-2 border-dashed border-neutral-800">
              <div className="max-w-md mx-auto">
                <h4 className="text-xl font-serif font-semibold text-neutral-50 mb-2">
                  No documents yet
                </h4>
                <p className="text-neutral-400 mb-6">
                  Upload your first document to start building your knowledge base
                </p>
                <button
                  onClick={() => setIsUploadModalOpen(true)}
                  className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
                >
                  Upload Your First Document
                </button>
              </div>
            </div>
          )}

          {/* Documents List */}
          {documents.length > 0 && (
            <div className="space-y-3">
              {documents.map((doc) => {
                const statusBadge = getStatusBadge(doc.status)
                return (
                  <div
                    key={doc.id}
                    onClick={() => setSelectedDocument({ id: doc.id, title: doc.title, status: doc.status })}
                    className="bg-neutral-900 rounded-lg border border-neutral-800 p-5 hover:border-neutral-700 transition-colors group cursor-pointer"
                  >
                    <div className="flex items-start gap-4">
                      {/* PDF Icon */}
                      <div className="shrink-0">
                        <div className="h-12 w-12 bg-accent-primary/10 rounded-lg flex items-center justify-center">
                          <DocumentTextIcon className="h-7 w-7 text-accent-primary" />
                        </div>
                      </div>

                      {/* Document Info */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-start justify-between gap-3">
                          <div className="flex-1 min-w-0">
                            <h4 className="font-serif font-semibold text-neutral-50 mb-1 truncate">
                              {doc.title}
                            </h4>
                            <div className="flex items-center gap-3 text-sm font-mono text-neutral-500">
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
                            <span
                              className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium ${statusBadge.bg} ${statusBadge.text}`}
                            >
                              {statusBadge.animate && (
                                <span className="relative flex h-2 w-2">
                                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-yellow-400 opacity-75"></span>
                                  <span className="relative inline-flex rounded-full h-2 w-2 bg-yellow-500"></span>
                                </span>
                              )}
                              {statusBadge.label}
                            </span>

                            {/* Delete Button */}
                            <button
                              onClick={(e) => {
                                e.stopPropagation()
                                setDeleteDocument({ id: doc.id, title: doc.title })
                              }}
                              className="p-2 text-neutral-500 hover:text-red-400 hover:bg-red-950/30 rounded-lg transition-colors opacity-0 group-hover:opacity-100"
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
        )}

        {/* Chat Tab */}
        {activeTab === 'chat' && !isFullScreen && (
          <div className="flex flex-col h-[calc(100vh-280px)] min-h-125">
          {/* Chat Header */}
          <div className="bg-neutral-900 border border-neutral-800 rounded-t-lg px-4 py-3 flex justify-between items-center">
            <div className="flex items-center gap-2 text-sm font-mono text-neutral-400">
              <DocumentTextIcon className="h-4 w-4" />
              <span>{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
            </div>
            <div className="flex items-center gap-3">
              <button
                onClick={() => setIsFullScreen(true)}
                className="text-sm text-neutral-400 hover:text-neutral-50 transition-colors flex items-center gap-2"
                title="Full screen mode"
              >
                <ArrowsPointingOutIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Expand</span>
              </button>
              {messages.length > 0 && (
                <button
                  onClick={handleClearChat}
                  className="text-sm text-neutral-400 hover:text-red-400 transition-colors flex items-center gap-2"
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
            className="flex-1 overflow-y-auto bg-neutral-950 border-x border-neutral-800"
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
                    <h4 className="text-xl font-serif font-semibold text-neutral-50 mb-2">
                      How can I help you today?
                    </h4>
                    <p className="text-neutral-400 text-sm">
                      Ask questions about your documents and get AI-powered answers with citations
                    </p>
                  </div>
                </div>
              )}

              <div className="space-y-8">
                {messages.map((message) => (
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
          <div className="bg-neutral-900 border border-neutral-800 rounded-b-lg">
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
                  className="w-full px-4 py-4 pr-24 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors disabled:opacity-50"
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

        {/* Insights Tab */}
        {activeTab === 'insights' && projectId && (
          <div className="mb-8">
            <div className="flex justify-between items-center mb-4">
              <h3 className="text-xl font-serif font-semibold text-neutral-50">Project Insights & Research Gaps</h3>
              <button
                onClick={() => setIsLitReviewOpen(true)}
                className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2"
              >
                <DocumentTextIcon className="h-5 w-5" />
                Generate Literature Review
              </button>
            </div>
            <Suspense fallback={<ComponentLoader />}>
              <ProjectInsights
                projectId={projectId}
                onOpenLiteratureReview={() => setIsLitReviewOpen(true)}
              />
            </Suspense>
          </div>
        )}

        {/* Analytics Tab */}
        {activeTab === 'analytics' && projectId && (
          <div className="mb-8">
            <div className="flex items-center gap-3 mb-6">
              <div className="p-2 bg-cyan-600/20 rounded-lg">
                <svg className="h-6 w-6 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
                </svg>
              </div>
              <div>
                <h3 className="text-xl font-serif font-semibold text-neutral-50">Citation Network Analysis</h3>
                <p className="text-sm text-neutral-400">Interactive visualization of paper relationships and influence</p>
              </div>
            </div>
            <Suspense fallback={<ComponentLoader />}>
              <CitationNetwork projectId={projectId} />
            </Suspense>
          </div>
        )}
          </>
        )}
      </main>

      {/* Full Screen Chat Mode */}
      {isFullScreen && (
        <div className="fixed inset-0 z-50 bg-neutral-950 flex flex-col">
          {/* Full Screen Header */}
          <div className="bg-neutral-900 border-b border-neutral-800">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
              <div className="flex justify-between items-center h-16">
                <div className="flex items-center gap-3">
                  <img src="/noesis.png" alt="Noesis" className="h-10" />
                  <div className="h-6 w-px bg-neutral-700"></div>
                  <div className="flex items-center gap-2 text-sm font-mono text-neutral-400">
                    <DocumentTextIcon className="h-4 w-4" />
                    <span>{documents.length} document{documents.length !== 1 ? 's' : ''}</span>
                  </div>
                </div>
                <div className="flex items-center gap-3">
                  {messages.length > 0 && (
                    <button
                      onClick={handleClearChat}
                      className="text-sm text-neutral-400 hover:text-red-400 transition-colors flex items-center gap-2"
                    >
                      <ClearIcon className="h-4 w-4" />
                      <span className="hidden sm:inline">Clear</span>
                    </button>
                  )}
                  <button
                    onClick={() => setIsFullScreen(false)}
                    className="text-sm text-neutral-400 hover:text-neutral-50 transition-colors flex items-center gap-2 px-3 py-1.5 border border-neutral-700 rounded-lg hover:bg-neutral-800"
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
            className="flex-1 overflow-y-auto bg-neutral-950"
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
                    <h4 className="text-2xl font-serif font-semibold text-neutral-50 mb-3">
                      How can I help you today?
                    </h4>
                    <p className="text-neutral-400">
                      Ask questions about your documents and get AI-powered answers with citations
                    </p>
                  </div>
                </div>
              )}

              <div className="space-y-8">
                {messages.map((message) => (
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
          <div className="bg-neutral-900 border-t border-neutral-800">
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
                  className="w-full px-5 py-4 pr-28 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors disabled:opacity-50 text-base"
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

      {/* RAG Settings Modal */}
      {projectId && (
        <Suspense fallback={null}>
          <RAGSettingsModal
            isOpen={isRAGSettingsOpen}
            onClose={() => setIsRAGSettingsOpen(false)}
            projectId={projectId}
          />
        </Suspense>
      )}

      {/* Document Detail Modal */}
      {selectedDocument && (
        <Suspense fallback={null}>
          <DocumentDetailModal
            isOpen={!!selectedDocument}
            onClose={() => setSelectedDocument(null)}
            document={selectedDocument}
          />
        </Suspense>
      )}

      {/* Literature Review Modal */}
      {projectId && (
        <Suspense fallback={null}>
          <LiteratureReviewModal
            isOpen={isLitReviewOpen}
            onClose={() => setIsLitReviewOpen(false)}
            projectId={projectId}
          />
        </Suspense>
      )}
    </div>
  )
}

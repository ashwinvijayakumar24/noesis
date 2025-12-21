import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { EllipsisVerticalIcon, TrashIcon, MagnifyingGlassIcon, TagIcon, XMarkIcon, DocumentTextIcon, ChatBubbleLeftRightIcon, SparklesIcon, ChartBarIcon } from '@heroicons/react/24/outline'
import { Menu } from '@headlessui/react'
import CreateProjectModal from '../components/CreateProjectModal'
import DeleteProjectModal from '../components/DeleteProjectModal'
import GlobalSearch from '../components/GlobalSearch'
import TagInput from '../components/TagInput'
import OnboardingTour from '../components/OnboardingTour'
import { analytics, trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'

interface Project {
  id: string
  title: string
  description: string | null
  created_at: string
  updated_at: string
  document_count?: number
}

interface ProjectTag {
  id: string
  tag_name: string
  tag_color: string
}

export default function Projects() {
  const navigate = useNavigate()
  const { user, session, signOut } = useAuthStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [isSearchOpen, setIsSearchOpen] = useState(false)
  const [deleteProject, setDeleteProject] = useState<{ id: string; title: string } | null>(null)
  const [projectTags, setProjectTags] = useState<Record<string, ProjectTag[]>>({})
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [showOnboarding, setShowOnboarding] = useState(false)

  useEffect(() => {
    document.title = 'Projects | Noesis'
  }, [])

  useEffect(() => {
    if (session?.access_token) {
      loadProjects()
    }
  }, [session])

  // Keyboard shortcuts
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      // Cmd+K / Ctrl+K for search
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        setIsSearchOpen(true)
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  const loadProjects = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      const data = await api.projects.list(session.access_token)
      setProjects(data)

      // Load tags for all projects
      await loadAllProjectTags(data)

      // Show onboarding for first-time users with no projects
      const hasSeenOnboarding = localStorage.getItem('noesis_onboarding_completed')
      if (!hasSeenOnboarding && data.length === 0) {
        setShowOnboarding(true)
      }
    } catch (error: any) {
      handleError(error, 'loading projects')
    } finally {
      setLoading(false)
    }
  }

  const handleOnboardingComplete = () => {
    trackEvent.onboardingCompleted()
    localStorage.setItem('noesis_onboarding_completed', 'true')
    setShowOnboarding(false)
  }

  const loadAllProjectTags = async (projectList: Project[]) => {
    if (!session?.access_token) return

    const tagsMap: Record<string, ProjectTag[]> = {}

    await Promise.all(
      projectList.map(async (project) => {
        try {
          const tags = await api.tags.getProjectTags(session.access_token!, project.id)
          tagsMap[project.id] = tags
        } catch (error) {
          console.error(`Failed to load tags for project ${project.id}:`, error)
          tagsMap[project.id] = []
        }
      })
    )

    setProjectTags(tagsMap)
  }

  // Get all unique tags across all projects
  const getAllUniqueTags = () => {
    const tagsMap = new Map<string, { name: string; color: string; count: number }>()

    Object.values(projectTags).forEach((tags) => {
      tags.forEach((tag) => {
        const existing = tagsMap.get(tag.tag_name)
        if (existing) {
          existing.count++
        } else {
          tagsMap.set(tag.tag_name, {
            name: tag.tag_name,
            color: tag.tag_color,
            count: 1,
          })
        }
      })
    })

    return Array.from(tagsMap.values()).sort((a, b) => b.count - a.count)
  }

  // Filter projects by selected tags
  const filteredProjects = selectedTags.length === 0
    ? projects
    : projects.filter((project) => {
        const tags = projectTags[project.id] || []
        return selectedTags.some((selectedTag) =>
          tags.some((tag) => tag.tag_name === selectedTag)
        )
      })

  const toggleTagFilter = (tagName: string) => {
    setSelectedTags((prev) =>
      prev.includes(tagName)
        ? prev.filter((t) => t !== tagName)
        : [...prev, tagName]
    )
  }

  const clearTagFilters = () => {
    setSelectedTags([])
  }

  // Map color names to Tailwind classes (same as TagInput)
  const getColorClasses = (color: string) => {
    const colorMap: Record<string, { bg: string; text: string; border: string }> = {
      'red-500': { bg: 'bg-red-500/20', text: 'text-red-300', border: 'border-red-500/50' },
      'orange-500': { bg: 'bg-orange-500/20', text: 'text-orange-300', border: 'border-orange-500/50' },
      'yellow-500': { bg: 'bg-yellow-500/20', text: 'text-yellow-300', border: 'border-yellow-500/50' },
      'green-500': { bg: 'bg-green-500/20', text: 'text-green-300', border: 'border-green-500/50' },
      'blue-500': { bg: 'bg-blue-500/20', text: 'text-blue-300', border: 'border-blue-500/50' },
      'purple-500': { bg: 'bg-purple-500/20', text: 'text-purple-300', border: 'border-purple-500/50' },
      'pink-500': { bg: 'bg-pink-500/20', text: 'text-pink-300', border: 'border-pink-500/50' },
      'cyan-500': { bg: 'bg-cyan-500/20', text: 'text-cyan-300', border: 'border-cyan-500/50' },
      'indigo-500': { bg: 'bg-indigo-500/20', text: 'text-indigo-300', border: 'border-indigo-500/50' },
      'rose-500': { bg: 'bg-rose-500/20', text: 'text-rose-300', border: 'border-rose-500/50' },
    }
    return colorMap[color] || { bg: 'bg-gray-500/20', text: 'text-gray-300', border: 'border-gray-500/50' }
  }

  const uniqueTags = getAllUniqueTags()

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
              {/* Search Button */}
              <button
                onClick={() => setIsSearchOpen(true)}
                className="flex items-center gap-2 px-3 py-1.5 text-sm text-neutral-400 hover:text-neutral-50 bg-neutral-800 hover:bg-neutral-700 rounded-lg border border-neutral-700 transition-colors group"
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
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        {/* Header with Create Button */}
        <div className="flex justify-between items-center mb-8">
          <div>
            <h2 className="text-3xl font-serif font-semibold text-neutral-50">Projects</h2>
            <p className="text-neutral-400 mt-2">
              Manage your research projects and documents
            </p>
          </div>
          <button
            onClick={() => setIsCreateModalOpen(true)}
            className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
          >
            Create Project
          </button>
        </div>

        {/* Tag Filters */}
        {uniqueTags.length > 0 && (
          <div className="mb-8 p-6 bg-neutral-900 rounded-lg border border-neutral-800">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TagIcon className="h-5 w-5 text-neutral-400" />
                <h3 className="text-sm font-semibold text-neutral-300">Filter by tags</h3>
              </div>
              {selectedTags.length > 0 && (
                <button
                  onClick={clearTagFilters}
                  className="text-xs text-neutral-400 hover:text-neutral-50 flex items-center gap-1 transition-colors"
                >
                  <XMarkIcon className="h-3 w-3" />
                  Clear filters
                </button>
              )}
            </div>
            <div className="flex flex-wrap gap-2">
              {uniqueTags.map((tag) => {
                const colors = getColorClasses(tag.color)
                const isSelected = selectedTags.includes(tag.name)
                return (
                  <button
                    key={tag.name}
                    onClick={() => toggleTagFilter(tag.name)}
                    className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-colors ${
                      isSelected
                        ? `${colors.bg} ${colors.text} ${colors.border} ring-2 ring-${colors.border}`
                        : 'bg-neutral-800 text-neutral-400 border-neutral-700 hover:border-neutral-600 hover:text-neutral-300'
                    }`}
                  >
                    <TagIcon className="h-3.5 w-3.5" />
                    {tag.name}
                    <span className="text-xs opacity-75 font-mono">({tag.count})</span>
                  </button>
                )
              })}
            </div>
          </div>
        )}

        {/* Loading State */}
        {loading && (
          <div className="text-center py-16">
            <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
            <p className="mt-4 text-neutral-400">Loading projects...</p>
          </div>
        )}

        {/* Empty State - No Projects */}
        {!loading && projects.length === 0 && (
          <div className="text-center py-16 bg-neutral-900 rounded-lg border-2 border-dashed border-neutral-800">
            <div className="max-w-md mx-auto">
              <h3 className="text-xl font-serif font-semibold text-neutral-50 mb-2">
                No projects yet
              </h3>
              <p className="text-neutral-400 mb-6">
                Get started by creating your first research project
              </p>
              <button
                onClick={() => setIsCreateModalOpen(true)}
                className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
              >
                Create Your First Project
              </button>
            </div>
          </div>
        )}

        {/* Empty State - No Matching Projects */}
        {!loading && projects.length > 0 && filteredProjects.length === 0 && (
          <div className="text-center py-16 bg-neutral-900 rounded-lg border-2 border-dashed border-neutral-800">
            <div className="max-w-md mx-auto">
              <h3 className="text-xl font-serif font-semibold text-neutral-50 mb-2">
                No projects match your filters
              </h3>
              <p className="text-neutral-400 mb-6">
                Try adjusting your tag filters to see more projects
              </p>
              <button
                onClick={clearTagFilters}
                className="px-6 py-3 border border-neutral-700 text-neutral-300 font-medium rounded-lg hover:border-neutral-600 hover:text-neutral-50 transition-colors"
              >
                Clear Filters
              </button>
            </div>
          </div>
        )}

        {/* Projects Grid */}
        {!loading && filteredProjects.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredProjects.map((project) => (
              <div
                key={project.id}
                className="bg-neutral-900 rounded-lg border border-neutral-800 p-6 hover:border-neutral-700 transition-colors relative group"
              >
                {/* Options Menu */}
                <Menu as="div" className="absolute top-4 right-4">
                  <Menu.Button
                    className="p-1 text-neutral-500 hover:text-neutral-300 rounded-lg hover:bg-neutral-800 transition-colors opacity-0 group-hover:opacity-100"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <EllipsisVerticalIcon className="h-5 w-5" />
                  </Menu.Button>
                  <Menu.Items className="absolute right-0 mt-2 w-48 bg-neutral-800 rounded-lg shadow-lg border border-neutral-700 py-1 z-10">
                    <Menu.Item>
                      {({ active }) => (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleteProject({ id: project.id, title: project.title })
                          }}
                          className={`${
                            active ? 'bg-red-900/30' : ''
                          } flex items-center gap-2 w-full px-4 py-2 text-sm text-red-400 hover:bg-red-900/30 transition-colors`}
                        >
                          <TrashIcon className="h-4 w-4" />
                          Delete Project
                        </button>
                      )}
                    </Menu.Item>
                  </Menu.Items>
                </Menu>

                {/* Card Content - Clickable */}
                <div
                  onClick={() => navigate(`/projects/${project.id}`)}
                  className="cursor-pointer"
                >
                  <h3 className="text-xl font-serif font-semibold text-neutral-50 mb-2 pr-8">
                    {project.title}
                  </h3>
                  <p className="text-neutral-400 text-sm mb-4 line-clamp-2">
                    {project.description || 'No description'}
                  </p>

                  {/* Tags */}
                  <div className="mb-4">
                    <TagInput projectId={project.id} />
                  </div>

                  <div className="flex items-center justify-between text-xs font-mono text-neutral-500">
                    <span>{project.document_count || 0} documents</span>
                    <span>{new Date(project.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </main>

      {/* Create Project Modal */}
      {session?.access_token && (
        <CreateProjectModal
          isOpen={isCreateModalOpen}
          onClose={() => setIsCreateModalOpen(false)}
          onSuccess={loadProjects}
          token={session.access_token}
        />
      )}

      {/* Delete Project Modal */}
      {session?.access_token && deleteProject && (
        <DeleteProjectModal
          isOpen={!!deleteProject}
          onClose={() => setDeleteProject(null)}
          onSuccess={loadProjects}
          token={session.access_token}
          projectId={deleteProject.id}
          projectTitle={deleteProject.title}
        />
      )}

      {/* Global Search Modal */}
      <GlobalSearch
        isOpen={isSearchOpen}
        onClose={() => setIsSearchOpen(false)}
      />

      {/* Onboarding Tour */}
      {showOnboarding && (
        <OnboardingTour
          onComplete={handleOnboardingComplete}
          steps={[
            {
              title: 'Welcome to Noesis!',
              description: 'Noesis is your AI-powered research workspace. Upload research papers, chat with your documents, generate literature reviews, and discover insights across your entire knowledge base.',
              action: 'Create your first project to get started',
              icon: <SparklesIcon className="h-6 w-6 text-accent-primary" />,
            },
            {
              title: 'Organize with Projects',
              description: 'Projects help you organize papers by research topic, course, or any category you choose. Each project has its own documents, chat history, and insights.',
              action: 'Click "Create Project" to begin',
              icon: <DocumentTextIcon className="h-6 w-6 text-blue-400" />,
            },
            {
              title: 'Upload Research Papers',
              description: 'Upload PDF research papers to your projects. Noesis will automatically extract metadata, analyze content, generate summaries, and make papers searchable.',
              icon: <DocumentTextIcon className="h-6 w-6 text-green-400" />,
            },
            {
              title: 'Chat with Your Papers',
              description: 'Ask questions about your uploaded papers using our RAG-powered chat. Get answers with citations, explore methodologies, and discover connections across your research.',
              icon: <ChatBubbleLeftRightIcon className="h-6 w-6 text-purple-400" />,
            },
            {
              title: 'Generate Insights',
              description: 'Automatically generate literature reviews, get research question suggestions, receive methodology recommendations, and visualize citation networks.',
              action: 'Use the Insights and Analytics tabs in your projects',
              icon: <ChartBarIcon className="h-6 w-6 text-cyan-400" />,
            },
          ]}
        />
      )}
    </div>
  )
}

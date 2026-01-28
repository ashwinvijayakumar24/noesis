import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import { EllipsisVerticalIcon, TrashIcon, MagnifyingGlassIcon, TagIcon, XMarkIcon, DocumentTextIcon, ChatBubbleLeftRightIcon, ChartBarIcon, BeakerIcon, LightBulbIcon, PencilIcon } from '@heroicons/react/24/outline'
import { Menu } from '@headlessui/react'
import CreateProjectModal from '../components/CreateProjectModal'
import DeleteProjectModal from '../components/DeleteProjectModal'
import GlobalSearch from '../components/GlobalSearch'
import TagInput from '../components/TagInput'
import OnboardingTour from '../components/OnboardingTour'
import { trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'
import { SkeletonProjectCard, SkeletonGrid } from '../components/ui/Skeleton'

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

  // Helper to get a color for project cards based on index
  const getProjectBorderColor = (index: number): string => {
    const colors = [
      'border-l-4 border-l-blue-400',
      'border-l-4 border-l-purple-400',
      'border-l-4 border-l-cyan-400',
      'border-l-4 border-l-indigo-400',
      'border-l-4 border-l-emerald-400',
      'border-l-4 border-l-pink-400',
    ]
    return colors[index % colors.length]
  }

  return (
    <div className="min-h-screen bg-bg-base">
      {/* Header */}
      <header className="bg-surface border-b border-border-subtle">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <img src="/noesis.png" alt="Noesis" className="h-10" />
              <span className="text-lg font-serif font-semibold text-text-primary">Noesis</span>
            </div>
            <div className="flex items-center gap-2 sm:gap-4">
              {/* Search Button */}
              <button
                onClick={() => setIsSearchOpen(true)}
                className="flex items-center gap-2 px-3 py-1.5 text-sm text-text-tertiary hover:text-text-primary bg-surface-hover hover:bg-surface-active rounded-lg border border-border-base transition-colors group"
              >
                <MagnifyingGlassIcon className="h-4 w-4" />
                <span className="hidden sm:inline">Search</span>
              </button>
              <span className="text-sm text-text-tertiary hidden md:inline font-mono">{user?.email}</span>
              <button
                onClick={() => signOut()}
                className="text-sm text-text-tertiary hover:text-text-primary font-medium transition-colors"
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
            <h2 className="text-4xl font-serif font-semibold text-text-primary">Projects</h2>
            <p className="text-text-secondary mt-2">
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
          <div className="mb-8 p-6 bg-surface rounded-lg border border-border-base">
            <div className="flex items-center justify-between mb-4">
              <div className="flex items-center gap-2">
                <TagIcon className="h-5 w-5 text-text-tertiary" />
                <h3 className="text-sm font-semibold text-text-secondary">Filter by tags</h3>
              </div>
              {selectedTags.length > 0 && (
                <button
                  onClick={clearTagFilters}
                  className="text-xs text-text-tertiary hover:text-text-primary flex items-center gap-1 transition-colors"
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
                        : 'bg-surface-hover text-text-tertiary border-border-base hover:border-border-subtle hover:text-text-secondary'
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
        {loading && <SkeletonGrid count={6} CardComponent={SkeletonProjectCard} />}

        {/* Empty State - No Projects */}
        {!loading && projects.length === 0 && (
          <div className="text-center py-16 bg-surface rounded-lg border-2 border-dashed border-border-base">
            <div className="max-w-md mx-auto">
              <h3 className="text-2xl font-serif font-semibold text-text-primary mb-2">
                No projects yet
              </h3>
              <p className="text-text-secondary mb-6">
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
          <div className="text-center py-16 bg-surface rounded-lg border-2 border-dashed border-border-base">
            <div className="max-w-md mx-auto">
              <h3 className="text-2xl font-serif font-semibold text-text-primary mb-2">
                No projects match your filters
              </h3>
              <p className="text-text-secondary mb-6">
                Try adjusting your tag filters to see more projects
              </p>
              <button
                onClick={clearTagFilters}
                className="px-6 py-3 bg-surface border border-border-base text-text-secondary font-medium rounded-lg hover:bg-surface-hover hover:border-accent-primary transition-colors"
              >
                Clear Filters
              </button>
            </div>
          </div>
        )}

        {/* Projects Grid */}
        {!loading && filteredProjects.length > 0 && (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            {filteredProjects.map((project, index) => (
              <div
                key={project.id}
                className={`bg-surface rounded-lg border border-border-base p-6 hover:border-accent-primary hover:bg-surface-hover hover:shadow-lg hover:shadow-red-600/20 transition-all relative group ${getProjectBorderColor(index)}`}
              >
                {/* Options Menu */}
                <Menu as="div" className="absolute top-4 right-4">
                  <Menu.Button
                    className="p-2 text-text-tertiary hover:text-text-primary rounded-md hover:bg-surface-hover transition-colors opacity-0 group-hover:opacity-100"
                    onClick={(e) => e.stopPropagation()}
                  >
                    <EllipsisVerticalIcon className="h-5 w-5" />
                  </Menu.Button>
                  <Menu.Items className="absolute right-0 mt-2 w-48 bg-surface-hover rounded-lg shadow-lg border border-border-base py-1 z-10">
                    <Menu.Item>
                      {({ active }) => (
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            setDeleteProject({ id: project.id, title: project.title })
                          }}
                          className={`${
                            active ? 'bg-red-500/10' : ''
                          } flex items-center gap-2 w-full px-4 py-2 text-sm text-red-400 hover:bg-red-500/10 transition-colors`}
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
                  <h3 className="text-2xl font-serif font-semibold text-text-primary mb-4 pr-8">
                    {project.title}
                  </h3>
                  <p className="text-sm text-text-secondary mb-4 line-clamp-2">
                    {project.description || 'No description'}
                  </p>

                  {/* Tags */}
                  <div className="mb-4">
                    <TagInput projectId={project.id} />
                  </div>

                  <div className="flex items-center justify-between text-xs font-mono text-text-muted">
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
              description: 'Noesis is your AI-powered research intelligence platform. Follow this recommended workflow to get the most value from your research.',
              action: 'Create your first project to get started',
              icon: <LightBulbIcon className="h-6 w-6 text-accent-primary" />,
            },
            {
              title: 'Step 1: Upload Research Papers',
              description: 'Start by uploading research papers related to your topic. Noesis will extract claims, methods, and findings using advanced AI analysis. This builds your knowledge base for citation suggestions.',
              action: 'Upload at least 1-3 papers to begin',
              icon: <DocumentTextIcon className="h-6 w-6 text-blue-400" />,
            },
            {
              title: 'Step 2: Analyze to Extract Insights',
              description: 'Each paper is automatically analyzed to extract structured data: research claims, methodologies with datasets, and quantitative findings. This happens automatically after upload.',
              icon: <BeakerIcon className="h-6 w-6 text-green-400" />,
            },
            {
              title: 'Step 3: Upload More Papers for Cross-Paper Analysis',
              description: 'Upload 2-3 more papers for richer insights. The more papers you add, the better the cross-paper analysis, gap detection, and theme identification.',
              action: 'Multiple papers unlock deeper analysis',
              icon: <DocumentTextIcon className="h-6 w-6 text-purple-400" />,
            },
            {
              title: 'Step 4: Generate Insights to Identify Gaps',
              description: 'Generate cross-paper insights to discover research gaps, common themes, methodological patterns, and conflicting findings across your literature.',
              action: 'Use the Insights tab to generate analysis',
              icon: <LightBulbIcon className="h-6 w-6 text-yellow-400" />,
            },
            {
              title: 'Step 5: Upload Your Draft for Citation Suggestions',
              description: 'Finally, upload your research draft. Noesis will provide AI-powered citation suggestions for your claims, identify coverage gaps, and offer expert reviewer feedback.',
              action: 'Upload draft in the Drafts tab',
              icon: <PencilIcon className="h-6 w-6 text-cyan-400" />,
            },
          ]}
        />
      )}
    </div>
  )
}

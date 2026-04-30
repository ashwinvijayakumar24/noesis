import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import { EllipsisVerticalIcon, TrashIcon, TagIcon, XMarkIcon, DocumentTextIcon, BeakerIcon, LightBulbIcon, PencilIcon, PlusIcon, LockClosedIcon } from '@heroicons/react/24/outline'
import { Menu } from '@headlessui/react'
import { motion } from 'framer-motion'
import CreateProjectModal from '../components/CreateProjectModal'
import DeleteProjectModal from '../components/DeleteProjectModal'
import TagInput from '../components/TagInput'
import OnboardingTour from '../components/OnboardingTour'
import { trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'
import toast from 'react-hot-toast'
import { SkeletonProjectCard, SkeletonGrid } from '../components/ui/Skeleton'
import PageContainer from '../components/layout/PageContainer'
import { Button } from '../components/ui/Button'

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
  project_id?: string
  tag_name: string
  tag_color: string
}

interface TagSuggestion {
  name: string
  color: string
}

export default function Projects() {
  const navigate = useNavigate()

  const { session } = useAuthStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [deleteProject, setDeleteProject] = useState<{ id: string; title: string } | null>(null)
  const [projectTags, setProjectTags] = useState<Record<string, ProjectTag[]>>({})
  const [tagSuggestions, setTagSuggestions] = useState<TagSuggestion[]>([])
  const [selectedTags, setSelectedTags] = useState<string[]>([])
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [projectLimit, setProjectLimit] = useState(3)

  useEffect(() => {
    document.title = 'Projects | Noesis'
  }, [])

  useEffect(() => {
    if (session?.access_token) {
      loadProjects()
      handlePendingLabInvite(session.access_token)
    }
  }, [session])

  const handlePendingLabInvite = async (token: string) => {
    const code = sessionStorage.getItem('pending_lab_invite')
    if (!code) return
    sessionStorage.removeItem('pending_lab_invite')
    try {
      const result = await api.labInvites.join(token, code)
      if (result.success) {
        const labName = sessionStorage.getItem('pending_lab_invite_name') || 'your lab'
        sessionStorage.removeItem('pending_lab_invite_name')
        toast.success(`Welcome! You've joined ${labName}'s workspace on Noesis.`, { duration: 5000 })
      }
    } catch {
      // Non-critical — invite may have expired, ignore silently
    }
  }

  const loadProjects = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      const [data, allTags] = await Promise.all([
        api.projects.list(session.access_token),
        api.tags.getAllProjectTags(session.access_token).catch(() => []),
      ])
      setProjects(data)
      setProjectTags(groupTagsByProject(allTags))

      // Tag suggestions are only needed when editing tags, so don't block initial render on them.
      api.tags.getSuggestions(session.access_token).then(setTagSuggestions).catch(() => {})
      api.quota.getSummary(session.access_token).then((quotaData) => {
        if (quotaData?.projects?.limit != null) {
          setProjectLimit(quotaData.projects.limit)
        }
      }).catch(() => {})

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

  const groupTagsByProject = (allTags: ProjectTag[]) => {
    const tagsMap: Record<string, ProjectTag[]> = {}

    allTags.forEach((tag) => {
      const projectId = tag.project_id
      if (!projectId) return
      if (!tagsMap[projectId]) {
        tagsMap[projectId] = []
      }
      tagsMap[projectId].push(tag)
    })

    return tagsMap
  }

  const handleProjectTagsChange = (projectId: string, tags: ProjectTag[]) => {
    setProjectTags((prev) => ({
      ...prev,
      [projectId]: tags,
    }))
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

  const uniqueTags = getAllUniqueTags()

  return (
    <PageContainer
      title="Projects"
      description="Manage your research projects and documents"
      headerActions={
        projects.length >= projectLimit ? (
          <div className="flex items-center gap-2">
            <span className="text-xs text-text-muted">
              {projectLimit}/{projectLimit} projects
            </span>
            <Button
              variant="primary"
              size="lg"
              disabled
              title={`Free plan is limited to ${projectLimit} projects`}
            >
              <LockClosedIcon className="h-4 w-4" />
              Create Project
            </Button>
          </div>
        ) : (
          <div className="flex items-center gap-2">
            {projects.length > 0 && (
              <span className="text-xs text-text-muted">
                {projects.length}/{projectLimit} projects
              </span>
            )}
            <Button
              onClick={() => setIsCreateModalOpen(true)}
              variant="primary"
              size="lg"
            >
              <PlusIcon className="h-5 w-5" />
              Create Project
            </Button>
          </div>
        )
      }
      spacing="loose"
    >

      {/* Tag Filters */}
      {uniqueTags.length > 0 && (
        <div className="p-6 bg-bg-surface rounded-lg border border-border-default">
          <div className="flex items-center justify-between mb-4">
            <div className="flex items-center gap-2">
              <TagIcon className="h-5 w-5 text-accent-primary" />
              <h3 className="text-sm font-sans font-semibold text-text-primary tracking-normal">Filter by tags</h3>
            </div>
            {selectedTags.length > 0 && (
              <button
                onClick={clearTagFilters}
                className="text-xs text-text-tertiary hover:text-accent-primary flex items-center gap-1 transition-colors duration-150"
              >
                <XMarkIcon className="h-3 w-3" />
                Clear filters
              </button>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            {uniqueTags.map((tag) => {
              const isSelected = selectedTags.includes(tag.name)
              return (
                <button
                  key={tag.name}
                  onClick={() => toggleTagFilter(tag.name)}
                  className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-md text-sm font-medium border transition-all duration-150 tracking-normal ${
                    isSelected
                      ? 'bg-bg-elevated border-border-default text-text-secondary ring-2 ring-offset-2 ring-offset-bg-void ring-border-default'
                      : 'bg-bg-hover text-text-tertiary border-border-default hover:border-accent-primary/30 hover:text-text-primary hover:bg-bg-elevated'
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
        <div className="text-center py-20 bg-bg-surface rounded-lg border border-dashed border-border-default">
          <div className="max-w-md mx-auto">
            <div className="h-20 w-20 mx-auto mb-6 rounded-xl bg-accent-light border border-accent-primary/30 flex items-center justify-center">
              <DocumentTextIcon className="h-10 w-10 text-accent-primary" />
            </div>
            <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
              No projects yet
            </h3>
            <p className="text-text-secondary mb-8 leading-relaxed tracking-normal">
              Get started by creating your first research project
            </p>
            <Button
              onClick={() => setIsCreateModalOpen(true)}
              variant="primary"
              size="lg"
            >
              Create Your First Project
            </Button>
          </div>
        </div>
      )}

      {/* Empty State - No Matching Projects */}
      {!loading && projects.length > 0 && filteredProjects.length === 0 && (
        <div className="text-center py-20 bg-bg-surface rounded-lg border border-dashed border-border-default">
          <div className="max-w-md mx-auto">
            <div className="h-20 w-20 mx-auto mb-6 rounded-xl bg-amber-light border border-amber-primary/30 flex items-center justify-center">
              <TagIcon className="h-10 w-10 text-amber-primary" />
            </div>
            <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
              No projects match your filters
            </h3>
            <p className="text-text-secondary mb-8 leading-relaxed tracking-normal">
              Try adjusting your tag filters to see more projects
            </p>
            <button
              onClick={clearTagFilters}
              className="px-6 py-3 bg-bg-surface border border-accent-primary/30 text-accent-primary font-semibold rounded-md hover:bg-accent-light transition-all duration-150"
            >
              Clear Filters
            </button>
          </div>
        </div>
      )}

      {/* Projects Grid - Animated */}
      {!loading && filteredProjects.length > 0 && (
        <motion.div
          className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6"
          initial="hidden"
          animate="visible"
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
          {filteredProjects.map((project) => (
            <motion.div
              key={project.id}
              className="group bg-bg-surface rounded-xl border border-border-default p-6 hover:border-accent-primary/30 hover:bg-bg-elevated hover:-translate-y-0.5 hover:shadow-md transition-all duration-150 relative cursor-pointer"
              onClick={() => navigate(`/projects/${project.id}`)}
              variants={{
                hidden: { opacity: 0, y: 20 },
                visible: {
                  opacity: 1,
                  y: 0,
                  transition: {
                    duration: 0.3,
                    ease: [0.16, 1, 0.3, 1]
                  }
                }
              }}
            >
              {/* Options Menu */}
              <Menu as="div" className="absolute top-4 right-4 z-10">
                <Menu.Button
                  className="p-2 text-text-tertiary hover:text-text-primary rounded-md hover:bg-bg-hover transition-all duration-150 opacity-0 group-hover:opacity-100"
                  onClick={(e) => e.stopPropagation()}
                >
                  <EllipsisVerticalIcon className="h-5 w-5" />
                </Menu.Button>
                <Menu.Items className="absolute right-0 mt-2 w-48 bg-bg-elevated rounded-lg shadow-lg border border-border-default py-1 z-10">
                  <Menu.Item>
                    {({ active }) => (
                      <button
                        onClick={(e) => {
                          e.stopPropagation()
                          setDeleteProject({ id: project.id, title: project.title })
                        }}
                        className={`${
                          active ? 'bg-red-950/30' : ''
                        } flex items-center gap-2 w-full px-4 py-2 text-sm text-red-400 hover:bg-red-950/30 transition-colors`}
                      >
                        <TrashIcon className="h-4 w-4" />
                        Delete Project
                      </button>
                    )}
                  </Menu.Item>
                </Menu.Items>
              </Menu>

              {/* Card Content */}
              <div>
                <h3 className="text-2xl font-sans font-semibold text-text-primary mb-3 pr-8 line-clamp-2 group-hover:text-accent-primary transition-colors duration-150 tracking-normal">
                  {project.title}
                </h3>
                <p className="text-sm text-text-secondary mb-4 line-clamp-2 leading-relaxed tracking-normal">
                  {project.description || 'No description'}
                </p>

                {/* Tags */}
                <div className="mb-4" onClick={(e) => e.stopPropagation()}>
                  <TagInput
                    projectId={project.id}
                    initialTags={projectTags[project.id] || []}
                    suggestions={tagSuggestions}
                    onTagsChange={(tags) => handleProjectTagsChange(project.id, tags)}
                  />
                </div>

                {/* Metadata Footer */}
                <div className="flex items-center justify-between text-xs font-mono text-text-muted pt-4 border-t border-border-default">
                  <div className="flex items-center gap-1.5">
                    <DocumentTextIcon className="h-3.5 w-3.5" />
                    <span>{project.document_count || 0} documents</span>
                  </div>
                  <span>{new Date(project.created_at).toLocaleDateString()}</span>
                </div>
              </div>
            </motion.div>
          ))}
        </motion.div>
      )}

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

      {/* Referral Widget — temporarily hidden */}
      {/* {!loading && projects.length > 0 && (
        <div className="mt-8">
          <ReferralWidget />
        </div>
      )} */}


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
              icon: <BeakerIcon className="h-6 w-6 text-success" />,
            },
            {
              title: 'Step 3: Upload More Papers for Cross-Paper Analysis',
              description: 'Upload 2-3 more papers for richer insights. The more papers you add, the better the cross-paper analysis, gap detection, and theme identification.',
              action: 'Multiple papers unlock deeper analysis',
              icon: <DocumentTextIcon className="h-6 w-6 text-accent-purple" />,
            },
            {
              title: 'Step 4: Generate Literature Map to Identify Gaps',
              description: 'Generate cross-paper insights to discover research gaps, common themes, methodological patterns, and conflicting findings across your literature.',
              action: 'Use the Literature Map tab to generate analysis',
              icon: <LightBulbIcon className="h-6 w-6 text-warning" />,
            },
            {
              title: 'Step 5: Upload Your Draft for Citation Suggestions',
              description: 'Finally, upload your research draft. Noesis will provide AI-powered citation suggestions for your claims, identify coverage gaps, and offer expert reviewer feedback.',
              action: 'Upload draft in the Drafts tab',
              icon: <PencilIcon className="h-6 w-6 text-accent-teal" />,
            },
          ]}
        />
      )}
    </PageContainer>
  )
}

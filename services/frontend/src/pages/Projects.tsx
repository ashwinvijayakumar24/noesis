import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import { ArrowRightIcon, DocumentTextIcon, EllipsisVerticalIcon, LockClosedIcon, PencilSquareIcon, PlusIcon, TrashIcon, BeakerIcon, LightBulbIcon } from '@heroicons/react/24/outline'
import { Menu } from '@headlessui/react'
import { motion } from 'framer-motion'
import CreateProjectModal from '../components/CreateProjectModal'
import DeleteProjectModal from '../components/DeleteProjectModal'
import OnboardingTour from '../components/OnboardingTour'
import { trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'
import toast from 'react-hot-toast'
import PageContainer from '../components/layout/PageContainer'
import { Button } from '../components/ui/Button'

interface Project {
  id: string
  title: string
  description: string | null
  created_at: string
  updated_at: string
  document_count?: number
  draft_count?: number
}

export default function Projects() {
  const navigate = useNavigate()

  const { session } = useAuthStore()
  const [projects, setProjects] = useState<Project[]>([])
  const [loading, setLoading] = useState(true)
  const [isCreateModalOpen, setIsCreateModalOpen] = useState(false)
  const [deleteProject, setDeleteProject] = useState<{ id: string; title: string } | null>(null)
  const [showOnboarding, setShowOnboarding] = useState(false)
  const [projectLimit, setProjectLimit] = useState(3)

  useEffect(() => {
    document.title = 'Projects | Noesis'
  }, [])

  const handlePendingLabInvite = useCallback(async (token: string) => {
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
  }, [])

  const loadProjects = useCallback(async () => {
    const token = session?.access_token
    if (!token) return

    try {
      setLoading(true)
      const [data] = await Promise.all([
        api.projects.list(token),
      ])
      setProjects(data)

      api.quota.getSummary(token).then((quotaData) => {
        if (quotaData?.projects?.limit != null) {
          setProjectLimit(quotaData.projects.limit)
        }
      }).catch(() => {})

      // Show onboarding for first-time users with no projects
      const hasSeenOnboarding = localStorage.getItem('noesis_onboarding_completed')
      if (!hasSeenOnboarding && data.length === 0) {
        setShowOnboarding(true)
      }
    } catch (error: unknown) {
      handleError(error, 'loading projects')
    } finally {
      setLoading(false)
    }
  }, [session?.access_token])

  useEffect(() => {
    if (session?.access_token) {
      loadProjects()
      handlePendingLabInvite(session.access_token)
    }
  }, [session?.access_token, loadProjects, handlePendingLabInvite])

  const handleOnboardingComplete = () => {
    trackEvent.onboardingCompleted()
    localStorage.setItem('noesis_onboarding_completed', 'true')
    setShowOnboarding(false)
  }

  const getProjectCue = (project: Project) => {
    const documentCount = project.document_count || 0
    const draftCount = project.draft_count || 0

    if (documentCount === 0) {
      return {
        label: 'Add literature',
        description: 'Start with papers',
        className: 'text-text-secondary',
      }
    }

    if (draftCount === 0) {
      return {
        label: 'Upload draft',
        description: 'Ready for review',
        className: 'text-amber-300',
      }
    }

    return {
      label: 'Continue review',
      description: 'Draft available',
      className: 'text-accent-primary',
    }
  }

  const formatDate = (value: string) => new Date(value).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })

  return (
    <PageContainer
      spacing="normal"
    >
      <div className="flex flex-col gap-5 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="mb-2 text-xs font-bold uppercase tracking-[0.12em] text-text-secondary">
            Workspace
          </p>
          <h1 className="text-3xl font-sans font-semibold leading-tight text-text-primary sm:text-4xl">
            Projects
          </h1>
          <p className="mt-2 max-w-2xl text-sm leading-6 text-text-secondary">
            Keep each manuscript focused: upload literature, then review one draft.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <span className="text-xs font-mono font-semibold text-text-secondary">
            {Math.min(projects.length, projectLimit)}/{projectLimit} projects
          </span>
          {projects.length >= projectLimit ? (
            <Button
              variant="primary"
              size="md"
              disabled
              title={`Free plan is limited to ${projectLimit} projects`}
            >
              <LockClosedIcon className="h-4 w-4" />
              Create Project
            </Button>
          ) : (
            <Button
              onClick={() => setIsCreateModalOpen(true)}
              variant="primary"
              size="md"
            >
              <PlusIcon className="h-4 w-4" />
              Create Project
            </Button>
          )}
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="overflow-hidden rounded-xl border border-border-default bg-bg-surface/80">
          {Array.from({ length: 4 }).map((_, index) => (
            <div
              key={index}
              className="grid gap-4 border-b border-border-default/70 px-5 py-4 last:border-b-0 md:grid-cols-[minmax(0,1fr)_220px_44px]"
            >
              <div className="space-y-2">
                <div className="h-4 w-48 animate-pulse rounded bg-bg-hover" />
                <div className="h-3 w-72 max-w-full animate-pulse rounded bg-bg-hover/70" />
              </div>
              <div className="flex items-center gap-2">
                <div className="h-6 w-20 animate-pulse rounded bg-bg-hover" />
                <div className="h-6 w-20 animate-pulse rounded bg-bg-hover/70" />
              </div>
              <div className="h-8 w-8 animate-pulse rounded-md bg-bg-hover" />
            </div>
          ))}
        </div>
      )}

      {/* Empty State - No Projects */}
      {!loading && projects.length === 0 && (
        <div className="rounded-xl border border-dashed border-border-default bg-bg-surface/70 px-6 py-14 text-center">
          <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-lg border border-border-default bg-bg-elevated">
            <DocumentTextIcon className="h-6 w-6 text-accent-primary" />
          </div>
          <h3 className="text-xl font-sans font-semibold text-text-primary">
            No projects yet
          </h3>
          <p className="mx-auto mt-2 max-w-md text-sm leading-6 text-text-secondary">
            Create a project to review one draft against its literature.
          </p>
          <div className="mt-7">
            <Button
              onClick={() => setIsCreateModalOpen(true)}
              variant="primary"
              size="md"
            >
              <PlusIcon className="h-4 w-4" />
              Create Project
            </Button>
          </div>
        </div>
      )}

      {/* Projects List */}
      {!loading && projects.length > 0 && (
        <motion.div
          className="overflow-hidden rounded-xl border border-border-default bg-bg-surface/80"
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
          {projects.map((project) => {
            const cue = getProjectCue(project)
            const documentCount = project.document_count || 0
            const draftCount = project.draft_count || 0

            return (
            <motion.div
              key={project.id}
              className="group relative grid cursor-pointer gap-4 border-b border-border-default/70 px-5 py-4 transition-colors duration-150 last:border-b-0 hover:bg-bg-elevated/70 md:grid-cols-[minmax(0,1fr)_280px_40px] md:items-center"
              onClick={() => navigate(`/projects/${project.id}`)}
              variants={{
                hidden: { opacity: 0, y: 8 },
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
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <h3 className="truncate text-base font-semibold text-text-primary transition-colors duration-150 group-hover:text-white">
                    {project.title}
                  </h3>
                  <ArrowRightIcon className="h-3.5 w-3.5 shrink-0 text-text-muted opacity-0 transition-all duration-150 group-hover:translate-x-0.5 group-hover:opacity-100" />
                </div>
                <p className="mt-1 line-clamp-1 text-sm text-text-secondary">
                  {project.description || 'No description'}
                </p>
                <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-2 text-xs font-mono font-semibold text-text-secondary md:hidden">
                  <span>{documentCount} paper{documentCount === 1 ? '' : 's'}</span>
                  <span>{draftCount > 0 ? 'Draft uploaded' : 'No draft'}</span>
                  <span>{formatDate(project.created_at)}</span>
                </div>
              </div>

              <div className="hidden items-center justify-between gap-5 md:flex">
                <div className="flex items-center gap-4 text-xs font-mono font-semibold text-text-secondary">
                  <span className="inline-flex items-center gap-1.5">
                    <DocumentTextIcon className="h-3.5 w-3.5" />
                    {documentCount}
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <PencilSquareIcon className="h-3.5 w-3.5" />
                    {draftCount > 0 ? 'Yes' : 'No'}
                  </span>
                  <span>{formatDate(project.created_at)}</span>
                </div>

                <div className="min-w-[118px] text-right">
                  <p className={`text-xs font-semibold ${cue.className}`}>{cue.label}</p>
                  <p className="mt-0.5 text-[11px] font-medium text-text-secondary">{cue.description}</p>
                </div>
              </div>

              <Menu as="div" className="relative z-10 justify-self-end">
                <Menu.Button
                  className="rounded-md p-2 text-text-tertiary opacity-100 transition-all duration-150 hover:bg-bg-hover hover:text-text-primary focus:bg-bg-hover focus:text-text-primary md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
                  onClick={(e) => e.stopPropagation()}
                >
                  <EllipsisVerticalIcon className="h-4 w-4" />
                </Menu.Button>
                <Menu.Items className="absolute right-0 mt-2 w-48 rounded-lg border border-border-default bg-bg-elevated py-1 shadow-lg">
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
                        Delete project
                      </button>
                    )}
                  </Menu.Item>
                </Menu.Items>
              </Menu>
            </motion.div>
          )})}
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
              description: 'Start by uploading papers related to the manuscript. Noesis will process them into the project library used during draft review.',
              action: 'Upload at least 1-3 papers to begin',
              icon: <DocumentTextIcon className="h-6 w-6 text-blue-400" />,
            },
            {
              title: 'Step 2: Let Literature Processing Finish',
              description: 'Noesis extracts searchable structure and embeddings in the background so draft analysis can compare claims against your uploaded sources.',
              icon: <BeakerIcon className="h-6 w-6 text-success" />,
            },
            {
              title: 'Step 3: Upload Your Draft',
              description: 'Add the manuscript you want reviewed. Noesis will use your project literature to check claims, citations, coverage, and reviewer-facing weaknesses.',
              action: 'Upload draft in the Your Draft tab',
              icon: <DocumentTextIcon className="h-6 w-6 text-accent-purple" />,
            },
            {
              title: 'Step 4: Analyze and Revise',
              description: 'Run the draft analysis, address the prioritized feedback, then upload a new version when you are ready to compare progress.',
              action: 'Run analysis from the Your Draft tab',
              icon: <LightBulbIcon className="h-6 w-6 text-warning" />,
            },
          ]}
        />
      )}
    </PageContainer>
  )
}

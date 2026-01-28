import { Fragment, useState, useEffect } from 'react'
import { Dialog, Transition, Tab } from '@headlessui/react'
import { XMarkIcon, MapIcon } from '@heroicons/react/24/outline'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import StructureAdvisorTab from './compass/StructureAdvisorTab'
import ThematicClusteringTab from './compass/ThematicClusteringTab'
import SynthesisQuestionsTab from './compass/SynthesisQuestionsTab'
import CoverageGapsTab from './compass/CoverageGapsTab'

interface LiteratureReviewCompassProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
  insights: any | null
}

interface CompassGuidance {
  structure_recommendations: StructureRecommendation[]
  synthesis_questions: SynthesisQuestion[]
  positioning_prompts: PositioningPrompt[]
}

interface StructureRecommendation {
  type: string
  score: number
  reasoning: string
  outline: {
    sections: Section[]
  }
}

interface Section {
  title: string
  papers: string[]
  focus_themes: string[]
  synthesis_prompt: string
}

interface SynthesisQuestion {
  question: string
  category: string
  icon: string
  related_papers: string[]
}

interface PositioningPrompt {
  prompt: string
  based_on: string
}

export default function LiteratureReviewCompass({
  isOpen,
  onClose,
  projectId,
  insights
}: LiteratureReviewCompassProps) {
  const { session } = useAuthStore()
  const [guidance, setGuidance] = useState<CompassGuidance | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (isOpen && !guidance) {
      loadGuidance()
    }
  }, [isOpen])

  const loadGuidance = async () => {
    if (!session?.access_token) return

    setLoading(true)
    try {
      const data = await api.compass.getGuidance(session.access_token, projectId)
      setGuidance(data)
    } catch (error: any) {
      console.error('Failed to load guidance:', error)
      toast.error(error.message || 'Failed to load compass guidance')
    } finally {
      setLoading(false)
    }
  }

  if (!insights) {
    return (
      <Transition appear show={isOpen} as={Fragment}>
        <Dialog as="div" className="relative z-50" onClose={onClose}>
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" />
          </Transition.Child>

          <div className="fixed inset-0 overflow-y-auto">
            <div className="flex min-h-full items-center justify-center p-4">
              <Transition.Child
                as={Fragment}
                enter="ease-out duration-300"
                enterFrom="opacity-0 scale-95"
                enterTo="opacity-100 scale-100"
                leave="ease-in duration-200"
                leaveFrom="opacity-100 scale-100"
                leaveTo="opacity-0 scale-95"
              >
                <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-xl bg-surface border border-border-base shadow-2xl transition-all p-6">
                  <Dialog.Title className="text-lg font-semibold text-text-primary mb-3">
                    Insights Required
                  </Dialog.Title>
                  <p className="text-text-tertiary text-sm mb-4">
                    Please analyze project insights first before using the Literature Review Compass.
                  </p>
                  <button
                    onClick={onClose}
                    className="w-full px-4 py-2 bg-accent-primary text-white rounded-lg hover:bg-accent-hover"
                  >
                    Close
                  </button>
                </Dialog.Panel>
              </Transition.Child>
            </div>
          </div>
        </Dialog>
      </Transition>
    )
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-5xl transform overflow-hidden rounded-xl bg-surface border border-border-base shadow-2xl transition-all max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-5 border-b border-border-subtle shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-accent-primary/10 rounded-lg">
                      <MapIcon className="h-6 w-6 text-accent-primary" />
                    </div>
                    <div>
                      <Dialog.Title className="text-2xl font-serif font-semibold text-text-primary">
                        Literature Review Compass
                      </Dialog.Title>
                      <p className="text-sm text-text-muted mt-1">
                        Structural guidance for organizing your literature review
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={onClose}
                    className="text-text-tertiary hover:text-text-primary transition-colors"
                  >
                    <XMarkIcon className="h-6 w-6" />
                  </button>
                </div>

                {/* Tabs */}
                <Tab.Group as="div" className="flex-1 flex flex-col min-h-0">
                  <Tab.List className="flex gap-1 px-6 border-b border-border-base shrink-0">
                    <Tab className={({ selected }) =>
                      `px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                        selected
                          ? 'border-accent-primary text-text-primary'
                          : 'border-transparent text-text-tertiary hover:text-text-secondary'
                      }`
                    }>
                      Structure Advisor
                    </Tab>
                    <Tab className={({ selected }) =>
                      `px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                        selected
                          ? 'border-accent-primary text-text-primary'
                          : 'border-transparent text-text-tertiary hover:text-text-secondary'
                      }`
                    }>
                      Thematic Clustering
                    </Tab>
                    <Tab className={({ selected }) =>
                      `px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                        selected
                          ? 'border-accent-primary text-text-primary'
                          : 'border-transparent text-text-tertiary hover:text-text-secondary'
                      }`
                    }>
                      Synthesis Questions
                    </Tab>
                    <Tab className={({ selected }) =>
                      `px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
                        selected
                          ? 'border-accent-primary text-text-primary'
                          : 'border-transparent text-text-tertiary hover:text-text-secondary'
                      }`
                    }>
                      Coverage & Gaps
                    </Tab>
                  </Tab.List>

                  {/* Content */}
                  <Tab.Panels className="flex-1 overflow-y-auto p-6">
                    {loading ? (
                      <div className="flex items-center justify-center py-12">
                        <div className="text-center">
                          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-accent-primary border-r-transparent" />
                          <p className="text-text-tertiary mt-3 text-sm">Loading guidance...</p>
                        </div>
                      </div>
                    ) : (
                      <>
                        <Tab.Panel>
                          {guidance && (
                            <StructureAdvisorTab
                              recommendations={guidance.structure_recommendations}
                            />
                          )}
                        </Tab.Panel>
                        <Tab.Panel>
                          <ThematicClusteringTab
                            themes={insights.common_themes || []}
                          />
                        </Tab.Panel>
                        <Tab.Panel>
                          {guidance && (
                            <SynthesisQuestionsTab
                              questions={guidance.synthesis_questions}
                            />
                          )}
                        </Tab.Panel>
                        <Tab.Panel>
                          <CoverageGapsTab
                            gaps={insights.research_gaps || []}
                            themes={insights.common_themes || []}
                          />
                        </Tab.Panel>
                      </>
                    )}
                  </Tab.Panels>
                </Tab.Group>

                {/* Footer */}
                <div className="px-6 py-4 bg-surface/50 border-t border-border-subtle flex justify-end shrink-0">
                  <button
                    onClick={onClose}
                    className="px-4 py-2 text-sm text-text-tertiary hover:text-text-primary transition-colors"
                  >
                    Close
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

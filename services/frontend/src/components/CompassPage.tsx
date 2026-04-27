import { useState, useEffect } from 'react'
import { Tab } from '@headlessui/react'
import { MapIcon, ClockIcon } from '@heroicons/react/24/outline'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import StructureAdvisorTab from './compass/StructureAdvisorTab'
import ThematicClusteringTab from './compass/ThematicClusteringTab'
import SynthesisQuestionsTab from './compass/SynthesisQuestionsTab'
import CoverageGapsTab from './compass/CoverageGapsTab'
import PaperRecommendations from './PaperRecommendations'

interface CompassPageProps {
  projectId: string
  insights: any | null
}

interface CompassGuidance {
  structure_recommendations: StructureRecommendation[]
  synthesis_questions: SynthesisQuestion[]
  positioning_prompts: PositioningPrompt[]
  structure_guidance?: StructureGuidanceItem[]
}

interface StructureGuidanceItem {
  text: string
  type: 'gap' | 'conflict' | 'pattern' | 'general'
  priority: number
  source_data: {
    conflicts: string[]
    gaps: string[]
    patterns: string[]
  }
}

interface StructureRecommendation {
  type: string
  score: number
  reasoning: string
  outline: {
    sections: Section[]
  }
  pros: string[]
  cons: string[]
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
  difficulty?: 'low' | 'medium' | 'high'
  confidence?: number
  metadata?: {
    source_conflicts?: string[]
    source_gaps?: string[]
    source_patterns?: string[]
  }
  requirements?: string[]
  actionable?: boolean
}

interface PositioningPrompt {
  prompt: string
  based_on: string
}

// Helper to detect insights changes
const getInsightsHash = (insights: any): string => {
  if (!insights) return ''

  return JSON.stringify({
    num_gaps: insights.research_gaps?.length || 0,
    num_themes: insights.common_themes?.length || 0,
    num_methods: insights.methodological_patterns?.length || 0,
    num_conflicts: insights.conflicting_findings?.length || 0,
    summary: insights.summary || ''
  })
}

export default function CompassPage({ projectId, insights }: CompassPageProps) {
  const { session } = useAuthStore()
  const [guidance, setGuidance] = useState<CompassGuidance | null>(null)
  const [loading, setLoading] = useState(false)
  const [lastInsightsHash, setLastInsightsHash] = useState<string>('')

  useEffect(() => {
    if (!insights) {
      setGuidance(null)
      setLastInsightsHash('')
      return
    }

    const currentHash = getInsightsHash(insights)

    // Load guidance if:
    // 1. Guidance doesn't exist yet, OR
    // 2. Insights have changed (hash different)
    if (!guidance || currentHash !== lastInsightsHash) {
      setLastInsightsHash(currentHash)
      loadGuidance()
    }
  }, [projectId, insights])

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
      <div className="bg-surface/50 rounded-lg border border-border-default p-12 text-center">
        <div className="max-w-md mx-auto">
          <div className="p-3 bg-accent-primary/10 rounded-lg inline-block mb-4">
            <MapIcon className="h-12 w-12 text-accent-primary" />
          </div>
          <h3 className="text-xl font-sans font-semibold text-text-primary mb-2">
            Insights Analysis Required
          </h3>
          <p className="text-text-tertiary mb-4">
            Please analyze project insights first before using the Literature Review Compass.
          </p>
          <p className="text-sm text-text-muted">
            Go to the <strong>Literature Map</strong> tab and click "Generate Literature Map"
          </p>
        </div>
      </div>
    )
  }

  return (
    <div className="mb-8">
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-accent-primary/10 rounded-lg">
            <MapIcon className="h-6 w-6 text-accent-primary" />
          </div>
          <div>
            <h3 className="text-2xl font-sans font-semibold text-text-primary">
              Literature Review Compass
            </h3>
            <p className="text-sm text-text-tertiary">
              Your expert guide for structuring and writing your literature review
            </p>
          </div>
        </div>
      </div>

      {/* Description */}
      <div className="bg-surface/50 rounded-lg border border-border-default p-6 mb-6">
        <h4 className="text-lg font-sans font-semibold text-text-primary mb-2">
          How the Compass Works
        </h4>
        <p className="text-sm text-text-tertiary mb-3">
          The Literature Review Compass analyzes your literature to provide structural guidance and critical
          thinking questions. Unlike AI writing tools, it doesn't write for you—it helps you become a better writer.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3 text-sm">
          <div className="flex items-start gap-2">
            <div className="p-1.5 bg-blue-500/10 rounded-md shrink-0">
              <svg className="h-4 w-4 text-blue-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-text-secondary">Structure Advisor</p>
              <p className="text-text-muted text-xs">Scored organizational approaches</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <div className="p-1.5 bg-purple-500/10 rounded-md shrink-0">
              <svg className="h-4 w-4 text-purple-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-text-secondary">Thematic Clusters</p>
              <p className="text-text-muted text-xs">How papers group by topic</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <div className="p-1.5 bg-emerald-500/10 rounded-md shrink-0">
              <svg className="h-4 w-4 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-text-secondary">Synthesis Questions</p>
              <p className="text-text-muted text-xs">Critical thinking prompts</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <div className="p-1.5 bg-orange-500/10 rounded-md shrink-0">
              <svg className="h-4 w-4 text-orange-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-text-secondary">Coverage & Gaps</p>
              <p className="text-text-muted text-xs">What's covered vs. missing</p>
            </div>
          </div>
          <div className="flex items-start gap-2">
            <div className="p-1.5 bg-indigo-500/10 rounded-md shrink-0">
              <svg className="h-4 w-4 text-indigo-300" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
              </svg>
            </div>
            <div>
              <p className="font-semibold text-text-secondary">Discover Papers</p>
              <p className="text-text-muted text-xs">AI-powered paper recommendations</p>
            </div>
          </div>
        </div>
      </div>

      {/* Loading State */}
      {loading && (
        <div className="bg-surface rounded-lg border border-border-default p-12 text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-solid border-accent-primary border-r-transparent mb-4"></div>
          <p className="text-text-secondary">
            {guidance ? 'Refreshing guidance...' : 'Analyzing your literature...'}
          </p>
        </div>
      )}

      {/* Tabs */}
      {!loading && guidance && (
        <Tab.Group>
          <Tab.List className="flex gap-2 border-b border-border-default mb-6 overflow-x-auto scrollbar-hide">
            <Tab
              className={({ selected }) =>
                `px-4 py-3 text-sm font-semibold transition-colors border-b-2 whitespace-nowrap ${
                  selected
                    ? 'border-accent-primary text-text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary'
                }`
              }
            >
              {({ selected }) => (
                <div className="flex items-center gap-2">
                  <svg className={`h-5 w-5 ${selected ? 'text-blue-400' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 17V7m0 10a2 2 0 01-2 2H5a2 2 0 01-2-2V7a2 2 0 012-2h2a2 2 0 012 2m0 10a2 2 0 002 2h2a2 2 0 002-2M9 7a2 2 0 012-2h2a2 2 0 012 2m0 10V7m0 10a2 2 0 002 2h2a2 2 0 002-2V7a2 2 0 00-2-2h-2a2 2 0 00-2 2" />
                  </svg>
                  <span>Structure Advisor</span>
                </div>
              )}
            </Tab>
            <Tab
              className={({ selected }) =>
                `px-4 py-3 text-sm font-semibold transition-colors border-b-2 whitespace-nowrap ${
                  selected
                    ? 'border-accent-primary text-text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary'
                }`
              }
            >
              {({ selected }) => (
                <div className="flex items-center gap-2">
                  <svg className={`h-5 w-5 ${selected ? 'text-purple-300' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
                  </svg>
                  <span>Thematic Clustering</span>
                </div>
              )}
            </Tab>
            <Tab
              className={({ selected }) =>
                `px-4 py-3 text-sm font-semibold transition-colors border-b-2 whitespace-nowrap ${
                  selected
                    ? 'border-accent-primary text-text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary'
                }`
              }
            >
              {({ selected }) => (
                <div className="flex items-center gap-2">
                  <svg className={`h-5 w-5 ${selected ? 'text-emerald-300' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8.228 9c.549-1.165 2.03-2 3.772-2 2.21 0 4 1.343 4 3 0 1.4-1.278 2.575-3.006 2.907-.542.104-.994.54-.994 1.093m0 3h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  <span>Synthesis Questions</span>
                </div>
              )}
            </Tab>
            <Tab
              className={({ selected }) =>
                `px-4 py-3 text-sm font-semibold transition-colors border-b-2 whitespace-nowrap ${
                  selected
                    ? 'border-accent-primary text-text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary'
                }`
              }
            >
              {({ selected }) => (
                <div className="flex items-center gap-2">
                  <svg className={`h-5 w-5 ${selected ? 'text-orange-400' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
                  </svg>
                  <span>Coverage & Gaps</span>
                </div>
              )}
            </Tab>
            <Tab
              className={({ selected }) =>
                `px-4 py-3 text-sm font-semibold transition-colors border-b-2 whitespace-nowrap ${
                  selected
                    ? 'border-accent-primary text-text-primary'
                    : 'border-transparent text-text-secondary hover:text-text-primary'
                }`
              }
            >
              {({ selected }) => (
                <div className="flex items-center gap-2">
                  <svg className={`h-5 w-5 ${selected ? 'text-indigo-300' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
                  </svg>
                  <span>Discover Papers</span>
                </div>
              )}
            </Tab>
          </Tab.List>

          <Tab.Panels>
            <Tab.Panel>
              <StructureAdvisorTab
                recommendations={guidance.structure_recommendations}
                structureGuidance={guidance.structure_guidance}
              />
            </Tab.Panel>
            <Tab.Panel>
              <ThematicClusteringTab themes={insights.common_themes || []} />
            </Tab.Panel>
            <Tab.Panel>
              <SynthesisQuestionsTab questions={guidance.synthesis_questions} />
            </Tab.Panel>
            <Tab.Panel>
              <CoverageGapsTab
                gaps={insights.research_gaps || []}
                themes={insights.common_themes || []}
                positioningPrompts={guidance.positioning_prompts || []}
              />
            </Tab.Panel>
            <Tab.Panel>
              <div className="space-y-6">
                {/* Loading State Message */}
                <div className="bg-slate-800/30 border border-slate-600/30 rounded-lg p-4 flex items-start gap-3">
                  <div className="p-2 bg-slate-700/50 rounded-lg shrink-0">
                    <ClockIcon className="h-5 w-5 text-slate-300" />
                  </div>
                  <div className="flex-1">
                    <h4 className="text-text-primary font-medium">Discovering Relevant Papers</h4>
                    <p className="text-text-secondary text-sm mt-1">
                      Finding relevant papers may take 30 seconds to 1 minute. The AI is searching academic databases and analyzing relevance to your research.
                    </p>
                  </div>
                </div>

                {/* Paper Recommendations */}
                <PaperRecommendations projectId={projectId} />
              </div>
            </Tab.Panel>
          </Tab.Panels>
        </Tab.Group>
      )}
    </div>
  )
}

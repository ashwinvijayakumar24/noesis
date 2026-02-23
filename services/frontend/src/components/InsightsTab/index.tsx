import { useState, useEffect, lazy, Suspense, useRef } from 'react'
import { useAuthStore } from '../../stores/authStore'
import { api } from '../../lib/api'
import SectionHeader from './SectionHeader'
import ResearchQuestions from '../ResearchQuestions'
import PaperRecommendations from '../PaperRecommendations'
import { Badge } from '../ui/Badge'
import Toast from '../ui/Toast'
import {
  LightBulbIcon,
  BeakerIcon,
  ExclamationTriangleIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  AcademicCapIcon
} from '@heroicons/react/24/outline'

// Lazy load compass sub-components
const SynthesisQuestionsTab = lazy(() => import('../compass/SynthesisQuestionsTab'))

interface InsightsTabProps {
  projectId: string
}

interface ResearchGap {
  category: 'methodological' | 'population' | 'theoretical' | 'temporal'
  title: string
  description: string
  supporting_evidence: string[]
  suggested_directions: string[]
}

interface CommonTheme {
  theme: string
  frequency: number
  description: string
  paper_titles?: string[]
}

interface MethodologicalPattern {
  methodology: string
  usage_count: number
  description: string
  variations?: string[]
}

interface ConflictingFinding {
  topic: string
  side_a: {
    position: string
    papers: string[]
    evidence: string
  }
  side_b: {
    position: string
    papers: string[]
    evidence: string
  }
  resolution?: string
}

interface Insights {
  research_gaps: ResearchGap[]
  common_themes: CommonTheme[]
  methodological_patterns: MethodologicalPattern[]
  conflicting_findings: ConflictingFinding[]
  key_insights?: string[]
  summary?: string
  analysis_metadata?: {
    num_papers_analyzed: number
    model: string
    timestamp: string
  }
}

interface CompassGuidance {
  structure_recommendations: any[]
  synthesis_questions: any[]
  positioning_prompts: any[]
}

function ComponentLoader() {
  return (
    <div className="flex items-center justify-center py-8">
      <div className="inline-block h-6 w-6 animate-spin rounded-full border-2 border-solid border-accent-primary border-r-transparent"></div>
    </div>
  )
}

export default function InsightsTab({ projectId }: InsightsTabProps) {
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<'not_analyzed' | 'analyzing' | 'analyzed' | 'failed'>('not_analyzed')
  const [insights, setInsights] = useState<Insights | null>(null)
  const [guidance, setGuidance] = useState<CompassGuidance | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pollingInterval, setPollingInterval] = useState<number | null>(null)
  const [showToast, setShowToast] = useState(false)
  const previousTimestampRef = useRef<string | null>(null)
  const isInitialLoadRef = useRef(true)

  // Section expansion state
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    overview: true,
    gaps: true,
    questions: true,
    recommendations: true,
    synthesis: false
  })

  useEffect(() => {
    if (session?.access_token && projectId) {
      loadInsights()
    }

    return () => {
      if (pollingInterval) {
        clearInterval(pollingInterval)
      }
    }
  }, [projectId, session])

  // Load compass guidance when insights are ready
  useEffect(() => {
    if (insights && session?.access_token) {
      loadGuidance()
    }
  }, [insights, session])

  const loadInsights = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      const data = await api.projects.getInsights(session.access_token, projectId)

      setStatus(data.status)

      if (data.status === 'analyzed') {
        const newTimestamp = data.insights?.analysis_metadata?.timestamp

        // Check if insights were updated (new timestamp and not initial load)
        if (newTimestamp &&
            !isInitialLoadRef.current &&
            previousTimestampRef.current &&
            previousTimestampRef.current !== newTimestamp) {
          setShowToast(true)
        }

        // Update the timestamp reference
        if (newTimestamp) {
          previousTimestampRef.current = newTimestamp
        }

        setInsights(data.insights)
        isInitialLoadRef.current = false

        if (pollingInterval) {
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
      } else if (data.status === 'analyzing') {
        if (!pollingInterval) {
          const interval = setInterval(() => {
            loadInsights()
          }, 3000)
          setPollingInterval(interval)
        }
      } else if (data.status === 'failed') {
        setError(data.message || 'Insights analysis failed')
        if (pollingInterval) {
          clearInterval(pollingInterval)
          setPollingInterval(null)
        }
      }
    } catch (err: any) {
      console.error('Failed to load insights:', err)
      setError(err.message || 'Failed to load insights')
    } finally {
      setLoading(false)
    }
  }

  const loadGuidance = async () => {
    if (!session?.access_token) return

    try {
      const data = await api.compass.getGuidance(session.access_token, projectId)
      setGuidance(data)
    } catch (error: any) {
      console.error('Failed to load guidance:', error)
    }
  }

  const handleAnalyze = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      await api.projects.analyzeInsights(session.access_token, projectId)

      setStatus('analyzing')
      const interval = setInterval(() => {
        loadInsights()
      }, 3000)
      setPollingInterval(interval)
    } catch (err: any) {
      console.error('Failed to start insights analysis:', err)
      setError(err.message || 'Failed to start insights analysis')
    } finally {
      setLoading(false)
    }
  }

  const toggleSection = (section: string) => {
    setExpandedSections(prev => ({
      ...prev,
      [section]: !prev[section]
    }))
  }

  if (loading && status === 'not_analyzed') {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
          <p className="text-text-tertiary text-sm mt-3">Loading...</p>
        </div>
      </div>
    )
  }

  if (status === 'not_analyzed') {
    return (
      <div className="bg-surface rounded-lg border border-border-default p-8 text-center">
        <div className="max-w-md mx-auto">
          <div className="h-16 w-16 mx-auto mb-4 rounded-full bg-accent-primary/10 flex items-center justify-center">
            <LightBulbIcon className="h-8 w-8 text-accent-primary" />
          </div>
          <h3 className="text-xl font-sans font-semibold text-text-primary mb-2">
            Analyze Your Literature
          </h3>
          <p className="text-text-tertiary mb-6">
            Get AI-powered insights including research gaps, common themes, methodology patterns, and structural guidance for your literature review.
          </p>
          <button
            onClick={handleAnalyze}
            className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors mx-auto"
          >
            Analyze Project Insights
          </button>
        </div>
      </div>
    )
  }

  if (status === 'analyzing') {
    return (
      <div className="bg-surface rounded-lg border border-border-default p-8 text-center">
        <div className="max-w-md mx-auto">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent mb-4"></div>
          <h3 className="text-xl font-sans font-semibold text-text-primary mb-2">
            Analyzing Project...
          </h3>
          <p className="text-text-tertiary">
            Our AI is analyzing all papers to identify cross-paper insights, research gaps, and patterns. This may take 30-60 seconds.
          </p>
        </div>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div className="bg-surface rounded-lg border border-red-900/50 p-8 text-center">
        <div className="max-w-md mx-auto">
          <XCircleIcon className="h-16 w-16 text-red-500 mx-auto mb-4" />
          <h3 className="text-xl font-sans font-semibold text-text-primary mb-2">
            Analysis Failed
          </h3>
          <p className="text-text-tertiary mb-4">
            {error || 'The insights analysis could not be completed. Please try again.'}
          </p>
          <button
            onClick={handleAnalyze}
            className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2 mx-auto"
          >
            <ArrowPathIcon className="h-5 w-5" />
            Retry Analysis
          </button>
        </div>
      </div>
    )
  }

  if (!insights) return null

  return (
    <div className="space-y-4">
      {/* Success Banner */}
      <div className="bg-surface border border-border-default rounded-lg p-4 flex items-start gap-3 border-l-4 border-l-success">
        <CheckCircleIcon className="h-6 w-6 text-success shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="text-text-primary font-medium">Insights Analysis Complete</h4>
          <p className="text-text-secondary text-sm mt-1">
            Analyzed {insights.analysis_metadata?.num_papers_analyzed || 0} papers
          </p>
        </div>
      </div>

      {/* Section 1: Overview & Key Insights */}
      <SectionHeader
        title="Overview & Key Insights"
        icon={<LightBulbIcon className="h-5 w-5" />}
        iconBg="bg-slate-700/50"
        iconColor="text-yellow-400"
        iconBorderColor="border-yellow-500/60"
        expanded={expandedSections.overview}
        onToggle={() => toggleSection('overview')}
      >
        <div className="space-y-4">
          {/* Summary */}
          {insights.summary && (
            <div className="bg-surface/50 rounded-lg p-4 border border-border-default">
              <p className="text-text-secondary leading-relaxed">{insights.summary}</p>
            </div>
          )}

          {/* Key Insights */}
          {insights.key_insights && insights.key_insights.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-text-primary mb-3">Key Findings</h4>
              <ul className="space-y-2">
                {insights.key_insights.map((insight, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-text-secondary">
                    <span className="text-accent-primary mt-1">•</span>
                    <span>{insight}</span>
                  </li>
                ))}
              </ul>
            </div>
          )}

          {/* Common Themes */}
          {insights.common_themes && insights.common_themes.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-text-primary mb-3">Common Themes</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                {insights.common_themes.slice(0, 4).map((theme, i) => (
                  <div key={i} className="bg-surface/50 rounded-lg p-3 border border-border-default">
                    <div className="flex items-start justify-between mb-1">
                      <h5 className="font-medium text-text-primary text-sm">{theme.theme}</h5>
                      <span className="text-xs text-text-muted font-mono">
                        {theme.frequency} paper{theme.frequency !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <p className="text-xs text-text-secondary line-clamp-2">{theme.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Methodology Patterns */}
          {insights.methodological_patterns && insights.methodological_patterns.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-text-primary mb-3">Methodology Patterns</h4>
              <div className="flex flex-wrap gap-2">
                {insights.methodological_patterns.map((pattern, i) => (
                  <Badge key={i} variant="info">
                    {pattern.methodology} ({pattern.usage_count})
                  </Badge>
                ))}
              </div>
            </div>
          )}

          {/* Conflicting Findings */}
          {insights.conflicting_findings && insights.conflicting_findings.length > 0 && (
            <div>
              <h4 className="text-sm font-semibold text-text-primary mb-3 flex items-center gap-2">
                <ExclamationTriangleIcon className="h-4 w-4 text-slate-300" />
                Conflicting Findings
              </h4>
              <div className="space-y-3">
                {insights.conflicting_findings.slice(0, 2).map((conflict, i) => (
                  <div key={i} className="bg-surface/50 border border-border-default rounded-lg p-3">
                    <h5 className="font-medium text-text-primary text-sm mb-2">{conflict.topic}</h5>
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div className="border-l-2 border-slate-500 pl-2">
                        <span className="text-text-muted">Position A:</span>
                        <p className="text-text-secondary mt-1">{conflict.side_a.position}</p>
                      </div>
                      <div className="border-l-2 border-slate-600 pl-2">
                        <span className="text-text-muted">Position B:</span>
                        <p className="text-text-secondary mt-1">{conflict.side_b.position}</p>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </SectionHeader>

      {/* Section 2: Research Gaps */}
      <SectionHeader
        title="Research Gaps"
        icon={<ExclamationTriangleIcon className="h-5 w-5" />}
        iconBg="bg-slate-700/50"
        iconColor="text-orange-400"
        iconBorderColor="border-orange-500/60"
        expanded={expandedSections.gaps}
        onToggle={() => toggleSection('gaps')}
      >
        {insights.research_gaps && insights.research_gaps.length > 0 ? (
          <div className="space-y-3">
            {insights.research_gaps.map((gap, i) => {
              const categoryColors: Record<string, string> = {
                methodological: 'bg-[#1e40af] text-white border-[#1e40af]',
                population: 'bg-[#166534] text-white border-[#166534]',
                theoretical: 'bg-[#6b21a8] text-white border-[#6b21a8]',
                temporal: 'bg-[#9a3412] text-white border-[#9a3412]',
              }
              const colorClass = categoryColors[gap.category] || 'bg-[#334155] text-white border-[#334155]'

              return (
                <div key={i} className="bg-surface/50 border border-border-default rounded-lg p-4">
                  <div className="flex items-start justify-between mb-2">
                    <h4 className="font-medium text-text-primary">{gap.title}</h4>
                    <span className={`text-xs px-2 py-1 rounded border font-mono ${colorClass}`}>
                      {gap.category.charAt(0).toUpperCase() + gap.category.slice(1)}
                    </span>
                  </div>
                <p className="text-sm text-text-secondary mb-3">{gap.description}</p>

                {gap.suggested_directions && gap.suggested_directions.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-text-muted mb-1">Suggested Directions:</p>
                    <ul className="text-xs space-y-1 text-text-secondary">
                      {gap.suggested_directions.map((direction, j) => (
                        <li key={j} className="flex items-start gap-1">
                          <span className="text-accent-primary">→</span>
                          {direction}
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
                </div>
              )
            })}
          </div>
        ) : (
          <p className="text-text-muted text-sm">No research gaps identified yet.</p>
        )}
      </SectionHeader>

      {/* Section 3: Paper Recommendations */}
      <SectionHeader
        title="Paper Recommendations"
        icon={<DocumentTextIcon className="h-5 w-5" />}
        iconBg="bg-slate-700/50"
        iconColor="text-green-400"
        iconBorderColor="border-green-500/60"
        expanded={expandedSections.recommendations}
        onToggle={() => toggleSection('recommendations')}
      >
        <PaperRecommendations projectId={projectId} insightsStatus={status} />
      </SectionHeader>

      {/* Section 4: Research Questions */}
      <SectionHeader
        title="Research Questions"
        icon={<AcademicCapIcon className="h-5 w-5" />}
        iconBg="bg-slate-700/50"
        iconColor="text-purple-400"
        iconBorderColor="border-purple-500/60"
        expanded={expandedSections.questions}
        onToggle={() => toggleSection('questions')}
      >
        <ResearchQuestions projectId={projectId} insightsStatus={status} hideMethodology={true} />
      </SectionHeader>

      {/* Section 5: Synthesis Questions (from Compass) */}
      {guidance?.synthesis_questions && guidance.synthesis_questions.length > 0 && (
        <SectionHeader
          title="Synthesis Questions"
          icon={<BeakerIcon className="h-5 w-5" />}
          iconBg="bg-slate-700/50"
          iconColor="text-pink-400"
          iconBorderColor="border-pink-500/60"
          expanded={expandedSections.synthesis}
          onToggle={() => toggleSection('synthesis')}
        >
          <Suspense fallback={<ComponentLoader />}>
            <SynthesisQuestionsTab questions={guidance.synthesis_questions} />
          </Suspense>
        </SectionHeader>
      )}

      {/* Toast notification for insights update */}
      {showToast && (
        <Toast
          type="success"
          title="Insights Updated"
          message={`Analysis has been refreshed with ${insights?.analysis_metadata?.num_papers_analyzed || 'all'} papers. New insights are now available.`}
          onClose={() => setShowToast(false)}
          duration={5000}
        />
      )}

    </div>
  )
}

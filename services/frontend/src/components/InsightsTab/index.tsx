import { useState, useEffect, lazy, Suspense, useRef } from 'react'
import { useAuthStore } from '../../stores/authStore'
import { api } from '../../lib/api'
import SectionHeader from './SectionHeader'
import { Badge } from '../ui/Badge'
import Toast from '../ui/Toast'
import {
  LightBulbIcon,
  BeakerIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon
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
  const [guidanceLoading, setGuidanceLoading] = useState(false)
  const [guidanceError, setGuidanceError] = useState<string | null>(null)
  const [isStale, setIsStale] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showToast, setShowToast] = useState(false)
  const [toastType, setToastType] = useState<'success' | 'error'>('success')
  const [toastMessage, setToastMessage] = useState('')
  const [isRefreshing, setIsRefreshing] = useState(false)

  // Use refs for things that need to be current inside interval callbacks
  // (avoids stale closure bugs that caused the infinite guidance loading loop)
  const pollingIntervalRef = useRef<number | null>(null)
  const guidanceLoadedTimestampRef = useRef<string | null>(null)
  const previousTimestampRef = useRef<string | null>(null)
  const isInitialLoadRef = useRef(true)

  // Section expansion state
  const [expandedSections, setExpandedSections] = useState<Record<string, boolean>>({
    overview: true,
    gaps: true,
    synthesis: true
  })

  useEffect(() => {
    if (session?.access_token && projectId) {
      loadInsights()
    }
    return () => {
      if (pollingIntervalRef.current) {
        clearInterval(pollingIntervalRef.current)
        pollingIntervalRef.current = null
      }
    }
  }, [projectId, session])

  const stopPolling = () => {
    if (pollingIntervalRef.current) {
      clearInterval(pollingIntervalRef.current)
      pollingIntervalRef.current = null
    }
  }

  const startPolling = () => {
    if (pollingIntervalRef.current) return // already polling
    pollingIntervalRef.current = setInterval(() => {
      loadInsights()
    }, 3000) as unknown as number
  }

  const loadInsights = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      const data = await api.projects.getInsights(session.access_token, projectId)

      setStatus(data.status)

      if (data.status === 'analyzed') {
        const newTimestamp = data.insights?.analysis_metadata?.timestamp

        // Show toast when insights were just refreshed (not on initial load)
        if (newTimestamp &&
            !isInitialLoadRef.current &&
            previousTimestampRef.current &&
            previousTimestampRef.current !== newTimestamp) {
          setToastType('success')
          setToastMessage(`Analysis refreshed with ${data.insights?.analysis_metadata?.num_papers_analyzed || 'all'} papers.`)
          setShowToast(true)
          setIsStale(false)
        }

        if (newTimestamp) {
          previousTimestampRef.current = newTimestamp
        }

        setInsights(data.insights)
        setIsStale(data.is_stale || false)
        isInitialLoadRef.current = false

        stopPolling()

        // Load guidance only once per unique insights timestamp
        const timestampKey = newTimestamp || 'no-timestamp'
        if (timestampKey !== guidanceLoadedTimestampRef.current) {
          guidanceLoadedTimestampRef.current = timestampKey
          loadGuidance()
        }

      } else if (data.status === 'analyzing') {
        startPolling()
      } else if (data.status === 'failed') {
        setError(data.message || 'Insights analysis failed')
        stopPolling()
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

    setGuidanceLoading(true)
    setGuidanceError(null)
    try {
      const data = await api.compass.getGuidance(session.access_token, projectId)
      setGuidance(data)
    } catch (error: any) {
      console.error('Failed to load guidance:', error)
      const msg = error?.message || ''
      if (msg.includes('2 analyzed documents') || msg.includes('Need at least')) {
        setGuidanceError('needs_more_docs')
      } else if (msg.includes('insights must be analyzed')) {
        setGuidanceError('needs_insights')
      } else {
        setGuidanceError('unknown')
      }
    } finally {
      setGuidanceLoading(false)
    }
  }

  const handleAnalyze = async () => {
    if (!session?.access_token || isRefreshing) return

    try {
      setIsRefreshing(true)
      await api.projects.analyzeInsights(session.access_token, projectId)
      setStatus('analyzing')
      setIsStale(false)
      startPolling()
    } catch (err: any) {
      console.error('Failed to start insights analysis:', err)
      setToastType('error')
      setToastMessage(err.message || 'Failed to start analysis. Please try again.')
      setShowToast(true)
    } finally {
      setIsRefreshing(false)
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
      <div className="bg-bg-surface rounded-lg border border-border-default p-8 text-center">
        <div className="max-w-md mx-auto">
          <div className="h-16 w-16 mx-auto mb-4 rounded-full bg-bg-elevated flex items-center justify-center">
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
      <div className="bg-bg-surface rounded-lg border border-border-default p-8 text-center">
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
      <div className="bg-bg-surface rounded-lg border border-border-default p-8 text-center">
        <div className="max-w-md mx-auto">
          <XCircleIcon className="h-16 w-16 text-error mx-auto mb-4" />
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
      {/* Stale Literature Banner */}
      {isStale && (
        <div className="bg-bg-surface border border-border-default border-l-2 border-l-warning rounded-lg p-4 flex items-start gap-3">
          <ExclamationTriangleIcon className="h-6 w-6 text-warning shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-text-primary font-semibold">Literature has changed</h4>
            <p className="text-text-secondary text-sm mt-1">
              Documents have been added or removed since your last analysis. Refresh to get up-to-date insights.
            </p>
          </div>
          <button
            onClick={handleAnalyze}
            disabled={isRefreshing}
            className="shrink-0 px-4 py-2 bg-accent-primary text-white text-sm font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2 disabled:opacity-60 disabled:cursor-not-allowed"
          >
            <ArrowPathIcon className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? 'Refreshing…' : 'Refresh'}
          </button>
        </div>
      )}

      {/* Success Banner */}
      {!isStale && (
        <div className="bg-bg-surface border border-border-default rounded-lg p-4 flex items-start gap-3 border-l-4 border-l-success">
          <CheckCircleIcon className="h-6 w-6 text-success shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-text-primary font-medium">Insights Analysis Complete</h4>
            <p className="text-text-secondary text-sm mt-1">
              Analyzed {insights.analysis_metadata?.num_papers_analyzed || 0} papers
            </p>
          </div>
        </div>
      )}

      {/* Section 1: Overview & Key Insights */}
      <SectionHeader
        title="Overview & Key Insights"
        icon={<LightBulbIcon className="h-5 w-5" />}
        iconBg="bg-bg-elevated"
        iconColor="text-text-secondary"
        iconBorderColor="border-border-default"
        expanded={expandedSections.overview}
        onToggle={() => toggleSection('overview')}
      >
        <div className="space-y-4">
          {/* Summary */}
          {insights.summary && (
            <div className="bg-bg-surface rounded-lg p-4 border border-border-default">
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
                  <div key={i} className="bg-bg-surface rounded-lg p-3 border border-border-default">
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
                <ExclamationTriangleIcon className="h-4 w-4 text-text-secondary" />
                Conflicting Findings
              </h4>
              <div className="space-y-3">
                {insights.conflicting_findings.slice(0, 2).map((conflict, i) => (
                  <div key={i} className="bg-bg-surface border border-border-default rounded-lg p-3">
                    <h5 className="font-medium text-text-primary text-sm mb-2">{conflict.topic}</h5>
                    <div className="grid grid-cols-2 gap-3 text-xs">
                      <div className="border-l-2 border-border-default pl-2">
                        <span className="text-text-muted">Position A:</span>
                        <p className="text-text-secondary mt-1">{conflict.side_a.position}</p>
                      </div>
                      <div className="border-l-2 border-border-default pl-2">
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
        iconBg="bg-bg-elevated"
        iconColor="text-text-secondary"
        iconBorderColor="border-border-default"
        expanded={expandedSections.gaps}
        onToggle={() => toggleSection('gaps')}
      >
        {insights.research_gaps && insights.research_gaps.length > 0 ? (
          <div className="space-y-3">
            {insights.research_gaps.map((gap, i) => {
              return (
                <div key={i} className="bg-bg-surface border border-border-default rounded-lg p-4">
                  <div className="flex items-start justify-between mb-2">
                    <h4 className="font-medium text-text-primary">{gap.title}</h4>
                    <span className="bg-bg-elevated text-text-muted border border-border-default rounded px-2 py-0.5 text-xs font-mono">
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

      {/* Section 3: Synthesis Questions (from Compass) */}
      <SectionHeader
        title="Synthesis Questions"
        icon={<BeakerIcon className="h-5 w-5" />}
        iconBg="bg-bg-elevated"
        iconColor="text-text-secondary"
        iconBorderColor="border-border-default"
        expanded={expandedSections.synthesis}
        onToggle={() => toggleSection('synthesis')}
      >
        {isStale && !guidanceLoading && !guidanceError && (guidance?.synthesis_questions?.length ?? 0) > 0 && (
          <div className="mb-4 bg-bg-surface border border-border-default border-l-2 border-l-warning rounded-xl p-3 flex items-start gap-2">
            <ExclamationTriangleIcon className="h-4 w-4 text-warning shrink-0 mt-0.5" />
            <p className="text-xs text-text-secondary">
              These questions are based on outdated insights. Refresh insights above to reflect your current papers.
            </p>
          </div>
        )}
        {guidanceLoading ? (
          <ComponentLoader />
        ) : guidanceError === 'needs_more_docs' ? (
          <div className="bg-bg-surface rounded-lg border border-border-default p-6 text-center">
            <p className="text-text-tertiary text-sm">
              Synthesis questions require at least 2 analyzed documents in this project. Upload more papers to unlock this section.
            </p>
          </div>
        ) : guidanceError ? (
          <div className="bg-bg-surface rounded-lg border border-border-default p-6 text-center">
            <p className="text-text-tertiary text-sm">
              Could not load synthesis questions. Try refreshing or re-running insights analysis.
            </p>
          </div>
        ) : guidance?.synthesis_questions && guidance.synthesis_questions.length > 0 ? (
          <Suspense fallback={<ComponentLoader />}>
            <SynthesisQuestionsTab questions={guidance.synthesis_questions} />
          </Suspense>
        ) : (
          <div className="bg-bg-surface rounded-lg border border-border-default p-6 text-center">
            <p className="text-text-tertiary text-sm">
              No synthesis questions generated yet. Add more documents with conflicting findings or research gaps to generate questions.
            </p>
          </div>
        )}
      </SectionHeader>

      {/* Toast notification for insights update */}
      {showToast && (
        <Toast
          type={toastType}
          title={toastType === 'success' ? 'Insights Updated' : 'Refresh Failed'}
          message={toastMessage || `Analysis has been refreshed with ${insights?.analysis_metadata?.num_papers_analyzed || 'all'} papers. New insights are now available.`}
          onClose={() => { setShowToast(false); setToastMessage('') }}
          duration={5000}
        />
      )}

    </div>
  )
}

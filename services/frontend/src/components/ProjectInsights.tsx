import { useState, useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import ResearchQuestions from './ResearchQuestions'
import { Badge } from './ui/Badge'
import {
  LightBulbIcon,
  BeakerIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  ArrowsRightLeftIcon as _ArrowsRightLeftIcon
} from '@heroicons/react/24/outline'

interface ProjectInsightsProps {
  projectId: string
  onOpenLiteratureReview?: () => void
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

interface TimelineItem {
  period: string
  development: string
  papers?: string[]
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

interface CitationPattern {
  cited_work: string
  frequency: number
  context: string
  papers_citing?: string[]
}

interface Insights {
  research_gaps: ResearchGap[]
  common_themes: CommonTheme[]
  methodological_patterns: MethodologicalPattern[]
  timeline: TimelineItem[]
  conflicting_findings: ConflictingFinding[]
  citation_patterns: CitationPattern[]
  key_insights?: string[]
  summary?: string
  analysis_metadata?: {
    num_papers_analyzed: number
    model: string
    timestamp: string
  }
}

const GAP_CATEGORY_COLORS = {
  methodological: 'bg-surface-hover/50 text-text-secondary border-border-subtle',
  population: 'bg-surface-hover/50 text-text-secondary border-border-subtle',
  theoretical: 'bg-surface-hover/50 text-text-secondary border-border-subtle',
  temporal: 'bg-surface-hover/50 text-text-secondary border-border-subtle'
}

type InsightsTab = 'overview' | 'gaps' | 'methodology'

export default function ProjectInsights({ projectId, onOpenLiteratureReview: _onOpenLiteratureReview }: ProjectInsightsProps) {
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<'not_analyzed' | 'analyzing' | 'analyzed' | 'failed'>('not_analyzed')
  const [insights, setInsights] = useState<Insights | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pollingInterval, setPollingInterval] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<InsightsTab>('overview')
  const [insightsDocCount, setInsightsDocCount] = useState<number>(0)
  const [_currentAnalyzedCount, setCurrentAnalyzedCount] = useState<number>(0)
  const [_isStale, setIsStale] = useState<boolean>(false)

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

  const loadInsights = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      const data = await api.projects.getInsights(session.access_token, projectId)

      setStatus(data.status)

      if (data.status === 'analyzed') {
        setInsights(data.insights)
        setInsightsDocCount(data.insights_doc_count || 0)
        setCurrentAnalyzedCount(data.current_analyzed_count || 0)
        setIsStale(data.is_stale || false)
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
      <div className="bg-surface rounded-lg border border-border-base p-8 text-center">
        <div className="max-w-md mx-auto">
          <div className="h-16 w-16 mx-auto mb-4 rounded-full bg-accent-primary/10 flex items-center justify-center">
            <LightBulbIcon className="h-8 w-8 text-accent-primary" />
          </div>
          <h3 className="text-xl font-serif font-semibold text-text-primary mb-2">
            Project Insights & Research Gaps
          </h3>
          <p className="text-text-tertiary mb-6">
            Analyze all papers in this project to identify research gaps, common themes, methodological patterns, and more.
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
      <div className="bg-surface rounded-lg border border-border-base p-8 text-center">
        <div className="max-w-md mx-auto">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent mb-4"></div>
          <h3 className="text-xl font-serif font-semibold text-text-primary mb-2">
            {insightsDocCount > 0 ? 'Updating Insights...' : 'Analyzing Project...'}
          </h3>
          <p className="text-text-tertiary">
            {insightsDocCount > 0
              ? 'Auto-regenerating insights with the latest documents. This may take 30-60 seconds.'
              : 'Our AI is analyzing all papers to identify cross-paper insights, research gaps, and patterns. This may take 30-60 seconds.'
            }
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
          <h3 className="text-xl font-serif font-semibold text-text-primary mb-2">
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
    <div className="space-y-6">
      {/* Success Banner */}
      <div className="bg-surface border border-border-base rounded-lg p-4 flex items-start gap-3 border-l-4 border-l-success">
        <CheckCircleIcon className="h-6 w-6 text-success shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="text-text-primary font-medium">Insights Analysis Complete</h4>
          <p className="text-text-secondary text-sm mt-1">
            Analyzed {insights.analysis_metadata?.num_papers_analyzed || 0} papers
          </p>
        </div>
      </div>

      {/* Phase 4.3: Removed manual regenerate button - auto-regeneration handles this */}
      {/* Insights auto-update when new documents are added (see Phase 2) */}

      {/* Sub-Tabs Navigation */}
      <div className="border-b border-border-base">
        <nav className="flex gap-1 overflow-x-auto">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'overview'
                ? 'border-accent-primary text-text-primary'
                : 'border-transparent text-text-tertiary hover:text-text-secondary'
            }`}
          >
            Overview & Analysis
          </button>
          <button
            onClick={() => setActiveTab('gaps')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'gaps'
                ? 'border-accent-primary text-text-primary'
                : 'border-transparent text-text-tertiary hover:text-text-secondary'
            }`}
          >
            Research Gaps & Questions
          </button>
          <button
            onClick={() => setActiveTab('methodology')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'methodology'
                ? 'border-accent-primary text-text-primary'
                : 'border-transparent text-text-tertiary hover:text-text-secondary'
            }`}
          >
            Methodology Recommendations
          </button>
        </nav>
      </div>

      {/* Overview & Analysis Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Summary */}
          {insights.summary && (
            <div className="bg-surface rounded-lg border border-border-base p-6">
              <h3 className="text-lg font-serif font-semibold text-text-primary mb-3">Overview</h3>
              <p className="text-text-secondary leading-relaxed">{insights.summary}</p>
            </div>
          )}

          {/* Key Insights */}
          {insights.key_insights && insights.key_insights.length > 0 && (
            <div className="bg-surface rounded-lg border border-border-base p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-accent-primary/10 rounded-lg">
                  <LightBulbIcon className="h-5 w-5 text-accent-primary" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-text-primary">Key Insights</h3>
              </div>
              <ul className="list-disc list-outside ml-5 space-y-2">
                {insights.key_insights.map((insight, i) => (
                  <li key={i} className="text-text-secondary leading-relaxed">{insight}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Common Themes */}
          {insights.common_themes && insights.common_themes.length > 0 && (
            <div className="bg-surface rounded-lg border border-border-base p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-slate-700/50 rounded-lg">
                  <DocumentTextIcon className="h-5 w-5 text-slate-300" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-text-primary">Common Themes</h3>
              </div>
              <div className="space-y-3">
                {insights.common_themes.map((theme, i) => (
                  <div key={i} className="bg-surface/50 rounded-lg p-4 border border-border-subtle">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold text-text-primary">{theme.theme}</h4>
                      <span className="text-xs text-text-secondary font-mono">
                        {theme.frequency} paper{theme.frequency !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <p className="text-sm text-text-secondary">{theme.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Methodological Patterns */}
          {insights.methodological_patterns && insights.methodological_patterns.length > 0 && (
            <div className="bg-surface rounded-lg border border-border-base p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-slate-700/50 rounded-lg">
                  <BeakerIcon className="h-5 w-5 text-slate-300" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-text-primary">Methodological Patterns</h3>
              </div>
              <div className="space-y-3">
                {insights.methodological_patterns.map((pattern, i) => (
                  <div key={i} className="bg-surface/50 rounded-lg p-4 border border-border-subtle">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold text-text-primary">{pattern.methodology}</h4>
                      <span className="text-xs text-text-secondary font-mono">
                        Used by {pattern.usage_count}
                      </span>
                    </div>
                    <p className="text-sm text-text-secondary mb-2">{pattern.description}</p>
                    {pattern.variations && pattern.variations.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {pattern.variations.map((variation, j) => (
                          <Badge key={j} variant="info">
                            {variation}
                          </Badge>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Citation Patterns */}
          {insights.citation_patterns && insights.citation_patterns.length > 0 && (
            <div className="bg-surface rounded-lg border border-border-base p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-slate-700/50 rounded-lg">
                  <DocumentTextIcon className="h-5 w-5 text-slate-300" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-text-primary">Citation Patterns</h3>
              </div>
              <div className="space-y-3">
                {insights.citation_patterns.map((pattern, i) => (
                  <div key={i} className="bg-surface/50 rounded-lg p-4 border border-border-subtle">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold text-text-primary">{pattern.cited_work}</h4>
                      <span className="text-xs text-text-secondary font-mono">
                        Cited {pattern.frequency}x
                      </span>
                    </div>
                    <p className="text-sm text-text-secondary">{pattern.context}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timeline */}
          {insights.timeline && insights.timeline.length > 0 && (
            <div className="bg-surface rounded-lg border border-border-base p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-slate-700/50 rounded-lg">
                  <ClockIcon className="h-5 w-5 text-slate-300" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-text-primary">Timeline & Evolution</h3>
              </div>
              <div className="space-y-3">
                {insights.timeline.map((item, i) => (
                  <div key={i} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <div className="w-3 h-3 rounded-full bg-slate-400"></div>
                      {i < insights.timeline!.length - 1 && (
                        <div className="w-0.5 h-full bg-slate-600/50 my-1"></div>
                      )}
                    </div>
                    <div className="flex-1 pb-4">
                      <h4 className="font-semibold text-text-primary mb-1">{item.period}</h4>
                      <p className="text-sm text-text-secondary">{item.development}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Conflicting Findings */}
          {insights.conflicting_findings && insights.conflicting_findings.length > 0 && (
            <div className="bg-surface rounded-lg border border-border-base p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-slate-700/50 rounded-lg">
                  <ExclamationTriangleIcon className="h-5 w-5 text-slate-300" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-text-primary">Conflicting Findings</h3>
              </div>
              <div className="space-y-4">
                {insights.conflicting_findings.map((conflict, i) => (
                  <div key={i} className="bg-surface/50 rounded-lg p-4 border border-border-subtle">
                    <h4 className="font-semibold text-text-primary mb-3">{conflict.topic}</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                      <div className="border-l-2 border-slate-500 pl-3">
                        <p className="text-xs font-semibold text-slate-400 mb-1">Position A:</p>
                        <p className="text-sm text-text-secondary mb-2">{conflict.side_a.position}</p>
                        <p className="text-xs text-text-tertiary">{conflict.side_a.evidence}</p>
                      </div>
                      <div className="border-l-2 border-slate-600 pl-3">
                        <p className="text-xs font-semibold text-slate-400 mb-1">Position B:</p>
                        <p className="text-sm text-text-secondary mb-2">{conflict.side_b.position}</p>
                        <p className="text-xs text-text-tertiary">{conflict.side_b.evidence}</p>
                      </div>
                    </div>
                    {conflict.resolution && (
                      <div className="border-t border-border-subtle pt-3 mt-3">
                        <p className="text-xs font-semibold text-text-tertiary mb-1">Possible Resolution:</p>
                        <p className="text-sm text-text-secondary">{conflict.resolution}</p>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Research Gaps & Questions Tab */}
      {activeTab === 'gaps' && (
        <div className="space-y-6">
          {/* Research Gaps */}
          {insights.research_gaps && insights.research_gaps.length > 0 && (
            <div className="bg-surface rounded-lg border border-border-base p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-slate-700/50 rounded-lg">
                  <ExclamationTriangleIcon className="h-5 w-5 text-slate-300" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-text-primary">Research Gaps Identified</h3>
              </div>
              <div className="space-y-4">
                {insights.research_gaps.map((gap, i) => (
                  <div key={i} className={`border rounded-lg p-4 ${GAP_CATEGORY_COLORS[gap.category]}`}>
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold">{gap.title}</h4>
                      <span className="text-xs uppercase px-2 py-1 rounded bg-surface/30 font-mono">
                        {gap.category}
                      </span>
                    </div>
                    <p className="text-sm mb-3 opacity-90">{gap.description}</p>

                    {gap.supporting_evidence && gap.supporting_evidence.length > 0 && (
                      <div className="mb-3">
                        <p className="text-xs font-semibold mb-1">Evidence:</p>
                        <ul className="text-xs space-y-1 opacity-80">
                          {gap.supporting_evidence.map((evidence, j) => (
                            <li key={j}>• {evidence}</li>
                          ))}
                        </ul>
                      </div>
                    )}

                    {gap.suggested_directions && gap.suggested_directions.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold mb-1">Suggested Research Directions:</p>
                        <ul className="text-xs space-y-1 opacity-80">
                          {gap.suggested_directions.map((direction, j) => (
                            <li key={j}>→ {direction}</li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Research Questions */}
          <ResearchQuestions projectId={projectId} insightsStatus={status} hideMethodology={true} />
        </div>
      )}

      {/* Methodology Recommendations Tab */}
      {activeTab === 'methodology' && (
        <div className="space-y-6">
          <div className="bg-surface rounded-lg border border-border-base p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-slate-700/50 rounded-lg">
                <BeakerIcon className="h-5 w-5 text-slate-300" />
              </div>
              <h3 className="text-lg font-serif font-semibold text-text-primary">Methodology Recommendations</h3>
            </div>
            <p className="text-sm text-text-secondary mb-4">
              AI-generated methodology recommendations for your research questions. Generate recommendations for specific questions to see detailed methodological approaches.
            </p>
          </div>

          {/* Research Questions with Methodology Focus */}
          <ResearchQuestions projectId={projectId} insightsStatus={status} methodologyOnly={true} />
        </div>
      )}
    </div>
  )
}

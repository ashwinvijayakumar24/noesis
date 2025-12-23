import { useState, useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import ResearchQuestions from './ResearchQuestions'
import PaperRecommendations from './PaperRecommendations'
import {
  SparklesIcon,
  LightBulbIcon,
  BeakerIcon,
  ExclamationTriangleIcon,
  ClockIcon,
  DocumentTextIcon,
  CheckCircleIcon,
  XCircleIcon,
  ArrowPathIcon,
  ArrowsRightLeftIcon
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
  methodological: 'bg-neutral-800/50 text-neutral-300 border-neutral-700',
  population: 'bg-neutral-800/50 text-neutral-300 border-neutral-700',
  theoretical: 'bg-neutral-800/50 text-neutral-300 border-neutral-700',
  temporal: 'bg-neutral-800/50 text-neutral-300 border-neutral-700'
}

type InsightsTab = 'overview' | 'gaps' | 'discover'

export default function ProjectInsights({ projectId, onOpenLiteratureReview: _onOpenLiteratureReview }: ProjectInsightsProps) {
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<'not_analyzed' | 'analyzing' | 'analyzed' | 'failed'>('not_analyzed')
  const [insights, setInsights] = useState<Insights | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pollingInterval, setPollingInterval] = useState<number | null>(null)
  const [activeTab, setActiveTab] = useState<InsightsTab>('overview')
  const [insightsDocCount, setInsightsDocCount] = useState<number>(0)
  const [currentAnalyzedCount, setCurrentAnalyzedCount] = useState<number>(0)
  const [isStale, setIsStale] = useState<boolean>(false)

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
          <p className="text-neutral-400 text-sm mt-3">Loading...</p>
        </div>
      </div>
    )
  }

  if (status === 'not_analyzed') {
    return (
      <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-8 text-center">
        <div className="max-w-md mx-auto">
          <div className="h-16 w-16 mx-auto mb-4 rounded-full bg-accent-primary/10 flex items-center justify-center">
            <LightBulbIcon className="h-8 w-8 text-accent-primary" />
          </div>
          <h3 className="text-xl font-serif font-semibold text-neutral-50 mb-2">
            Project Insights & Research Gaps
          </h3>
          <p className="text-neutral-400 mb-6">
            Analyze all papers in this project to identify research gaps, common themes, methodological patterns, and more.
          </p>
          <button
            onClick={handleAnalyze}
            className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2 mx-auto"
          >
            <SparklesIcon className="h-5 w-5" />
            Analyze Project Insights
          </button>
        </div>
      </div>
    )
  }

  if (status === 'analyzing') {
    return (
      <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-8 text-center">
        <div className="max-w-md mx-auto">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent mb-4"></div>
          <h3 className="text-xl font-serif font-semibold text-neutral-50 mb-2">
            Analyzing Project...
          </h3>
          <p className="text-neutral-400">
            Our AI is analyzing all papers to identify cross-paper insights, research gaps, and patterns. This may take 30-60 seconds.
          </p>
        </div>
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div className="bg-neutral-900 rounded-lg border border-red-900/50 p-8 text-center">
        <div className="max-w-md mx-auto">
          <XCircleIcon className="h-16 w-16 text-red-500 mx-auto mb-4" />
          <h3 className="text-xl font-serif font-semibold text-neutral-50 mb-2">
            Analysis Failed
          </h3>
          <p className="text-neutral-400 mb-4">
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
      <div className="bg-green-900/20 border border-green-600/30 rounded-lg p-4 flex items-start gap-3">
        <CheckCircleIcon className="h-6 w-6 text-green-400 shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="text-green-200 font-medium">Insights Analysis Complete</h4>
          <p className="text-green-300/70 text-sm mt-1">
            Analyzed {insights.analysis_metadata?.num_papers_analyzed || 0} papers
          </p>
        </div>
      </div>

      {/* Stale Insights Warning Banner */}
      {isStale && (
        <div className="bg-yellow-900/20 border border-yellow-600/30 rounded-lg p-4 flex items-start gap-3">
          <ExclamationTriangleIcon className="h-6 w-6 text-yellow-400 shrink-0 mt-0.5" />
          <div className="flex-1">
            <h4 className="text-yellow-200 font-medium">New Documents Added</h4>
            <p className="text-yellow-300/70 text-sm mt-1">
              Your insights were generated from {insightsDocCount} paper{insightsDocCount !== 1 ? 's' : ''}.
              You now have {currentAnalyzedCount} analyzed paper{currentAnalyzedCount !== 1 ? 's' : ''}.
            </p>
            <p className="text-yellow-300/70 text-sm mt-1">
              Regenerate insights to include the latest documents for the most accurate analysis.
            </p>
            <button
              onClick={handleAnalyze}
              className="mt-3 px-4 py-2 bg-yellow-600 text-white text-sm font-semibold rounded-lg hover:bg-yellow-700 transition-colors flex items-center gap-2"
            >
              <ArrowsRightLeftIcon className="h-4 w-4" />
              Regenerate Insights
            </button>
          </div>
        </div>
      )}

      {/* Sub-Tabs Navigation */}
      <div className="border-b border-neutral-800">
        <nav className="flex gap-1 overflow-x-auto">
          <button
            onClick={() => setActiveTab('overview')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'overview'
                ? 'border-accent-primary text-neutral-50'
                : 'border-transparent text-neutral-400 hover:text-neutral-300'
            }`}
          >
            Overview & Analysis
          </button>
          <button
            onClick={() => setActiveTab('gaps')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'gaps'
                ? 'border-accent-primary text-neutral-50'
                : 'border-transparent text-neutral-400 hover:text-neutral-300'
            }`}
          >
            Research Gaps & Questions
          </button>
          <button
            onClick={() => setActiveTab('discover')}
            className={`px-4 py-3 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'discover'
                ? 'border-accent-primary text-neutral-50'
                : 'border-transparent text-neutral-400 hover:text-neutral-300'
            }`}
          >
            Discover Papers
          </button>
        </nav>
      </div>

      {/* Overview & Analysis Tab */}
      {activeTab === 'overview' && (
        <div className="space-y-6">
          {/* Summary */}
          {insights.summary && (
            <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6">
              <h3 className="text-lg font-serif font-semibold text-neutral-50 mb-3">Overview</h3>
              <p className="text-neutral-300 leading-relaxed">{insights.summary}</p>
            </div>
          )}

          {/* Key Insights */}
          {insights.key_insights && insights.key_insights.length > 0 && (
            <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-accent-primary/10 rounded-lg">
                  <SparklesIcon className="h-5 w-5 text-accent-primary" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-neutral-50">Key Insights</h3>
              </div>
              <ul className="list-disc list-outside ml-5 space-y-2">
                {insights.key_insights.map((insight, i) => (
                  <li key={i} className="text-neutral-300 leading-relaxed">{insight}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Common Themes */}
          {insights.common_themes && insights.common_themes.length > 0 && (
            <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-purple-600/20 rounded-lg">
                  <DocumentTextIcon className="h-5 w-5 text-purple-400" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-neutral-50">Common Themes</h3>
              </div>
              <div className="space-y-3">
                {insights.common_themes.map((theme, i) => (
                  <div key={i} className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800/50">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold text-purple-300">{theme.theme}</h4>
                      <span className="text-xs text-purple-400 font-mono">
                        {theme.frequency} paper{theme.frequency !== 1 ? 's' : ''}
                      </span>
                    </div>
                    <p className="text-sm text-neutral-300">{theme.description}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Methodological Patterns */}
          {insights.methodological_patterns && insights.methodological_patterns.length > 0 && (
            <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-blue-600/20 rounded-lg">
                  <BeakerIcon className="h-5 w-5 text-blue-400" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-neutral-50">Methodological Patterns</h3>
              </div>
              <div className="space-y-3">
                {insights.methodological_patterns.map((pattern, i) => (
                  <div key={i} className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800/50">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold text-blue-300">{pattern.methodology}</h4>
                      <span className="text-xs text-blue-400 font-mono">
                        Used by {pattern.usage_count}
                      </span>
                    </div>
                    <p className="text-sm text-neutral-300 mb-2">{pattern.description}</p>
                    {pattern.variations && pattern.variations.length > 0 && (
                      <div className="flex flex-wrap gap-2 mt-2">
                        {pattern.variations.map((variation, j) => (
                          <span key={j} className="text-xs px-2 py-1 bg-blue-900/30 text-blue-200 rounded">
                            {variation}
                          </span>
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
            <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-indigo-600/20 rounded-lg">
                  <DocumentTextIcon className="h-5 w-5 text-indigo-400" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-neutral-50">Citation Patterns</h3>
              </div>
              <div className="space-y-3">
                {insights.citation_patterns.map((pattern, i) => (
                  <div key={i} className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800/50">
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold text-indigo-300">{pattern.cited_work}</h4>
                      <span className="text-xs text-indigo-400 font-mono">
                        Cited {pattern.frequency}x
                      </span>
                    </div>
                    <p className="text-sm text-neutral-300">{pattern.context}</p>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Timeline */}
          {insights.timeline && insights.timeline.length > 0 && (
            <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-green-600/20 rounded-lg">
                  <ClockIcon className="h-5 w-5 text-green-400" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-neutral-50">Timeline & Evolution</h3>
              </div>
              <div className="space-y-3">
                {insights.timeline.map((item, i) => (
                  <div key={i} className="flex gap-4">
                    <div className="flex flex-col items-center">
                      <div className="w-3 h-3 rounded-full bg-green-500"></div>
                      {i < insights.timeline!.length - 1 && (
                        <div className="w-0.5 h-full bg-green-500/30 my-1"></div>
                      )}
                    </div>
                    <div className="flex-1 pb-4">
                      <h4 className="font-semibold text-green-300 mb-1">{item.period}</h4>
                      <p className="text-sm text-neutral-300">{item.development}</p>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Conflicting Findings */}
          {insights.conflicting_findings && insights.conflicting_findings.length > 0 && (
            <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-red-600/20 rounded-lg">
                  <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-neutral-50">Conflicting Findings</h3>
              </div>
              <div className="space-y-4">
                {insights.conflicting_findings.map((conflict, i) => (
                  <div key={i} className="bg-neutral-900/50 rounded-lg p-4 border border-neutral-800/50">
                    <h4 className="font-semibold text-red-300 mb-3">{conflict.topic}</h4>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                      <div className="border-l-2 border-blue-500 pl-3">
                        <p className="text-xs font-semibold text-blue-400 mb-1">Position A:</p>
                        <p className="text-sm text-neutral-300 mb-2">{conflict.side_a.position}</p>
                        <p className="text-xs text-neutral-400">{conflict.side_a.evidence}</p>
                      </div>
                      <div className="border-l-2 border-orange-500 pl-3">
                        <p className="text-xs font-semibold text-orange-400 mb-1">Position B:</p>
                        <p className="text-sm text-neutral-300 mb-2">{conflict.side_b.position}</p>
                        <p className="text-xs text-neutral-400">{conflict.side_b.evidence}</p>
                      </div>
                    </div>
                    {conflict.resolution && (
                      <div className="border-t border-neutral-700 pt-3 mt-3">
                        <p className="text-xs font-semibold text-neutral-400 mb-1">Possible Resolution:</p>
                        <p className="text-sm text-neutral-300">{conflict.resolution}</p>
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
            <div className="bg-neutral-900 rounded-lg border border-neutral-800 p-6">
              <div className="flex items-center gap-3 mb-4">
                <div className="p-2 bg-yellow-600/20 rounded-lg">
                  <ExclamationTriangleIcon className="h-5 w-5 text-yellow-400" />
                </div>
                <h3 className="text-lg font-serif font-semibold text-neutral-50">Research Gaps Identified</h3>
              </div>
              <div className="space-y-4">
                {insights.research_gaps.map((gap, i) => (
                  <div key={i} className={`border rounded-lg p-4 ${GAP_CATEGORY_COLORS[gap.category]}`}>
                    <div className="flex items-start justify-between mb-2">
                      <h4 className="font-semibold">{gap.title}</h4>
                      <span className="text-xs uppercase px-2 py-1 rounded bg-neutral-900/30 font-mono">
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
          <ResearchQuestions projectId={projectId} insightsStatus={status} />
        </div>
      )}

      {/* Discover Papers Tab */}
      {activeTab === 'discover' && (
        <div className="space-y-6">
          {/* Loading State Message */}
          <div className="bg-blue-900/20 border border-blue-600/30 rounded-lg p-4 flex items-start gap-3">
            <div className="p-2 bg-blue-600/20 rounded-lg shrink-0">
              <ClockIcon className="h-5 w-5 text-blue-400" />
            </div>
            <div className="flex-1">
              <h4 className="text-blue-200 font-medium">Discovering Relevant Papers</h4>
              <p className="text-blue-300/70 text-sm mt-1">
                Finding relevant papers may take 30 seconds to 1 minute. The AI is searching academic databases and analyzing relevance to your research.
              </p>
            </div>
          </div>

          {/* Paper Recommendations */}
          <PaperRecommendations projectId={projectId} />
        </div>
      )}
    </div>
  )
}

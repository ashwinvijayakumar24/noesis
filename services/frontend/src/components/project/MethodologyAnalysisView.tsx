import { useState } from 'react'
import {
  ChartBarIcon,
  SparklesIcon,
  DocumentTextIcon,
  BeakerIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  ChevronDownIcon,
  ChevronUpIcon
} from '@heroicons/react/24/outline'
import { Badge } from '../ui/Badge'

interface MethodologyAnalysisViewProps {
  insights: any | null
  projectId: string
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

export default function MethodologyAnalysisView({ insights, projectId }: MethodologyAnalysisViewProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(new Set(['summary']))

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections)
    if (newExpanded.has(section)) {
      newExpanded.delete(section)
    } else {
      newExpanded.add(section)
    }
    setExpandedSections(newExpanded)
  }

  if (!insights) {
    return (
      <div className="bg-surface/50 rounded-lg border border-border-base p-12 text-center">
        <div className="max-w-md mx-auto">
          <div className="p-3 bg-emerald-500/10 rounded-lg inline-block mb-4">
            <ChartBarIcon className="h-12 w-12 text-emerald-400" />
          </div>
          <h3 className="text-xl font-serif font-semibold text-text-primary mb-2">
            Insights Analysis Required
          </h3>
          <p className="text-text-tertiary mb-4">
            Please analyze project insights first before viewing methodology analysis.
          </p>
          <p className="text-sm text-text-muted">
            Click <strong>"Analyze Insights"</strong> in the sidebar
          </p>
        </div>
      </div>
    )
  }

  const commonThemes: CommonTheme[] = insights.common_themes || []
  const methodologicalPatterns: MethodologicalPattern[] = insights.methodological_patterns || []
  const timeline: TimelineItem[] = insights.timeline || []
  const conflictingFindings: ConflictingFinding[] = insights.conflicting_findings || []
  const citationPatterns: CitationPattern[] = insights.citation_patterns || []

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-emerald-500/10 rounded-lg">
            <ChartBarIcon className="h-6 w-6 text-emerald-400" />
          </div>
          <div>
            <h2 className="text-2xl font-serif font-semibold text-text-primary">
              Methodology & Analysis
            </h2>
            <p className="text-sm text-text-tertiary">
              Deep insights into methodological patterns, themes, and analysis
            </p>
          </div>
        </div>
      </div>

      {/* Accordion Sections */}
      <div className="space-y-4">
        {/* Project Overview */}
        {insights.summary && (
          <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
            <button
              onClick={() => toggleSection('summary')}
              className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
            >
              <div className="flex items-center gap-3">
                <SparklesIcon className="h-5 w-5 text-accent-primary" />
                <h3 className="text-lg font-serif font-semibold text-text-primary">Project Overview</h3>
              </div>
              {expandedSections.has('summary') ? (
                <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
              ) : (
                <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
              )}
            </button>

            {expandedSections.has('summary') && (
              <div className="px-6 pb-6">
                <p className="text-text-secondary leading-relaxed">{insights.summary}</p>

                {/* Key Insights */}
                {insights.key_insights && insights.key_insights.length > 0 && (
                  <div className="mt-4 pt-4 border-t border-border-subtle">
                    <h4 className="text-sm font-semibold text-text-primary mb-2">Key Insights</h4>
                    <ul className="list-disc list-outside ml-5 space-y-2">
                      {insights.key_insights.map((insight: string, i: number) => (
                        <li key={i} className="text-text-secondary leading-relaxed text-sm">{insight}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* Common Themes */}
        {commonThemes.length > 0 && (
          <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
            <button
              onClick={() => toggleSection('themes')}
              className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
            >
              <div className="flex items-center gap-3">
                <DocumentTextIcon className="h-5 w-5 text-purple-400" />
                <h3 className="text-lg font-serif font-semibold text-text-primary">
                  Common Themes ({commonThemes.length})
                </h3>
              </div>
              {expandedSections.has('themes') ? (
                <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
              ) : (
                <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
              )}
            </button>

            {expandedSections.has('themes') && (
              <div className="px-6 pb-6">
                <div className="space-y-3">
                  {commonThemes.map((theme, i) => (
                    <div key={i} className="bg-surface/50 rounded-lg p-4 border border-border-subtle">
                      <div className="flex items-start justify-between mb-2">
                        <h4 className="font-semibold text-purple-300">{theme.theme}</h4>
                        <span className="text-xs text-purple-400 font-mono">
                          {theme.frequency} paper{theme.frequency !== 1 ? 's' : ''}
                        </span>
                      </div>
                      <p className="text-sm text-text-secondary">{theme.description}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Methodological Patterns */}
        {methodologicalPatterns.length > 0 && (
          <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
            <button
              onClick={() => toggleSection('patterns')}
              className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
            >
              <div className="flex items-center gap-3">
                <BeakerIcon className="h-5 w-5 text-blue-400" />
                <h3 className="text-lg font-serif font-semibold text-text-primary">
                  Methodological Patterns ({methodologicalPatterns.length})
                </h3>
              </div>
              {expandedSections.has('patterns') ? (
                <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
              ) : (
                <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
              )}
            </button>

            {expandedSections.has('patterns') && (
              <div className="px-6 pb-6">
                <div className="space-y-3">
                  {methodologicalPatterns.map((pattern, i) => (
                    <div key={i} className="bg-surface/50 rounded-lg p-4 border border-border-subtle">
                      <div className="flex items-start justify-between mb-2">
                        <h4 className="font-semibold text-blue-300">{pattern.methodology}</h4>
                        <span className="text-xs text-blue-400 font-mono">
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
          </div>
        )}

        {/* Citation Patterns */}
        {citationPatterns.length > 0 && (
          <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
            <button
              onClick={() => toggleSection('citations')}
              className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
            >
              <div className="flex items-center gap-3">
                <DocumentTextIcon className="h-5 w-5 text-indigo-400" />
                <h3 className="text-lg font-serif font-semibold text-text-primary">
                  Citation Patterns ({citationPatterns.length})
                </h3>
              </div>
              {expandedSections.has('citations') ? (
                <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
              ) : (
                <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
              )}
            </button>

            {expandedSections.has('citations') && (
              <div className="px-6 pb-6">
                <div className="space-y-3">
                  {citationPatterns.map((pattern, i) => (
                    <div key={i} className="bg-surface/50 rounded-lg p-4 border border-border-subtle">
                      <div className="flex items-start justify-between mb-2">
                        <h4 className="font-semibold text-indigo-300">{pattern.cited_work}</h4>
                        <span className="text-xs text-indigo-400 font-mono">
                          Cited {pattern.frequency}x
                        </span>
                      </div>
                      <p className="text-sm text-text-secondary">{pattern.context}</p>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Timeline & Evolution */}
        {timeline.length > 0 && (
          <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
            <button
              onClick={() => toggleSection('timeline')}
              className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
            >
              <div className="flex items-center gap-3">
                <ClockIcon className="h-5 w-5 text-green-400" />
                <h3 className="text-lg font-serif font-semibold text-text-primary">
                  Timeline & Evolution
                </h3>
              </div>
              {expandedSections.has('timeline') ? (
                <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
              ) : (
                <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
              )}
            </button>

            {expandedSections.has('timeline') && (
              <div className="px-6 pb-6">
                <div className="space-y-3">
                  {timeline.map((item, i) => (
                    <div key={i} className="flex gap-4">
                      <div className="flex flex-col items-center">
                        <div className="w-3 h-3 rounded-full bg-emerald-500"></div>
                        {i < timeline.length - 1 && (
                          <div className="w-0.5 h-full bg-emerald-500/30 my-1"></div>
                        )}
                      </div>
                      <div className="flex-1 pb-4">
                        <h4 className="font-semibold text-emerald-300 mb-1">{item.period}</h4>
                        <p className="text-sm text-text-secondary">{item.development}</p>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Conflicting Findings */}
        {conflictingFindings.length > 0 && (
          <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
            <button
              onClick={() => toggleSection('conflicts')}
              className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
            >
              <div className="flex items-center gap-3">
                <ExclamationTriangleIcon className="h-5 w-5 text-red-400" />
                <h3 className="text-lg font-serif font-semibold text-text-primary">
                  Conflicting Findings ({conflictingFindings.length})
                </h3>
              </div>
              {expandedSections.has('conflicts') ? (
                <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
              ) : (
                <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
              )}
            </button>

            {expandedSections.has('conflicts') && (
              <div className="px-6 pb-6">
                <div className="space-y-4">
                  {conflictingFindings.map((conflict, i) => (
                    <div key={i} className="bg-surface/50 rounded-lg p-4 border border-border-subtle">
                      <h4 className="font-semibold text-red-300 mb-3">{conflict.topic}</h4>
                      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-3">
                        <div className="border-l-2 border-blue-500 pl-3">
                          <p className="text-xs font-semibold text-blue-400 mb-1">Position A:</p>
                          <p className="text-sm text-text-secondary mb-2">{conflict.side_a.position}</p>
                          <p className="text-xs text-text-tertiary">{conflict.side_a.evidence}</p>
                        </div>
                        <div className="border-l-2 border-amber-500 pl-3">
                          <p className="text-xs font-semibold text-amber-400 mb-1">Position B:</p>
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
      </div>
    </div>
  )
}

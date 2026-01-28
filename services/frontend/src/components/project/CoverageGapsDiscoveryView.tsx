import { useState } from 'react'
import {
  XMarkIcon,
  ChartBarIcon,
  ExclamationTriangleIcon,
  AcademicCapIcon,
  ChevronDownIcon,
  ChevronUpIcon
} from '@heroicons/react/24/outline'
import PaperRecommendations from '../PaperRecommendations'

interface CoverageGapsDiscoveryViewProps {
  insights: any | null
  projectId: string
  onClose: () => void
}

interface CommonTheme {
  theme: string
  frequency: number
  description: string
  paper_titles?: string[]
}

interface ResearchGap {
  category: 'methodological' | 'population' | 'theoretical' | 'temporal'
  title: string
  description: string
  supporting_evidence: string[]
  suggested_directions: string[]
}

const GAP_CATEGORY_COLORS = {
  methodological: 'bg-blue-600/20 text-blue-400 border-blue-600/30',
  population: 'bg-purple-600/20 text-purple-400 border-purple-600/30',
  theoretical: 'bg-amber-600/20 text-amber-400 border-amber-600/30',
  temporal: 'bg-green-600/20 text-green-400 border-green-600/30'
}

export default function CoverageGapsDiscoveryView({
  insights,
  projectId,
  onClose
}: CoverageGapsDiscoveryViewProps) {
  const [expandedSections, setExpandedSections] = useState<Set<string>>(
    new Set(['coverage', 'gaps', 'discovery'])
  )

  const toggleSection = (section: string) => {
    const newExpanded = new Set(expandedSections)
    if (newExpanded.has(section)) {
      newExpanded.delete(section)
    } else {
      newExpanded.add(section)
    }
    setExpandedSections(newExpanded)
  }

  const commonThemes: CommonTheme[] = insights?.common_themes || []
  const researchGaps: ResearchGap[] = insights?.research_gaps || []

  return (
    <div className="fixed inset-0 z-50 overflow-hidden bg-black/60 backdrop-blur-sm">
      <div className="flex items-center justify-center min-h-screen p-4">
        <div className="bg-surface-base w-full max-w-6xl max-h-[90vh] rounded-xl border border-border-base shadow-2xl flex flex-col">
          {/* Header */}
          <div className="flex items-center justify-between p-6 border-b border-border-base shrink-0">
            <div className="flex items-center gap-3">
              <div className="p-2 bg-orange-600/20 rounded-lg">
                <ChartBarIcon className="h-6 w-6 text-orange-400" />
              </div>
              <div>
                <h2 className="text-2xl font-serif font-semibold text-text-primary">
                  Coverage, Gaps & Discovery
                </h2>
                <p className="text-sm text-text-tertiary">
                  Analyze your literature coverage, identify gaps, and discover relevant papers
                </p>
              </div>
            </div>
            <button
              onClick={onClose}
              className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
            >
              <XMarkIcon className="h-6 w-6 text-text-tertiary" />
            </button>
          </div>

          {/* Scrollable Content */}
          <div className="flex-1 overflow-y-auto p-6">
            <div className="space-y-6">
              {/* Section 1: Coverage Overview */}
              <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
                <button
                  onClick={() => toggleSection('coverage')}
                  className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <ChartBarIcon className="h-5 w-5 text-emerald-400" />
                    <h3 className="text-lg font-serif font-semibold text-text-primary">
                      Coverage Overview ({commonThemes.length} themes)
                    </h3>
                  </div>
                  {expandedSections.has('coverage') ? (
                    <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
                  ) : (
                    <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
                  )}
                </button>

                {expandedSections.has('coverage') && (
                  <div className="px-6 pb-6">
                    {commonThemes.length === 0 ? (
                      <p className="text-text-tertiary text-sm">
                        No coverage analysis available. Ensure insights have been analyzed.
                      </p>
                    ) : (
                      <>
                        <p className="text-sm text-text-secondary mb-4">
                          These themes represent well-covered topics in your literature collection:
                        </p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {commonThemes.map((theme, i) => (
                            <div
                              key={i}
                              className="bg-surface/50 rounded-lg p-4 border border-border-subtle"
                            >
                              <div className="flex items-start justify-between mb-2">
                                <h4 className="font-semibold text-emerald-300">{theme.theme}</h4>
                                <span className="text-xs text-emerald-400 font-mono">
                                  {theme.frequency} paper{theme.frequency !== 1 ? 's' : ''}
                                </span>
                              </div>
                              <p className="text-sm text-text-secondary">{theme.description}</p>
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Section 2: Research Gaps */}
              <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
                <button
                  onClick={() => toggleSection('gaps')}
                  className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <ExclamationTriangleIcon className="h-5 w-5 text-amber-400" />
                    <h3 className="text-lg font-serif font-semibold text-text-primary">
                      Research Gaps Identified ({researchGaps.length})
                    </h3>
                  </div>
                  {expandedSections.has('gaps') ? (
                    <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
                  ) : (
                    <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
                  )}
                </button>

                {expandedSections.has('gaps') && (
                  <div className="px-6 pb-6">
                    {researchGaps.length === 0 ? (
                      <p className="text-text-tertiary text-sm">
                        No research gaps identified. Ensure insights have been analyzed.
                      </p>
                    ) : (
                      <>
                        <p className="text-sm text-text-secondary mb-4">
                          Areas where existing research is limited or missing:
                        </p>
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                          {researchGaps.map((gap, i) => (
                            <div
                              key={i}
                              className={`border rounded-lg p-4 ${GAP_CATEGORY_COLORS[gap.category]}`}
                            >
                              <div className="flex items-start justify-between mb-2">
                                <h4 className="font-semibold text-text-primary">{gap.title}</h4>
                                <span className="text-xs uppercase px-2 py-1 rounded bg-surface/30 font-mono text-text-muted">
                                  {gap.category}
                                </span>
                              </div>
                              <p className="text-sm mb-3 text-text-secondary">{gap.description}</p>

                              {gap.supporting_evidence && gap.supporting_evidence.length > 0 && (
                                <div className="mb-3">
                                  <p className="text-xs font-semibold mb-1 text-text-tertiary">
                                    Evidence:
                                  </p>
                                  <ul className="text-xs space-y-1 text-text-muted">
                                    {gap.supporting_evidence.map((evidence, j) => (
                                      <li key={j}>• {evidence}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}

                              {gap.suggested_directions && gap.suggested_directions.length > 0 && (
                                <div>
                                  <p className="text-xs font-semibold mb-1 text-text-tertiary">
                                    Suggested Research Directions:
                                  </p>
                                  <ul className="text-xs space-y-1 text-text-muted">
                                    {gap.suggested_directions.map((direction, j) => (
                                      <li key={j}>→ {direction}</li>
                                    ))}
                                  </ul>
                                </div>
                              )}
                            </div>
                          ))}
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>

              {/* Section 3: Discover Relevant Papers */}
              <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
                <button
                  onClick={() => toggleSection('discovery')}
                  className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
                >
                  <div className="flex items-center gap-3">
                    <AcademicCapIcon className="h-5 w-5 text-cyan-400" />
                    <h3 className="text-lg font-serif font-semibold text-text-primary">
                      Discover Relevant Papers
                    </h3>
                  </div>
                  {expandedSections.has('discovery') ? (
                    <ChevronUpIcon className="h-5 w-5 text-text-tertiary" />
                  ) : (
                    <ChevronDownIcon className="h-5 w-5 text-text-tertiary" />
                  )}
                </button>

                {expandedSections.has('discovery') && (
                  <div className="px-6 pb-6">
                    <p className="text-sm text-text-secondary mb-4">
                      AI-powered paper recommendations to fill gaps and strengthen your literature coverage:
                    </p>
                    <PaperRecommendations projectId={projectId} />
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}

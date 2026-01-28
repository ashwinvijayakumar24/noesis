import { BeakerIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'
import ResearchQuestions from '../ResearchQuestions'

interface ResearchPlanningViewProps {
  insights: any | null
  projectId: string
}

interface ResearchGap {
  category: 'methodological' | 'population' | 'theoretical' | 'temporal'
  title: string
  description: string
  supporting_evidence: string[]
  suggested_directions: string[]
}

const GAP_CATEGORY_COLORS = {
  methodological: 'bg-surface-hover/50 text-text-secondary border-border-subtle',
  population: 'bg-surface-hover/50 text-text-secondary border-border-subtle',
  theoretical: 'bg-surface-hover/50 text-text-secondary border-border-subtle',
  temporal: 'bg-surface-hover/50 text-text-secondary border-border-subtle'
}

export default function ResearchPlanningView({ insights, projectId }: ResearchPlanningViewProps) {
  if (!insights) {
    return (
      <div className="bg-surface/50 rounded-lg border border-border-base p-12 text-center">
        <div className="max-w-md mx-auto">
          <div className="p-3 bg-purple-500/10 rounded-lg inline-block mb-4">
            <BeakerIcon className="h-12 w-12 text-purple-400" />
          </div>
          <h3 className="text-xl font-serif font-semibold text-text-primary mb-2">
            Insights Analysis Required
          </h3>
          <p className="text-text-tertiary mb-4">
            Please analyze project insights first before using Research Planning features.
          </p>
          <p className="text-sm text-text-muted">
            Click <strong>"Analyze Insights"</strong> in the sidebar
          </p>
        </div>
      </div>
    )
  }

  const researchGaps: ResearchGap[] = insights.research_gaps || []

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-purple-500/10 rounded-lg">
            <BeakerIcon className="h-6 w-6 text-purple-400" />
          </div>
          <div>
            <h2 className="text-2xl font-serif font-semibold text-text-primary">
              Research Planning
            </h2>
            <p className="text-sm text-text-tertiary">
              Identify gaps, generate questions, and plan your research direction
            </p>
          </div>
        </div>
      </div>

      {/* Description */}
      <div className="bg-surface/50 rounded-lg border border-border-base p-6 mb-6">
        <h3 className="text-lg font-serif font-semibold text-text-primary mb-2">
          How Research Planning Works
        </h3>
        <p className="text-sm text-text-tertiary">
          This tab helps you identify gaps in existing research, generate research questions, and get methodology recommendations for your study.
        </p>
      </div>

      {/* Main Content - Vertical Flow */}
      <div className="space-y-6">
        {/* Section 1: Research Gaps Identified */}
        {researchGaps.length > 0 && (
          <div className="bg-surface rounded-lg border border-border-base p-6">
            <div className="flex items-center gap-3 mb-4">
              <div className="p-2 bg-amber-600/20 rounded-lg">
                <ExclamationTriangleIcon className="h-5 w-5 text-amber-400" />
              </div>
              <div>
                <h3 className="text-lg font-serif font-semibold text-text-primary">
                  Research Gaps Identified ({researchGaps.length})
                </h3>
                <p className="text-sm text-text-tertiary">
                  Areas where existing research is limited or missing
                </p>
              </div>
            </div>

            {/* Gap Cards in Grid */}
            <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
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
                      <p className="text-xs font-semibold mb-1 text-text-tertiary">Evidence:</p>
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
          </div>
        )}

        {/* Section 2: Research Questions */}
        <div className="bg-surface rounded-lg border border-border-base p-6">
          <ResearchQuestions
            projectId={projectId}
            insightsStatus="analyzed"
            hideMethodology={true}
          />
        </div>

        {/* Section 3: Methodology Recommendations */}
        <div className="bg-surface rounded-lg border border-border-base p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-blue-600/20 rounded-lg">
              <BeakerIcon className="h-5 w-5 text-blue-400" />
            </div>
            <div>
              <h3 className="text-lg font-serif font-semibold text-text-primary">
                Methodology Recommendations
              </h3>
              <p className="text-sm text-text-tertiary">
                Get detailed methodology recommendations for your research questions
              </p>
            </div>
          </div>
          <p className="text-sm text-text-secondary mb-4">
            AI-generated methodology recommendations for your research questions. Generate recommendations for specific questions to see detailed methodological approaches.
          </p>

          <ResearchQuestions
            projectId={projectId}
            insightsStatus="analyzed"
            methodologyOnly={true}
          />
        </div>
      </div>
    </div>
  )
}

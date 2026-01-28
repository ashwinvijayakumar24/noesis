import { BeakerIcon } from '@heroicons/react/24/outline'

interface ResearchPlanningViewProps {
  insights: any | null
  projectId: string
}

export default function ResearchPlanningView({ insights, projectId }: ResearchPlanningViewProps) {
  // Placeholder for Phase 2 implementation
  return (
    <div className="bg-surface/50 rounded-lg border border-border-base p-12 text-center">
      <div className="max-w-md mx-auto">
        <div className="p-3 bg-purple-500/10 rounded-lg inline-block mb-4">
          <BeakerIcon className="h-12 w-12 text-purple-400" />
        </div>
        <h3 className="text-xl font-serif font-semibold text-text-primary mb-2">
          Research Planning
        </h3>
        <p className="text-text-tertiary mb-4">
          Identify gaps, generate questions, and discover new papers to explore.
        </p>
        <p className="text-sm text-text-muted">
          This feature will be implemented in Phase 2
        </p>
        <div className="mt-6 text-left bg-surface p-4 rounded-lg border border-border-subtle">
          <h4 className="text-sm font-semibold text-text-secondary mb-2">Coming Soon:</h4>
          <ul className="text-sm text-text-tertiary space-y-1">
            <li>• Research Gaps Analysis</li>
            <li>• Research Questions Generator</li>
            <li>• Methodology Recommendations</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

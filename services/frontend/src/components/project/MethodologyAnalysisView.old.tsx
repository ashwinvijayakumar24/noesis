import { ChartBarIcon } from '@heroicons/react/24/outline'

interface MethodologyAnalysisViewProps {
  insights: any | null
  projectId: string
}

export default function MethodologyAnalysisView({ insights, projectId }: MethodologyAnalysisViewProps) {
  // Placeholder for Phase 3 implementation
  return (
    <div className="bg-surface/50 rounded-lg border border-border-base p-12 text-center">
      <div className="max-w-md mx-auto">
        <div className="p-3 bg-emerald-500/10 rounded-lg inline-block mb-4">
          <ChartBarIcon className="h-12 w-12 text-emerald-400" />
        </div>
        <h3 className="text-xl font-serif font-semibold text-text-primary mb-2">
          Methodology & Analysis
        </h3>
        <p className="text-text-tertiary mb-4">
          Deep insights into methodological patterns, common themes, and citation networks.
        </p>
        <p className="text-sm text-text-muted">
          This feature will be implemented in Phase 3
        </p>
        <div className="mt-6 text-left bg-surface p-4 rounded-lg border border-border-subtle">
          <h4 className="text-sm font-semibold text-text-secondary mb-2">Coming Soon:</h4>
          <ul className="text-sm text-text-tertiary space-y-1">
            <li>• Project Overview Insights</li>
            <li>• Common Themes Analysis</li>
            <li>• Methodological Patterns</li>
            <li>• Citation Network Visualization</li>
            <li>• Methodology Recommendations</li>
          </ul>
        </div>
      </div>
    </div>
  )
}

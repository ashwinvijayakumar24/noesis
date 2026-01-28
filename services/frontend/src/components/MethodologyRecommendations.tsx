import {
  BeakerIcon,
  ClockIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ChartBarIcon,
  DocumentMagnifyingGlassIcon,
  AcademicCapIcon
} from '@heroicons/react/24/outline'

interface PrimaryMethodology {
  name: string
  fit_score: number
  rationale: string
  approach: string[]
  required_resources: string[]
  timeline: string
  challenges: string[]
  example_studies?: string[]
}

interface AlternativeMethodology {
  name: string
  fit_score: number
  rationale: string
  when_to_use: string
}

interface DataCollection {
  strategy: string
  sources: string[]
  tools: string[]
  sample_size?: string
}

interface MethodologyRecommendationsProps {
  recommendations: {
    primary_methodology: PrimaryMethodology
    alternative_methodologies: AlternativeMethodology[]
    data_collection: DataCollection
    analysis_techniques: string[]
    validation_approach: string
  }
  question: string
}

export default function MethodologyRecommendations({ recommendations, question }: MethodologyRecommendationsProps) {
  const { primary_methodology, alternative_methodologies, data_collection, analysis_techniques, validation_approach } = recommendations

  return (
    <div className="space-y-4 mt-4 pt-4 border-t border-border-subtle">
      {/* Question Context */}
      <div className="bg-indigo-900/20 border border-indigo-700/30 rounded-lg p-4">
        <h4 className="text-sm font-semibold text-indigo-300 mb-2">Research Question:</h4>
        <p className="text-sm text-text-secondary italic">{question}</p>
      </div>

      {/* Primary Methodology */}
      <div className="bg-blue-900/20 rounded-lg border border-blue-700/30 p-5">
        <div className="flex items-start justify-between mb-4">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-600/30 rounded-lg">
              <BeakerIcon className="h-6 w-6 text-blue-400" />
            </div>
            <div>
              <h3 className="text-lg font-serif font-bold text-text-primary">{primary_methodology.name}</h3>
              <div className="flex items-center gap-2 mt-1">
                <div className="flex items-center gap-1">
                  {[...Array(10)].map((_, i) => (
                    <div
                      key={i}
                      className={`w-2 h-2 rounded-full ${
                        i < primary_methodology.fit_score ? 'bg-emerald-500' : 'bg-surface-hover'
                      }`}
                    />
                  ))}
                </div>
                <span className="text-xs text-text-tertiary font-mono">Fit Score: {primary_methodology.fit_score}/10</span>
              </div>
            </div>
          </div>
          <span className="px-3 py-1 bg-emerald-600/20 text-emerald-400 text-xs font-semibold rounded-full border border-emerald-600/30">
            RECOMMENDED
          </span>
        </div>

        <p className="text-sm text-text-secondary mb-4">{primary_methodology.rationale}</p>

        {/* Approach Steps */}
        <div className="mb-4">
          <h4 className="text-sm font-semibold text-blue-300 mb-2 flex items-center gap-2">
            <CheckCircleIcon className="h-4 w-4" />
            Step-by-Step Approach
          </h4>
          <ol className="space-y-2">
            {primary_methodology.approach.map((step, i) => (
              <li key={i} className="flex gap-3 text-sm text-text-secondary">
                <span className="shrink-0 w-6 h-6 bg-blue-600/30 text-blue-400 rounded-full flex items-center justify-center text-xs font-bold">
                  {i + 1}
                </span>
                <span>{step}</span>
              </li>
            ))}
          </ol>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Timeline */}
          <div className="bg-surface/50 rounded-lg border border-border-subtle p-3">
            <div className="flex items-center gap-2 mb-2">
              <ClockIcon className="h-4 w-4 text-amber-400" />
              <h4 className="text-xs font-semibold text-amber-300">Estimated Timeline</h4>
            </div>
            <p className="text-sm text-text-secondary">{primary_methodology.timeline}</p>
          </div>

          {/* Resources */}
          <div className="bg-surface/50 rounded-lg border border-border-subtle p-3">
            <div className="flex items-center gap-2 mb-2">
              <AcademicCapIcon className="h-4 w-4 text-purple-400" />
              <h4 className="text-xs font-semibold text-purple-300">Required Resources</h4>
            </div>
            <ul className="space-y-1">
              {primary_methodology.required_resources.slice(0, 2).map((resource, i) => (
                <li key={i} className="text-xs text-text-tertiary">• {resource}</li>
              ))}
              {primary_methodology.required_resources.length > 2 && (
                <li className="text-xs text-text-muted">+ {primary_methodology.required_resources.length - 2} more</li>
              )}
            </ul>
          </div>
        </div>

        {/* Challenges */}
        {primary_methodology.challenges && primary_methodology.challenges.length > 0 && (
          <div className="mt-4 bg-red-900/20 border border-red-700/30 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <ExclamationTriangleIcon className="h-4 w-4 text-red-400" />
              <h4 className="text-xs font-semibold text-red-300">Challenges & Mitigation</h4>
            </div>
            <ul className="space-y-1">
              {primary_methodology.challenges.map((challenge, i) => (
                <li key={i} className="text-xs text-text-secondary">• {challenge}</li>
              ))}
            </ul>
          </div>
        )}

        {/* Example Studies */}
        {primary_methodology.example_studies && primary_methodology.example_studies.length > 0 && (
          <div className="mt-4 bg-emerald-900/20 border border-emerald-700/30 rounded-lg p-3">
            <div className="flex items-center gap-2 mb-2">
              <DocumentMagnifyingGlassIcon className="h-4 w-4 text-emerald-400" />
              <h4 className="text-xs font-semibold text-emerald-300">Example Studies</h4>
            </div>
            <ul className="space-y-1">
              {primary_methodology.example_studies.map((study, i) => (
                <li key={i} className="text-xs text-text-secondary">• {study}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Alternative Methodologies */}
      {alternative_methodologies && alternative_methodologies.length > 0 && (
        <div className="bg-surface/50 rounded-lg border border-border-base p-4">
          <h3 className="text-sm font-semibold text-text-secondary mb-3">Alternative Approaches</h3>
          <div className="space-y-3">
            {alternative_methodologies.map((alt, i) => (
              <div key={i} className="bg-surface/50 rounded-lg p-3 border border-border-subtle">
                <div className="flex items-center justify-between mb-2">
                  <h4 className="text-sm font-semibold text-text-primary">{alt.name}</h4>
                  <div className="flex items-center gap-1">
                    {[...Array(10)].map((_, j) => (
                      <div
                        key={j}
                        className={`w-1.5 h-1.5 rounded-full ${
                          j < alt.fit_score ? 'bg-blue-500' : 'bg-surface-hover'
                        }`}
                      />
                    ))}
                  </div>
                </div>
                <p className="text-xs text-text-tertiary mb-2">{alt.rationale}</p>
                <p className="text-xs text-blue-400">
                  <span className="font-semibold">When to use:</span> {alt.when_to_use}
                </p>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Data Collection */}
      <div className="bg-surface/50 rounded-lg border border-border-base p-4">
        <div className="flex items-center gap-2 mb-3">
          <ChartBarIcon className="h-5 w-5 text-cyan-400" />
          <h3 className="text-sm font-semibold text-text-primary">Data Collection Strategy</h3>
        </div>
        <p className="text-sm text-text-secondary mb-3">{data_collection.strategy}</p>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          <div>
            <h4 className="text-xs font-semibold text-cyan-300 mb-1">Sources</h4>
            <ul className="space-y-1">
              {data_collection.sources.map((source, i) => (
                <li key={i} className="text-xs text-text-tertiary">• {source}</li>
              ))}
            </ul>
          </div>
          <div>
            <h4 className="text-xs font-semibold text-cyan-300 mb-1">Tools</h4>
            <ul className="space-y-1">
              {data_collection.tools.map((tool, i) => (
                <li key={i} className="text-xs text-text-tertiary">• {tool}</li>
              ))}
            </ul>
          </div>
          {data_collection.sample_size && (
            <div>
              <h4 className="text-xs font-semibold text-cyan-300 mb-1">Sample Size</h4>
              <p className="text-xs text-text-tertiary">{data_collection.sample_size}</p>
            </div>
          )}
        </div>
      </div>

      {/* Analysis Techniques */}
      <div className="bg-surface/50 rounded-lg border border-border-base p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-3">Analysis Techniques</h3>
        <ul className="space-y-2">
          {analysis_techniques.map((technique, i) => (
            <li key={i} className="text-sm text-text-secondary flex gap-2">
              <span className="text-purple-400">→</span>
              {technique}
            </li>
          ))}
        </ul>
      </div>

      {/* Validation */}
      <div className="bg-surface/50 rounded-lg border border-border-base p-4">
        <h3 className="text-sm font-semibold text-text-primary mb-2">Validation Approach</h3>
        <p className="text-sm text-text-secondary">{validation_approach}</p>
      </div>
    </div>
  )
}

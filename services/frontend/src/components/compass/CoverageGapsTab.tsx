import { ClipboardDocumentIcon, CheckIcon } from '@heroicons/react/24/outline'
import { useState } from 'react'
import toast from 'react-hot-toast'

interface CoverageGapsTabProps {
  gaps: ResearchGap[]
  themes: Theme[]
  positioningPrompts: PositioningPrompt[]
}

interface ResearchGap {
  category: string
  title: string
  description: string
  supporting_evidence: string[]
  suggested_directions: string[]
}

interface Theme {
  theme: string
  frequency: number
  description: string
}

interface PositioningPrompt {
  prompt: string
  based_on: string
}

export default function CoverageGapsTab({ gaps, themes, positioningPrompts }: CoverageGapsTabProps) {
  const [copiedGap, setCopiedGap] = useState<number | null>(null)

  const copyGapDetails = (gap: ResearchGap, index: number) => {
    const text = `
${gap.title}

Category: ${gap.category}

Description: ${gap.description}

Evidence:
${gap.supporting_evidence.map(e => `• ${e}`).join('\n')}

Suggested Directions:
${gap.suggested_directions.map(d => `• ${d}`).join('\n')}
    `.trim()

    navigator.clipboard.writeText(text)
    setCopiedGap(index)
    toast.success('Gap details copied!')
    setTimeout(() => setCopiedGap(null), 2000)
  }

  // Categorize themes as well-covered or under-explored
  const wellCoveredThemes = themes.filter(t => t.frequency >= 3)
  const underExploredThemes = themes.filter(t => t.frequency < 3 && t.frequency > 0)

  // Category styles with hardcoded Tailwind classes (no dynamic class generation)
  const categoryStyles = {
    methodological: {
      badge: 'px-2 py-0.5 bg-blue-600/10 border border-blue-600/20 rounded text-xs text-blue-400 capitalize'
    },
    population: {
      badge: 'px-2 py-0.5 bg-green-600/10 border border-green-600/20 rounded text-xs text-green-400 capitalize'
    },
    theoretical: {
      badge: 'px-2 py-0.5 bg-purple-600/10 border border-purple-600/20 rounded text-xs text-purple-400 capitalize'
    },
    temporal: {
      badge: 'px-2 py-0.5 bg-orange-600/10 border border-orange-600/20 rounded text-xs text-orange-400 capitalize'
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-surface/50 rounded-lg border border-border-base p-6">
        <h3 className="text-lg font-serif font-semibold text-text-primary mb-2">
          Coverage Analysis
        </h3>
        <p className="text-sm text-text-tertiary">
          Understanding what's well-covered and what's missing helps you position your contribution
          and identify opportunities for original research.
        </p>
      </div>

      {/* Coverage Summary */}
      <div className="grid grid-cols-2 gap-4">
        <div className="bg-surface rounded-lg border border-border-base p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-2xl">✓</span>
            <h4 className="text-sm font-semibold text-text-secondary">Well-Covered Areas</h4>
          </div>
          <div className="space-y-2">
            {wellCoveredThemes.length > 0 ? (
              wellCoveredThemes.map((theme, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <div className="px-2 py-1 bg-green-600/10 border border-green-600/20 rounded text-xs text-green-400">
                    {theme.theme}
                  </div>
                  <span className="text-xs text-text-muted">({theme.frequency} papers)</span>
                </div>
              ))
            ) : (
              <p className="text-xs text-text-muted">No themes with strong coverage identified</p>
            )}
          </div>
        </div>

        <div className="bg-surface rounded-lg border border-border-base p-4">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-2xl">⚠️</span>
            <h4 className="text-sm font-semibold text-text-secondary">Under-Explored Areas</h4>
          </div>
          <div className="space-y-2">
            {underExploredThemes.length > 0 ? (
              underExploredThemes.map((theme, idx) => (
                <div key={idx} className="flex items-center gap-2">
                  <div className="px-2 py-1 bg-yellow-600/10 border border-yellow-600/20 rounded text-xs text-yellow-400">
                    {theme.theme}
                  </div>
                  <span className="text-xs text-text-muted">({theme.frequency} {theme.frequency === 1 ? 'paper' : 'papers'})</span>
                </div>
              ))
            ) : (
              <p className="text-xs text-text-muted">All themes have balanced coverage</p>
            )}
          </div>
        </div>
      </div>

      {/* Positioning Prompts */}
      {positioningPrompts && positioningPrompts.length > 0 && (
        <div className="bg-surface rounded-lg border border-border-base">
          <div className="p-4 border-b border-border-subtle">
            <div className="flex items-center gap-2 mb-2">
              <span className="text-2xl">🎯</span>
              <h4 className="text-lg font-semibold text-text-primary">
                Positioning Your Research
              </h4>
            </div>
            <p className="text-sm text-text-tertiary">
              These prompts help you articulate how your research fits into the broader landscape.
            </p>
          </div>

          <div className="p-4 space-y-3">
            {positioningPrompts.map((prompt, index) => (
              <div
                key={index}
                className="p-4 bg-gradient-to-r from-indigo-600/10 to-purple-600/10 border border-indigo-600/20 rounded-lg"
              >
                <div className="flex items-start gap-3">
                  <span className="text-2xl shrink-0">💡</span>
                  <div className="flex-1">
                    <p className="text-sm text-text-primary mb-2">{prompt.prompt}</p>
                    <div className="text-xs text-text-muted">
                      Based on: <span className="text-text-tertiary capitalize">
                        {prompt.based_on.replace(/_/g, ' ')}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>

          <div className="p-4 bg-surface/50 border-t border-border-subtle">
            <p className="text-xs text-text-muted">
              <strong>How to use:</strong> Answer these questions in your Introduction or Discussion
              to clearly position your research contribution.
            </p>
          </div>
        </div>
      )}

      {/* Research Gaps */}
      {gaps && gaps.length > 0 ? (
        <div>
          <h4 className="text-lg font-semibold text-text-primary mb-3">Research Gaps</h4>
          <div className="space-y-3">
            {gaps.map((gap, index) => {
              const category = gap.category as keyof typeof categoryStyles
              const styles = categoryStyles[category] || categoryStyles.methodological
              return (
                <div
                  key={index}
                  className="bg-surface rounded-lg border border-border-base p-4 hover:border-border-subtle transition-colors"
                >
                  <div className="flex items-start justify-between gap-3 mb-3">
                    <div className="flex items-start gap-2 flex-1">
                      <span className="text-2xl">🕳️</span>
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-1">
                          <h5 className="text-base font-semibold text-text-primary">{gap.title}</h5>
                          <span className={styles.badge}>
                            {gap.category}
                          </span>
                        </div>
                        <p className="text-sm text-text-tertiary">{gap.description}</p>
                      </div>
                    </div>
                    <button
                      onClick={() => copyGapDetails(gap, index)}
                      className="text-text-tertiary hover:text-text-primary transition-colors"
                    >
                      {copiedGap === index ? (
                        <CheckIcon className="h-5 w-5 text-green-500" />
                      ) : (
                        <ClipboardDocumentIcon className="h-5 w-5" />
                      )}
                    </button>
                  </div>

                  <div className="space-y-3 ml-8">
                    {/* Evidence */}
                    <div>
                      <h6 className="text-xs font-semibold text-text-secondary mb-1">Evidence:</h6>
                      <ul className="space-y-1">
                        {gap.supporting_evidence.map((evidence, idx) => (
                          <li key={idx} className="text-xs text-text-tertiary flex items-start gap-2">
                            <span className="text-text-muted mt-0.5">•</span>
                            <span>{evidence}</span>
                          </li>
                        ))}
                      </ul>
                    </div>

                    {/* Suggested Directions */}
                    <div className="p-3 bg-blue-600/10 border border-blue-600/20 rounded">
                      <h6 className="text-xs font-semibold text-blue-400 mb-2">💡 Suggested Directions:</h6>
                      <ul className="space-y-1">
                        {gap.suggested_directions.map((direction, idx) => (
                          <li key={idx} className="text-xs text-text-secondary flex items-start gap-2">
                            <span className="text-blue-400">→</span>
                            <span>{direction}</span>
                          </li>
                        ))}
                      </ul>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </div>
      ) : (
        <div className="bg-surface/50 rounded-lg border border-border-base p-6 text-center">
          <span className="text-4xl mb-2 block">🔍</span>
          <p className="text-sm text-text-tertiary">
            No specific research gaps identified yet. As you add more papers,
            the system will detect patterns and identify missing areas of study.
          </p>
        </div>
      )}

      {/* Note */}
      <div className="bg-surface/50 rounded-lg border border-border-base p-4">
        <p className="text-xs text-text-muted">
          <strong>Positioning Tip:</strong> Research gaps aren't just limitations — they're opportunities.
          When writing your literature review, explicitly connect gaps to how your research addresses them.
        </p>
      </div>
    </div>
  )
}

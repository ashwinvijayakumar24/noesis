import { useState } from 'react'
import { ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline'

interface ThematicClusteringTabProps {
  themes: Theme[]
}

interface Theme {
  theme: string
  frequency: number
  description: string
  paper_titles: string[]
}

export default function ThematicClusteringTab({ themes }: ThematicClusteringTabProps) {
  const [expandedTheme, setExpandedTheme] = useState<string | null>(null)

  if (!themes || themes.length === 0) {
    return (
      <div className="bg-surface/50 rounded-lg border border-border-default p-8 text-center">
        <p className="text-text-tertiary">
          No themes identified yet. Analyze more documents to detect thematic patterns.
        </p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      <div className="bg-surface/50 rounded-lg border border-border-default p-6">
        <h3 className="text-lg font-sans font-semibold text-text-primary mb-2">
          Thematic Clusters
        </h3>
        <p className="text-sm text-text-tertiary">
          Your literature groups into {themes.length} major themes. Use these to organize a thematic review
          or to identify how different papers relate to each other.
        </p>
      </div>

      <div className="space-y-3">
        {themes.map((theme, index) => {
          const isExpanded = expandedTheme === theme.theme
          return (
            <div
              key={index}
              className="bg-surface rounded-lg border border-border-default hover:border-border-default transition-colors"
            >
              {/* Header */}
              <div
                className="p-4 cursor-pointer"
                onClick={() => setExpandedTheme(isExpanded ? null : theme.theme)}
              >
                <div className="flex items-start justify-between gap-4">
                  <div className="flex-1">
                    <div className="flex items-center gap-3 mb-2">
                      <div className="p-2 bg-accent-primary/10 rounded-lg">
                        <span className="text-lg">🎯</span>
                      </div>
                      <div>
                        <h4 className="text-lg font-semibold text-text-primary">{theme.theme}</h4>
                        <p className="text-xs text-text-muted">
                          {theme.frequency} {theme.frequency === 1 ? 'paper' : 'papers'}
                        </p>
                      </div>
                    </div>
                    <p className="text-sm text-text-tertiary ml-11">{theme.description}</p>
                  </div>
                  <button className="text-text-tertiary hover:text-text-primary transition-colors">
                    {isExpanded ? (
                      <ChevronUpIcon className="h-5 w-5" />
                    ) : (
                      <ChevronDownIcon className="h-5 w-5" />
                    )}
                  </button>
                </div>
              </div>

              {/* Expanded Content */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-border-default pt-4 space-y-4">
                  {/* Papers */}
                  <div>
                    <h5 className="text-sm font-semibold text-text-secondary mb-2">Papers in this theme:</h5>
                    <div className="space-y-2">
                      {theme.paper_titles.map((paper, idx) => (
                        <div key={idx} className="flex items-start gap-2 text-sm">
                          <span className="text-text-muted mt-0.5">•</span>
                          <span className="text-text-primary">{paper}</span>
                        </div>
                      ))}
                    </div>
                  </div>

                  {/* Synthesis Prompts */}
                  <div className="p-3 bg-blue-600/10 border border-blue-600/20 rounded">
                    <h5 className="text-sm font-semibold text-blue-400 mb-2">💭 Synthesis Prompts:</h5>
                    <ul className="space-y-1 text-xs text-text-secondary">
                      <li>→ How do findings converge on {theme.theme}? What tensions exist?</li>
                      <li>→ What's the strongest evidence for this theme?</li>
                      <li>→ Where do papers disagree about {theme.theme}?</li>
                      <li>→ How has understanding of {theme.theme} evolved over time?</li>
                    </ul>
                  </div>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

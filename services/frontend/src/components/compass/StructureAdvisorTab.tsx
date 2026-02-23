import { useState } from 'react'
import {
  ClipboardDocumentIcon,
  CheckIcon,
  ArrowDownTrayIcon,
  DocumentTextIcon
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { Badge } from '../ui/Badge'
import InsightCard from './InsightCard'

interface StructureAdvisorTabProps {
  recommendations: StructureRecommendation[]
  structureGuidance?: StructureGuidanceItem[]
}

interface StructureGuidanceItem {
  text: string
  type: 'gap' | 'conflict' | 'pattern' | 'general'
  priority: number
  source_data: {
    conflicts: string[]
    gaps: string[]
    patterns: string[]
  }
}

interface StructureRecommendation {
  type: string
  score: number
  reasoning: string
  outline: {
    sections: Section[]
  }
  pros: string[]
  cons: string[]
}

interface Section {
  title: string
  papers: string[]
  focus_themes: string[]
  synthesis_prompt: string
}

export default function StructureAdvisorTab({ recommendations, structureGuidance = [] }: StructureAdvisorTabProps) {
  const [selectedStructure, setSelectedStructure] = useState<string>(
    recommendations.length > 0 ? recommendations[0].type : ''
  )
  const [copied, setCopied] = useState(false)

  const selectedRec = recommendations.find(r => r.type === selectedStructure)

  const formatOutlineAsMarkdown = (outline: { sections: Section[] }): string => {
    let text = '# Literature Review Outline\n\n'

    outline.sections.forEach((section, index) => {
      text += `## ${index + 1}. ${section.title}\n\n`

      if (section.papers.length > 0) {
        text += `**Papers:**\n`
        section.papers.forEach(paper => {
          text += `- ${paper}\n`
        })
        text += '\n'
      }

      if (section.focus_themes.length > 0) {
        text += `**Key Themes:** ${section.focus_themes.join(', ')}\n\n`
      }

      text += `**Synthesis Prompt:** ${section.synthesis_prompt}\n\n`
      text += `---\n\n`
    })

    return text
  }

  const copyOutline = () => {
    if (!selectedRec) return

    const outlineText = formatOutlineAsMarkdown(selectedRec.outline)
    navigator.clipboard.writeText(outlineText)
    setCopied(true)
    toast.success('Outline copied to clipboard!')
    setTimeout(() => setCopied(false), 2000)
  }

  const downloadOutline = () => {
    if (!selectedRec) return

    const outlineText = formatOutlineAsMarkdown(selectedRec.outline)
    const blob = new Blob([outlineText], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `literature-review-outline-${selectedRec.type}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
    toast.success('Outline downloaded!')
  }

  return (
    <div className="space-y-4">
      {/* Introduction */}
      <div className="bg-surface/50 rounded-lg p-4 border border-border-default">
        <p className="text-sm text-text-secondary">
          Based on your literature's characteristics, here are recommended organizational approaches.
          Select a structure to preview its outline.
        </p>
      </div>

      {/* Structure Guidance (NEW - using template variations) */}
      {structureGuidance && structureGuidance.length > 0 && (
        <div className="space-y-3">
          <h4 className="text-sm font-semibold text-text-primary">Structure Guidance</h4>
          <div className="space-y-3">
            {structureGuidance.map((guidance, index) => {
              const sourceCount =
                guidance.source_data.conflicts.length +
                guidance.source_data.gaps.length +
                guidance.source_data.patterns.length

              return (
                <InsightCard
                  key={index}
                  title={`Guidance ${index + 1}`}
                  type={guidance.type}
                  priority={guidance.priority}
                  metadata={{
                    sourceCount,
                    actionable: true
                  }}
                >
                  <p className="text-sm text-text-secondary leading-relaxed">
                    {guidance.text}
                  </p>

                  {/* Source data breakdown */}
                  {sourceCount > 0 && (
                    <div className="mt-3 pt-3 border-t border-border-default/50">
                      <div className="text-xs text-text-muted space-y-1">
                        {guidance.source_data.conflicts.length > 0 && (
                          <div>
                            <span className="font-semibold">Conflicts:</span>{' '}
                            {guidance.source_data.conflicts.join(', ')}
                          </div>
                        )}
                        {guidance.source_data.gaps.length > 0 && (
                          <div>
                            <span className="font-semibold">Gaps:</span>{' '}
                            {guidance.source_data.gaps.join(', ')}
                          </div>
                        )}
                        {guidance.source_data.patterns.length > 0 && (
                          <div>
                            <span className="font-semibold">Patterns:</span>{' '}
                            {guidance.source_data.patterns.join(', ')}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </InsightCard>
              )
            })}
          </div>
        </div>
      )}

      {/* Structure Selection Cards */}
      <div className="space-y-3">
        <h4 className="text-sm font-semibold text-text-primary">Available Structures</h4>

        {recommendations.map((rec) => {
          const isSelected = selectedStructure === rec.type
          const scorePercent = (rec.score * 100).toFixed(0)

          return (
            <div
              key={rec.type}
              onClick={() => setSelectedStructure(rec.type)}
              className={`border rounded-lg p-4 cursor-pointer transition-all ${
                isSelected
                  ? 'border-accent-primary bg-surface'
                  : 'border-border-default bg-surface/50 hover:border-border-default'
              }`}
            >
              <div className="flex items-start justify-between mb-2">
                <h4 className="font-medium text-text-primary capitalize">
                  {rec.type} Organization
                </h4>
                <Badge variant="info">
                  {scorePercent}% match
                </Badge>
              </div>

              <p className="text-sm text-text-secondary">{rec.reasoning}</p>
            </div>
          )
        })}
      </div>

      {/* Outline Preview */}
      {selectedRec && (
        <div className="space-y-3">
          <div className="flex items-center justify-between">
            <h4 className="text-sm font-semibold text-text-primary">Outline Preview</h4>
            <div className="flex gap-2">
              <button
                onClick={copyOutline}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary bg-surface border border-border-default hover:border-border-default rounded transition-colors"
              >
                {copied ? (
                  <>
                    <CheckIcon className="h-3.5 w-3.5 text-success" />
                    Copied
                  </>
                ) : (
                  <>
                    <ClipboardDocumentIcon className="h-3.5 w-3.5" />
                    Copy
                  </>
                )}
              </button>
              <button
                onClick={downloadOutline}
                className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary bg-surface border border-border-default hover:border-border-default rounded transition-colors"
              >
                <ArrowDownTrayIcon className="h-3.5 w-3.5" />
                Export
              </button>
            </div>
          </div>

          <div className="bg-surface/50 rounded-lg border border-border-default p-4">
            <div className="space-y-4">
              {selectedRec.outline.sections.map((section, index) => (
                <div key={index} className="space-y-2">
                  {/* Section Title */}
                  <div className="flex items-start gap-2">
                    <span className="text-text-muted font-mono text-sm shrink-0 mt-0.5">
                      {index + 1}.
                    </span>
                    <h5 className="text-text-primary font-medium">
                      {section.title}
                    </h5>
                  </div>

                  {/* Papers */}
                  {section.papers.length > 0 && (
                    <div className="ml-5 bg-bg-base/50 rounded p-2.5 border border-border-default">
                      <div className="flex items-start gap-2">
                        <DocumentTextIcon className="h-3.5 w-3.5 text-text-muted shrink-0 mt-0.5" />
                        <div className="flex-1 min-w-0">
                          <p className="text-xs font-semibold text-text-muted mb-1">Papers to Include:</p>
                          <p className="text-xs text-text-secondary">
                            {section.papers.join(', ')}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Themes */}
                  {section.focus_themes.length > 0 && (
                    <div className="ml-5">
                      <p className="text-xs font-semibold text-text-muted mb-1.5">Key Themes:</p>
                      <div className="flex flex-wrap gap-1.5">
                        {section.focus_themes.map((theme, i) => (
                          <span
                            key={i}
                            className="text-xs px-2 py-0.5 rounded bg-surface border border-border-default text-text-secondary"
                          >
                            {theme}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* Synthesis Prompt */}
                  <div className="ml-5 p-2.5 bg-surface/50 border border-border-default rounded">
                    <p className="text-xs font-semibold text-text-muted mb-1">
                      Writing Guidance:
                    </p>
                    <p className="text-xs text-text-secondary leading-relaxed">
                      {section.synthesis_prompt}
                    </p>
                  </div>

                  {/* Divider between sections */}
                  {index < selectedRec.outline.sections.length - 1 && (
                    <div className="border-t border-border-default mt-4" />
                  )}
                </div>
              ))}
            </div>

            {/* Note at bottom */}
            <div className="mt-4 pt-4 border-t border-border-default">
              <p className="text-xs text-text-muted">
                <strong>Note:</strong> This outline provides section structure and writing guidance.
                You write the actual content based on your understanding of the papers.
              </p>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

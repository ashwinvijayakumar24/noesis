import { useState } from 'react'
import { ClipboardDocumentIcon, CheckIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import QuestionCard from './QuestionCard'

interface SynthesisQuestionsTabProps {
  questions: SynthesisQuestion[]
}

interface SynthesisQuestion {
  question: string
  category: string
  icon: string
  related_papers: string[]
  difficulty?: 'low' | 'medium' | 'high'
  confidence?: number
  metadata?: {
    source_conflicts?: string[]
    source_gaps?: string[]
    source_patterns?: string[]
  }
  requirements?: string[]
  actionable?: boolean
}

export default function SynthesisQuestionsTab({ questions }: SynthesisQuestionsTabProps) {
  const [copiedCategory, setCopiedCategory] = useState<string | null>(null)

  const copyAllInCategory = (category: string) => {
    const categoryQuestions = questions.filter(q => q.category === category)
    const text = categoryQuestions.map(q => `• ${q.question}`).join('\n\n')
    navigator.clipboard.writeText(text)
    setCopiedCategory(category)
    toast.success(`All ${categoryInfo[category as keyof typeof categoryInfo]?.title || category} questions copied!`)
    setTimeout(() => setCopiedCategory(null), 2000)
  }

  const copyAll = () => {
    const text = questions.map(q => `[${categoryInfo[q.category as keyof typeof categoryInfo]?.title || q.category}]\n${q.question}`).join('\n\n')
    navigator.clipboard.writeText(text)
    toast.success('All synthesis questions copied!')
  }

  // Group by category
  const questionsByCategory = questions.reduce((acc, q) => {
    if (!acc[q.category]) acc[q.category] = []
    acc[q.category].push(q)
    return acc
  }, {} as Record<string, SynthesisQuestion[]>)

  const categoryInfo: Record<string, { title: string; description: string; order: number }> = {
    conflict: {
      title: 'Conflict Resolution',
      description: 'Questions arising from disagreements or competing perspectives in the literature.',
      order: 1
    },
    gap: {
      title: 'Gap Bridging',
      description: 'Questions about understudied areas and opportunities for new research.',
      order: 2
    },
    pattern: {
      title: 'Pattern Analysis',
      description: 'Questions about common methodologies, trends, and recurring themes.',
      order: 3
    },
    methodology: {
      title: 'Methodological Synthesis',
      description: 'Questions comparing different research approaches and their implications.',
      order: 4
    },
    positioning: {
      title: 'Research Positioning',
      description: 'Questions to help situate your work within the broader research landscape.',
      order: 5
    },
    temporal: {
      title: 'Temporal Evolution',
      description: 'Questions about how the field has changed over time.',
      order: 6
    },
    cross_domain: {
      title: 'Cross-Domain Connections',
      description: 'Questions linking insights across different research domains.',
      order: 7
    },
    evidence: {
      title: 'Evidence Weighting',
      description: 'Questions about the strength and quality of supporting evidence.',
      order: 8
    }
  }

  if (questions.length === 0) {
    return (
      <div className="bg-surface/50 rounded-lg border border-border-base p-8 text-center">
        <p className="text-text-tertiary">
          No synthesis questions generated. Analyze more documents to detect patterns and conflicts.
        </p>
      </div>
    )
  }

  // Sort categories by order
  const sortedCategories = Object.keys(questionsByCategory).sort((a, b) => {
    const orderA = categoryInfo[a]?.order || 999
    const orderB = categoryInfo[b]?.order || 999
    return orderA - orderB
  })

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="bg-surface/50 rounded-lg border border-border-base p-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="text-lg font-serif font-semibold text-text-primary mb-1">
              Synthesis Questions
            </h3>
            <p className="text-sm text-text-tertiary">
              Critical thinking questions to guide your analysis and writing. These questions help you synthesize findings across papers.
            </p>
          </div>
          <button
            onClick={copyAll}
            className="px-4 py-2 text-sm text-text-secondary hover:text-text-primary bg-surface-hover hover:bg-surface border border-border-subtle hover:border-border-base rounded transition-colors flex items-center gap-2 shrink-0"
          >
            <ClipboardDocumentIcon className="h-4 w-4" />
            Copy All
          </button>
        </div>
      </div>

      {/* Questions grouped by category */}
      {sortedCategories.map(category => {
        const categoryQuestions = questionsByCategory[category]
        const info = categoryInfo[category] || { title: category, description: '', order: 999 }

        return (
          <div key={category} className="bg-surface rounded-lg border border-border-base">
            <div className="p-4 border-b border-border-subtle">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-base font-semibold text-text-primary mb-1">
                    {info.title}
                  </h4>
                  <p className="text-sm text-text-tertiary">{info.description}</p>
                </div>
                <button
                  onClick={() => copyAllInCategory(category)}
                  className="px-3 py-1.5 text-xs text-text-tertiary hover:text-text-primary bg-surface-hover hover:bg-surface rounded transition-colors flex items-center gap-2 shrink-0"
                >
                  {copiedCategory === category ? (
                    <>
                      <CheckIcon className="h-4 w-4 text-success" />
                      Copied!
                    </>
                  ) : (
                    <>
                      <ClipboardDocumentIcon className="h-4 w-4" />
                      Copy ({categoryQuestions.length})
                    </>
                  )}
                </button>
              </div>
            </div>

            <div className="p-4 space-y-3">
              {categoryQuestions.map((q, index) => (
                <QuestionCard
                  key={index}
                  question={q.question}
                  category={q.category as any}
                  requirements={q.requirements}
                />
              ))}
            </div>
          </div>
        )
      })}
    </div>
  )
}

import { useState } from 'react'
import { ClipboardDocumentIcon, CheckIcon, ViewColumnsIcon, MapIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import SynthesisQuestionsMindMap from './SynthesisQuestionsMindMap'

interface SynthesisQuestionsTabProps {
  questions: SynthesisQuestion[]
}

interface SynthesisQuestion {
  question: string
  category: string
  icon: string
  related_papers: string[]
}

export default function SynthesisQuestionsTab({ questions }: SynthesisQuestionsTabProps) {
  const [copiedQuestion, setCopiedQuestion] = useState<number | null>(null)
  const [copiedCategory, setCopiedCategory] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<'list' | 'mindmap'>('list')

  const copyQuestion = (question: string, index: number) => {
    navigator.clipboard.writeText(question)
    setCopiedQuestion(index)
    toast.success('Question copied!')
    setTimeout(() => setCopiedQuestion(null), 2000)
  }

  const copyAllInCategory = (category: string) => {
    const categoryQuestions = questions.filter(q => q.category === category)
    const text = categoryQuestions.map(q => `• ${q.question}`).join('\n\n')
    navigator.clipboard.writeText(text)
    setCopiedCategory(category)
    toast.success(`All ${category} questions copied!`)
    setTimeout(() => setCopiedCategory(null), 2000)
  }

  const questionsByCategory = questions.reduce((acc, q) => {
    if (!acc[q.category]) acc[q.category] = []
    acc[q.category].push(q)
    return acc
  }, {} as Record<string, SynthesisQuestion[]>)

  const categoryInfo = {
    conflict: {
      title: 'Questions from Conflicting Findings',
      description: 'Papers disagree on these topics. Understanding why can strengthen your analysis.',
      color: 'orange'
    },
    gap: {
      title: 'Questions from Research Gaps',
      description: 'Areas not yet studied. Consider why these gaps exist and their importance.',
      color: 'purple'
    },
    pattern: {
      title: 'Questions from Methodological Patterns',
      description: 'Common methods across papers. Reflect on implications of these choices.',
      color: 'blue'
    },
    positioning: {
      title: 'Questions for Positioning Your Research',
      description: 'Use these to articulate how your work fits into the broader landscape.',
      color: 'green'
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

  return (
    <div className="space-y-4">
      <div className="bg-surface/50 rounded-lg border border-border-base p-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-lg font-serif font-semibold text-text-primary">
            Critical Thinking Questions
          </h3>
          {/* View mode toggle */}
          <div className="flex gap-1 bg-surface-hover rounded-lg p-1">
            <button
              onClick={() => setViewMode('list')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded transition-colors ${
                viewMode === 'list'
                  ? 'bg-accent-primary text-white'
                  : 'text-text-tertiary hover:text-text-primary'
              }`}
            >
              <ViewColumnsIcon className="h-4 w-4" />
              <span className="text-xs font-medium">List</span>
            </button>
            <button
              onClick={() => setViewMode('mindmap')}
              className={`flex items-center gap-2 px-3 py-1.5 rounded transition-colors ${
                viewMode === 'mindmap'
                  ? 'bg-accent-primary text-white'
                  : 'text-text-tertiary hover:text-text-primary'
              }`}
            >
              <MapIcon className="h-4 w-4" />
              <span className="text-xs font-medium">Mind Map</span>
            </button>
          </div>
        </div>
        <p className="text-sm text-text-tertiary">
          These questions help you think across papers and synthesize findings.
          Use them as prompts when writing your literature review.
        </p>
      </div>

      {viewMode === 'list' ? (
        // List View
        <>
          {Object.entries(questionsByCategory).map(([category, categoryQuestions]) => {
            const info = categoryInfo[category as keyof typeof categoryInfo]
            if (!info) return null

            return (
              <div key={category} className="bg-surface rounded-lg border border-border-base">
                <div className="p-4 border-b border-border-subtle">
                  <div className="flex items-center justify-between">
                    <div>
                      <h4 className="text-lg font-semibold text-text-primary mb-1">
                        {categoryQuestions[0]?.icon} {info.title}
                      </h4>
                      <p className="text-sm text-text-tertiary">{info.description}</p>
                    </div>
                    <button
                      onClick={() => copyAllInCategory(category)}
                      className="px-3 py-1.5 text-xs text-text-tertiary hover:text-text-primary bg-surface-hover hover:bg-surface rounded transition-colors flex items-center gap-2"
                    >
                      {copiedCategory === category ? (
                        <>
                          <CheckIcon className="h-4 w-4 text-green-500" />
                          Copied!
                        </>
                      ) : (
                        <>
                          <ClipboardDocumentIcon className="h-4 w-4" />
                          Copy All
                        </>
                      )}
                    </button>
                  </div>
                </div>

                <div className="p-4 space-y-3">
                  {categoryQuestions.map((q, index) => (
                    <div
                      key={index}
                      className="p-3 bg-bg-base rounded-lg border border-border-base hover:border-border-subtle transition-colors group"
                    >
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex-1">
                          <p className="text-sm text-text-primary mb-2">{q.question}</p>
                          {q.related_papers && q.related_papers.length > 0 && (
                            <div className="text-xs text-text-muted">
                              <span>Papers: </span>
                              <span className="text-text-tertiary">{q.related_papers.join(', ')}</span>
                            </div>
                          )}
                        </div>
                        <button
                          onClick={() => copyQuestion(q.question, index)}
                          className="opacity-0 group-hover:opacity-100 transition-opacity text-text-tertiary hover:text-text-primary"
                        >
                          {copiedQuestion === index ? (
                            <CheckIcon className="h-4 w-4 text-green-500" />
                          ) : (
                            <ClipboardDocumentIcon className="h-4 w-4" />
                          )}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )
          })}
        </>
      ) : (
        // Mind Map View
        <SynthesisQuestionsMindMap questions={questions} />
      )}
    </div>
  )
}

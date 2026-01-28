import { useState, useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'
import MethodologyRecommendations from './MethodologyRecommendations'
import { Badge } from './ui/Badge'
import {
  LightBulbIcon,
  BeakerIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  TrashIcon,
  MagnifyingGlassIcon as _MagnifyingGlassIcon
} from '@heroicons/react/24/outline'

const MAX_RESEARCH_QUESTIONS = 30

interface ResearchQuestion {
  id: string
  question: string
  rationale: string
  suggested_methodology: string
  gap_category: string | null
  status: 'new' | 'exploring' | 'answered'
  notes: string | null
  created_at: string
}

interface ResearchQuestionsProps {
  projectId: string
  insightsStatus: string
  hideMethodology?: boolean
  methodologyOnly?: boolean
}

const GAP_CATEGORY_COLORS = {
  methodological: 'bg-blue-600/20 text-blue-400 border-blue-600/30',
  population: 'bg-green-600/20 text-green-400 border-green-600/30',
  theoretical: 'bg-purple-600/20 text-purple-400 border-purple-600/30',
  temporal: 'bg-orange-600/20 text-orange-400 border-orange-600/30',
}

const STATUS_OPTIONS = [
  { value: 'new', label: 'New', color: 'text-text-tertiary' },
  { value: 'exploring', label: 'Exploring', color: 'text-blue-400' },
  { value: 'answered', label: 'Answered', color: 'text-emerald-400' },
]

export default function ResearchQuestions({
  projectId,
  insightsStatus,
  hideMethodology = false,
  methodologyOnly = false
}: ResearchQuestionsProps) {
  const { session } = useAuthStore()
  const [questions, setQuestions] = useState<ResearchQuestion[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [selectedQuestions, setSelectedQuestions] = useState<Set<string>>(new Set())
  const [expandedQuestions, setExpandedQuestions] = useState<Set<string>>(new Set())
  const [editingNotes, setEditingNotes] = useState<string | null>(null)
  const [noteText, setNoteText] = useState('')
  const [methodologyRecommendations, setMethodologyRecommendations] = useState<Map<string, any[]>>(new Map())
  const [loadingMethodology, setLoadingMethodology] = useState<Set<string>>(new Set())
  const [customQuestion, setCustomQuestion] = useState('')
  const [generatingCustomMethodology, setGeneratingCustomMethodology] = useState(false)
  const [customMethodology, setCustomMethodology] = useState<any>(null)

  const MAX_METHODOLOGY_PER_QUESTION = 3

  useEffect(() => {
    if (insightsStatus === 'analyzed') {
      fetchQuestions()
    }
  }, [projectId, insightsStatus])

  const fetchQuestions = async () => {
    if (!session?.access_token) return

    setLoading(true)
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/research-questions/projects/${projectId}/questions`,
        {
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!response.ok) throw new Error('Failed to fetch questions')

      const data = await response.json()
      setQuestions(data.questions || [])
    } catch (error: any) {
      console.error('Failed to fetch questions:', error)
    } finally {
      setLoading(false)
    }
  }

  const handleGenerate = async () => {
    if (!session?.access_token) return

    // Check capacity before generating
    const isAtCapacity = questions.length >= MAX_RESEARCH_QUESTIONS
    const isNearCapacity = questions.length >= MAX_RESEARCH_QUESTIONS - 5

    if (isAtCapacity) {
      toast.error(`Maximum capacity reached (${MAX_RESEARCH_QUESTIONS}). Please delete some questions to generate more.`)
      return
    }

    if (isNearCapacity) {
      const confirmed = confirm(
        `You have ${questions.length}/${MAX_RESEARCH_QUESTIONS} questions. ` +
        `After generating 5 more, you'll be at capacity. Continue?`
      )
      if (!confirmed) return
    }

    setGenerating(true)
    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/research-questions/projects/${projectId}/generate`,
        {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail?.message || errorData.detail || 'Failed to generate questions')
      }

      const data = await response.json()
      const newQuestions = data.questions || []

      // Simply add new questions (no auto-deletion)
      setQuestions(prev => [...prev, ...newQuestions])
      toast.success(`Discovered ${newQuestions.length} new research questions!`)
    } catch (error: any) {
      console.error('Failed to generate questions:', error)
      toast.error(error.message || 'Failed to explore research questions')
    } finally {
      setGenerating(false)
    }
  }

  const handleStatusChange = async (questionId: string, newStatus: string) => {
    if (!session?.access_token) return

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/research-questions/questions/${questionId}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({ status: newStatus }),
        }
      )

      if (!response.ok) throw new Error('Failed to update status')

      const data = await response.json()
      setQuestions(prev => prev.map(q => q.id === questionId ? data.question : q))
      toast.success('Status updated')
    } catch (error: any) {
      console.error('Failed to update status:', error)
      toast.error('Failed to update status')
    }
  }

  const handleSaveNotes = async (questionId: string) => {
    if (!session?.access_token) return

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/research-questions/questions/${questionId}`,
        {
          method: 'PATCH',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({ notes: noteText }),
        }
      )

      if (!response.ok) throw new Error('Failed to save notes')

      const data = await response.json()
      setQuestions(prev => prev.map(q => q.id === questionId ? data.question : q))
      setEditingNotes(null)
      setNoteText('')
      toast.success('Notes saved')
    } catch (error: any) {
      console.error('Failed to save notes:', error)
      toast.error('Failed to save notes')
    }
  }

  const handleBulkDelete = async () => {
    if (!session?.access_token) return
    if (selectedQuestions.size === 0) {
      toast.error('Please select questions to delete')
      return
    }

    const confirmed = confirm(`Delete ${selectedQuestions.size} selected question(s)?`)
    if (!confirmed) return

    try {
      const questionIds = Array.from(selectedQuestions)

      // Delete each question
      await Promise.all(
        questionIds.map(id =>
          fetch(
            `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/research-questions/questions/${id}`,
            {
              method: 'DELETE',
              headers: {
                'Authorization': `Bearer ${session.access_token}`,
              },
            }
          )
        )
      )

      // Update local state
      setQuestions(prev => prev.filter(q => !selectedQuestions.has(q.id)))
      setSelectedQuestions(new Set())
      toast.success(`Deleted ${questionIds.length} question(s)`)
    } catch (error: any) {
      console.error('Failed to delete questions:', error)
      toast.error('Failed to delete questions')
    }
  }

  const handleDelete = async (questionId: string) => {
    if (!session?.access_token) return
    if (!confirm('Delete this research question?')) return

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/research-questions/questions/${questionId}`,
        {
          method: 'DELETE',
          headers: {
            'Authorization': `Bearer ${session.access_token}`,
          },
        }
      )

      if (!response.ok) throw new Error('Failed to delete question')

      setQuestions(prev => prev.filter(q => q.id !== questionId))
      toast.success('Question deleted')
    } catch (error: any) {
      console.error('Failed to delete question:', error)
      toast.error('Failed to delete question')
    }
  }

  const toggleExpanded = (questionId: string) => {
    setExpandedQuestions(prev => {
      const newSet = new Set(prev)
      if (newSet.has(questionId)) {
        newSet.delete(questionId)
      } else {
        newSet.add(questionId)
      }
      return newSet
    })
  }

  const handleDeleteMethodology = (questionId: string, methodologyId: string) => {
    setMethodologyRecommendations(prev => {
      const newMap = new Map(prev)
      const existing = newMap.get(questionId) || []
      const filtered = existing.filter((m: any) => m.id !== methodologyId)

      if (filtered.length === 0) {
        newMap.delete(questionId)
      } else {
        newMap.set(questionId, filtered)
      }

      return newMap
    })
    toast.success('Methodology deleted')
  }

  const handleGetMethodology = async (questionId: string, _question: string) => {
    if (!session?.access_token) return

    // Check if already at max capacity for this question
    const existingMethodologies = methodologyRecommendations.get(questionId) || []
    if (existingMethodologies.length >= MAX_METHODOLOGY_PER_QUESTION) {
      toast.error(`Maximum ${MAX_METHODOLOGY_PER_QUESTION} methodology recommendations per question. Delete one to generate more.`)
      return
    }

    setLoadingMethodology(prev => new Set(prev).add(questionId))

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/methodology-recommendations/generate`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({
            question_id: questionId,
            project_id: projectId
          }),
        }
      )

      if (!response.ok) throw new Error('Failed to generate methodology')

      const data = await response.json()

      // Add new methodology to array instead of replacing
      setMethodologyRecommendations(prev => {
        const newMap = new Map(prev)
        const existing = newMap.get(questionId) || []
        newMap.set(questionId, [...existing, { id: crypto.randomUUID(), ...data }])
        return newMap
      })

      const newCount = existingMethodologies.length + 1
      if (newCount >= MAX_METHODOLOGY_PER_QUESTION) {
        toast.success(`Methodology generated! (${newCount}/${MAX_METHODOLOGY_PER_QUESTION} - at capacity)`)
      } else {
        toast.success(`Methodology generated! (${newCount}/${MAX_METHODOLOGY_PER_QUESTION})`)
      }
    } catch (error: any) {
      console.error('Failed to generate methodology:', error)
      toast.error('Failed to generate methodology recommendations')
    } finally {
      setLoadingMethodology(prev => {
        const newSet = new Set(prev)
        newSet.delete(questionId)
        return newSet
      })
    }
  }

  const handleCustomQuestionMethodology = async () => {
    if (!session?.access_token || !customQuestion.trim()) return

    setGeneratingCustomMethodology(true)

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/methodology-recommendations/generate`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({
            custom_question: customQuestion.trim(),
            project_id: projectId
          }),
        }
      )

      if (!response.ok) throw new Error('Failed to generate methodology')

      const data = await response.json()
      setCustomMethodology(data)
      toast.success('Methodology recommendations generated!')
    } catch (error: any) {
      console.error('Failed to generate methodology:', error)
      toast.error('Failed to generate methodology recommendations')
    } finally {
      setGeneratingCustomMethodology(false)
    }
  }

  if (insightsStatus !== 'analyzed') {
    return (
      <div className="bg-surface/50 rounded-lg border border-border-subtle p-8 text-center">
        <LightBulbIcon className="h-12 w-12 text-text-muted mx-auto mb-4" />
        <p className="text-text-tertiary">Analyze project insights first to generate research questions</p>
      </div>
    )
  }

  const isAtCapacity = questions.length >= MAX_RESEARCH_QUESTIONS
  const isNearCapacity = questions.length >= MAX_RESEARCH_QUESTIONS - 5

  return (
    <div className="space-y-4">
      {/* Header - hide when methodologyOnly */}
      {!methodologyOnly && (
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-purple-600/20 rounded-lg">
              <LightBulbIcon className="h-6 w-6 text-purple-400" />
            </div>
            <div>
              <h3 className="text-lg font-serif font-semibold text-text-primary">Research Questions</h3>
              <div className="flex items-center gap-2">
                <Badge variant={isAtCapacity ? 'error' : isNearCapacity ? 'warning' : 'neutral'}>
                  {questions.length} / {MAX_RESEARCH_QUESTIONS}
                </Badge>
                {isAtCapacity && (
                  <p className="text-sm text-text-tertiary">
                    ⚠️ At capacity - delete some to generate more
                  </p>
                )}
              </div>
            </div>
          </div>
          <div className="flex gap-2">
            {selectedQuestions.size > 0 && (
              <button
                onClick={handleBulkDelete}
                className="px-4 py-2 bg-red-600 text-white font-semibold rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2"
              >
                <TrashIcon className="h-5 w-5" />
                Delete Selected ({selectedQuestions.size})
              </button>
            )}
            <button
              onClick={handleGenerate}
              disabled={generating || isAtCapacity}
              className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {generating ? (
                <>
                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                  Exploring...
                </>
              ) : (
                <>
                  Explore More Questions
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Custom Question Input - hide when hideMethodology */}
      {!hideMethodology && (
        <div className="bg-surface/50 rounded-lg border border-border-base p-4">
        <h4 className="text-sm font-semibold text-text-secondary mb-3">Get Methodology for Your Own Question</h4>
        <div className="flex gap-3">
          <input
            type="text"
            value={customQuestion}
            onChange={(e) => setCustomQuestion(e.target.value)}
            placeholder="Enter your research question..."
            className="flex-1 px-4 py-2 bg-bg-base border border-border-subtle rounded-lg text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
            onKeyPress={(e) => e.key === 'Enter' && handleCustomQuestionMethodology()}
          />
          <button
            onClick={handleCustomQuestionMethodology}
            disabled={generatingCustomMethodology || !customQuestion.trim()}
            className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {generatingCustomMethodology ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                Generating...
              </>
            ) : (
              <>
                <BeakerIcon className="h-5 w-5" />
                Get Methodology
              </>
            )}
          </button>
        </div>
        {customMethodology && (
          <MethodologyRecommendations
            recommendations={customMethodology.recommendations}
            question={customMethodology.question}
          />
        )}
        </div>
      )}

      {/* Questions List - hide when methodologyOnly */}
      {!methodologyOnly && (
        loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
        </div>
      ) : questions.length === 0 ? (
        <div className="bg-surface/30 rounded-lg border border-border-subtle p-8 text-center">
          <p className="text-text-tertiary">No research questions yet. Click "Explore More Questions" to discover potential avenues for your research.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {questions.map((question) => {
            const isExpanded = expandedQuestions.has(question.id)
            const isEditingNotes = editingNotes === question.id
            const currentStatus = STATUS_OPTIONS.find(s => s.value === question.status)

            return (
              <div key={question.id} className="bg-surface/50 rounded-lg border border-border-base hover:border-border-subtle transition-colors">
                {/* Question Header */}
                <div className="p-4">
                  <div className="flex items-start gap-3">
                    {/* Checkbox for bulk selection */}
                    <input
                      type="checkbox"
                      checked={selectedQuestions.has(question.id)}
                      onChange={(e) => {
                        const newSelected = new Set(selectedQuestions)
                        if (e.target.checked) {
                          newSelected.add(question.id)
                        } else {
                          newSelected.delete(question.id)
                        }
                        setSelectedQuestions(newSelected)
                      }}
                      className="mt-1 h-4 w-4 text-accent-primary border-border-base rounded focus:ring-2 focus:ring-accent-primary"
                    />
                    <div className="flex-1 flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        {question.gap_category && (
                          <span className={`text-xs px-2 py-1 rounded border font-mono ${GAP_CATEGORY_COLORS[question.gap_category as keyof typeof GAP_CATEGORY_COLORS] || 'bg-surface-hover text-text-secondary'}`}>
                            {question.gap_category}
                          </span>
                        )}
                        <select
                          value={question.status}
                          onChange={(e) => handleStatusChange(question.id, e.target.value)}
                          className={`text-xs px-2 py-1 rounded bg-bg-base border border-border-subtle ${currentStatus?.color} focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors`}
                        >
                          {STATUS_OPTIONS.map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </div>
                      <h4 className="text-text-primary font-medium leading-relaxed">{question.question}</h4>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleExpanded(question.id)}
                        className="text-text-tertiary hover:text-text-primary transition-colors"
                      >
                        {isExpanded ? (
                          <ChevronUpIcon className="h-5 w-5" />
                        ) : (
                          <ChevronDownIcon className="h-5 w-5" />
                        )}
                      </button>
                      <button
                        onClick={() => handleDelete(question.id)}
                        className="text-text-tertiary hover:text-red-400 transition-colors"
                      >
                        <TrashIcon className="h-5 w-5" />
                      </button>
                    </div>
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="px-4 pb-4 space-y-4 border-t border-border-subtle pt-4">
                    {/* Rationale */}
                    <div>
                      <h5 className="text-sm font-semibold text-text-secondary mb-1">Why this matters:</h5>
                      <p className="text-sm text-text-tertiary leading-relaxed">{question.rationale}</p>
                    </div>

                    {/* Methodology */}
                    <div className="flex items-start gap-2">
                      <BeakerIcon className="h-5 w-5 text-blue-400 mt-0.5" />
                      <div>
                        <h5 className="text-sm font-semibold text-text-secondary">Suggested Methodology:</h5>
                        <p className="text-sm text-text-tertiary">{question.suggested_methodology}</p>
                      </div>
                    </div>

                    {/* Notes */}
                    <div>
                      <h5 className="text-sm font-semibold text-text-secondary mb-2">Notes:</h5>
                      {isEditingNotes ? (
                        <div className="space-y-2">
                          <textarea
                            value={noteText}
                            onChange={(e) => setNoteText(e.target.value)}
                            placeholder="Add your notes..."
                            className="w-full px-3 py-2 bg-bg-base border border-border-subtle rounded text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                            rows={3}
                          />
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleSaveNotes(question.id)}
                              className="px-3 py-1 bg-accent-primary text-white text-sm font-semibold rounded hover:bg-accent-hover transition-colors"
                            >
                              Save
                            </button>
                            <button
                              onClick={() => {
                                setEditingNotes(null)
                                setNoteText('')
                              }}
                              className="px-3 py-1 bg-surface-hover text-text-secondary text-sm rounded hover:bg-surface transition-colors"
                            >
                              Cancel
                            </button>
                          </div>
                        </div>
                      ) : (
                        <div
                          onClick={() => {
                            setEditingNotes(question.id)
                            setNoteText(question.notes || '')
                          }}
                          className="text-sm text-text-tertiary cursor-pointer hover:text-text-secondary transition-colors"
                        >
                          {question.notes ? (
                            <p className="whitespace-pre-wrap">{question.notes}</p>
                          ) : (
                            <p className="italic text-text-muted">Click to add notes...</p>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Methodology Recommendations - hide when hideMethodology */}
                    {!hideMethodology && (
                      <div className="pt-4 border-t border-border-subtle space-y-4">
                        {/* Generate button with count */}
                        {(() => {
                          const existingMethodologies = methodologyRecommendations.get(question.id) || []
                          const count = existingMethodologies.length
                          const isAtMax = count >= MAX_METHODOLOGY_PER_QUESTION

                          return (
                            <button
                              onClick={() => handleGetMethodology(question.id, question.question)}
                              disabled={loadingMethodology.has(question.id) || isAtMax}
                              className="w-full px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                            >
                              {loadingMethodology.has(question.id) ? (
                                <>
                                  <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                                  Generating Methodology...
                                </>
                              ) : (
                                <>
                                  <BeakerIcon className="h-5 w-5" />
                                  Get Methodology ({count}/{MAX_METHODOLOGY_PER_QUESTION})
                                  {isAtMax && ' - At Capacity'}
                                </>
                              )}
                            </button>
                          )
                        })()}

                        {/* Display all methodologies */}
                        {methodologyRecommendations.has(question.id) && methodologyRecommendations.get(question.id)!.map((methodology: any, index: number) => (
                          <div key={methodology.id} className="relative">
                            {/* Delete button for each methodology */}
                            <div className="flex items-center justify-between mb-2">
                              <span className="text-xs text-text-muted font-mono">
                                Methodology Option #{index + 1}
                              </span>
                              <button
                                onClick={() => handleDeleteMethodology(question.id, methodology.id)}
                                className="text-text-tertiary hover:text-red-400 transition-colors flex items-center gap-1 text-xs"
                              >
                                <TrashIcon className="h-4 w-4" />
                                Delete
                              </button>
                            </div>
                            <MethodologyRecommendations
                              recommendations={methodology.recommendations}
                              question={question.question}
                            />
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            )
          })}
        </div>
        )
      )}
    </div>
  )
}

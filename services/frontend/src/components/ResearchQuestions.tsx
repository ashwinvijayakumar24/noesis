import { useState, useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import MethodologyRecommendations from './MethodologyRecommendations'
import {
  SparklesIcon,
  LightBulbIcon,
  BeakerIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  TrashIcon
} from '@heroicons/react/24/outline'

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
}

const GAP_CATEGORY_COLORS = {
  methodological: 'bg-blue-600/20 text-blue-400 border-blue-600/30',
  population: 'bg-green-600/20 text-green-400 border-green-600/30',
  theoretical: 'bg-purple-600/20 text-purple-400 border-purple-600/30',
  temporal: 'bg-orange-600/20 text-orange-400 border-orange-600/30',
}

const STATUS_OPTIONS = [
  { value: 'new', label: 'New', color: 'text-neutral-400' },
  { value: 'exploring', label: 'Exploring', color: 'text-blue-400' },
  { value: 'answered', label: 'Answered', color: 'text-green-400' },
]

export default function ResearchQuestions({ projectId, insightsStatus }: ResearchQuestionsProps) {
  const { session } = useAuthStore()
  const [questions, setQuestions] = useState<ResearchQuestion[]>([])
  const [loading, setLoading] = useState(false)
  const [generating, setGenerating] = useState(false)
  const [expandedQuestions, setExpandedQuestions] = useState<Set<string>>(new Set())
  const [editingNotes, setEditingNotes] = useState<string | null>(null)
  const [noteText, setNoteText] = useState('')
  const [methodologyRecommendations, setMethodologyRecommendations] = useState<Map<string, any>>(new Map())
  const [loadingMethodology, setLoadingMethodology] = useState<Set<string>>(new Set())
  const [customQuestion, setCustomQuestion] = useState('')
  const [generatingCustomMethodology, setGeneratingCustomMethodology] = useState(false)
  const [customMethodology, setCustomMethodology] = useState<any>(null)

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
      setQuestions(data.questions || [])
      toast.success(`Generated ${data.count} research questions!`)
    } catch (error: any) {
      console.error('Failed to generate questions:', error)
      toast.error(error.message || 'Failed to generate research questions')
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

  const handleGetMethodology = async (questionId: string, question: string) => {
    if (!session?.access_token) return

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
      setMethodologyRecommendations(prev => new Map(prev).set(questionId, data.recommendations))
      toast.success('Methodology recommendations generated!')
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
      <div className="bg-neutral-900/50 rounded-lg border border-neutral-800/50 p-8 text-center">
        <LightBulbIcon className="h-12 w-12 text-neutral-600 mx-auto mb-4" />
        <p className="text-neutral-400">Analyze project insights first to generate research questions</p>
      </div>
    )
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-purple-600/20 rounded-lg">
            <LightBulbIcon className="h-6 w-6 text-purple-400" />
          </div>
          <div>
            <h3 className="text-lg font-serif font-semibold text-neutral-50">Research Questions</h3>
            <p className="text-sm text-neutral-400">AI-generated questions based on identified gaps</p>
          </div>
        </div>
        <button
          onClick={handleGenerate}
          disabled={generating}
          className="px-4 py-2 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          {generating ? (
            <>
              <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
              Generating...
            </>
          ) : (
            <>
              <SparklesIcon className="h-5 w-5" />
              Generate Questions
            </>
          )}
        </button>
      </div>

      {/* Custom Question Input */}
      <div className="bg-neutral-900/50 rounded-lg border border-neutral-800 p-4">
        <h4 className="text-sm font-semibold text-neutral-300 mb-3">Get Methodology for Your Own Question</h4>
        <div className="flex gap-3">
          <input
            type="text"
            value={customQuestion}
            onChange={(e) => setCustomQuestion(e.target.value)}
            placeholder="Enter your research question..."
            className="flex-1 px-4 py-2 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
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

      {/* Questions List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
        </div>
      ) : questions.length === 0 ? (
        <div className="bg-neutral-900/30 rounded-lg border border-neutral-800/50 p-8 text-center">
          <p className="text-neutral-400">No research questions yet. Click "Generate Questions" to create them.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {questions.map((question) => {
            const isExpanded = expandedQuestions.has(question.id)
            const isEditingNotes = editingNotes === question.id
            const currentStatus = STATUS_OPTIONS.find(s => s.value === question.status)

            return (
              <div key={question.id} className="bg-neutral-900/50 rounded-lg border border-neutral-800 hover:border-neutral-700 transition-colors">
                {/* Question Header */}
                <div className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        {question.gap_category && (
                          <span className={`text-xs px-2 py-1 rounded border font-mono ${GAP_CATEGORY_COLORS[question.gap_category as keyof typeof GAP_CATEGORY_COLORS] || 'bg-neutral-700 text-neutral-300'}`}>
                            {question.gap_category}
                          </span>
                        )}
                        <select
                          value={question.status}
                          onChange={(e) => handleStatusChange(question.id, e.target.value)}
                          className={`text-xs px-2 py-1 rounded bg-neutral-950 border border-neutral-700 ${currentStatus?.color} focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors`}
                        >
                          {STATUS_OPTIONS.map(option => (
                            <option key={option.value} value={option.value}>{option.label}</option>
                          ))}
                        </select>
                      </div>
                      <h4 className="text-neutral-50 font-medium leading-relaxed">{question.question}</h4>
                    </div>
                    <div className="flex items-center gap-2">
                      <button
                        onClick={() => toggleExpanded(question.id)}
                        className="text-neutral-400 hover:text-neutral-50 transition-colors"
                      >
                        {isExpanded ? (
                          <ChevronUpIcon className="h-5 w-5" />
                        ) : (
                          <ChevronDownIcon className="h-5 w-5" />
                        )}
                      </button>
                      <button
                        onClick={() => handleDelete(question.id)}
                        className="text-neutral-400 hover:text-red-400 transition-colors"
                      >
                        <TrashIcon className="h-5 w-5" />
                      </button>
                    </div>
                  </div>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="px-4 pb-4 space-y-4 border-t border-neutral-700/50 pt-4">
                    {/* Rationale */}
                    <div>
                      <h5 className="text-sm font-semibold text-neutral-300 mb-1">Why this matters:</h5>
                      <p className="text-sm text-neutral-400 leading-relaxed">{question.rationale}</p>
                    </div>

                    {/* Methodology */}
                    <div className="flex items-start gap-2">
                      <BeakerIcon className="h-5 w-5 text-blue-400 mt-0.5" />
                      <div>
                        <h5 className="text-sm font-semibold text-neutral-300">Suggested Methodology:</h5>
                        <p className="text-sm text-neutral-400">{question.suggested_methodology}</p>
                      </div>
                    </div>

                    {/* Notes */}
                    <div>
                      <h5 className="text-sm font-semibold text-neutral-300 mb-2">Notes:</h5>
                      {isEditingNotes ? (
                        <div className="space-y-2">
                          <textarea
                            value={noteText}
                            onChange={(e) => setNoteText(e.target.value)}
                            placeholder="Add your notes..."
                            className="w-full px-3 py-2 bg-neutral-950 border border-neutral-700 rounded text-sm text-neutral-50 placeholder-neutral-500 focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
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
                              className="px-3 py-1 bg-neutral-700 text-neutral-300 text-sm rounded hover:bg-neutral-600 transition-colors"
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
                          className="text-sm text-neutral-400 cursor-pointer hover:text-neutral-300 transition-colors"
                        >
                          {question.notes ? (
                            <p className="whitespace-pre-wrap">{question.notes}</p>
                          ) : (
                            <p className="italic text-neutral-500">Click to add notes...</p>
                          )}
                        </div>
                      )}
                    </div>

                    {/* Methodology Recommendations */}
                    <div className="pt-4 border-t border-neutral-700/50">
                      {!methodologyRecommendations.has(question.id) ? (
                        <button
                          onClick={() => handleGetMethodology(question.id, question.question)}
                          disabled={loadingMethodology.has(question.id)}
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
                              Get Methodology Recommendations
                            </>
                          )}
                        </button>
                      ) : (
                        <MethodologyRecommendations
                          recommendations={methodologyRecommendations.get(question.id)}
                          question={question.question}
                        />
                      )}
                    </div>
                  </div>
                )}
              </div>
            )
          })}
        </div>
      )}
    </div>
  )
}

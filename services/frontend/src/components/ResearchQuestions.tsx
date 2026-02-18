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
  PlusCircleIcon,
  XMarkIcon
} from '@heroicons/react/24/outline'

const MAX_RESEARCH_QUESTIONS = 10

interface ResearchQuestion {
  id: string
  question: string
  rationale: string
  suggested_methodology: string
  gap_category: string | null
  status: 'new' | 'added' | 'dismissed'
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
  methodological: 'bg-[#1e40af] text-white border-[#1e40af]',
  population: 'bg-[#166534] text-white border-[#166534]',
  theoretical: 'bg-[#6b21a8] text-white border-[#6b21a8]',
  temporal: 'bg-[#9a3412] text-white border-[#9a3412]',
}

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
  const [activeTab, setActiveTab] = useState<'new' | 'accepted' | 'dismissed'>('new')
  const [selectedDismissed, setSelectedDismissed] = useState<Set<string>>(new Set())
  const [expandedQuestions, setExpandedQuestions] = useState<Set<string>>(new Set())
  const [editingNotes, setEditingNotes] = useState<string | null>(null)
  const [noteText, setNoteText] = useState('')
  const [methodologyRecommendations, setMethodologyRecommendations] = useState<Map<string, any[]>>(new Map())
  const [loadingMethodology, setLoadingMethodology] = useState<Set<string>>(new Set())
  const [customQuestion, setCustomQuestion] = useState('')
  const [generatingCustomMethodology, setGeneratingCustomMethodology] = useState(false)
  const [customMethodology, setCustomMethodology] = useState<any>(null)
  const [currentPage, setCurrentPage] = useState(1)

  const MAX_METHODOLOGY_PER_QUESTION = 3
  const QUESTIONS_PER_PAGE = 10

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

  const handleKeepQuestion = async (questionId: string) => {
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
          body: JSON.stringify({ status: 'added' }),
        }
      )

      if (!response.ok) throw new Error('Failed to update status')

      const data = await response.json()
      setQuestions(prev => prev.map(q => q.id === questionId ? { ...data.question, status: 'added' } : q))
      toast.success('Question saved to Accepted!')
    } catch (error: any) {
      console.error('Failed to keep question:', error)
      toast.error('Failed to keep question')
    }
  }

  const handleDismiss = async (questionId: string) => {
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
          body: JSON.stringify({ status: 'dismissed' }),
        }
      )

      if (!response.ok) throw new Error('Failed to dismiss')

      const data = await response.json()
      setQuestions(prev => prev.map(q => q.id === questionId ? { ...data.question, status: 'dismissed' } : q))
      toast.success('Question dismissed')
    } catch (error: any) {
      console.error('Failed to dismiss:', error)
      toast.error('Failed to dismiss question')
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

  const handlePermanentDelete = async () => {
    if (!session?.access_token) return
    if (selectedDismissed.size === 0) {
      toast.error('Please select questions to delete')
      return
    }

    const confirmed = confirm(`Permanently delete ${selectedDismissed.size} question(s)? This will free up space in your quota.`)
    if (!confirmed) return

    try {
      const questionIds = Array.from(selectedDismissed)

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
      setQuestions(prev => prev.filter(q => !selectedDismissed.has(q.id)))
      setSelectedDismissed(new Set())
      toast.success(`Permanently deleted ${questionIds.length} question(s)`)
    } catch (error: any) {
      console.error('Failed to delete questions:', error)
      toast.error('Failed to delete questions')
    }
  }

  const handleRestore = async () => {
    if (!session?.access_token) return
    if (selectedDismissed.size === 0) {
      toast.error('Please select questions to restore')
      return
    }

    try {
      const questionIds = Array.from(selectedDismissed)

      // Restore each question to 'new' status
      await Promise.all(
        questionIds.map(id =>
          fetch(
            `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/research-questions/questions/${id}`,
            {
              method: 'PATCH',
              headers: {
                'Content-Type': 'application/json',
                'Authorization': `Bearer ${session.access_token}`,
              },
              body: JSON.stringify({ status: 'new' }),
            }
          )
        )
      )

      // Update local state
      setQuestions(prev => prev.map(q =>
        selectedDismissed.has(q.id) ? { ...q, status: 'new' } : q
      ))
      setSelectedDismissed(new Set())
      toast.success(`Restored ${questionIds.length} question(s) to New`)
    } catch (error: any) {
      console.error('Failed to restore questions:', error)
      toast.error('Failed to restore questions')
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

  const tabQuestions = activeTab === 'new'
    ? questions.filter(q => q.status === 'new')
    : activeTab === 'accepted'
    ? questions.filter(q => q.status === 'added')
    : questions.filter(q => q.status === 'dismissed')

  const totalQuestions = questions.length
  const isAtCapacity = totalQuestions >= MAX_RESEARCH_QUESTIONS
  const isNearCapacity = totalQuestions >= MAX_RESEARCH_QUESTIONS - 5

  // Pagination calculations
  const totalPages = Math.ceil(tabQuestions.length / QUESTIONS_PER_PAGE)
  const startIndex = (currentPage - 1) * QUESTIONS_PER_PAGE
  const endIndex = startIndex + QUESTIONS_PER_PAGE
  const paginatedQuestions = tabQuestions.slice(startIndex, endIndex)

  // Reset to page 1 when tab changes
  useEffect(() => {
    setCurrentPage(1)
  }, [activeTab])

  // Adjust page if current page exceeds total pages
  useEffect(() => {
    if (currentPage > totalPages && totalPages > 0) {
      setCurrentPage(totalPages)
    }
  }, [totalPages, currentPage])

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
                  {totalQuestions} / {MAX_RESEARCH_QUESTIONS}
                </Badge>
                {isAtCapacity && (
                  <p className="text-sm text-text-tertiary">
                    ⚠️ At capacity - permanently delete dismissed questions to generate more
                  </p>
                )}
              </div>
            </div>
          </div>
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
      )}

      {/* Tab Navigation */}
      {!methodologyOnly && questions.length > 0 && (
        <div className="flex items-center gap-2">
          <button
            onClick={() => setActiveTab('new')}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
              activeTab === 'new'
                ? 'bg-purple-800 text-purple-100 border border-purple-700'
                : 'bg-surface-hover text-text-secondary hover:bg-surface border border-border-base'
            }`}
          >
            New ({questions.filter(q => q.status === 'new').length})
          </button>
          <button
            onClick={() => setActiveTab('accepted')}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
              activeTab === 'accepted'
                ? 'bg-purple-800 text-purple-100 border border-purple-700'
                : 'bg-surface-hover text-text-secondary hover:bg-surface border border-border-base'
            }`}
          >
            Accepted ({questions.filter(q => q.status === 'added').length})
          </button>
          <button
            onClick={() => setActiveTab('dismissed')}
            className={`px-4 py-2 text-sm font-semibold rounded-lg transition-colors ${
              activeTab === 'dismissed'
                ? 'bg-purple-800 text-purple-100 border border-purple-700'
                : 'bg-surface-hover text-text-secondary hover:bg-surface border border-border-base'
            }`}
          >
            Dismissed ({questions.filter(q => q.status === 'dismissed').length})
          </button>
        </div>
      )}

      {/* Dismissed Tab Actions */}
      {!methodologyOnly && activeTab === 'dismissed' && selectedDismissed.size > 0 && (
        <div className="flex gap-2">
          <button
            onClick={handleRestore}
            className="px-4 py-2 bg-purple-800 text-purple-100 font-semibold rounded-lg hover:bg-purple-700 transition-colors flex items-center gap-2 border border-purple-700"
          >
            Restore ({selectedDismissed.size})
          </button>
          <button
            onClick={handlePermanentDelete}
            className="px-4 py-2 bg-red-600 text-white font-semibold rounded-lg hover:bg-red-700 transition-colors flex items-center gap-2"
          >
            <TrashIcon className="h-5 w-5" />
            Delete Permanently ({selectedDismissed.size})
          </button>
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
      ) : tabQuestions.length === 0 ? (
        <div className="bg-surface/30 rounded-lg border border-border-subtle p-8 text-center">
          <LightBulbIcon className="h-12 w-12 text-text-muted mx-auto mb-4" />
          <p className="text-text-tertiary">
            {questions.length === 0
              ? 'No research questions yet. Click "Explore More Questions" to discover potential avenues for your research.'
              : activeTab === 'new'
              ? 'No new questions. Generate more or check other tabs.'
              : activeTab === 'accepted'
              ? 'No accepted questions yet. Keep questions from the New tab to see them here.'
              : 'No dismissed questions.'}
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {paginatedQuestions.map((question) => {
            const isExpanded = expandedQuestions.has(question.id)
            const isEditingNotes = editingNotes === question.id

            return (
              <div key={question.id} className="bg-surface/50 rounded-lg border border-border-base hover:border-border-subtle transition-colors">
                {/* Question Header */}
                <div className="p-4">
                  <div className="flex items-start gap-3">
                    {/* Checkbox only for dismissed tab */}
                    {activeTab === 'dismissed' && (
                      <input
                        type="checkbox"
                        checked={selectedDismissed.has(question.id)}
                        onChange={(e) => {
                          const newSelected = new Set(selectedDismissed)
                          if (e.target.checked) {
                            newSelected.add(question.id)
                          } else {
                            newSelected.delete(question.id)
                          }
                          setSelectedDismissed(newSelected)
                        }}
                        className="mt-1 h-4 w-4 text-accent-primary border-border-base rounded focus:ring-2 focus:ring-accent-primary shrink-0"
                      />
                    )}
                    <div className="flex-1 flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-2">
                        {question.gap_category && (
                          <span className={`text-xs px-2 py-1 rounded border font-mono ${GAP_CATEGORY_COLORS[question.gap_category as keyof typeof GAP_CATEGORY_COLORS] || 'bg-surface-hover text-text-secondary'}`}>
                            {question.gap_category.charAt(0).toUpperCase() + question.gap_category.slice(1)}
                          </span>
                        )}
                      </div>
                      <h4 className="text-text-primary font-medium leading-relaxed">{question.question}</h4>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                      {activeTab === 'new' && (
                        <>
                          <button
                            onClick={() => handleKeepQuestion(question.id)}
                            className="px-3 py-1.5 bg-green-800 text-green-100 text-sm font-semibold rounded hover:bg-green-700 transition-colors flex items-center gap-1 border border-green-700"
                          >
                            <PlusCircleIcon className="h-4 w-4" />
                            Keep Question
                          </button>
                          <button
                            onClick={() => handleDismiss(question.id)}
                            className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded transition-colors"
                            title="Dismiss question"
                          >
                            <XMarkIcon className="h-5 w-5" />
                          </button>
                        </>
                      )}
                      {activeTab === 'accepted' && (
                        <>
                          <span className="px-3 py-1.5 bg-green-900/40 text-green-200 text-sm font-semibold rounded border border-green-800">
                            Kept
                          </span>
                          <button
                            onClick={() => handleDismiss(question.id)}
                            className="p-1.5 text-red-400 hover:text-red-300 hover:bg-red-900/20 rounded transition-colors"
                            title="Dismiss question"
                          >
                            <XMarkIcon className="h-5 w-5" />
                          </button>
                        </>
                      )}
                      {activeTab === 'dismissed' && (
                        <span className="px-3 py-1.5 bg-surface-hover text-text-muted text-sm rounded">
                          Dismissed
                        </span>
                      )}
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

      {/* Pagination Controls */}
      {!methodologyOnly && tabQuestions.length > QUESTIONS_PER_PAGE && (
        <div className="flex items-center justify-between pt-4 border-t border-border-subtle">
          <div className="text-sm text-text-tertiary">
            Showing {startIndex + 1}-{Math.min(endIndex, tabQuestions.length)} of {tabQuestions.length} questions
          </div>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setCurrentPage(prev => Math.max(1, prev - 1))}
              disabled={currentPage === 1}
              className="px-3 py-1.5 text-sm bg-surface-hover text-text-secondary rounded hover:bg-surface transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Previous
            </button>
            <div className="flex items-center gap-1">
              {Array.from({ length: totalPages }, (_, i) => i + 1).map(page => (
                <button
                  key={page}
                  onClick={() => setCurrentPage(page)}
                  className={`px-3 py-1.5 text-sm rounded transition-colors ${
                    currentPage === page
                      ? 'bg-accent-primary text-white font-semibold'
                      : 'bg-surface-hover text-text-secondary hover:bg-surface'
                  }`}
                >
                  {page}
                </button>
              ))}
            </div>
            <button
              onClick={() => setCurrentPage(prev => Math.min(totalPages, prev + 1))}
              disabled={currentPage === totalPages}
              className="px-3 py-1.5 text-sm bg-surface-hover text-text-secondary rounded hover:bg-surface transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            >
              Next
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

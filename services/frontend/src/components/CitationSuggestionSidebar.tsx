import { useState, useEffect } from 'react'
import {
  SparklesIcon,
  CheckCircleIcon,
  XCircleIcon,
  EyeSlashIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  BookOpenIcon,
  ClipboardDocumentCheckIcon
} from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { handleError } from '../lib/errorHandler'
import { Badge, type BadgeVariant } from './ui/Badge'
import { Button } from './ui/Button'

interface CitationSuggestion {
  id: string
  suggestion_id?: string
  claim_text: string
  suggestion_type: string
  suggested_paper: {
    document_id?: string
    title: string
    authors: string[]
    year: string
    doi?: string
    abstract?: string
    relevance_excerpt?: string
  }
  confidence_score: number
  relevance_score: number
  reasoning: string
  impact_level: string
  priority_score: number
  status: string
}

interface CitationSuggestionSidebarProps {
  token: string
  draftId: string
  projectId: string
  onSuggestionAccepted?: (suggestion: CitationSuggestion) => void
}

const getImpactBadgeVariant = (impact: string): BadgeVariant => {
  switch (impact.toLowerCase()) {
    case 'critical':
    case 'high':
      return 'error'
    case 'medium':
      return 'warning'
    case 'low':
      return 'info'
    default:
      return 'neutral'
  }
}

const SUGGESTION_TYPE_LABELS = {
  missing_citation: 'Missing Citation',
  weak_citation: 'Weak Citation',
  alternative_source: 'Alternative Source',
  recent_work: 'Recent Work',
  foundational_work: 'Foundational Work',
}

export default function CitationSuggestionSidebar({
  token,
  draftId,
  projectId: _projectId, // Unused for now - will be used in bulk generation feature
  onSuggestionAccepted
}: CitationSuggestionSidebarProps) {
  const [suggestions, setSuggestions] = useState<CitationSuggestion[]>([])
  const [loading, setLoading] = useState(true)
  const [expandedSuggestions, setExpandedSuggestions] = useState<Set<string>>(new Set())
  const [filterStatus, setFilterStatus] = useState<string>('pending')
  const [respondingTo, setRespondingTo] = useState<string | null>(null)
  // const [generatingAll, setGeneratingAll] = useState(false) // TODO: Implement bulk generation feature

  useEffect(() => {
    if (draftId) {
      loadSuggestions()
    }
  }, [draftId, filterStatus, token])

  const loadSuggestions = async () => {
    try {
      setLoading(true)
      const statusFilter = filterStatus !== 'all' ? filterStatus : undefined
      console.log('[CITATION-SIDEBAR] Loading suggestions with filter:', statusFilter)
      const data = await api.citations.getDraftSuggestions(
        token,
        draftId,
        statusFilter
      )
      console.log('[CITATION-SIDEBAR] API response:', data)
      console.log('[CITATION-SIDEBAR] Suggestions array:', data.suggestions)
      console.log('[CITATION-SIDEBAR] Number of suggestions:', data.suggestions?.length || 0)
      
      // Normalize suggestions - handle JSONB fields that might be strings
      const suggestionsList = (data.suggestions || []).map((suggestion: any) => {
        // Ensure suggested_paper is an object, not a string
        let suggestedPaper = suggestion.suggested_paper
        if (typeof suggestedPaper === 'string') {
          try {
            suggestedPaper = JSON.parse(suggestedPaper)
          } catch (e) {
            console.error('[CITATION-SIDEBAR] Failed to parse suggested_paper:', e)
            suggestedPaper = { title: 'Unknown', authors: [], year: 'n.d.' }
          }
        }
        
        // Ensure authors is an array
        if (!Array.isArray(suggestedPaper.authors)) {
          suggestedPaper.authors = suggestedPaper.authors ? [suggestedPaper.authors] : []
        }
        
        return {
          ...suggestion,
          id: suggestion.id || suggestion.suggestion_id || '',
          suggestion_id: suggestion.suggestion_id || suggestion.id || '',
          suggested_paper: suggestedPaper,
          claim_text: suggestion.claim_text || '',
          status: suggestion.status || 'pending'
        }
      })
      
      console.log('[CITATION-SIDEBAR] Normalized suggestions:', suggestionsList)
      console.log('[CITATION-SIDEBAR] Setting suggestions:', suggestionsList.length)
      setSuggestions(suggestionsList)
    } catch (error: any) {
      console.error('[CITATION-SIDEBAR] Failed to load citation suggestions:', error)
      handleError(error, 'loading citation suggestions')
      setSuggestions([])
    } finally {
      setLoading(false)
    }
  }

  // TODO: Implement bulk generation feature
  // const handleGenerateAllSuggestions = async () => {
  //   ... implementation commented out for now
  // }

  const handleRespond = async (suggestionId: string, status: string, feedback?: string) => {
    try {
      setRespondingTo(suggestionId)

      await api.citations.respondToSuggestion(token, suggestionId, {
        status,
        user_feedback: feedback
      })

      toast.success(
        status === 'accepted' ? 'Citation suggestion accepted!' :
        status === 'rejected' ? 'Citation suggestion rejected' :
        'Citation suggestion dismissed'
      )

      // Find and trigger callback if accepted
      const suggestion = suggestions.find(s => (s.id || s.suggestion_id) === suggestionId)
      if (status === 'accepted' && suggestion && onSuggestionAccepted) {
        onSuggestionAccepted(suggestion)
      }

      // Reload suggestions
      await loadSuggestions()
    } catch (error: any) {
      handleError(error, 'responding to citation suggestion')
    } finally {
      setRespondingTo(null)
    }
  }

  const toggleExpanded = (suggestionId: string) => {
    setExpandedSuggestions(prev => {
      const newSet = new Set(prev)
      if (newSet.has(suggestionId)) {
        newSet.delete(suggestionId)
      } else {
        newSet.add(suggestionId)
      }
      return newSet
    })
  }

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    toast.success(`${label} copied to clipboard!`)
  }

  const getConfidenceColor = (score: number) => {
    if (score >= 0.8) return 'text-success'
    if (score >= 0.6) return 'text-warning'
    return 'text-error'
  }

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center bg-bg-base border-l border-border-base">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary mb-4"></div>
          <p className="text-text-tertiary text-sm">Loading suggestions...</p>
        </div>
      </div>
    )
  }

  return (
    <div className="h-full flex flex-col bg-bg-base border-l border-border-base">
      {/* Header */}
      <div className="p-4 border-b border-border-subtle">
        <div className="flex items-center gap-2 mb-3">
          <SparklesIcon className="h-5 w-5 text-accent-primary" />
          <h3 className="text-lg font-semibold text-text-primary">Citation Suggestions</h3>
        </div>

        {/* Filter Tabs */}
        <div className="flex gap-2 text-xs">
          {['pending', 'accepted', 'rejected', 'all'].map((status) => (
            <button
              key={status}
              onClick={() => setFilterStatus(status)}
              className={`px-3 py-1 rounded-md transition-colors ${
                filterStatus === status
                  ? 'bg-accent-primary text-neutral-900 font-medium'
                  : 'bg-surface text-text-tertiary hover:bg-surface-hover'
              }`}
            >
              {status.charAt(0).toUpperCase() + status.slice(1)}
            </button>
          ))}
        </div>
      </div>

      {/* Suggestions List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {suggestions.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-full py-12 px-4">
            <BookOpenIcon className="h-16 w-16 text-text-muted mx-auto mb-4" />
            <h3 className="text-lg font-semibold text-text-primary mb-2">
              {filterStatus === 'pending' ? 'No Citation Suggestions' : `No ${filterStatus} Suggestions`}
            </h3>
            <p className="text-text-tertiary text-sm text-center max-w-md mb-4">
              {filterStatus === 'pending'
                ? 'Citation suggestions require research papers in your library.'
                : `No ${filterStatus} suggestions found.`
              }
            </p>
            {filterStatus === 'pending' && (
              <div className="bg-surface-hover border border-border-base rounded-lg p-4 max-w-md text-left">
                <p className="text-sm font-semibold text-text-primary mb-2 flex items-center gap-2">
                  <svg className="h-5 w-5 text-amber-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                  To get citation suggestions:
                </p>
                <ul className="space-y-2 text-xs text-text-secondary">
                  <li className="flex items-start gap-2">
                    <span className="text-accent-primary font-bold mt-0.5">1.</span>
                    <span>Upload research papers to your project (Documents tab)</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-accent-primary font-bold mt-0.5">2.</span>
                    <span>Papers are automatically analyzed to extract claims</span>
                  </li>
                  <li className="flex items-start gap-2">
                    <span className="text-accent-primary font-bold mt-0.5">3.</span>
                    <span>Re-analyze your draft to get citation suggestions</span>
                  </li>
                </ul>
                <p className="text-xs text-text-muted mt-3 italic">
                  The more papers you upload, the better the citation suggestions
                </p>
              </div>
            )}
          </div>
        ) : (
          suggestions.map((suggestion) => {
            const suggestionId = suggestion.id || suggestion.suggestion_id || ''
            const isExpanded = expandedSuggestions.has(suggestionId)
            const isResponding = respondingTo === suggestionId

            return (
              <div
                key={suggestionId}
                className="bg-surface border border-border-base rounded-lg overflow-hidden hover:border-border-subtle transition-colors"
              >
                {/* Suggestion Header */}
                <div className="p-3">
                  <div className="flex items-start justify-between gap-2 mb-2">
                    <Badge variant={getImpactBadgeVariant(suggestion.impact_level)}>
                      {suggestion.impact_level?.toUpperCase()}
                    </Badge>
                    <Badge variant="neutral">
                      {SUGGESTION_TYPE_LABELS[suggestion.suggestion_type as keyof typeof SUGGESTION_TYPE_LABELS] ||
                        suggestion.suggestion_type}
                    </Badge>
                  </div>

                  {/* Paper Info */}
                  <h4 className="text-sm font-medium text-text-primary mb-1 line-clamp-2">
                    {suggestion.suggested_paper.title}
                  </h4>

                  <p className="text-xs text-text-tertiary mb-2">
                    {suggestion.suggested_paper.authors.slice(0, 3).join(', ')}
                    {suggestion.suggested_paper.authors.length > 3 && ' et al.'} ({suggestion.suggested_paper.year})
                  </p>

                  {/* Scores */}
                  <div className="flex items-center gap-3 text-xs mb-3">
                    <div>
                      <span className="text-text-muted">Confidence: </span>
                      <span className={`font-medium ${getConfidenceColor(suggestion.confidence_score)}`}>
                        {(suggestion.confidence_score * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div>
                      <span className="text-text-muted">Relevance: </span>
                      <span className={`font-medium ${getConfidenceColor(suggestion.relevance_score)}`}>
                        {(suggestion.relevance_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>

                  {/* Reasoning */}
                  <p className="text-xs text-text-secondary mb-3 italic">
                    "{suggestion.reasoning}"
                  </p>

                  {/* Expand/Collapse Button */}
                  <button
                    onClick={() => toggleExpanded(suggestionId)}
                    className="flex items-center gap-1 text-xs text-accent-primary hover:text-accent-secondary transition-colors"
                  >
                    {isExpanded ? (
                      <>
                        <ChevronUpIcon className="h-4 w-4" />
                        Show Less
                      </>
                    ) : (
                      <>
                        <ChevronDownIcon className="h-4 w-4" />
                        Show More
                      </>
                    )}
                  </button>
                </div>

                {/* Expanded Details */}
                {isExpanded && (
                  <div className="border-t border-border-subtle p-3 bg-surface-hover space-y-3">
                    {/* Claim Context */}
                    {suggestion.claim_text && (
                      <div>
                        <p className="text-xs font-medium text-text-tertiary mb-1">For Claim:</p>
                        <p className="text-xs text-text-secondary bg-bg-base p-2 rounded border border-border-subtle">
                          {suggestion.claim_text}
                        </p>
                      </div>
                    )}

                    {/* Abstract */}
                    {suggestion.suggested_paper.abstract && (
                      <div>
                        <p className="text-xs font-medium text-text-tertiary mb-1">Abstract:</p>
                        <p className="text-xs text-text-secondary line-clamp-4">
                          {suggestion.suggested_paper.abstract}
                        </p>
                      </div>
                    )}

                    {/* DOI/Link */}
                    {suggestion.suggested_paper.doi && (
                      <div className="flex items-center gap-2">
                        <a
                          href={`https://doi.org/${suggestion.suggested_paper.doi}`}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-accent-primary hover:text-accent-secondary underline"
                        >
                          View Paper (DOI)
                        </a>
                        <button
                          onClick={() => copyToClipboard(suggestion.suggested_paper.doi || '', 'DOI')}
                          className="text-text-tertiary hover:text-text-secondary"
                        >
                          <ClipboardDocumentCheckIcon className="h-4 w-4" />
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* Action Buttons */}
                {suggestion.status === 'pending' && (
                  <div className="border-t border-border-subtle p-3 bg-surface-hover flex gap-2">
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handleRespond(suggestionId, 'accepted')}
                      disabled={isResponding}
                      className="flex-1 bg-success hover:bg-success/90"
                    >
                      <CheckCircleIcon className="h-4 w-4" />
                      Accept
                    </Button>
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => handleRespond(suggestionId, 'rejected')}
                      disabled={isResponding}
                      className="flex-1 bg-error hover:bg-error/90"
                    >
                      <XCircleIcon className="h-4 w-4" />
                      Reject
                    </Button>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => handleRespond(suggestionId, 'dismissed')}
                      disabled={isResponding}
                      title="Dismiss"
                    >
                      <EyeSlashIcon className="h-4 w-4" />
                    </Button>
                  </div>
                )}

                {/* Status Badge for Non-Pending */}
                {suggestion.status !== 'pending' && (
                  <div className="border-t border-border-subtle px-3 py-2 bg-surface-hover">
                    <Badge variant={
                      suggestion.status === 'accepted' ? 'success' :
                      suggestion.status === 'rejected' ? 'error' :
                      'neutral'
                    }>
                      {suggestion.status.charAt(0).toUpperCase() + suggestion.status.slice(1)}
                    </Badge>
                  </div>
                )}
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

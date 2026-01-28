import { Fragment, useState, useEffect } from 'react'
import { Dialog, Transition, Tab } from '@headlessui/react'
import { XMarkIcon, ExclamationTriangleIcon, CheckCircleIcon, LightBulbIcon, MagnifyingGlassIcon, MapPinIcon, LinkIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import { handleError } from '../lib/errorHandler'
import DocumentViewer from './DocumentViewer'
import CitationSuggestionSidebar from './CitationSuggestionSidebar'
import { Badge, type BadgeVariant } from './ui/Badge'
import { Button } from './ui/Button'
import toast from 'react-hot-toast'

interface DraftAnalysisModalProps {
  isOpen: boolean
  onClose: () => void
  draftId: string
  draftFileUrl: string
  draftFileType: string
  token: string
  projectId: string
}

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  section_location: string
  importance_score: number
  requires_citation: boolean
  existing_citations: string[]
  reasoning?: string  // AI reasoning for transparency
  // Location tracking fields
  section_id?: string
  char_offset_from_section?: number
  pdf_coordinates?: {
    page: number
    x: number
    y: number
    width: number
    height: number
  }
  line_number?: number
  match_confidence?: number
  text_snippet?: string
}

interface Gap {
  id: string
  gap_type: string
  description: string
  priority: string
  suggested_papers: any[]
}

interface Feedback {
  id: string
  feedback_type: string
  severity: string
  feedback_text: string
  suggestions: string[]
  section_reference?: string
  // Location tracking fields
  section_id?: string
  char_offset_from_section?: number
  pdf_coordinates?: {
    page: number
    x: number
    y: number
    width: number
    height: number
  }
  line_number?: number
  match_confidence?: number
  text_snippet?: string
}

export default function DraftAnalysisModal({
  isOpen,
  onClose,
  draftId,
  draftFileUrl,
  draftFileType,
  token,
  projectId,
}: DraftAnalysisModalProps) {
  const [loading, setLoading] = useState(true)
  const [claims, setClaims] = useState<Claim[]>([])
  const [gaps, setGaps] = useState<Gap[]>([])
  const [feedback, setFeedback] = useState<Feedback[]>([])
  const [generatingSuggestions, setGeneratingSuggestions] = useState<string | null>(null)
  const [activeAnnotationId, setActiveAnnotationId] = useState<string | null>(null)

  useEffect(() => {
    if (isOpen && draftId) {
      loadAnalysisResults()
    }
  }, [isOpen, draftId])

  const loadAnalysisResults = async () => {
    try {
      setLoading(true)

      // Load all analysis results in parallel
      const [claimsData, gapsData, feedbackData] = await Promise.all([
        api.drafts.getClaims(token, draftId).catch(() => ({ claims: [] })),
        api.drafts.getGaps(token, draftId).catch(() => ({ gaps: [] })),
        api.drafts.getFeedback(token, draftId).catch(() => ({ feedback: [] })),
      ])

      console.log('[DRAFT-ANALYSIS] Claims data received:', claimsData)
      console.log('[DRAFT-ANALYSIS] Number of claims:', claimsData.claims?.length || 0)
      console.log('[DRAFT-ANALYSIS] Sample claim:', claimsData.claims?.[0])

      // Normalize claims data - ensure existing_citations is always an array and requires_citation is always a boolean
      const normalizedClaims = (claimsData.claims || []).map((claim: any) => ({
        ...claim,
        existing_citations: Array.isArray(claim.existing_citations) 
          ? claim.existing_citations 
          : (claim.existing_citations ? [claim.existing_citations] : []),
        requires_citation: claim.requires_citation !== null && claim.requires_citation !== undefined 
          ? Boolean(claim.requires_citation) 
          : true, // Default to true if not set
      }))

      console.log('[DRAFT-ANALYSIS] Normalized claims:', normalizedClaims)
      console.log('[DRAFT-ANALYSIS] Claims requiring citation:', normalizedClaims.filter((c: any) => c.requires_citation))
      console.log('[DRAFT-ANALYSIS] Claims with existing citations:', normalizedClaims.filter((c: any) => c.existing_citations && c.existing_citations.length > 0))

      setClaims(normalizedClaims)
      setGaps(gapsData.gaps || [])
      setFeedback(feedbackData.feedback || [])
    } catch (error: any) {
      handleError(error, 'loading analysis results')
    } finally {
      setLoading(false)
    }
  }

  const handleFindSuggestions = async (claim: Claim) => {
    try {
      setGeneratingSuggestions(claim.id)
      toast.loading('Finding relevant citations...')

      await api.citations.generateSuggestions(token, {
        claim_text: claim.claim_text,
        project_id: projectId,
        draft_id: draftId,
        existing_citations: claim.existing_citations || [],
        max_suggestions: 5
      })

      toast.dismiss()
      toast.success('Citation suggestions found! Check the Citations tab.')
    } catch (error: any) {
      toast.dismiss()
      handleError(error, 'finding citation suggestions')
    } finally {
      setGeneratingSuggestions(null)
    }
  }

  const handleScrollToFeedback = (item: Feedback) => {
    // Set as active annotation for highlighting
    setActiveAnnotationId(item.id)

    // For now, show a toast with location info
    // TODO: Integrate with DocumentViewer component for actual scrolling
    if (item.section_id) {
      const confidence = item.match_confidence ? (item.match_confidence * 100).toFixed(0) : 'unknown'
      toast.success(`Location found: ${item.section_reference || 'Section'} (${confidence}% confidence)`, {
        duration: 3000
      })
    } else {
      toast('Location tracking not available for this feedback item', {
        icon: 'ℹ️',
        duration: 3000
      })
    }
  }

  const handleScrollToClaim = (claim: Claim) => {
    // Set as active annotation for highlighting
    setActiveAnnotationId(claim.id)

    // For now, show a toast with location info
    // TODO: Integrate with DocumentViewer component for actual scrolling
    if (claim.section_id) {
      const confidence = claim.match_confidence ? (claim.match_confidence * 100).toFixed(0) : 'unknown'
      toast.success(`Location found: ${claim.section_location || 'Section'} (${confidence}% confidence)`, {
        duration: 3000
      })
    } else {
      toast('Location tracking not available for this claim', {
        icon: 'ℹ️',
        duration: 3000
      })
    }
  }

  const getSeverityVariant = (severity: string): BadgeVariant => {
    switch (severity) {
      case 'critical':
      case 'major':
        return 'error'
      case 'minor':
        return 'warning'
      case 'suggestion':
        return 'info'
      default:
        return 'neutral'
    }
  }

  const getPriorityVariant = (priority: string): BadgeVariant => {
    switch (priority) {
      case 'high':
        return 'error'
      case 'medium':
        return 'warning'
      case 'low':
        return 'success'
      default:
        return 'neutral'
    }
  }

  const getSeverityIcon = (severity: string) => {
    switch (severity) {
      case 'critical':
      case 'major':
        return <ExclamationTriangleIcon className="h-5 w-5 text-text-tertiary" />
      case 'minor':
        return <LightBulbIcon className="h-5 w-5 text-text-tertiary" />
      case 'suggestion':
        return <CheckCircleIcon className="h-5 w-5 text-text-tertiary" />
      default:
        return null
    }
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/25 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-200"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-7xl h-[90vh] transform overflow-hidden rounded-xl bg-surface border border-border-base text-left align-middle shadow-xl transition-all flex flex-col">
                {/* Header */}
                <div className="border-b border-border-subtle px-6 py-5 flex items-center justify-between">
                  <Dialog.Title as="h3" className="text-2xl font-serif font-semibold text-text-primary">
                    Draft Analysis Results
                  </Dialog.Title>
                  <button
                    onClick={onClose}
                    className="text-text-tertiary hover:text-text-secondary transition-colors"
                  >
                    <XMarkIcon className="h-5 w-5" />
                  </button>
                </div>

                {/* Content - Split Screen */}
                <div className="flex-1 flex overflow-hidden">
                  {/* Left: Document Viewer */}
                  <div className="w-1/2 border-r border-border-base p-4 overflow-hidden">
                    <DocumentViewer fileUrl={draftFileUrl} fileType={draftFileType} />
                  </div>

                  {/* Right: Analysis */}
                  <div className="w-1/2 flex flex-col overflow-hidden">
                    {loading ? (
                      <div className="flex-1 flex items-center justify-center">
                        <div className="text-center">
                          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary"></div>
                          <p className="mt-2 text-sm text-text-tertiary">Loading analysis...</p>
                        </div>
                      </div>
                    ) : (
                      <Tab.Group as="div" className="flex flex-col h-full">
                      <Tab.List className="flex space-x-2 border-b border-border-subtle px-6 pt-4 shrink-0">
                        <Tab className={({ selected }) =>
                          `px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                            selected
                              ? 'border-accent-primary text-text-primary'
                              : 'border-transparent text-text-secondary hover:text-text-primary'
                          }`
                        }>
                          Feedback ({feedback.length})
                        </Tab>
                        <Tab className={({ selected }) =>
                          `px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                            selected
                              ? 'border-accent-primary text-text-primary'
                              : 'border-transparent text-text-secondary hover:text-text-primary'
                          }`
                        }>
                          Coverage Gaps ({gaps.length})
                        </Tab>
                        <Tab className={({ selected }) =>
                          `px-4 py-2 text-sm font-medium transition-colors border-b-2 ${
                            selected
                              ? 'border-accent-primary text-text-primary'
                              : 'border-transparent text-text-secondary hover:text-text-primary'
                          }`
                        }>
                          Claims ({claims.length})
                        </Tab>
                        <Tab className={({ selected }) =>
                          `px-4 py-2 text-sm font-medium transition-colors border-b-2 flex items-center gap-1 ${
                            selected
                              ? 'border-accent-primary text-text-primary'
                              : 'border-transparent text-text-secondary hover:text-text-primary'
                          }`
                        }>
                          <LinkIcon className="h-4 w-4" />
                          Citations
                        </Tab>
                      </Tab.List>

                      <Tab.Panels className="flex-1 overflow-y-auto px-6 py-6 min-h-0">
                        {/* Feedback Panel */}
                        <Tab.Panel>
                          {feedback.length === 0 ? (
                            <p className="text-center text-text-tertiary py-8">No feedback available yet</p>
                          ) : (
                            <div className="space-y-4">
                              {feedback
                                .sort((a, b) => {
                                  const severityOrder = { critical: 0, major: 1, minor: 2, suggestion: 3 }
                                  return severityOrder[a.severity as keyof typeof severityOrder] -
                                         severityOrder[b.severity as keyof typeof severityOrder]
                                })
                                .map((item) => (
                                  <div
                                    key={item.id}
                                    className={`border border-border-base rounded-lg p-4 bg-surface-hover transition-colors ${
                                      item.section_id ? 'cursor-pointer hover:bg-surface-active hover:border-accent-primary/50' : ''
                                    } ${activeAnnotationId === item.id ? 'ring-2 ring-accent-primary' : ''}`}
                                    onClick={() => {
                                      if (item.section_id) {
                                        handleScrollToFeedback(item)
                                      }
                                    }}
                                  >
                                    <div className="flex items-start gap-3">
                                      {getSeverityIcon(item.severity)}
                                      <div className="flex-1">
                                        <div className="flex items-center gap-2 mb-2">
                                          <span className="text-xs font-medium text-text-tertiary font-mono uppercase">
                                            {item.feedback_type}
                                          </span>
                                          <Badge variant={getSeverityVariant(item.severity)}>
                                            {item.severity.toUpperCase()}
                                          </Badge>
                                        </div>
                                        <p className="text-sm text-text-secondary mb-3">{item.feedback_text}</p>
                                        {item.suggestions && item.suggestions.length > 0 && (
                                          <div className="mt-3 border-t border-border-subtle pt-3">
                                            <p className="text-xs font-medium text-text-tertiary mb-2 font-mono">Suggested improvements:</p>
                                            <ul className="space-y-1 text-sm text-text-tertiary">
                                              {item.suggestions.map((improvement, idx) => (
                                                <li key={idx} className="text-sm flex gap-2">
                                                  <span className="text-text-muted">•</span>
                                                  <span>{improvement}</span>
                                                </li>
                                              ))}
                                            </ul>
                                          </div>
                                        )}

                                        {/* Location indicator */}
                                        {item.section_id && (
                                          <div className="mt-3 pt-3 border-t border-border-subtle flex items-center gap-2 text-xs text-text-muted">
                                            <MapPinIcon className="h-3 w-3" />
                                            <span>Click to jump to location</span>
                                            {item.match_confidence && (
                                              <Badge variant="neutral">
                                                {(item.match_confidence * 100).toFixed(0)}% match
                                              </Badge>
                                            )}
                                          </div>
                                        )}
                                      </div>
                                    </div>
                                  </div>
                                ))}
                            </div>
                          )}
                        </Tab.Panel>

                        {/* Coverage Gaps Panel */}
                        <Tab.Panel>
                          {gaps.length === 0 ? (
                            <p className="text-center text-text-tertiary py-8">No coverage gaps identified</p>
                          ) : (
                            <div className="space-y-4">
                              {gaps
                                .sort((a, b) => {
                                  const priorityOrder = { high: 0, medium: 1, low: 2 }
                                  return priorityOrder[a.priority as keyof typeof priorityOrder] -
                                         priorityOrder[b.priority as keyof typeof priorityOrder]
                                })
                                .map((gap) => (
                                  <div key={gap.id} className="border border-border-base rounded-lg p-4 bg-surface-hover">
                                    <div className="flex items-center gap-2 mb-2">
                                      <span className="text-xs font-medium text-text-tertiary font-mono uppercase">
                                        {gap.gap_type.replace('_', ' ')}
                                      </span>
                                      <Badge variant={getPriorityVariant(gap.priority)}>
                                        {gap.priority.toUpperCase()} PRIORITY
                                      </Badge>
                                    </div>
                                    <p className="text-sm text-text-secondary mb-3">{gap.description}</p>
                                    {gap.suggested_papers && gap.suggested_papers.length > 0 && (
                                      <div className="mt-3 border-t border-border-subtle pt-3">
                                        <p className="text-xs font-medium text-text-tertiary mb-2 font-mono">
                                          Suggested papers from your literature:
                                        </p>
                                        <ul className="space-y-1">
                                          {gap.suggested_papers.slice(0, 3).map((paper, idx) => (
                                            <li key={idx} className="text-sm text-text-tertiary flex gap-2">
                                              <span className="text-text-muted">•</span>
                                              <span>{paper.title} ({paper.year})</span>
                                            </li>
                                          ))}
                                        </ul>
                                      </div>
                                    )}
                                  </div>
                                ))}
                            </div>
                          )}
                        </Tab.Panel>

                        {/* Claims Panel */}
                        <Tab.Panel>
                          {claims.length === 0 ? (
                            <div className="text-center py-8">
                              <p className="text-text-tertiary mb-2">No claims extracted yet</p>
                              <p className="text-xs text-text-muted">Make sure your draft has been analyzed first.</p>
                            </div>
                          ) : (
                            <>
                              {/* Color Coding Legend */}
                              <div className="mb-4 p-3 bg-surface-hover rounded-lg border border-border-base">
                                <p className="text-xs font-medium text-text-tertiary mb-2 font-mono">CLAIM COLOR CODING:</p>
                                <div className="flex flex-wrap gap-3 text-xs">
                                  <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-red-500"></div>
                                    <span className="text-text-secondary">Missing citations (needs support)</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-blue-500"></div>
                                    <span className="text-text-secondary">Has citations (supported)</span>
                                  </div>
                                  <div className="flex items-center gap-1">
                                    <div className="w-3 h-3 rounded-full bg-green-500"></div>
                                    <span className="text-text-secondary">Original contribution</span>
                                  </div>
                                </div>
                              </div>

                              <div className="space-y-3">
                              {claims
                                .sort((a, b) => b.importance_score - a.importance_score)
                                .map((claim) => {
                                  // Ensure we have normalized data for rendering
                                  const hasExistingCitations = Array.isArray(claim.existing_citations) && claim.existing_citations.length > 0
                                  const requiresCitation = claim.requires_citation === true

                                  // Determine color based on status
                                  let borderColor = 'border-border-base'
                                  let indicatorColor = 'bg-gray-500'
                                  if (!requiresCitation) {
                                    // Original contribution (doesn't need citation)
                                    borderColor = 'border-green-500/30'
                                    indicatorColor = 'bg-green-500'
                                  } else if (hasExistingCitations) {
                                    // Has citations (supported)
                                    borderColor = 'border-blue-500/30'
                                    indicatorColor = 'bg-blue-500'
                                  } else {
                                    // Missing citations (needs support)
                                    borderColor = 'border-red-500/30'
                                    indicatorColor = 'bg-red-500'
                                  }

                                  return (
                                  <div
                                    key={claim.id}
                                    className={`border ${borderColor} rounded-lg p-3 bg-surface-hover transition-colors relative ${
                                      claim.section_id ? 'cursor-pointer hover:bg-surface-active hover:border-accent-primary/50' : ''
                                    } ${activeAnnotationId === claim.id ? 'ring-2 ring-accent-primary' : ''}`}
                                    onClick={(e) => {
                                      // Only trigger if not clicking on a button or details element
                                      if (claim.section_id && !(e.target as HTMLElement).closest('button') && !(e.target as HTMLElement).closest('details')) {
                                        handleScrollToClaim(claim)
                                      }
                                    }}
                                  >
                                    {/* Color indicator bar on left */}
                                    <div className={`absolute top-3 left-0 w-1 h-[calc(100%-24px)] ${indicatorColor} rounded-r`}></div>

                                    <div className="pl-3">
                                    <div className="flex items-center gap-2 mb-2">
                                      <span className="text-xs font-medium text-text-tertiary font-mono uppercase">
                                        {claim.claim_type}
                                      </span>
                                      <span className="text-xs text-text-muted font-mono">
                                        {claim.section_location}
                                      </span>
                                      <div className="flex-1" />
                                      <span className="text-xs text-text-muted font-mono">
                                        Importance: {(claim.importance_score * 100).toFixed(0)}%
                                      </span>
                                    </div>
                                    <p className="text-sm text-text-secondary mb-2">{claim.claim_text}</p>

                                    {/* AI Reasoning Toggle */}
                                    {claim.reasoning && (
                                      <details className="mt-2 text-xs">
                                        <summary className="cursor-pointer text-text-muted hover:text-text-secondary font-mono select-none">
                                          Show AI reasoning
                                        </summary>
                                        <p className="mt-2 p-2 bg-surface rounded border border-border-subtle text-text-tertiary">
                                          {claim.reasoning}
                                        </p>
                                      </details>
                                    )}

                                    {/* Location indicator */}
                                    {claim.section_id && (
                                      <div className="mb-3 flex items-center gap-2 text-xs text-text-muted">
                                        <MapPinIcon className="h-3 w-3" />
                                        <span>Click to jump to location</span>
                                        {claim.match_confidence && (
                                          <Badge variant="neutral">
                                            {(claim.match_confidence * 100).toFixed(0)}% match
                                          </Badge>
                                        )}
                                      </div>
                                    )}

                                    {hasExistingCitations ? (
                                      <div className="flex items-center justify-between gap-2 mt-2">
                                        <div className="flex items-center gap-2 text-xs text-text-muted">
                                          <span className="font-mono">Citations:</span>
                                          <span className="font-mono">{claim.existing_citations.join(', ')}</span>
                                        </div>
                                        <Button
                                          variant="secondary"
                                          size="sm"
                                          onClick={(e) => {
                                            e.stopPropagation()
                                            handleFindSuggestions(claim)
                                          }}
                                          disabled={generatingSuggestions === claim.id}
                                          className="shadow-lg"
                                          style={{ minWidth: '140px' }}
                                        >
                                          <MagnifyingGlassIcon className="h-4 w-4" />
                                          {generatingSuggestions === claim.id ? 'Finding...' : 'Find More'}
                                        </Button>
                                      </div>
                                    ) : requiresCitation ? (
                                      <div className="flex items-center justify-between gap-2 mt-2">
                                        <Badge variant="error">
                                          MISSING CITATIONS
                                        </Badge>
                                        <Button
                                          variant="primary"
                                          size="sm"
                                          onClick={(e) => {
                                            e.stopPropagation()
                                            handleFindSuggestions(claim)
                                          }}
                                          disabled={generatingSuggestions === claim.id}
                                          className="shadow-lg"
                                          style={{ minWidth: '160px' }}
                                        >
                                          <MagnifyingGlassIcon className="h-4 w-4" />
                                          {generatingSuggestions === claim.id ? 'Finding...' : 'Find Suggestions'}
                                        </Button>
                                      </div>
                                    ) : (
                                      <Badge variant="neutral" className="mt-2">
                                        ORIGINAL CONTRIBUTION
                                      </Badge>
                                    )}
                                    </div>
                                  </div>
                                  )
                                })}
                            </div>
                            </>
                          )}
                        </Tab.Panel>

                        {/* Citations Panel */}
                        <Tab.Panel className="h-full p-0 -mx-6 -my-4">
                          <CitationSuggestionSidebar
                            token={token}
                            draftId={draftId}
                            projectId={projectId}
                          />
                        </Tab.Panel>
                      </Tab.Panels>
                      </Tab.Group>
                    )}
                  </div>
                </div>

                {/* Footer */}
                <div className="border-t border-border-subtle px-6 py-5 flex justify-end">
                  <Button variant="secondary" onClick={onClose}>
                    Close
                  </Button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

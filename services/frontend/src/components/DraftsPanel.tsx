import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { DocumentTextIcon, TrashIcon, CalendarIcon, ArrowsRightLeftIcon, ClockIcon, ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { handleError } from '../lib/errorHandler'
import { Badge, type BadgeVariant } from './ui/Badge'
import { SkeletonListItem, SkeletonList } from './ui/Skeleton'
import VersionTimeline from './draft-analysis/VersionTimeline'
import RecurringPatterns from './draft-analysis/RecurringPatterns'

interface Draft {
  id: string
  title: string
  version: number
  file_type: string
  file_url: string
  status: string
  created_at: string
  updated_at: string
}

interface DraftsPanelProps {
  token: string
  projectId: string
  refreshTrigger?: number
  onDraftsLoaded?: (count: number) => void
}

interface CompareModalState {
  isOpen: boolean
  selectedDraftId: string | null
}

interface DeleteModalState {
  isOpen: boolean
  draftId: string | null
  draftTitle: string
  isDeleting: boolean
}

export default function DraftsPanel({ token, projectId, refreshTrigger, onDraftsLoaded }: DraftsPanelProps) {
  const navigate = useNavigate()
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)
  const [compareModal, setCompareModal] = useState<CompareModalState>({ isOpen: false, selectedDraftId: null })
  const [deleteModal, setDeleteModal] = useState<DeleteModalState>({ isOpen: false, draftId: null, draftTitle: '', isDeleting: false })
  const [showTimeline, setShowTimeline] = useState(false)
  const [timeline, setTimeline] = useState<any[]>([])
  const [recurringPatterns, setRecurringPatterns] = useState<any[]>([])
  const [overallObservation, setOverallObservation] = useState<string | null>(null)
  const [patternsLoading, setPatternsLoading] = useState(false)

  const loadDrafts = async () => {
    try {
      setLoading(true)
      const data = await api.drafts.list(token, projectId)
      console.log('[DRAFTS-PANEL] API response:', data)
      console.log('[DRAFTS-PANEL] Drafts array:', data.drafts)
      console.log('[DRAFTS-PANEL] Number of drafts:', data.drafts?.length || 0)
      const draftsList = data.drafts || []
      setDrafts(draftsList)

      // Notify parent of draft count
      if (onDraftsLoaded) {
        onDraftsLoaded(draftsList.length)
      }
    } catch (error: any) {
      console.error('[DRAFTS-PANEL] Error loading drafts:', error)
      handleError(error, 'loading drafts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDrafts()
  }, [token, projectId, refreshTrigger])

  // Load timeline and recurring patterns when analyzed draft count changes
  useEffect(() => {
    const analyzedCount = drafts.filter(d => d.status === 'analyzed').length
    if (analyzedCount < 2) {
      setTimeline([])
      setRecurringPatterns([])
      return
    }

    // Fetch timeline (2+ analyzed drafts)
    api.drafts.getTimeline(token, projectId)
      .then(data => setTimeline(data.timeline || []))
      .catch(() => {}) // non-critical

    // Fetch recurring patterns (3+ analyzed drafts)
    if (analyzedCount >= 3) {
      setPatternsLoading(true)
      api.drafts.getRecurringPatterns(token, projectId)
        .then(data => {
          setRecurringPatterns(data.patterns || [])
          setOverallObservation(data.overall_observation || null)
        })
        .catch(() => {})
        .finally(() => setPatternsLoading(false))
    }
  }, [drafts, token, projectId])

  // Poll for status updates if there are processing drafts
  useEffect(() => {
    const hasProcessingDrafts = drafts.some(
      (draft) => draft.status === 'processing' || draft.status === 'uploaded'
    )

    if (!hasProcessingDrafts) return

    const pollInterval = setInterval(() => {
      console.log('[DRAFTS-PANEL] Polling for status updates...')
      // Silent reload - update state without triggering loading state
      api.drafts.list(token, projectId).then(data => {
        setDrafts(data.drafts || [])
      }).catch(error => {
        console.error('[DRAFTS-PANEL] Polling error:', error)
      })
    }, 5000) // Poll every 5 seconds

    return () => {
      clearInterval(pollInterval)
    }
  }, [drafts, token, projectId])

  const handleDelete = (draftId: string, title: string) => {
    setDeleteModal({ isOpen: true, draftId, draftTitle: title, isDeleting: false })
  }

  const confirmDelete = async () => {
    if (!deleteModal.draftId) return
    setDeleteModal(prev => ({ ...prev, isDeleting: true }))
    try {
      await api.drafts.delete(token, deleteModal.draftId)
      toast.success('Draft deleted successfully')
      setDeleteModal({ isOpen: false, draftId: null, draftTitle: '', isDeleting: false })
      loadDrafts()
    } catch (error: any) {
      handleError(error, 'deleting draft')
      setDeleteModal(prev => ({ ...prev, isDeleting: false }))
    }
  }

  const handleViewAnalysis = (draftId: string) => {
    navigate(`/projects/${projectId}/drafts/${draftId}`)
  }

  const handleAnalyze = async (draftId: string) => {
    try {
      toast.loading('Starting analysis...')
      await api.drafts.analyze(token, draftId)
      toast.dismiss()
      toast.success('Analysis started! This may take 1-2 minutes.')
      // Reload drafts to update status
      setTimeout(() => loadDrafts(), 2000)
    } catch (error: any) {
      toast.dismiss()
      handleError(error, 'analyzing draft')
    }
  }

  const getStatusBadge = (status: string): BadgeVariant => {
    switch (status) {
      case 'analyzed':
        return 'success'
      case 'processing':
      case 'uploaded':
        return 'warning'
      case 'failed':
        return 'error'
      default:
        return 'neutral'
    }
  }

  const handleOpenCompareModal = (draftId: string) => {
    setCompareModal({ isOpen: true, selectedDraftId: draftId })
  }

  const handleCloseCompareModal = () => {
    setCompareModal({ isOpen: false, selectedDraftId: null })
  }

  const handleCompareWithDraft = (otherDraftId: string) => {
    if (!compareModal.selectedDraftId) return

    // Navigate to comparison page with the two draft IDs
    // Convention: older draft first, newer draft second
    const draft1 = drafts.find(d => d.id === compareModal.selectedDraftId)
    const draft2 = drafts.find(d => d.id === otherDraftId)

    if (!draft1 || !draft2) return

    // Order by version number (or creation date if versions are equal)
    const [olderDraft, newerDraft] = draft1.version < draft2.version
      ? [draft1, draft2]
      : draft2.version < draft1.version
      ? [draft2, draft1]
      : new Date(draft1.created_at) < new Date(draft2.created_at)
      ? [draft1, draft2]
      : [draft2, draft1]

    navigate(`/projects/${projectId}/compare/${olderDraft.id}/${newerDraft.id}`)
  }

  // Get analyzed drafts for comparison
  const analyzedDrafts = drafts.filter(d => d.status === 'analyzed')

  if (loading) {
    return <SkeletonList count={4} ItemComponent={SkeletonListItem} />
  }

  if (drafts.length === 0) {
    return (
      <div className="text-center py-12 bg-bg-base rounded-lg border-2 border-dashed border-border-default">
        <DocumentTextIcon className="mx-auto h-12 w-12 text-text-tertiary" />
        <h3 className="mt-2 text-sm font-medium text-text-primary">No drafts yet</h3>
        <p className="mt-1 text-sm text-text-tertiary">
          Upload your research draft to get expert feedback and analysis
        </p>
      </div>
    )
  }

  return (
    <>
      {/* Action buttons row (shows when 2+ analyzed drafts exist) */}
      {analyzedDrafts.length >= 2 && (
        <div className="mb-4 flex items-center gap-2 flex-wrap">
          <button
            onClick={() => handleOpenCompareModal(analyzedDrafts[0].id)}
            className="px-4 py-2 bg-indigo-600/20 border-2 border-indigo-600/50 text-indigo-300 font-semibold rounded-lg hover:bg-indigo-600/30 hover:border-indigo-500 transition-all flex items-center gap-2"
          >
            <ArrowsRightLeftIcon className="h-5 w-5" />
            Compare Versions
          </button>
          <button
            onClick={() => setShowTimeline(v => !v)}
            className="px-4 py-2 bg-bg-surface border border-border-default text-text-secondary font-semibold rounded-lg hover:border-accent-primary/40 hover:text-text-primary transition-all flex items-center gap-2"
          >
            <ClockIcon className="h-5 w-5" />
            {showTimeline ? 'Hide History' : 'Version History'}
          </button>
        </div>
      )}

      {/* Version Timeline */}
      {showTimeline && timeline.length > 0 && (
        <div className="mb-4">
          <VersionTimeline
            projectId={projectId}
            timeline={timeline}
            onClose={() => setShowTimeline(false)}
          />
        </div>
      )}

      {/* Recurring Patterns (3+ analyzed drafts) */}
      {analyzedDrafts.length >= 3 && (
        <div className="mb-4">
          <RecurringPatterns
            patterns={recurringPatterns}
            overallObservation={overallObservation}
            loading={patternsLoading}
          />
        </div>
      )}

      <div className="space-y-3">
        {drafts.map((draft) => {
          return (
            <div
              key={draft.id}
              onClick={() => draft.status === 'analyzed' ? handleViewAnalysis(draft.id) : undefined}
              className={`bg-slate-800/40 hover:bg-slate-800/60 border border-slate-700/50 rounded-lg p-4 transition-all ${
                draft.status === 'analyzed'
                  ? 'cursor-pointer hover:border-slate-600'
                  : ''
              }`}
            >
              <div className="flex items-center gap-4">
                {/* Icon Box (larger, styled like document card) */}
                <div className="flex-shrink-0">
                  <div className="w-12 h-12 rounded-lg border-2 border-purple-600 bg-purple-950/50 flex items-center justify-center">
                    <DocumentTextIcon className="h-6 w-6 text-purple-300" />
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1 min-w-0">
                  <h3 className="text-base font-medium text-slate-200 truncate mb-1">
                    {draft.title}
                  </h3>
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <CalendarIcon className="h-4 w-4" />
                    <span>{new Date(draft.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                  </div>
                </div>

                {/* Right Side Actions */}
                <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
                  {/* Status Badge */}
                  <Badge variant={getStatusBadge(draft.status)}>
                    {draft.status === 'analyzed' ? 'Processed' : draft.status.charAt(0).toUpperCase() + draft.status.slice(1).toLowerCase()}
                  </Badge>

                  {/* Action Buttons */}
                  {draft.status === 'uploaded' && (
                    <button
                      onClick={() => handleAnalyze(draft.id)}
                      className="px-3 py-1 text-xs font-medium text-slate-200 bg-slate-700 hover:bg-slate-600 rounded border border-slate-600 transition-colors"
                    >
                      Analyze
                    </button>
                  )}
                  {draft.status === 'failed' && (
                    <button
                      onClick={() => handleAnalyze(draft.id)}
                      className="px-3 py-1 text-xs font-medium text-slate-200 bg-slate-700 hover:bg-slate-600 rounded border border-slate-600 transition-colors"
                    >
                      Retry
                    </button>
                  )}

                  {/* Delete Button */}
                  <button
                    onClick={() => handleDelete(draft.id, draft.title)}
                    className="p-2 text-slate-400 hover:text-slate-200 hover:bg-slate-700/50 rounded-md transition-colors"
                    title="Delete Draft"
                  >
                    <TrashIcon className="h-5 w-5" />
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

      {/* Compare Modal */}
      {compareModal.isOpen && compareModal.selectedDraftId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm">
          <div className="bg-slate-800 border-2 border-slate-700 rounded-lg max-w-md w-full mx-4 p-6">
            <h3 className="text-xl font-semibold text-slate-200 mb-4">Compare with Version</h3>
            <p className="text-sm text-slate-400 mb-6">
              Select another draft to compare with{' '}
              <span className="font-medium text-slate-300">
                {drafts.find(d => d.id === compareModal.selectedDraftId)?.title}
              </span>
            </p>

            <div className="space-y-2 max-h-96 overflow-y-auto mb-6">
              {analyzedDrafts
                .filter(d => d.id !== compareModal.selectedDraftId)
                .map(draft => (
                  <button
                    key={draft.id}
                    onClick={() => handleCompareWithDraft(draft.id)}
                    className="w-full text-left px-4 py-3 bg-slate-900/50 border border-slate-700 rounded-lg hover:bg-slate-900 hover:border-purple-600 transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <div>
                        <div className="font-medium text-slate-200">{draft.title}</div>
                        <div className="text-xs text-slate-400 mt-1 font-mono">
                          Version {draft.version} • {new Date(draft.created_at).toLocaleDateString()}
                        </div>
                      </div>
                      <ArrowsRightLeftIcon className="h-5 w-5 text-purple-400" />
                    </div>
                  </button>
                ))
              }
            </div>

            <button
              onClick={handleCloseCompareModal}
              className="w-full px-4 py-2 bg-slate-700 text-slate-200 font-medium rounded-lg hover:bg-slate-600 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Delete Draft Modal */}
      {deleteModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => !deleteModal.isDeleting && setDeleteModal(prev => ({ ...prev, isOpen: false }))} />
          <div className="relative bg-bg-surface border border-border-default rounded-xl w-full max-w-md shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-5 border-b border-border-default">
              <div className="flex items-center gap-3">
                <ExclamationTriangleIcon className="h-6 w-6 text-error" />
                <h2 className="text-xl font-semibold text-text-primary">Delete Draft</h2>
              </div>
              <button
                onClick={() => !deleteModal.isDeleting && setDeleteModal(prev => ({ ...prev, isOpen: false }))}
                className="p-1 text-text-secondary hover:text-text-primary rounded transition-colors duration-fast"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            {/* Body */}
            <div className="px-6 py-6">
              <p className="text-text-secondary mb-2">Are you sure you want to delete</p>
              <p className="font-semibold text-text-primary mb-4 break-words">"{deleteModal.draftTitle}"</p>
              <p className="text-text-muted text-sm leading-relaxed">
                This will permanently delete the draft, its analysis, all claims, gaps, and feedback. This action cannot be undone.
              </p>
            </div>

            {/* Actions */}
            <div className="flex gap-3 px-6 pb-6">
              <button
                onClick={() => setDeleteModal(prev => ({ ...prev, isOpen: false }))}
                disabled={deleteModal.isDeleting}
                className="flex-1 px-4 py-3 rounded-xl border border-border-default text-text-secondary font-semibold hover:text-text-primary hover:border-border-subtle transition-all duration-fast disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleteModal.isDeleting}
                className="flex-1 px-4 py-3 rounded-xl bg-error text-white font-semibold hover:bg-error/90 transition-all duration-fast disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {deleteModal.isDeleting ? (
                  <>
                    <div className="h-4 w-4 animate-spin rounded-full border-2 border-white border-t-transparent" />
                    Deleting...
                  </>
                ) : 'Delete Draft'}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  )
}

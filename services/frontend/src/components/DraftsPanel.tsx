import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { DocumentTextIcon, TrashIcon, CalendarIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { handleError } from '../lib/errorHandler'
import { Badge, type BadgeVariant } from './ui/Badge'
import { SkeletonListItem, SkeletonList } from './ui/Skeleton'

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

export default function DraftsPanel({ token, projectId, refreshTrigger, onDraftsLoaded }: DraftsPanelProps) {
  const navigate = useNavigate()
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)

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

  const handleDelete = async (draftId: string, title: string) => {
    if (!confirm(`Are you sure you want to delete "${title}"?`)) {
      return
    }

    try {
      await api.drafts.delete(token, draftId)
      toast.success('Draft deleted successfully')
      loadDrafts()
    } catch (error: any) {
      handleError(error, 'deleting draft')
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

  if (loading) {
    return <SkeletonList count={4} ItemComponent={SkeletonListItem} />
  }

  if (drafts.length === 0) {
    return (
      <div className="text-center py-12 bg-bg-base rounded-lg border-2 border-dashed border-border-base">
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

    </>
  )
}

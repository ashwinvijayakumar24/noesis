import { useState, useEffect, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import { DocumentTextIcon, TrashIcon, CalendarIcon, ExclamationTriangleIcon, XMarkIcon, UserGroupIcon, ClipboardDocumentIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { handleError } from '../lib/errorHandler'
import { SkeletonListItem, SkeletonList } from './ui/Skeleton'
import { useAnalysisStream } from '../hooks/useAnalysisStream'

function DraftStatusBadge({ status, updatedAt }: { status: string; updatedAt: string }) {
  const s = status.toLowerCase()
  const recentlyFailed = s === 'failed' && Date.now() - new Date(updatedAt).getTime() < 15 * 60 * 1000
  const isProcessing = s === 'processing' || s === 'uploaded' || recentlyFailed

  if (isProcessing) {
    return (
      <span className="inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-sm border bg-[#2C1A06] text-amber-400 border-[#5C3A10]">
        <span className="relative flex h-1.5 w-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
          <span className="relative inline-flex h-1.5 w-1.5 rounded-full bg-amber-400" />
        </span>
        Analyzing
      </span>
    )
  }

  if (s === 'analyzed') {
    return (
      <span className="text-xs font-medium px-2 py-0.5 rounded-sm border bg-[#0D2E1F] text-emerald-400 border-[#1A5C3A]">
        Processed
      </span>
    )
  }

  if (s === 'failed') {
    return (
      <span className="text-xs font-medium px-2 py-0.5 rounded-sm border bg-[#2C0D0D] text-red-400 border-[#5C1A1A]">
        Failed
      </span>
    )
  }

  return (
    <span className="text-xs font-medium px-2 py-0.5 rounded-sm border bg-bg-elevated text-text-muted border-border-default">
      {status.charAt(0).toUpperCase() + status.slice(1)}
    </span>
  )
}

function AnimatedDots() {
  const [dots, setDots] = useState('.')
  useEffect(() => {
    const id = setInterval(() => setDots(d => d.length >= 3 ? '.' : d + '.'), 500)
    return () => clearInterval(id)
  }, [])
  return <span className="inline-block w-4 text-left">{dots}</span>
}

function ElapsedTimer({ startedAt }: { startedAt: number }) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startedAt) / 1000)), 1000)
    return () => clearInterval(id)
  }, [startedAt])
  const m = Math.floor(elapsed / 60)
  const s = elapsed % 60
  return <span>{m > 0 ? `${m}m ` : ''}{s}s</span>
}

function DraftProgressBar({ draftId, onComplete }: { draftId: string; onComplete?: () => void }) {
  const stream = useAnalysisStream(draftId, true)
  const firedRef = useRef(false)
  const startedAt = useRef(Date.now())

  // WS has data: use its progress. WS disconnected or never connected: indeterminate.
  const hasStreamData = stream.progress > 0
  const pct = hasStreamData ? Math.max(stream.progress, 5) : null

  useEffect(() => {
    if (stream.complete && !firedRef.current && onComplete) {
      firedRef.current = true
      onComplete()
    }
  }, [stream.complete, onComplete])

  return (
    <div className="mt-3 px-1">
      <div className="flex justify-between items-center mb-1.5">
        <span className="text-xs text-slate-400 flex items-center gap-1">
          <svg className="animate-spin h-3 w-3 text-accent-primary flex-shrink-0" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"/>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v4a4 4 0 00-4 4H4z"/>
          </svg>
          <span>{stream.message || 'Starting analysis'}<AnimatedDots /></span>
        </span>
        <span className="text-xs text-slate-500 flex items-center gap-1.5">
          {pct !== null && <span>{stream.progress}%</span>}
          <span className="text-slate-600">· <ElapsedTimer startedAt={startedAt.current} /></span>
        </span>
      </div>
      <div className="w-full bg-slate-700/50 rounded-full h-1.5 overflow-hidden">
        {pct !== null ? (
          // Determinate — WS is feeding progress
          <div
            className="h-full rounded-full transition-all duration-700 relative overflow-hidden"
            style={{ width: `${pct}%`, background: 'var(--color-accent-primary, #E5484D)' }}
          >
            <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/30 to-transparent animate-shimmer-sweep" />
          </div>
        ) : (
          // Indeterminate — WS not yet connected or disconnected before 100%
          <div
            className="h-full rounded-full relative overflow-hidden w-full"
            style={{ background: 'var(--color-accent-primary, #E5484D)', opacity: 0.35 }}
          >
            <span className="absolute inset-0 bg-gradient-to-r from-transparent via-white/40 to-transparent animate-shimmer-sweep" />
          </div>
        )}
      </div>
    </div>
  )
}

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
  const [deleteModal, setDeleteModal] = useState<DeleteModalState>({ isOpen: false, draftId: null, draftTitle: '', isDeleting: false })
  const [inviteModal, setInviteModal] = useState<{ isOpen: boolean; inviteUrl: string; labName: string }>({
    isOpen: false, inviteUrl: '', labName: '',
  })
  const [editingDraftId, setEditingDraftId] = useState<string | null>(null)
  const [editDraftTitle, setEditDraftTitle] = useState('')
  const draftTitleInputRef = useRef<HTMLInputElement>(null)

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

  // Silent reload — does not trigger loading spinner, used for polling and onComplete callbacks
  const silentReloadDrafts = () => {
    api.drafts.list(token, projectId).then(data => {
      setDrafts(data.drafts || [])
    }).catch(err => console.error('[DRAFTS-PANEL] Silent reload error:', err))
  }

  const startEditDraft = (e: React.MouseEvent, draft: Draft) => {
    e.stopPropagation()
    setEditDraftTitle(draft.title)
    setEditingDraftId(draft.id)
    setTimeout(() => draftTitleInputRef.current?.focus(), 0)
  }

  const saveDraftTitle = async (draftId: string) => {
    const trimmed = editDraftTitle.trim()
    const original = drafts.find(d => d.id === draftId)?.title ?? ''
    setEditingDraftId(null)
    if (!trimmed || trimmed === original) return
    try {
      await api.drafts.update(token, draftId, trimmed)
      setDrafts(prev => prev.map(d => d.id === draftId ? { ...d, title: trimmed } : d))
    } catch {
      // revert silently
    }
  }

  useEffect(() => {
    loadDrafts()
  }, [token, projectId, refreshTrigger])

  // Poll for status updates if there are processing or recently-failed drafts
  useEffect(() => {
    const now = Date.now()
    const hasActiveDrafts = drafts.some((draft) => {
      if (draft.status === 'processing' || draft.status === 'uploaded') return true
      // Also poll 'failed' drafts updated within the last 15 minutes — Celery may retry
      if (draft.status === 'failed') {
        const updatedAt = new Date(draft.updated_at).getTime()
        return now - updatedAt < 15 * 60 * 1000
      }
      return false
    })

    if (!hasActiveDrafts) return

    const pollInterval = setInterval(() => {
      console.log('[DRAFTS-PANEL] Polling for status updates...')
      silentReloadDrafts()
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
      // Optimistically set to 'processing' immediately so polling starts right away
      // (Celery task may not have updated the DB yet when we reload)
      setDrafts(prev => prev.map(d =>
        d.id === draftId ? { ...d, status: 'processing', updated_at: new Date().toISOString() } : d
      ))
    } catch (error: any) {
      toast.dismiss()
      handleError(error, 'analyzing draft')
    }
  }


  const handleCopyInviteUrl = () => {
    navigator.clipboard.writeText(inviteModal.inviteUrl)
    toast.success('Invite link copied!')
  }

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
                  {editingDraftId === draft.id ? (
                    <div className="flex items-center gap-1.5 mb-1" onClick={e => e.stopPropagation()}>
                      <input
                        ref={draftTitleInputRef}
                        value={editDraftTitle}
                        onChange={e => setEditDraftTitle(e.target.value)}
                        onKeyDown={e => { if (e.key === 'Enter') saveDraftTitle(draft.id); if (e.key === 'Escape') setEditingDraftId(null) }}
                        onBlur={() => saveDraftTitle(draft.id)}
                        className="flex-1 min-w-0 text-sm bg-slate-700 border border-purple-500/40 rounded px-2 py-0.5 text-slate-200 outline-none"
                      />
                    </div>
                  ) : (
                    <h3
                      onClick={e => startEditDraft(e, draft)}
                      className="text-base font-medium text-slate-200 truncate mb-1 cursor-text hover:text-purple-300 hover:underline decoration-dotted underline-offset-2 transition-colors duration-150"
                    >
                      {draft.title}
                    </h3>
                  )}
                  <div className="flex items-center gap-2 text-sm text-slate-400">
                    <CalendarIcon className="h-4 w-4" />
                    <span>{new Date(draft.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
                  </div>
                </div>

                {/* Right Side Actions */}
                <div className="flex items-center gap-3" onClick={(e) => e.stopPropagation()}>
                  {/* Status Badge */}
                  <DraftStatusBadge status={draft.status} updatedAt={draft.updated_at} />

                  {/* Action Buttons */}
                  {draft.status === 'uploaded' && (
                    <button
                      onClick={() => handleAnalyze(draft.id)}
                      className="px-3 py-1 text-xs font-medium text-slate-200 bg-slate-700 hover:bg-slate-600 rounded border border-slate-600 transition-colors"
                    >
                      Analyze
                    </button>
                  )}
                  {draft.status === 'failed' && (Date.now() - new Date(draft.updated_at).getTime() >= 15 * 60 * 1000) && (
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

              {/* Progress bar — shown for any in-progress state */}
              {(draft.status === 'processing' || draft.status === 'uploaded') && (
                <DraftProgressBar draftId={draft.id} onComplete={silentReloadDrafts} />
              )}
            </div>
          )
        })}
      </div>

      {/* Lab Invite Modal */}
      {inviteModal.isOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div className="absolute inset-0 bg-black/70 backdrop-blur-sm" onClick={() => setInviteModal(prev => ({ ...prev, isOpen: false }))} />
          <div className="relative bg-bg-surface border border-border-default rounded-xl w-full max-w-md shadow-2xl">
            <div className="flex items-center justify-between px-6 py-5 border-b border-border-default">
              <div className="flex items-center gap-3">
                <UserGroupIcon className="h-5 w-5 text-accent-primary" />
                <h2 className="text-lg font-semibold text-text-primary">Invite Lab Members</h2>
              </div>
              <button onClick={() => setInviteModal(prev => ({ ...prev, isOpen: false }))} className="p-1 text-text-secondary hover:text-text-primary rounded transition-colors">
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>
            <div className="px-6 py-6 space-y-4">
              <p className="text-sm text-text-secondary leading-relaxed">
                Share this link with your lab members. When they sign up, they'll get a personalized welcome experience linked to <span className="font-semibold text-text-primary">{inviteModal.labName}</span>.
              </p>
              <div className="flex items-center gap-2">
                <input
                  readOnly
                  value={inviteModal.inviteUrl}
                  className="flex-1 px-3 py-2 bg-bg-hover border border-border-default rounded-lg text-sm text-text-secondary font-mono truncate focus:outline-none"
                />
                <button
                  onClick={handleCopyInviteUrl}
                  className="flex items-center gap-1.5 px-3 py-2 bg-accent-primary text-white text-sm font-semibold rounded-lg hover:bg-accent-hover transition-colors shrink-0"
                >
                  <ClipboardDocumentIcon className="h-4 w-4" />
                  Copy
                </button>
              </div>
              <p className="text-xs text-text-muted">
                Free for your whole lab during beta. One early finding from a real reviewer = worth it.
              </p>
            </div>
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

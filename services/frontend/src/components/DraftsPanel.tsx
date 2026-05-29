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

function sortDraftsByRecency(drafts: Draft[]) {
  return [...drafts].sort((a, b) => {
    const aTime = new Date(a.updated_at || a.created_at).getTime()
    const bTime = new Date(b.updated_at || b.created_at).getTime()
    return bTime - aTime
  })
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
      const draftsList = sortDraftsByRecency(data.drafts || [])
      setDrafts(draftsList)

      // Notify parent of draft count
      if (onDraftsLoaded) {
        onDraftsLoaded(draftsList.length)
      }
    } catch (error: unknown) {
      console.error('[DRAFTS-PANEL] Error loading drafts:', error)
      handleError(error, 'loading drafts')
    } finally {
      setLoading(false)
    }
  }

  // Silent reload — does not trigger loading spinner, used for polling and onComplete callbacks
  const silentReloadDrafts = () => {
    api.drafts.list(token, projectId).then(data => {
      const draftsList = sortDraftsByRecency(data.drafts || [])
      setDrafts(draftsList)
      onDraftsLoaded?.(draftsList.length)
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
    } catch (error: unknown) {
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
    } catch (error: unknown) {
      toast.dismiss()
      handleError(error, 'analyzing draft')
    }
  }


  const handleCopyInviteUrl = () => {
    navigator.clipboard.writeText(inviteModal.inviteUrl)
    toast.success('Invite link copied!')
  }

  const activeDraft = drafts[0]
  const previousDrafts = drafts.slice(1)

  const renderDraftCard = (draft: Draft, variant: 'current' | 'history' = 'current') => {
    const isCurrent = variant === 'current'

    return (
      <div
        key={draft.id}
        onClick={() => draft.status === 'analyzed' ? handleViewAnalysis(draft.id) : undefined}
        className={`group grid gap-4 border-b border-border-default/70 px-5 py-4 transition-colors duration-150 last:border-b-0 md:grid-cols-[minmax(0,1fr)_220px_40px] md:items-center ${
          isCurrent ? 'bg-bg-surface/70 hover:bg-bg-elevated/60' : 'bg-bg-surface/40 hover:bg-bg-elevated/50'
        } ${draft.status === 'analyzed' ? 'cursor-pointer' : ''}`}
      >
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-2">
            <DocumentTextIcon className="h-4 w-4 shrink-0 text-accent-primary" />
            {editingDraftId === draft.id ? (
              <div className="flex min-w-0 flex-1 items-center gap-1.5" onClick={e => e.stopPropagation()}>
                <input
                  ref={draftTitleInputRef}
                  value={editDraftTitle}
                  onChange={e => setEditDraftTitle(e.target.value)}
                  onKeyDown={e => { if (e.key === 'Enter') saveDraftTitle(draft.id); if (e.key === 'Escape') setEditingDraftId(null) }}
                  onBlur={() => saveDraftTitle(draft.id)}
                  className="min-w-0 flex-1 rounded border border-accent-primary/40 bg-bg-void px-2 py-1 text-sm text-text-primary outline-none"
                />
              </div>
            ) : (
              <h3
                onClick={e => startEditDraft(e, draft)}
                className={`truncate text-base font-semibold cursor-text transition-colors duration-150 hover:underline decoration-dotted underline-offset-2 ${
                  isCurrent
                    ? 'text-base text-text-primary hover:text-accent-primary'
                    : 'text-sm text-text-secondary hover:text-text-primary'
                }`}
              >
                {draft.title}
              </h3>
            )}
          </div>
          <div className="mt-2 flex flex-wrap items-center gap-x-4 gap-y-1 font-mono text-xs font-semibold text-text-secondary">
            {isCurrent && <span>Current draft</span>}
            <span className="inline-flex items-center gap-1.5">
              <CalendarIcon className="h-3.5 w-3.5" />
              {new Date(draft.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
            </span>
            {draft.version > 1 && <span>v{draft.version}</span>}
          </div>
        </div>

        <div className="flex items-center gap-3 md:justify-end" onClick={(e) => e.stopPropagation()}>
          <div className="flex items-center gap-2">
            <DraftStatusBadge status={draft.status} updatedAt={draft.updated_at} />
            {draft.status === 'uploaded' && (
              <button
                onClick={() => handleAnalyze(draft.id)}
                className="rounded-md border border-border-default px-2.5 py-1 text-xs font-semibold text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
              >
                Analyze
              </button>
            )}
            {draft.status === 'failed' && (Date.now() - new Date(draft.updated_at).getTime() >= 15 * 60 * 1000) && (
              <button
                onClick={() => handleAnalyze(draft.id)}
                className="rounded-md border border-border-default px-2.5 py-1 text-xs font-semibold text-text-secondary transition-colors hover:bg-bg-hover hover:text-text-primary"
              >
                Retry
              </button>
            )}
          </div>
        </div>

        <button
          onClick={(e) => {
            e.stopPropagation()
            handleDelete(draft.id, draft.title)
          }}
          className="justify-self-start rounded-md p-2 text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-error md:justify-self-end md:opacity-0 md:group-hover:opacity-100 md:focus:opacity-100"
          title="Delete Draft"
        >
          <TrashIcon className="h-4 w-4" />
        </button>

        {(draft.status === 'processing' || draft.status === 'uploaded') && (
          <div className="md:col-span-3">
            <DraftProgressBar draftId={draft.id} onComplete={silentReloadDrafts} />
          </div>
        )}
        </div>
    )
  }

  if (loading) {
    return <SkeletonList count={1} ItemComponent={SkeletonListItem} />
  }

  if (!activeDraft) {
    return (
      <div className="rounded-xl border border-dashed border-border-default bg-bg-surface/70 px-6 py-12 text-center">
        <div className="mx-auto flex h-10 w-10 items-center justify-center rounded-lg border border-border-default bg-bg-elevated">
          <DocumentTextIcon className="h-5 w-5 text-accent-primary" />
        </div>
        <h3 className="mt-3 text-sm font-semibold text-text-primary">No draft uploaded</h3>
        <p className="mx-auto mt-1 max-w-md text-sm leading-6 text-text-secondary">
          Upload the manuscript you want reviewed against this project's literature.
        </p>
      </div>
    )
  }

  return (
    <>
      <div className="space-y-3">
        <div className="overflow-hidden rounded-xl border border-border-default bg-bg-surface/80">
          {renderDraftCard(activeDraft)}
        </div>

        {previousDrafts.length > 0 && (
          <details className="group overflow-hidden rounded-xl border border-border-default bg-bg-surface/70">
            <summary className="flex cursor-pointer list-none items-center justify-between gap-3 px-4 py-3 text-sm font-semibold text-text-secondary transition-colors hover:bg-bg-elevated/50 hover:text-text-primary">
              <span className="font-medium">Previous uploads</span>
              <span className="text-xs font-mono font-semibold text-text-secondary">
                {previousDrafts.length} kept for reference
              </span>
            </summary>
            <div className="border-t border-border-default">
              {previousDrafts.map((draft) => renderDraftCard(draft, 'history'))}
            </div>
          </details>
        )}
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
          <div className="relative w-full max-w-md overflow-hidden rounded-xl border border-border-default bg-bg-surface shadow-2xl">
            {/* Header */}
            <div className="flex items-center justify-between border-b border-border-default px-5 py-4">
              <div className="flex items-center gap-3">
                <ExclamationTriangleIcon className="h-5 w-5 text-error" />
                <h2 className="text-base font-semibold text-text-primary">Delete Draft</h2>
              </div>
              <button
                onClick={() => !deleteModal.isDeleting && setDeleteModal(prev => ({ ...prev, isOpen: false }))}
                className="rounded-md p-1.5 text-text-secondary transition-colors duration-fast hover:bg-bg-hover hover:text-text-primary"
              >
                <XMarkIcon className="h-5 w-5" />
              </button>
            </div>

            {/* Body */}
            <div className="px-5 py-5">
              <p className="mb-2 text-sm font-medium text-text-secondary">Are you sure you want to delete</p>
              <p className="mb-4 break-words text-sm font-semibold text-text-primary">"{deleteModal.draftTitle}"</p>
              <p className="text-sm leading-6 text-text-secondary">
                This will permanently delete the draft, its analysis, all claims, gaps, and feedback. This action cannot be undone.
              </p>
            </div>

            {/* Actions */}
            <div className="flex gap-2 border-t border-border-default bg-bg-void/35 px-5 py-4">
              <button
                onClick={() => setDeleteModal(prev => ({ ...prev, isOpen: false }))}
                disabled={deleteModal.isDeleting}
                className="flex-1 rounded-md border border-border-default px-3 py-2 text-sm font-semibold text-text-secondary transition-all duration-fast hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                onClick={confirmDelete}
                disabled={deleteModal.isDeleting}
                className="flex flex-1 items-center justify-center gap-2 rounded-md bg-error px-3 py-2 text-sm font-semibold text-white transition-all duration-fast hover:bg-error/90 disabled:opacity-50"
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

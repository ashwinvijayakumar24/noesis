import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import {
  DocumentTextIcon,
  PlusIcon,
  ChevronDownIcon,
  ChevronRightIcon,
  PencilSquareIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline'
import { Badge } from '../ui/Badge'
import DocumentListItem from './DocumentListItem'
import { useAuthStore } from '../../stores/authStore'
import { api } from '../../lib/api'

interface Document {
  id: string
  title: string
  file_url: string
  status: string
  created_at: string
}

interface Draft {
  id: string
  title: string
  version: number
  file_type: string
  status: string
  created_at: string
}

interface SidebarProps {
  projectId: string
  documents: Document[]
  onUploadDocument: () => void
  onUploadDraft: () => void
  onDocumentClick?: (documentId: string) => void
  onDraftClick?: (draftId: string) => void
  // Quick actions
  insightsStatus?: 'not_analyzed' | 'analyzing' | 'analyzed'
  onAnalyzeInsights?: () => void
  draftRefreshTrigger?: number
}

export default function Sidebar({
  projectId,
  documents,
  onUploadDocument,
  onUploadDraft,
  onDocumentClick,
  onDraftClick,
  insightsStatus = 'not_analyzed',
  onAnalyzeInsights,
  draftRefreshTrigger = 0
}: SidebarProps) {
  const { session } = useAuthStore()
  const [isDraftCollapsed, setIsDraftCollapsed] = useState(false)
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [draftsLoading, setDraftsLoading] = useState(false)

  // Fetch drafts
  useEffect(() => {
    if (!session?.access_token) return

    const fetchDrafts = async () => {
      setDraftsLoading(true)
      try {
        const data = await api.drafts.list(session.access_token, projectId)
        setDrafts(data.drafts || [])
      } catch (error) {
        console.error('Failed to fetch drafts:', error)
      } finally {
        setDraftsLoading(false)
      }
    }

    fetchDrafts()
  }, [session, projectId, draftRefreshTrigger])

  return (
    <div className="h-full flex flex-col bg-surface border-r border-border-base">
      {/* Documents Section */}
      <div className="flex-shrink-0 border-b border-border-subtle">
        <div className="p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <DocumentTextIcon className="h-5 w-5 text-text-tertiary" />
              <h3 className="text-sm font-semibold text-text-primary">Documents</h3>
              {documents.length > 0 && (
                <span className="px-2 py-0.5 text-xs bg-surface-hover rounded-full font-mono text-text-muted">
                  {documents.length}
                </span>
              )}
            </div>
          </div>

          {/* Upload Button */}
          {documents.length === 0 ? (
            <button
              onClick={onUploadDocument}
              className="w-full py-4 bg-accent-primary text-white rounded-lg text-sm font-semibold hover:bg-accent-hover flex items-center justify-center gap-2 transition-colors"
            >
              <PlusIcon className="h-5 w-5" />
              Upload First Document
            </button>
          ) : (
            <button
              onClick={onUploadDocument}
              className="w-full py-2 bg-accent-primary/10 text-accent-primary rounded-lg text-sm font-medium hover:bg-accent-primary/20 flex items-center justify-center gap-2 border-2 border-dashed border-accent-primary transition-colors"
            >
              <PlusIcon className="h-4 w-4" />
              Upload Document
            </button>
          )}
        </div>

        {/* Documents List */}
        <div className="max-h-[300px] overflow-y-auto scrollbar-thin scrollbar-thumb-border-base scrollbar-track-transparent">
          {documents.length > 0 && (
            <div className="px-2 pb-2 space-y-1">
              {documents.map((doc) => (
                <DocumentListItem
                  key={doc.id}
                  document={doc}
                  onClick={() => onDocumentClick?.(doc.id)}
                />
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Draft Section (Collapsible) */}
      <div className="flex-shrink-0 border-b border-border-subtle">
        <button
          onClick={() => setIsDraftCollapsed(!isDraftCollapsed)}
          className="w-full p-4 flex items-center justify-between hover:bg-surface-hover transition-colors"
        >
          <div className="flex items-center gap-2">
            <PencilSquareIcon className="h-5 w-5 text-text-tertiary" />
            <h3 className="text-sm font-semibold text-text-primary">Your Draft</h3>
          </div>
          {isDraftCollapsed ? (
            <ChevronRightIcon className="h-4 w-4 text-text-tertiary" />
          ) : (
            <ChevronDownIcon className="h-4 w-4 text-text-tertiary" />
          )}
        </button>

        {!isDraftCollapsed && (
          <div className="px-4 pb-4">
            <button
              onClick={onUploadDraft}
              className="w-full py-2 mb-3 bg-purple-500/10 text-purple-400 rounded-lg text-sm font-medium hover:bg-purple-500/20 flex items-center justify-center gap-2 border border-dashed border-purple-400 transition-colors"
            >
              <PlusIcon className="h-4 w-4" />
              {drafts.length > 0 ? 'Upload New Version' : 'Upload Draft'}
            </button>

            {draftsLoading ? (
              <div className="flex items-center justify-center py-4">
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-purple-400 border-t-transparent" />
              </div>
            ) : drafts.length === 0 ? (
              <p className="text-xs text-text-muted text-center py-2">
                Get expert feedback on your writing
              </p>
            ) : (
              <div className="space-y-2 max-h-[200px] overflow-y-auto scrollbar-thin scrollbar-thumb-border-base scrollbar-track-transparent">
                {[...drafts]
                  .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
                  .slice(0, 1)
                  .map((draft) => (
                  <button
                    key={draft.id}
                    onClick={() => onDraftClick?.(draft.id)}
                    className="w-full p-2 bg-surface-hover hover:bg-surface rounded text-left transition-colors"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex-1 min-w-0">
                        <p className="text-sm text-text-primary font-medium truncate">
                          {draft.title}
                        </p>
                        <p className="text-xs text-text-muted mt-0.5">v{draft.version}</p>
                      </div>
                      <Badge
                        variant={
                          draft.status === 'analyzed' ? 'success' :
                          draft.status === 'processing' ? 'warning' :
                          draft.status === 'failed' ? 'error' : 'neutral'
                        }
                      >
                        {draft.status}
                      </Badge>
                    </div>
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Quick Actions */}
      {insightsStatus !== 'analyzed' && (
        <div className="flex-shrink-0 p-4 border-b border-border-subtle bg-surface-hover/50">
          <button
            onClick={onAnalyzeInsights}
            disabled={insightsStatus === 'analyzing'}
            className={`w-full py-2.5 rounded-lg text-sm font-medium flex items-center justify-center gap-2 transition-colors ${
              insightsStatus === 'analyzing'
                ? 'bg-amber-500/20 text-amber-400 cursor-wait'
                : 'bg-blue-500/10 text-blue-400 hover:bg-blue-500/20 border border-blue-400/50 animate-pulse'
            }`}
          >
            {insightsStatus === 'analyzing' ? (
              <>
                <div className="h-4 w-4 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
                Analyzing...
              </>
            ) : (
              <>
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                Analyze Insights
              </>
            )}
          </button>
          {documents.length >= 2 && insightsStatus === 'not_analyzed' && (
            <p className="text-xs text-text-muted mt-2 text-center">
              Unlock Compass & Research Planning
            </p>
          )}
        </div>
      )}

      <div className="border-t border-border-subtle p-4">
        <Link
          to="/privacy"
          className="flex items-center gap-2 rounded-lg border border-border-default bg-bg-elevated px-3 py-2 text-xs text-text-secondary transition-colors hover:text-text-primary"
        >
          <ShieldCheckIcon className="h-4 w-4 text-accent-primary" />
          Private by default
        </Link>
      </div>
    </div>
  )
}

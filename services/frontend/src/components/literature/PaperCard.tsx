import { useNavigate } from 'react-router-dom'
import { useState, useRef } from 'react'
import {
  DocumentTextIcon,
  BookOpenIcon,
  TrashIcon,
  ArrowPathIcon,
  ArrowTopRightOnSquareIcon,
  TagIcon,
  XMarkIcon,
  PlusIcon,
} from '@heroicons/react/24/outline'
import { api } from '../../lib/api'

export interface PaperDocument {
  id: string
  title: string
  status: string
  source_type?: string
  resolution_status?: string | null
  file_url?: string
  created_at: string
  tags?: string[]
  metadata?: {
    authors?: string[]
    year?: string
    journal?: string
    abstract?: string
    doi?: string
    url?: string
    import_source?: string
  }
}

interface PaperCardProps {
  document: PaperDocument
  projectId: string
  onDelete: (id: string, title: string) => void
  token?: string
  onResolved?: () => void
}

// ─── Source badge ────────────────────────────────────────────────────────────

function SourceBadge({ sourceType, resolutionStatus, status }: { sourceType?: string; resolutionStatus?: string | null; status?: string }) {
  // Papers imported via BibTeX may have source_type=null in the DB — use status/resolution_status as fallback signals
  const isBibTeX =
    sourceType === 'bibtex_import' ||
    sourceType === 'zotero_import' ||
    status === 'imported' ||
    (resolutionStatus != null && resolutionStatus !== '')

  if (sourceType === 'zotero_import') {
    return (
      <span className="text-xs font-mono px-1.5 py-0.5 rounded border bg-[#2C0D0D] text-red-400/80 border-[#5C1A1A]">
        Zotero
      </span>
    )
  }
  if (isBibTeX) {
    return (
      <span className="text-xs font-mono px-1.5 py-0.5 rounded border bg-[#1A0D2C] text-violet-400 border-[#3A1A5C]">
        BibTeX
      </span>
    )
  }
  if (sourceType === 'discovered') {
    return (
      <span className="text-xs font-mono px-1.5 py-0.5 rounded border bg-[#071A1A] text-teal-400 border-[#0D3A3A]">
        Discovered
      </span>
    )
  }
  return (
    <span className="text-xs font-mono px-1.5 py-0.5 rounded border bg-bg-elevated text-text-muted border-border-default">
      PDF
    </span>
  )
}

// ─── Status badge ─────────────────────────────────────────────────────────────

function StatusBadge({
  status,
  resolutionStatus,
}: {
  status: string
  resolutionStatus?: string | null
}) {
  const s = status.toLowerCase()
  const r = resolutionStatus?.toLowerCase()

  // Any in-progress state (resolving BibTeX, analyzing PDF, processing upload) → single label
  if (r === 'resolving' || s === 'analyzing' || s === 'processing' || s === 'uploaded' || s === 'ready') {
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

  if (r === 'unresolved') {
    return (
      <span className="text-xs font-medium px-2 py-0.5 rounded-sm border bg-[#071A2C] text-sky-400 border-[#0E3A5C]">
        Imported
      </span>
    )
  }

  // Standard document statuses
  switch (s) {
    case 'analyzed':
    case 'resolved_no_pdf':
      return (
        <span className="text-xs font-medium px-2 py-0.5 rounded-sm border bg-[#0D2E1F] text-emerald-400 border-[#1A5C3A]">
          Processed
        </span>
      )
    case 'failed':
      return (
        <span className="text-xs font-medium px-2 py-0.5 rounded-sm border bg-[#2C0D0D] text-red-400 border-[#5C1A1A]">
          Failed
        </span>
      )
    case 'imported':
      // bibtex imported but not yet resolved or metadata-only
      if (r === null || r === undefined) {
        return (
          <span className="text-xs font-medium px-2 py-0.5 rounded-sm border bg-[#071A2C] text-sky-400 border-[#0E3A5C]">
            Imported
          </span>
        )
      }
      return null
    default:
      return (
        <span className="text-xs font-medium px-2 py-0.5 rounded-sm border bg-bg-elevated text-text-muted border-border-default">
          {status.charAt(0).toUpperCase() + status.slice(1)}
        </span>
      )
  }
}

// ─── Inline tag editor ────────────────────────────────────────────────────────

function DocumentTagRow({ docId, initialTags, token }: { docId: string; initialTags: string[]; token?: string }) {
  const [tags, setTags] = useState<string[]>(initialTags)
  const [inputVisible, setInputVisible] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const inputRef = useRef<HTMLInputElement>(null)

  const saveTag = async (newTags: string[]) => {
    if (!token) return
    try {
      await api.documents.updateTags(token, docId, newTags)
    } catch {
      // silently revert on failure
    }
  }

  const addTag = async () => {
    const t = inputValue.trim().toLowerCase()
    if (!t || tags.includes(t) || tags.length >= 10) { setInputValue(''); setInputVisible(false); return }
    const next = [...tags, t]
    setTags(next)
    setInputValue('')
    setInputVisible(false)
    await saveTag(next)
  }

  const removeTag = async (tag: string) => {
    const next = tags.filter(t => t !== tag)
    setTags(next)
    await saveTag(next)
  }

  if (tags.length === 0 && !inputVisible) {
    return (
      <button
        onClick={(e) => { e.stopPropagation(); setInputVisible(true); setTimeout(() => inputRef.current?.focus(), 0) }}
        className="inline-flex items-center gap-1 text-xs text-text-muted hover:text-text-tertiary transition-colors duration-150 mt-1.5"
      >
        <TagIcon className="h-3 w-3" />
        <span>add tag</span>
      </button>
    )
  }

  return (
    <div className="flex flex-wrap items-center gap-1 mt-1.5" onClick={e => e.stopPropagation()}>
      {tags.map(tag => (
        <span key={tag} className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded border bg-bg-elevated text-text-secondary border-border-default group/tag">
          {tag}
          <button onClick={() => removeTag(tag)} className="opacity-0 group-hover/tag:opacity-100 transition-opacity">
            <XMarkIcon className="h-2.5 w-2.5 text-text-muted hover:text-error" />
          </button>
        </span>
      ))}
      {inputVisible ? (
        <input
          ref={inputRef}
          value={inputValue}
          onChange={e => setInputValue(e.target.value)}
          onKeyDown={e => { if (e.key === 'Enter') addTag(); if (e.key === 'Escape') { setInputVisible(false); setInputValue('') } }}
          onBlur={addTag}
          maxLength={24}
          className="text-xs bg-bg-elevated border border-accent-primary/40 rounded px-1.5 py-0.5 text-text-primary outline-none w-20"
          placeholder="tag…"
        />
      ) : tags.length < 10 && (
        <button
          onClick={() => { setInputVisible(true); setTimeout(() => inputRef.current?.focus(), 0) }}
          className="inline-flex items-center justify-center h-5 w-5 rounded border border-dashed border-border-default text-text-muted hover:border-accent-primary/40 hover:text-text-secondary transition-colors duration-150"
        >
          <PlusIcon className="h-3 w-3" />
        </button>
      )}
    </div>
  )
}

// ─── Main component ───────────────────────────────────────────────────────────

export default function PaperCard({ document, projectId, onDelete, token }: PaperCardProps) {
  const navigate = useNavigate()

  const isAnalyzed = document.status.toLowerCase() === 'analyzed'
  const isResolving = document.resolution_status === 'resolving'
  const isBibtex = document.source_type === 'bibtex_import' || document.source_type === 'zotero_import'
  const isClickable = isAnalyzed && !isResolving

  // Icon selection
  const Icon = isBibtex ? BookOpenIcon : DocumentTextIcon
  const statusLower = document.status.toLowerCase()
  const iconColor = isAnalyzed
    ? 'text-accent-primary'
    : statusLower === 'failed'
    ? 'text-error'
    : statusLower === 'analyzing' || statusLower === 'processing' || statusLower === 'uploaded'
    ? 'text-amber-400'
    : 'text-text-tertiary'

  // Left accent border per status — gives at-a-glance status scanning
  const statusAccent = statusLower === 'analyzed'
    ? 'border-l-[3px] border-l-emerald-500/50'
    : statusLower === 'failed'
    ? 'border-l-[3px] border-l-red-500/50'
    : statusLower === 'analyzing' || statusLower === 'processing' || statusLower === 'uploaded'
    ? 'border-l-[3px] border-l-amber-500/50'
    : statusLower === 'imported'
    ? 'border-l-[3px] border-l-sky-500/40'
    : document.resolution_status === 'resolving'
    ? 'border-l-[3px] border-l-amber-500/50'
    : ''

  // Meta line: Authors · Year · Journal
  const meta = document.metadata ?? {}
  const authors = meta.authors ?? []
  const year = meta.year ?? ''
  const journal = meta.journal ?? ''
  const doi = meta.doi ?? ''
  const abstract = meta.abstract ?? ''
  const metaUrl = meta.url ?? ''
  const fileUrl = document.file_url ?? ''
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

  // Build "View Paper" href: prefer DOI, fall back to metadata url
  const viewPaperHref = doi
    ? `https://doi.org/${doi.replace(/^https?:\/\/(dx\.)?doi\.org\//, '')}`
    : metaUrl || ''
  const hasPdf = fileUrl && document.resolution_status !== 'resolved_no_pdf'

  const authorLine =
    authors.length === 0
      ? ''
      : authors.length <= 2
      ? authors.join(', ')
      : `${authors[0]}, ${authors[1]} et al.`

  const metaLine = [authorLine, year, journal].filter(Boolean).join(' · ')
  const showAbstract = !isAnalyzed && abstract.trim().length > 0

  const handleClick = () => {
    if (isClickable) {
      navigate(`/projects/${projectId}/documents/${document.id}`)
    }
  }

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    onDelete(document.id, document.title)
  }

  const handleOpenPdf = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!token) return
    try {
      const res = await fetch(`${API_URL}/documents/${document.id}/signed-url`, {
        headers: { Authorization: `Bearer ${token}` },
      })
      if (!res.ok) throw new Error('Failed to get signed URL')
      const { signed_url } = await res.json()
      window.open(signed_url, '_blank', 'noopener,noreferrer')
    } catch {
      // Fallback: open file_url directly (works if bucket is public)
      if (fileUrl) window.open(fileUrl, '_blank', 'noopener,noreferrer')
    }
  }

  const handleRetry = async (e: React.MouseEvent) => {
    e.stopPropagation()
    if (!token) return

    await api.documents.retry(token, document.id)
  }

  return (
    <div
      onClick={handleClick}
      className={`
        group flex items-start gap-4 bg-bg-surface rounded-xl border border-border-default
        px-4 py-3.5 transition-all duration-150
        ${statusAccent}
        ${isClickable
          ? 'cursor-pointer hover:border-accent-primary/30 hover:bg-bg-hover'
          : 'cursor-default'
        }
      `}
    >
      {/* Left: icon zone (48px) */}
      <div className="shrink-0 w-10 flex items-center justify-center pt-0.5">
        <Icon className={`h-6 w-6 transition-colors duration-150 ${iconColor} ${isClickable ? 'group-hover:text-accent-primary' : ''}`} />
      </div>

      {/* Center: content */}
      <div className="flex-1 min-w-0">
        {/* Row 1: Title */}
        <p className={`font-semibold text-sm text-text-primary leading-snug line-clamp-1 transition-colors duration-150 ${isClickable ? 'group-hover:text-accent-primary' : ''}`}>
          {document.title}
        </p>

        {/* Row 2: Meta */}
        {metaLine && (
          <p className="text-xs text-text-tertiary font-mono mt-0.5 line-clamp-1">
            {metaLine}
          </p>
        )}

        {/* Row 3: Document tags */}
        <DocumentTagRow docId={document.id} initialTags={document.tags ?? []} token={token} />

        {/* Row 4: Unresolved hint */}
        {document.resolution_status === 'unresolved' && (
          <p className="text-xs text-text-tertiary mt-1.5 italic">
            No open-access PDF found. Upload the PDF manually for full RAG analysis.
          </p>
        )}

        {/* Row 5: Abstract preview (metadata-only entries) */}
        {showAbstract && (
          <p className="text-xs text-text-secondary mt-1.5 line-clamp-2 leading-relaxed">
            {abstract}
          </p>
        )}

        {/* Row 6: Action buttons — View Paper, PDF */}
        {(viewPaperHref || hasPdf) && (
          <div className="flex items-center gap-1.5 mt-2" onClick={e => e.stopPropagation()}>
            {viewPaperHref && (
              <a
                href={viewPaperHref}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1.5 text-xs text-text-secondary border border-border-default rounded-lg px-2.5 py-1 hover:text-text-primary hover:border-border-subtle transition-colors duration-150"
              >
                <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" />
                View Paper
              </a>
            )}
            {hasPdf && token && (
              <button
                onClick={handleOpenPdf}
                className="inline-flex items-center gap-1.5 text-xs text-text-secondary border border-border-default rounded-lg px-2.5 py-1 hover:text-text-primary hover:border-border-subtle transition-colors duration-150"
              >
                <DocumentTextIcon className="h-3.5 w-3.5" />
                Access PDF
              </button>
            )}
          </div>
        )}
      </div>

      {/* Right: badges + delete */}
      <div className="shrink-0 flex flex-col items-end gap-1.5 pt-0.5">
        <div className="flex items-center gap-1.5 flex-wrap justify-end">
          <SourceBadge sourceType={document.source_type} resolutionStatus={document.resolution_status} status={document.status} />
          <StatusBadge
            status={document.status}
            resolutionStatus={document.resolution_status}
          />
        </div>

        <div className="mt-1 flex items-center gap-1">
          {statusLower === 'failed' && token && (
            <button
              onClick={handleRetry}
              className="p-1 rounded-md text-text-muted hover:text-accent-primary transition-colors duration-150"
              title="Retry analysis"
            >
              <ArrowPathIcon className="h-4 w-4" />
            </button>
          )}
          <button
            onClick={handleDelete}
            className="p-1 rounded-md text-text-muted hover:text-error transition-colors duration-150"
            title="Remove paper"
          >
            <TrashIcon className="h-4 w-4" />
          </button>
        </div>
      </div>
    </div>
  )
}

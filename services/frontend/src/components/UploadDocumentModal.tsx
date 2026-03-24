import { Fragment, useState, useRef, useEffect, type FormEvent } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import {
  XMarkIcon,
  DocumentArrowUpIcon,
  BookOpenIcon,
  CheckIcon,
  ArrowTopRightOnSquareIcon,
} from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import { trackEvent } from '../lib/analytics'
import { validateFileSize, validateFileType, handleError, handleQuotaError } from '../lib/errorHandler'
import UploadSuccessModal from './UploadSuccessModal'

type TabId = 'pdf' | 'bibtex' | 'zotero'

interface QuotaSummary {
  pdfs: { used: number; limit: number }
  bib_refs: { used: number; limit: number }
  plan_tier: string
}

interface BibEntryStatus {
  id: string
  title: string
  status: string
  resolution_status: 'resolving' | 'resolved' | 'unresolved' | null
}

interface UploadDocumentModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  token: string
  projectId: string
  /** 'pdf' = PDF-only modal, 'import' = BibTeX/Zotero modal, undefined = all tabs */
  mode?: 'pdf' | 'import'
}

// ─── Quota indicator bar ──────────────────────────────────────────────────────

function QuotaBar({ used, limit, label }: { used: number; limit: number; label: string }) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0
  const isWarning = pct >= 80
  return (
    <div className="flex items-center gap-2">
      <span className="text-xs text-text-muted shrink-0 w-20">{label}</span>
      <div className="flex-1 h-1 bg-bg-elevated rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-300 ${isWarning ? 'bg-amber-400' : 'bg-accent-primary'}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs font-mono shrink-0 ${isWarning ? 'text-amber-400' : 'text-text-muted'}`}>
        {used}/{limit}
      </span>
    </div>
  )
}

// ─── BibTeX per-entry status icon ─────────────────────────────────────────────

function EntryStatusIcon({ status }: { status: BibEntryStatus['resolution_status'] }) {
  if (status === 'resolving') {
    return (
      <span className="flex items-center gap-1 text-xs text-amber-300">
        <span className="h-2.5 w-2.5 inline-block">
          <svg className="animate-spin h-2.5 w-2.5" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z" />
          </svg>
        </span>
        Searching…
      </span>
    )
  }
  if (status === 'resolved') {
    return (
      <span className="flex items-center gap-1 text-xs text-success">
        <CheckIcon className="h-3 w-3" />
        Processed
      </span>
    )
  }
  return (
    <span className="text-xs text-text-muted">
      No OA PDF — metadata only
    </span>
  )
}

// ─── Main Modal ───────────────────────────────────────────────────────────────

export default function UploadDocumentModal({
  isOpen,
  onClose,
  onSuccess,
  token,
  projectId,
  mode,
}: UploadDocumentModalProps) {
  const [activeTab, setActiveTab] = useState<TabId>(mode === 'import' ? 'bibtex' : 'pdf')

  // PDF upload state
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  // BibTeX state
  const [bibtexFile, setBibtexFile] = useState<File | null>(null)
  const bibtexInputRef = useRef<HTMLInputElement>(null)
  const [bibPhase, setBibPhase] = useState<'select' | 'resolving'>('select')
  const [bibEntries, setBibEntries] = useState<BibEntryStatus[]>([])
  const [bibPollTimer, setBibPollTimer] = useState<ReturnType<typeof setInterval> | null>(null)
  const [_bibImportedCount, setBibImportedCount] = useState(0)

  // Zotero state
  const [zoteroKey, setZoteroKey] = useState('')
  const [zoteroUserId, setZoteroUserId] = useState<number | null>(null)
  const [zoteroUsername, setZoteroUsername] = useState('')
  const [zoteroCollections, setZoteroCollections] = useState<any[]>([])
  const [zoteroSelectedCollection, setZoteroSelectedCollection] = useState<string>('')
  const [zoteroValidating, setZoteroValidating] = useState(false)
  const [zoteroValidated, setZoteroValidated] = useState(false)

  // Quota state
  const [quota, setQuota] = useState<QuotaSummary | null>(null)

  // Success modal
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [uploadedCount, setUploadedCount] = useState(0)
  const [uploadedTitles, setUploadedTitles] = useState<string[]>([])

  const MAX_FILES = 10
  const MAX_SIZE_MB = 50

  // Reset active tab when modal opens based on mode
  useEffect(() => {
    if (isOpen) {
      setActiveTab(mode === 'import' ? 'bibtex' : 'pdf')
    }
  }, [isOpen, mode])

  // Fetch quota when modal opens
  useEffect(() => {
    if (!isOpen || !token) return
    api.quota.getSummary(token)
      .then((q: QuotaSummary) => setQuota(q))
      .catch(() => {}) // Non-critical
  }, [isOpen, token])

  // Cleanup bib polling on unmount
  useEffect(() => {
    return () => {
      if (bibPollTimer) clearInterval(bibPollTimer)
    }
  }, [bibPollTimer])

  // ─── PDF handlers ───────────────────────────────────────────────────────────

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return
    const filesArray = Array.from(e.target.files)
    if (filesArray.length > MAX_FILES) {
      toast.error(`Maximum ${MAX_FILES} files allowed`)
      return
    }
    const validFiles = filesArray.filter(f =>
      validateFileType(f, ['pdf']) && validateFileSize(f, MAX_SIZE_MB)
    )
    if (validFiles.length === 0) {
      toast.error('No valid PDF files selected')
      return
    }
    setSelectedFiles(validFiles)
  }

  const removeFile = (index: number) => {
    setSelectedFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!loading) setIsDragging(true)
  }

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
  }

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    setIsDragging(false)
    if (loading) return
    const validFiles = Array.from(e.dataTransfer.files).filter(f =>
      f.type === 'application/pdf' && f.size <= MAX_SIZE_MB * 1024 * 1024
    )
    if (validFiles.length > MAX_FILES) {
      toast.error(`Maximum ${MAX_FILES} files allowed`)
      return
    }
    if (validFiles.length === 0) {
      toast.error('No valid PDF files found')
      return
    }
    setSelectedFiles(validFiles)
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (selectedFiles.length === 0) {
      toast.error('Please select at least one PDF file')
      return
    }
    try {
      setLoading(true)
      const uploadPromises = selectedFiles.map(file =>
        api.documents.upload(token, file, {
          project_id: projectId,
          title: file.name.replace('.pdf', ''),
          description: description.trim() || undefined,
        })
      )
      const uploadResults = await Promise.all(uploadPromises)
      uploadResults.forEach(r => trackEvent.documentUploaded(projectId, r.document.id))
      Promise.allSettled(
        uploadResults.map(r =>
          api.rag.ingest(token, r.document.id).catch(() => {})
        )
      )
      const titles = uploadResults.map(r => r.document.title)
      setSelectedFiles([])
      setDescription('')
      if (fileInputRef.current) fileInputRef.current.value = ''
      onClose()
      setUploadedCount(uploadResults.length)
      setUploadedTitles(titles)
      setShowSuccessModal(true)
      onSuccess()
    } catch (error: any) {
      if (!handleQuotaError(error)) {
        handleError(error, 'uploading documents')
      }
    } finally {
      setLoading(false)
    }
  }

  // ─── BibTeX handlers ─────────────────────────────────────────────────────────

  const handleBibtexSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!bibtexFile) {
      toast.error('Please select a .bib file')
      return
    }
    try {
      setLoading(true)
      const result = await api.documents.importBibtex(token, projectId, bibtexFile)
      setBibImportedCount(result.imported)

      // If resolution was started, show live panel
      if (result.resolution_started && result.imported > 0) {
        // Build initial entry list from document_ids
        const initialEntries: BibEntryStatus[] = (result.document_ids || []).map(
          (id: string) => ({ id, title: '…', status: 'imported', resolution_status: 'resolving' })
        )
        setBibEntries(initialEntries)
        setBibPhase('resolving')

        // Start polling
        const timer = setInterval(async () => {
          try {
            const statusData = await api.projects.getBibResolutionStatus(token, projectId)
            const entries: BibEntryStatus[] = (statusData.entries || []).map((e: any) => ({
              id: e.id,
              title: e.title || 'Untitled',
              status: e.status,
              resolution_status: e.resolution_status,
            }))
            setBibEntries(entries)

            // Stop polling when nothing is resolving
            if (statusData.resolving_count === 0) {
              clearInterval(timer)
              setBibPollTimer(null)
              onSuccess() // Refresh parent list
            }
          } catch {
            // Silent fail — keep polling
          }
        }, 3000)
        setBibPollTimer(timer)
        onSuccess() // Refresh parent list immediately
      } else {
        // No resolution (0 entries) — just close
        setBibtexFile(null)
        if (bibtexInputRef.current) bibtexInputRef.current.value = ''
        onClose()
        onSuccess()
        setUploadedCount(result.imported)
        setShowSuccessModal(true)
        toast.success(`Imported ${result.imported} references`)
      }
    } catch (error: any) {
      if (!handleQuotaError(error)) {
        handleError(error, 'importing BibTeX file')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleBibContinue = () => {
    if (bibPollTimer) clearInterval(bibPollTimer)
    setBibPollTimer(null)
    handleClose()
    onSuccess()
  }

  // ─── Zotero handlers ──────────────────────────────────────────────────────────

  const handleZoteroValidate = async () => {
    if (!zoteroKey.trim()) {
      toast.error('Enter your Zotero API key')
      return
    }
    setZoteroValidating(true)
    try {
      const result = await api.zotero.validateKey(token, zoteroKey.trim())
      if (result.valid) {
        setZoteroUserId(result.user_id)
        setZoteroUsername(result.username || result.name || '')
        setZoteroValidated(true)
        const libs = await api.zotero.getLibraries(token, zoteroKey.trim())
        setZoteroCollections(libs.collections || [])
        toast.success(`Connected as ${result.username || result.name}`)
      } else {
        toast.error('Invalid Zotero API key')
      }
    } catch {
      toast.error('Failed to validate Zotero key')
    } finally {
      setZoteroValidating(false)
    }
  }

  const handleZoteroImport = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!zoteroUserId) return
    setLoading(true)
    try {
      const result = await api.zotero.importCollection(
        token, zoteroKey.trim(), zoteroUserId, projectId,
        zoteroSelectedCollection || undefined,
      )
      onClose()
      onSuccess()
      setUploadedCount(result.imported)
      setUploadedTitles([])
      setShowSuccessModal(true)
      toast.success(result.message || `Imported ${result.imported} references from Zotero`)
    } catch {
      toast.error('Failed to import from Zotero')
    } finally {
      setLoading(false)
    }
  }

  // ─── Close ───────────────────────────────────────────────────────────────────

  const handleClose = () => {
    if (loading && bibPhase === 'select') return
    setSelectedFiles([])
    setDescription('')
    setIsDragging(false)
    setBibtexFile(null)
    setBibPhase('select')
    setBibEntries([])
    setZoteroKey('')
    setZoteroValidated(false)
    setZoteroCollections([])
    setZoteroSelectedCollection('')
    if (fileInputRef.current) fileInputRef.current.value = ''
    if (bibtexInputRef.current) bibtexInputRef.current.value = ''
    onClose()
  }

  // Derived stats for bib resolution panel
  const bibResolved = bibEntries.filter(e => e.resolution_status === 'resolved').length
  const bibResolving = bibEntries.filter(e => e.resolution_status === 'resolving').length
  const bibAllDone = bibResolving === 0 && bibEntries.length > 0

  return (
    <>
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300" enterFrom="opacity-0" enterTo="opacity-100"
          leave="ease-in duration-200" leaveFrom="opacity-100" leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-300" enterFrom="opacity-0 scale-95" enterTo="opacity-100 scale-100"
              leave="ease-in duration-200" leaveFrom="opacity-100 scale-100" leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-lg transform overflow-hidden rounded-xl bg-bg-surface border border-border-default shadow-xl transition-all">

                {/* ── Header ─────────────────────────────────────────── */}
                <div className="px-6 py-5 border-b border-border-default">
                  <div className="flex items-center justify-between">
                    <Dialog.Title className="text-lg font-semibold text-text-primary">
                      {mode === 'pdf' ? 'Upload PDFs' : mode === 'import' ? 'Import References' : 'Add Papers'}
                    </Dialog.Title>
                    <button
                      onClick={handleClose}
                      className="text-text-tertiary hover:text-text-primary hover:bg-bg-hover rounded-lg p-1.5 transition-all duration-150"
                    >
                      <XMarkIcon className="h-5 w-5" />
                    </button>
                  </div>

                  {/* Tab switcher — only when mode is unset (all tabs) or import (bib+zotero) */}
                  {bibPhase !== 'resolving' && mode !== 'pdf' && (
                    <div className="flex gap-0.5 mt-4 bg-bg-elevated rounded-lg p-1 border border-border-default">
                      {([
                        mode !== 'import' ? { id: 'pdf', label: 'Upload PDF' } : null,
                        { id: 'bibtex', label: 'BibTeX' },
                        { id: 'zotero', label: 'Zotero' },
                      ] as ({ id: TabId; label: string } | null)[])
                        .filter((t): t is { id: TabId; label: string } => t !== null)
                        .map(tab => (
                          <button
                            key={tab.id}
                            type="button"
                            onClick={() => setActiveTab(tab.id)}
                            className={`flex-1 py-1.5 px-2 rounded-md text-xs font-semibold transition-all duration-150 ${
                              activeTab === tab.id
                                ? 'bg-bg-surface text-text-primary border border-border-default shadow-xs'
                                : 'text-text-muted hover:text-text-secondary'
                            }`}
                          >
                            {tab.label}
                          </button>
                        ))}
                    </div>
                  )}
                </div>

                {/* ── PDF Tab ────────────────────────────────────────── */}
                {activeTab === 'pdf' && bibPhase === 'select' && mode !== 'import' && (
                  <form onSubmit={handleSubmit} className="p-6 space-y-4">

                    {/* Quota bar */}
                    {quota && (
                      <QuotaBar used={quota.pdfs.used} limit={quota.pdfs.limit} label="PDFs/month" />
                    )}

                    {/* Drop zone */}
                    <div
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      className={`relative border-2 border-dashed rounded-xl p-8 transition-all duration-150 text-center ${
                        isDragging
                          ? 'border-accent-primary bg-bg-elevated'
                          : 'border-border-default hover:border-accent-primary/40 hover:bg-bg-hover'
                      } ${loading ? 'opacity-50 pointer-events-none' : 'cursor-pointer'}`}
                    >
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="application/pdf,.pdf"
                        multiple
                        onChange={handleFileSelect}
                        disabled={loading}
                        className="hidden"
                        id="file-upload"
                      />
                      <label htmlFor="file-upload" className="cursor-pointer block">
                        <DocumentArrowUpIcon className={`h-8 w-8 mx-auto mb-2 ${isDragging ? 'text-accent-primary' : 'text-text-tertiary'}`} />
                        {selectedFiles.length > 0 ? (
                          <>
                            <p className="text-sm font-semibold text-text-primary">
                              {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} selected
                            </p>
                            <p className="text-xs text-text-muted mt-0.5">Click or drag to change</p>
                          </>
                        ) : (
                          <>
                            <p className="text-sm font-semibold text-text-secondary">
                              {isDragging ? 'Drop files here' : 'Drag & drop or click to browse'}
                            </p>
                            <p className="text-xs text-text-muted mt-0.5 font-mono">
                              PDF only · max {MAX_SIZE_MB}MB each · up to {MAX_FILES} files
                            </p>
                          </>
                        )}
                      </label>
                    </div>

                    {/* File list */}
                    {selectedFiles.length > 0 && (
                      <div className="space-y-1.5 max-h-40 overflow-y-auto">
                        {selectedFiles.map((file, index) => (
                          <div key={index} className="flex items-center justify-between gap-2 px-3 py-2 bg-bg-elevated border border-border-default rounded-lg group">
                            <div className="flex-1 min-w-0">
                              <p className="text-xs font-medium text-text-primary truncate">{file.name}</p>
                              <p className="text-xs text-text-muted font-mono">{(file.size / (1024 * 1024)).toFixed(1)} MB</p>
                            </div>
                            <button
                              type="button"
                              onClick={() => removeFile(index)}
                              disabled={loading}
                              className="text-text-muted hover:text-error transition-colors p-0.5"
                            >
                              <XMarkIcon className="h-3.5 w-3.5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}

                    {/* Actions */}
                    <div className="flex gap-2 pt-1">
                      <button
                        type="button"
                        onClick={handleClose}
                        disabled={loading}
                        className="flex-1 px-4 py-2.5 border border-border-default text-text-secondary text-sm font-semibold rounded-lg hover:bg-bg-hover hover:border-accent-primary/30 hover:text-text-primary transition-all duration-150 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={loading || selectedFiles.length === 0}
                        className="flex-1 px-4 py-2.5 bg-accent-primary text-white text-sm font-semibold rounded-lg hover:bg-accent-hover transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {loading ? (
                          <>
                            <span className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent" />
                            Uploading…
                          </>
                        ) : (
                          `Upload ${selectedFiles.length > 0 ? selectedFiles.length + ' ' : ''}PDF${selectedFiles.length > 1 ? 's' : ''}`
                        )}
                      </button>
                    </div>
                  </form>
                )}

                {/* ── BibTeX Tab — Phase A: file selection ─────────── */}
                {activeTab === 'bibtex' && bibPhase === 'select' && mode !== 'pdf' && (
                  <form onSubmit={handleBibtexSubmit} className="p-6 space-y-4">
                    <p className="text-sm text-text-secondary leading-relaxed">
                      Import references from Zotero, Mendeley, or Endnote. We'll search for open-access PDFs and analyze them automatically.
                    </p>

                    {/* Quota bar */}
                    {quota && (
                      <QuotaBar used={quota.bib_refs.used} limit={quota.bib_refs.limit} label="Refs/month" />
                    )}

                    {/* .bib file picker */}
                    <div
                      className={`relative border-2 border-dashed rounded-xl p-8 transition-all duration-150 text-center ${
                        bibtexFile
                          ? 'border-accent-primary/50 bg-bg-elevated'
                          : 'border-border-default hover:border-accent-primary/40 hover:bg-bg-hover'
                      } ${loading ? 'opacity-50 pointer-events-none' : 'cursor-pointer'}`}
                    >
                      <input
                        ref={bibtexInputRef}
                        type="file"
                        accept=".bib"
                        onChange={e => setBibtexFile(e.target.files?.[0] || null)}
                        disabled={loading}
                        className="hidden"
                        id="bibtex-upload"
                      />
                      <label htmlFor="bibtex-upload" className="cursor-pointer block">
                        <BookOpenIcon className={`h-8 w-8 mx-auto mb-2 ${bibtexFile ? 'text-accent-primary' : 'text-text-tertiary'}`} />
                        {bibtexFile ? (
                          <>
                            <p className="text-sm font-semibold text-text-primary">{bibtexFile.name}</p>
                            <p className="text-xs text-text-muted mt-0.5">Click to change file</p>
                          </>
                        ) : (
                          <>
                            <p className="text-sm font-semibold text-text-secondary">Click to select .bib file</p>
                            <p className="text-xs text-text-muted mt-0.5 font-mono">Exported from Zotero, Mendeley, Endnote</p>
                          </>
                        )}
                      </label>
                    </div>

                    <div className="flex gap-2 pt-1">
                      <button
                        type="button"
                        onClick={handleClose}
                        disabled={loading}
                        className="flex-1 px-4 py-2.5 border border-border-default text-text-secondary text-sm font-semibold rounded-lg hover:bg-bg-hover hover:border-accent-primary/30 hover:text-text-primary transition-all duration-150 disabled:opacity-50"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={loading || !bibtexFile}
                        className="flex-1 px-4 py-2.5 bg-accent-primary text-white text-sm font-semibold rounded-lg hover:bg-accent-hover transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {loading ? (
                          <>
                            <span className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent" />
                            Importing…
                          </>
                        ) : 'Import & Resolve'}
                      </button>
                    </div>
                  </form>
                )}

                {/* ── BibTeX Tab — Phase B: live resolution panel ────── */}
                {bibPhase === 'resolving' && (
                  <div className="p-6 space-y-4">
                    {/* Header */}
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-sm font-semibold text-text-primary">
                          {bibAllDone
                            ? `Done — ${bibResolved} of ${bibEntries.length} resolved`
                            : `Finding open-access PDFs…`}
                        </p>
                        <p className="text-xs text-text-muted mt-0.5">
                          {bibAllDone
                            ? 'Papers are ready in your literature tab.'
                            : `${bibResolved} of ${bibEntries.length} done — this may take a minute`}
                        </p>
                      </div>
                      {!bibAllDone && (
                        <span className="text-xs font-mono text-text-muted bg-bg-elevated px-2 py-1 rounded border border-border-default">
                          {bibResolved}/{bibEntries.length}
                        </span>
                      )}
                    </div>

                    {/* Progress bar */}
                    {bibEntries.length > 0 && (
                      <div className="h-1 bg-bg-elevated rounded-full overflow-hidden">
                        <div
                          className="h-full bg-accent-primary rounded-full transition-all duration-500"
                          style={{ width: `${(bibResolved / bibEntries.length) * 100}%` }}
                        />
                      </div>
                    )}

                    {/* Per-entry list */}
                    <div className="space-y-1 max-h-64 overflow-y-auto">
                      {bibEntries.slice(0, 20).map(entry => (
                        <div key={entry.id} className="flex items-center justify-between gap-3 py-1.5 px-3 bg-bg-elevated rounded-lg border border-border-default">
                          <BookOpenIcon className={`h-4 w-4 shrink-0 ${entry.resolution_status === 'resolved' ? 'text-success' : 'text-text-tertiary'}`} />
                          <p className="flex-1 text-xs text-text-primary truncate">{entry.title}</p>
                          <EntryStatusIcon status={entry.resolution_status} />
                        </div>
                      ))}
                      {bibEntries.length > 20 && (
                        <p className="text-xs text-text-muted text-center py-1">
                          + {bibEntries.length - 20} more entries…
                        </p>
                      )}
                    </div>

                    {/* Action buttons */}
                    <div className="flex gap-2 pt-1">
                      <button
                        type="button"
                        onClick={handleBibContinue}
                        className="flex-1 px-4 py-2.5 border border-border-default text-text-secondary text-sm font-semibold rounded-lg hover:bg-bg-hover hover:border-accent-primary/30 hover:text-text-primary transition-all duration-150"
                      >
                        Continue to Literature
                      </button>
                      {bibAllDone && (
                        <button
                          type="button"
                          onClick={handleBibContinue}
                          className="flex-1 px-4 py-2.5 bg-accent-primary text-white text-sm font-semibold rounded-lg hover:bg-accent-hover transition-all duration-150 flex items-center justify-center gap-2"
                        >
                          <CheckIcon className="h-4 w-4" />
                          Done — View Papers
                        </button>
                      )}
                    </div>
                    {!bibAllDone && (
                      <div className="flex justify-center pt-1">
                        <button
                          type="button"
                          onClick={() => {
                            if (bibPollTimer) clearInterval(bibPollTimer)
                            setBibPollTimer(null)
                            handleClose()
                          }}
                          className="text-sm text-text-secondary hover:text-text-primary transition-colors duration-150 underline"
                        >
                          Close — resolving in background
                        </button>
                      </div>
                    )}
                  </div>
                )}

                {/* ── Zotero Tab ─────────────────────────────────────── */}
                {activeTab === 'zotero' && bibPhase === 'select' && mode !== 'pdf' && (
                  <div className="p-6 space-y-4">
                    <div className="rounded-xl bg-bg-elevated p-4 border border-border-default">
                      <p className="text-sm text-text-secondary leading-relaxed">
                        Connect your <span className="font-semibold text-text-primary">Zotero library</span>.
                        Get your API key at{' '}
                        <a
                          href="https://www.zotero.org/settings/keys"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-accent-primary hover:underline inline-flex items-center gap-0.5"
                        >
                          zotero.org/settings/keys
                          <ArrowTopRightOnSquareIcon className="h-3 w-3" />
                        </a>{' '}
                        (enable "Allow library access").
                      </p>
                    </div>

                    {!zoteroValidated ? (
                      <div className="space-y-3">
                        <div>
                          <label className="block text-xs font-medium text-text-secondary mb-1.5">Zotero API Key</label>
                          <input
                            type="password"
                            value={zoteroKey}
                            onChange={e => setZoteroKey(e.target.value)}
                            placeholder="Paste your API key…"
                            disabled={zoteroValidating}
                            className="w-full px-3 py-2.5 bg-bg-void border border-border-default rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors font-mono text-sm"
                          />
                        </div>
                        <div className="flex gap-2">
                          <button
                            type="button"
                            onClick={handleClose}
                            disabled={zoteroValidating}
                            className="flex-1 px-4 py-2.5 border border-border-default text-text-secondary text-sm font-semibold rounded-lg hover:bg-bg-hover hover:border-accent-primary/30 hover:text-text-primary transition-all duration-150 disabled:opacity-50"
                          >
                            Cancel
                          </button>
                          <button
                            type="button"
                            onClick={handleZoteroValidate}
                            disabled={zoteroValidating || !zoteroKey.trim()}
                            className="flex-1 px-4 py-2.5 bg-accent-primary text-white text-sm font-semibold rounded-lg hover:bg-accent-hover transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                          >
                            {zoteroValidating ? (
                              <>
                                <span className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent" />
                                Connecting…
                              </>
                            ) : 'Connect Zotero'}
                          </button>
                        </div>
                      </div>
                    ) : (
                      <form onSubmit={handleZoteroImport} className="space-y-3">
                        <div className="flex items-center gap-2 text-xs text-success font-semibold">
                          <CheckIcon className="h-3.5 w-3.5" />
                          Connected as {zoteroUsername}
                        </div>
                        <div>
                          <label className="block text-xs font-medium text-text-secondary mb-1.5">
                            Collection <span className="text-text-muted font-mono">(optional)</span>
                          </label>
                          <select
                            value={zoteroSelectedCollection}
                            onChange={e => setZoteroSelectedCollection(e.target.value)}
                            disabled={loading}
                            className="w-full px-3 py-2.5 bg-bg-void border border-border-default rounded-lg text-text-primary focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors text-sm"
                          >
                            <option value="">Entire Library</option>
                            {zoteroCollections.map(col => (
                              <option key={col.key} value={col.key}>
                                {col.name} ({col.num_items} items)
                              </option>
                            ))}
                          </select>
                        </div>
                        <div className="flex gap-2 pt-1">
                          <button
                            type="button"
                            onClick={() => { setZoteroValidated(false); setZoteroCollections([]) }}
                            disabled={loading}
                            className="flex-1 px-4 py-2.5 border border-border-default text-text-secondary text-sm font-semibold rounded-lg hover:bg-bg-hover hover:border-accent-primary/30 hover:text-text-primary transition-all duration-150 disabled:opacity-50"
                          >
                            Change Key
                          </button>
                          <button
                            type="submit"
                            disabled={loading}
                            className="flex-1 px-4 py-2.5 bg-accent-primary text-white text-sm font-semibold rounded-lg hover:bg-accent-hover transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                          >
                            {loading ? (
                              <>
                                <span className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent" />
                                Importing…
                              </>
                            ) : 'Import from Zotero'}
                          </button>
                        </div>
                      </form>
                    )}
                  </div>
                )}

              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>

    <UploadSuccessModal
      isOpen={showSuccessModal}
      onClose={() => setShowSuccessModal(false)}
      uploadedCount={uploadedCount}
      documentTitles={uploadedTitles}
    />
    </>
  )
}

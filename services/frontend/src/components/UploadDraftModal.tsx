import { Fragment, useState, useRef, type FormEvent } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, DocumentArrowUpIcon, ShieldCheckIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import { getApiErrorDetail, getApiErrorDetailsList } from '../lib/apiErrors'
import { trackEvent } from '../lib/analytics'
import { validateFileSize, validateFileType, handleError, handleQuotaError } from '../lib/errorHandler'
import InlineAlert from './ui/InlineAlert'

const PAPER_TYPES = [
  { value: 'journal_article', label: 'Journal article' },
  { value: 'conference_paper', label: 'Conference paper' },
  { value: 'thesis', label: 'Thesis' },
  { value: 'dissertation', label: 'Dissertation' },
  { value: 'preprint', label: 'Preprint' },
]

const CITATION_STYLES = [
  { value: 'apa', label: 'APA' },
  { value: 'mla', label: 'MLA' },
  { value: 'chicago', label: 'Chicago' },
  { value: 'ieee', label: 'IEEE' },
  { value: 'vancouver', label: 'Vancouver' },
  { value: 'other', label: 'Other / mixed' },
]

interface UploadDraftModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  token: string
  projectId: string
  hasExistingDraft?: boolean
}

export default function UploadDraftModal({
  isOpen,
  onClose,
  onSuccess,
  token,
  projectId,
  hasExistingDraft = false,
}: UploadDraftModalProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [paperType, setPaperType] = useState('journal_article')
  const [citationStyle, setCitationStyle] = useState('apa')
  const [loading, setLoading] = useState(false)
  const [showPrivacyInfo, setShowPrivacyInfo] = useState(false)
  const [inlineError, setInlineError] = useState<{ title: string; message: string; details: string[] } | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const resetForm = () => {
    setSelectedFile(null)
    setTitle('')
    setPaperType('journal_article')
    setCitationStyle('apa')
    setShowPrivacyInfo(false)
    setInlineError(null)
    if (fileInputRef.current) {
      fileInputRef.current.value = ''
    }
  }

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      setInlineError(null)
      // Validate file type (PDF, DOCX, TXT)
      if (!validateFileType(file, ['pdf', 'docx', 'txt'])) {
        toast.error('Please select a PDF, DOCX, or TXT file')
        return
      }

      // Validate file size (100MB limit for drafts)
      if (!validateFileSize(file, 100)) {
        return
      }

      setSelectedFile(file)
      // Auto-fill title with filename (without extension)
      if (!title) {
        const fileName = file.name.replace(/\.(pdf|docx|txt)$/i, '')
        setTitle(fileName)
      }
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    if (!selectedFile) {
      toast.error('Please select a draft file')
      return
    }

    if (!title.trim()) {
      toast.error('Please provide a title for your draft')
      return
    }

    try {
      setInlineError(null)
      setLoading(true)

      const uploadResult = await api.drafts.upload(token, selectedFile, {
        project_id: projectId,
        title: title.trim(),
        paper_type: paperType,
        citation_style: citationStyle,
      })

      const draftId = uploadResult.draft.id

      // Track analytics
      trackEvent.draftUploaded(projectId, draftId)

      // Enhanced progress notification
      toast.success(
        hasExistingDraft
          ? 'New draft version uploaded. Analysis will complete in 2-3 minutes.'
          : 'Draft uploaded! Analysis will complete in 2-3 minutes. Citation suggestions will appear when ready.',
        { duration: 5000 }
      )

      // Reset form
      resetForm()

      onClose()
      onSuccess()
    } catch (error: unknown) {
      if (!handleQuotaError(error)) {
        const detail = getApiErrorDetail(error)
        setInlineError({
          title: detail?.title || 'Draft upload failed',
          message: detail?.message || 'We could not upload this draft.',
          details: getApiErrorDetailsList(detail),
        })
        handleError(error, 'uploading draft')
      }
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    if (!loading) {
      resetForm()
      onClose()
    }
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={handleClose}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-300"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-200"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" />
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
              <Dialog.Panel className="w-full max-w-lg transform overflow-hidden rounded-xl border border-border-default bg-bg-surface shadow-2xl transition-all">
                {/* Header */}
                <div className="border-b border-border-default px-5 py-4">
                  <div className="flex items-center justify-between">
                    <Dialog.Title className="text-base font-semibold text-text-primary">
                      {hasExistingDraft ? 'Upload New Version' : 'Upload Draft'}
                    </Dialog.Title>
                    <button
                      onClick={handleClose}
                      disabled={loading}
                      className="rounded-md p-1.5 text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
                    >
                      <XMarkIcon className="h-5 w-5" />
                    </button>
                  </div>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="space-y-4 p-5">
                  {inlineError && (
                    <InlineAlert
                      title={inlineError.title}
                      message={inlineError.message}
                      details={inlineError.details}
                    />
                  )}
                  {/* Privacy Notice */}
                  <div className="rounded-lg border border-border-default bg-bg-void/45 px-3 py-2.5">
                    <div className="flex items-start gap-2.5">
                      <ShieldCheckIcon className="mt-0.5 h-4 w-4 shrink-0 text-accent-primary" aria-hidden="true" />
                      <div className="min-w-0 flex-1">
                        <p className="text-xs font-semibold text-text-primary">Private by default</p>
                        <p className="mt-0.5 text-xs leading-5 text-text-secondary">
                          Files stay in your workspace and are not used to train models.
                        </p>
                        <button
                          type="button"
                          onClick={() => setShowPrivacyInfo(!showPrivacyInfo)}
                          className="mt-1 text-xs font-semibold text-accent-primary transition-colors duration-150 hover:text-accent-hover"
                        >
                          {showPrivacyInfo ? 'Hide details' : 'View details'}
                        </button>
                        {showPrivacyInfo && (
                          <div className="mt-2 space-y-1.5 border-t border-border-default pt-2 text-xs leading-5 text-text-secondary">
                            <p><strong className="text-text-primary">Database:</strong> Row-Level Security isolates data by user ID.</p>
                            <p><strong className="text-text-primary">AI Processing:</strong> Content is sent only to providers needed for analysis.</p>
                            <p><strong className="text-text-primary">Storage:</strong> Files are stored in private buckets with user-specific access controls.</p>
                          </div>
                        )}
                      </div>
                    </div>
                  </div>

                  {/* File Picker */}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label
                        htmlFor="draft-paper-type"
                        className="mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-text-secondary"
                      >
                        Paper Type
                      </label>
                      <select
                        id="draft-paper-type"
                        value={paperType}
                        onChange={(e) => setPaperType(e.target.value)}
                        disabled={loading}
                        className="w-full rounded-lg border border-border-default bg-bg-void px-3 py-2.5 text-sm text-text-primary transition-colors focus:border-accent-primary focus:ring-1 focus:ring-accent-primary"
                      >
                        {PAPER_TYPES.map((type) => (
                          <option key={type.value} value={type.value}>
                            {type.label}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label
                        htmlFor="draft-citation-style"
                        className="mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-text-secondary"
                      >
                        Citation Style
                      </label>
                      <select
                        id="draft-citation-style"
                        value={citationStyle}
                        onChange={(e) => setCitationStyle(e.target.value)}
                        disabled={loading}
                        className="w-full rounded-lg border border-border-default bg-bg-void px-3 py-2.5 text-sm text-text-primary transition-colors focus:border-accent-primary focus:ring-1 focus:ring-accent-primary"
                      >
                        {CITATION_STYLES.map((style) => (
                          <option key={style.value} value={style.value}>
                            {style.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <p className="-mt-2 text-xs font-medium text-text-secondary">
                    These answers tune the editing pass and reviewer expectations before analysis starts.
                  </p>

                  <div>
                    <label className="mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-text-secondary">
                      Draft File
                    </label>
                    <div className="flex items-center gap-3 rounded-xl border border-dashed border-border-default bg-bg-void/35 p-3 transition-colors hover:border-accent-primary/40 hover:bg-bg-hover">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                        onChange={handleFileSelect}
                        disabled={loading}
                        className="hidden"
                        id="draft-file-upload"
                      />
                      <label
                        htmlFor="draft-file-upload"
                        className="flex cursor-pointer items-center gap-2 rounded-md border border-border-default bg-bg-surface px-3 py-2 text-sm font-semibold text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary"
                      >
                        <DocumentArrowUpIcon className="h-4 w-4 text-text-secondary" />
                        <span>
                          {selectedFile ? 'Change File' : 'Choose File'}
                        </span>
                      </label>
                      {selectedFile && (
                        <span className="flex-1 truncate text-sm font-medium text-text-secondary">
                          {selectedFile.name}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 font-mono text-xs font-medium text-text-secondary">
                      PDF, DOCX, or TXT files, max 100MB
                    </p>
                  </div>

                  {/* Title */}
                  <div>
                    <label
                      htmlFor="draft-title"
                      className="mb-1.5 block text-xs font-bold uppercase tracking-[0.1em] text-text-secondary"
                    >
                      Title
                    </label>
                    <input
                      id="draft-title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full rounded-lg border border-border-default bg-bg-void px-3 py-2.5 text-sm text-text-primary transition-colors placeholder:text-text-muted focus:border-accent-primary focus:ring-1 focus:ring-accent-primary"
                      placeholder={hasExistingDraft ? 'My Research Draft v2' : 'My Research Draft'}
                      disabled={loading}
                      required
                    />
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 border-t border-border-default pt-4">
                    <button
                      type="button"
                      onClick={handleClose}
                      disabled={loading}
                      className="flex-1 rounded-md border border-border-default px-3 py-2 text-sm font-semibold text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !selectedFile || !title.trim()}
                      className="flex flex-1 items-center justify-center gap-2 rounded-md bg-accent-primary px-3 py-2 text-sm font-semibold text-white transition-all duration-150 hover:bg-accent-hover disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {loading ? (
                        <>
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                          Uploading...
                        </>
                      ) : (
                        hasExistingDraft ? 'Upload New Version' : 'Upload Draft'
                      )}
                    </button>
                  </div>
                </form>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

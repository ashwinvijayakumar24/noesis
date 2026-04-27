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
}

export default function UploadDraftModal({
  isOpen,
  onClose,
  onSuccess,
  token,
  projectId,
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
        'Draft uploaded! Analysis will complete in 2-3 minutes. Citation suggestions will appear when ready.',
        { duration: 5000 }
      )

      // Reset form
      resetForm()

      onClose()
      onSuccess()
    } catch (error: any) {
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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-lg bg-bg-surface border border-border-default shadow-xl transition-all">
                {/* Header */}
                <div className="px-6 py-5 border-b border-border-default">
                  <div className="flex items-center justify-between">
                    <Dialog.Title className="text-2xl font-sans font-semibold text-text-primary tracking-normal">
                      Upload Draft
                    </Dialog.Title>
                    <button
                      onClick={handleClose}
                      disabled={loading}
                      className="text-text-tertiary hover:text-accent-primary hover:bg-accent-light rounded-md p-2 transition-all duration-150"
                    >
                      <XMarkIcon className="h-6 w-6" />
                    </button>
                  </div>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="p-6 space-y-5">
                  {inlineError && (
                    <InlineAlert
                      title={inlineError.title}
                      message={inlineError.message}
                      details={inlineError.details}
                    />
                  )}
                  {/* Privacy Notice */}
                  <div className="mb-4 rounded-md bg-bg-elevated p-4 border border-border-default">
                    <div className="flex">
                      <div className="flex-shrink-0">
                        <ShieldCheckIcon className="h-5 w-5 text-teal-primary" aria-hidden="true" />
                      </div>
                      <div className="ml-3 flex-1">
                        <h3 className="text-sm font-medium text-text-primary tracking-normal">
                          Your research is private and secure
                        </h3>
                        <div className="mt-2 text-sm text-text-secondary tracking-normal">
                          <ul className="list-disc space-y-1 pl-5">
                            <li>Your drafts are never shared with other users</li>
                            <li>Your files stay inside your workspace by default</li>
                            <li>Your work is isolated to your account only</li>
                            <li>No data is used for model training or indexing</li>
                          </ul>
                          <button
                            type="button"
                            onClick={() => setShowPrivacyInfo(!showPrivacyInfo)}
                            className="mt-2 text-sm font-medium text-accent-primary hover:text-accent-hover transition-colors duration-150"
                          >
                            {showPrivacyInfo ? 'Hide details' : 'Learn more about our privacy practices'}
                          </button>
                          {showPrivacyInfo && (
                            <div className="mt-3 text-xs text-text-tertiary tracking-normal space-y-2 border-t border-border-default pt-2">
                              <p><strong>Database Security:</strong> Row-Level Security ensures your data is isolated by user ID.</p>
                              <p><strong>AI Processing:</strong> Your content is sent only to the providers needed to run analysis, and it is not used to train models.</p>
                              <p><strong>Storage:</strong> Files are stored in private buckets with user-specific access controls.</p>
                              <p><strong>No Internal Reuse:</strong> Noesis does not cross-reference your work with other projects or users.</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  <p className="text-xs text-text-muted">
                    Private by default. Your files stay in your workspace and are not used to train models.
                  </p>

                  {/* File Picker */}
                  <div className="grid gap-4 sm:grid-cols-2">
                    <div>
                      <label
                        htmlFor="draft-paper-type"
                        className="block text-sm font-medium text-text-secondary mb-2 tracking-normal"
                      >
                        Paper Type
                      </label>
                      <select
                        id="draft-paper-type"
                        value={paperType}
                        onChange={(e) => setPaperType(e.target.value)}
                        disabled={loading}
                        className="w-full px-4 py-3 bg-bg-surface border border-border-default rounded-md text-text-primary focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors tracking-normal"
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
                        className="block text-sm font-medium text-text-secondary mb-2 tracking-normal"
                      >
                        Citation Style
                      </label>
                      <select
                        id="draft-citation-style"
                        value={citationStyle}
                        onChange={(e) => setCitationStyle(e.target.value)}
                        disabled={loading}
                        className="w-full px-4 py-3 bg-bg-surface border border-border-default rounded-md text-text-primary focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors tracking-normal"
                      >
                        {CITATION_STYLES.map((style) => (
                          <option key={style.value} value={style.value}>
                            {style.label}
                          </option>
                        ))}
                      </select>
                    </div>
                  </div>

                  <p className="text-xs text-text-muted -mt-2">
                    These answers tune the editing pass and reviewer expectations before analysis starts.
                  </p>

                  <div>
                    <label className="block text-sm font-medium text-text-secondary mb-2 tracking-normal">
                      Draft File
                    </label>
                    <div className="flex items-center gap-3">
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
                        className="flex items-center gap-2 px-4 py-3 border border-border-default rounded-md hover:border-accent-primary/30 hover:bg-bg-hover transition-all duration-150 cursor-pointer disabled:opacity-50"
                      >
                        <DocumentArrowUpIcon className="h-5 w-5 text-text-tertiary" />
                        <span className="text-sm text-text-secondary font-medium tracking-normal">
                          {selectedFile ? 'Change File' : 'Choose File'}
                        </span>
                      </label>
                      {selectedFile && (
                        <span className="text-sm text-text-tertiary truncate flex-1 tracking-normal">
                          {selectedFile.name}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-xs font-mono text-text-muted">
                      PDF, DOCX, or TXT files, max 100MB
                    </p>
                  </div>

                  {/* Title */}
                  <div>
                    <label
                      htmlFor="draft-title"
                      className="block text-sm font-medium text-text-secondary mb-2 tracking-normal"
                    >
                      Title
                    </label>
                    <input
                      id="draft-title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-4 py-3 bg-bg-surface border border-border-default rounded-md text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors tracking-normal"
                      placeholder="My Research Draft v1"
                      disabled={loading}
                      required
                    />
                  </div>

                  {/* Actions */}
                  <div className="flex gap-3 pt-2">
                    <button
                      type="button"
                      onClick={handleClose}
                      disabled={loading}
                      className="flex-1 px-4 py-3 border border-border-default text-text-secondary font-medium rounded-md hover:border-accent-primary/30 hover:text-text-primary hover:bg-bg-hover transition-all duration-150 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !selectedFile || !title.trim()}
                      className="flex-1 px-4 py-3 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {loading ? (
                        <>
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                          Uploading...
                        </>
                      ) : (
                        'Upload Draft'
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

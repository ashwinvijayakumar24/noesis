import { Fragment, useState, useRef, type FormEvent } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, DocumentArrowUpIcon, ShieldCheckIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import { trackEvent } from '../lib/analytics'
import { validateFileSize, validateFileType, handleError } from '../lib/errorHandler'

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
  const [loading, setLoading] = useState(false)
  const [showPrivacyInfo, setShowPrivacyInfo] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
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
      setLoading(true)

      const uploadResult = await api.drafts.upload(token, selectedFile, {
        project_id: projectId,
        title: title.trim(),
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
      setSelectedFile(null)
      setTitle('')
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }

      onClose()
      onSuccess()
    } catch (error: any) {
      handleError(error, 'uploading draft')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    if (!loading) {
      setSelectedFile(null)
      setTitle('')
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-xl bg-surface border border-border-base shadow-xl transition-all">
                {/* Header */}
                <div className="px-6 py-5 border-b border-border-subtle">
                  <div className="flex items-center justify-between">
                    <Dialog.Title className="text-2xl font-serif font-semibold text-text-primary">
                      Upload Draft
                    </Dialog.Title>
                    <button
                      onClick={handleClose}
                      disabled={loading}
                      className="text-text-tertiary hover:text-text-primary transition-colors"
                    >
                      <XMarkIcon className="h-6 w-6" />
                    </button>
                  </div>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="p-6 space-y-5">
                  {/* Privacy Notice */}
                  <div className="mb-4 rounded-md bg-blue-50 p-4 border border-blue-200">
                    <div className="flex">
                      <div className="flex-shrink-0">
                        <ShieldCheckIcon className="h-5 w-5 text-blue-400" aria-hidden="true" />
                      </div>
                      <div className="ml-3 flex-1">
                        <h3 className="text-sm font-medium text-blue-800">
                          Your research is private and secure
                        </h3>
                        <div className="mt-2 text-sm text-blue-700">
                          <ul className="list-disc space-y-1 pl-5">
                            <li>Your drafts are never shared with other users</li>
                            <li>AI analysis uses zero data retention (OpenAI does not store your content)</li>
                            <li>Your work is isolated to your account only</li>
                            <li>No data is used for model training or indexing</li>
                          </ul>
                          <button
                            type="button"
                            onClick={() => setShowPrivacyInfo(!showPrivacyInfo)}
                            className="mt-2 text-sm font-medium text-blue-600 hover:text-blue-500"
                          >
                            {showPrivacyInfo ? 'Hide details' : 'Learn more about our privacy practices'}
                          </button>
                          {showPrivacyInfo && (
                            <div className="mt-3 text-xs text-blue-600 space-y-2 border-t border-blue-200 pt-2">
                              <p><strong>Database Security:</strong> Row-Level Security ensures your data is isolated by user ID.</p>
                              <p><strong>AI Processing:</strong> We use OpenAI's API with zero data retention enabled. Your content is processed but never stored by OpenAI.</p>
                              <p><strong>Storage:</strong> Files are stored in private buckets with user-specific access controls.</p>
                              <p><strong>No Internal Reuse:</strong> Noesis does not cross-reference your work with other projects or users.</p>
                            </div>
                          )}
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* File Picker */}
                  <div>
                    <label className="block text-sm font-medium text-text-secondary mb-2">
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
                        className="flex items-center gap-2 px-4 py-3 border border-border-base rounded-lg hover:border-border-subtle transition-colors cursor-pointer disabled:opacity-50"
                      >
                        <DocumentArrowUpIcon className="h-5 w-5 text-text-tertiary" />
                        <span className="text-sm text-text-secondary font-medium">
                          {selectedFile ? 'Change File' : 'Choose File'}
                        </span>
                      </label>
                      {selectedFile && (
                        <span className="text-sm text-text-tertiary truncate flex-1">
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
                      className="block text-sm font-medium text-text-secondary mb-2"
                    >
                      Title
                    </label>
                    <input
                      id="draft-title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-4 py-3 bg-bg-base border border-border-base rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
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
                      className="flex-1 px-4 py-3 border border-border-base text-text-secondary font-medium rounded-lg hover:border-border-subtle hover:text-text-primary transition-colors disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !selectedFile || !title.trim()}
                      className="flex-1 px-4 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
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

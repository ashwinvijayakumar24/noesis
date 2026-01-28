import { Fragment, useState, useRef, type FormEvent } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, DocumentArrowUpIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import { trackEvent } from '../lib/analytics'
import { validateFileSize, validateFileType, handleError } from '../lib/errorHandler'
import UploadSuccessModal from './UploadSuccessModal'

interface UploadDocumentModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  token: string
  projectId: string
}

export default function UploadDocumentModal({
  isOpen,
  onClose,
  onSuccess,
  token,
  projectId,
}: UploadDocumentModalProps) {
  const [selectedFile, setSelectedFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [uploadedDocTitle, setUploadedDocTitle] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (file) {
      // Validate file type
      if (!validateFileType(file, ['pdf'])) {
        return
      }

      // Validate file size (50MB limit)
      if (!validateFileSize(file, 50)) {
        return
      }

      setSelectedFile(file)
      // Auto-fill title with filename (without .pdf extension)
      if (!title) {
        setTitle(file.name.replace('.pdf', ''))
      }
    }
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    if (!selectedFile) {
      toast.error('Please select a PDF file')
      return
    }

    try {
      setLoading(true)

      const uploadResult = await api.documents.upload(token, selectedFile, {
        project_id: projectId,
        title: title.trim() || undefined,
        description: description.trim() || undefined,
      })

      const documentId = uploadResult.document.id
      const docTitle = uploadResult.document.title
      console.log('[UPLOAD] Document uploaded successfully, ID:', documentId)

      // Track analytics
      trackEvent.documentUploaded(projectId, documentId)

      // Auto-trigger RAG ingestion asynchronously (don't block the UI)
      console.log('[UPLOAD] Triggering RAG ingestion for document:', documentId)
      api.rag.ingest(token, documentId).catch((ingestError: any) => {
        console.error('[UPLOAD] RAG ingestion failed:', ingestError)
      })

      // Auto-trigger document analysis after a brief delay (500ms) to avoid race condition with RAG
      // This ensures RAG has set initial status before analysis starts
      console.log('[UPLOAD] Scheduling document analysis for document:', documentId)
      setTimeout(() => {
        console.log('[UPLOAD] Auto-triggering document analysis for document:', documentId)
        api.documents.analyze(token, documentId)
          .then((analyzeResult) => {
            console.log('[UPLOAD] ✓ Document analysis triggered successfully!', analyzeResult)
          })
          .catch((analysisError: any) => {
            console.error('[UPLOAD] ✗ Document analysis failed to trigger:', analysisError)
            toast.error('Analysis failed to start automatically. Please refresh the page.', { duration: 6000 })
          })
      }, 500)

      // Reset form
      setSelectedFile(null)
      setTitle('')
      setDescription('')
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }

      // Close upload modal and show success modal
      onClose()
      setUploadedDocTitle(docTitle)
      setShowSuccessModal(true)
      onSuccess()
    } catch (error: any) {
      handleError(error, 'uploading document')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    if (!loading) {
      setSelectedFile(null)
      setTitle('')
      setDescription('')
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }
      onClose()
    }
  }

  return (
    <>
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
                      Upload Document
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
                  {/* File Picker */}
                  <div>
                    <label className="block text-sm font-medium text-text-secondary mb-2">
                      PDF File
                    </label>
                    <div className="flex items-center gap-3">
                      <input
                        ref={fileInputRef}
                        type="file"
                        accept="application/pdf,.pdf"
                        onChange={handleFileSelect}
                        disabled={loading}
                        className="hidden"
                        id="file-upload"
                      />
                      <label
                        htmlFor="file-upload"
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
                      PDF files only, max 50MB
                    </p>
                  </div>

                  {/* Title */}
                  <div>
                    <label
                      htmlFor="title"
                      className="block text-sm font-medium text-text-secondary mb-2"
                    >
                      Title <span className="text-text-muted font-mono text-xs">(optional)</span>
                    </label>
                    <input
                      id="title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-4 py-3 bg-bg-base border border-border-base rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                      placeholder="Defaults to filename"
                      disabled={loading}
                    />
                  </div>

                  {/* Description */}
                  <div>
                    <label
                      htmlFor="description"
                      className="block text-sm font-medium text-text-secondary mb-2"
                    >
                      Description <span className="text-text-muted font-mono text-xs">(optional)</span>
                    </label>
                    <textarea
                      id="description"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={3}
                      className="w-full px-4 py-3 bg-bg-base border border-border-base rounded-lg text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors resize-none"
                      placeholder="Add notes about this document..."
                      disabled={loading}
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
                      disabled={loading || !selectedFile}
                      className="flex-1 px-4 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                    >
                      {loading ? (
                        <>
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                          Uploading...
                        </>
                      ) : (
                        'Upload Document'
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

    {/* Success Modal - shown after upload completes */}
    <UploadSuccessModal
      isOpen={showSuccessModal}
      onClose={() => setShowSuccessModal(false)}
      documentTitle={uploadedDocTitle}
    />
    </>
  )
}

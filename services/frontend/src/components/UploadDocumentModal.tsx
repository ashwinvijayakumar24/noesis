import { Fragment, useState, useRef, type FormEvent } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, DocumentArrowUpIcon, LockClosedIcon } from '@heroicons/react/24/outline'
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
  const [isDragging, setIsDragging] = useState(false)
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

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault()
    e.stopPropagation()
    if (!loading) {
      setIsDragging(true)
    }
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

    const file = e.dataTransfer.files?.[0]
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
      setIsDragging(false)
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
      setIsDragging(false)
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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-lg bg-bg-surface border border-border-default shadow-xl transition-all">
                {/* Header */}
                <div className="px-6 py-5 border-b border-border-default">
                  <div className="flex items-center justify-between">
                    <Dialog.Title className="text-2xl font-sans font-semibold text-text-primary tracking-normal">
                      Upload Document
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
                  {/* Privacy Notice */}
                  <div className="mb-4 rounded-md bg-bg-elevated p-4 border border-border-default">
                    <div className="flex">
                      <div className="flex-shrink-0">
                        <LockClosedIcon className="h-5 w-5 text-teal-primary" aria-hidden="true" />
                      </div>
                      <div className="ml-3 flex-1">
                        <h3 className="text-sm font-medium text-text-primary tracking-normal">
                          Private literature library
                        </h3>
                        <p className="mt-1 text-sm text-text-secondary tracking-normal leading-relaxed">
                          Your uploaded papers are private to your account and project. They're used only for your research analysis and are never shared with other users or used for training AI models.
                        </p>
                      </div>
                    </div>
                  </div>

                  {/* File Picker with Drag & Drop */}
                  <div>
                    <label className="block text-sm font-medium text-text-secondary mb-2 tracking-normal">
                      PDF File
                    </label>
                    <div
                      onDragOver={handleDragOver}
                      onDragLeave={handleDragLeave}
                      onDrop={handleDrop}
                      className={`
                        relative border-2 border-dashed rounded-md p-6 transition-all duration-150
                        ${isDragging
                          ? 'border-accent-primary bg-accent-light/30'
                          : 'border-border-default hover:border-accent-primary/30'
                        }
                        ${loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}
                      `}
                    >
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
                        className="flex flex-col items-center gap-2 cursor-pointer"
                      >
                        <DocumentArrowUpIcon className={`h-10 w-10 ${isDragging ? 'text-accent-primary' : 'text-text-tertiary'}`} />
                        {selectedFile ? (
                          <div className="text-center">
                            <p className="text-sm text-text-primary font-medium tracking-normal">
                              {selectedFile.name}
                            </p>
                            <p className="text-xs text-text-muted mt-1 tracking-normal">
                              Click or drag to change file
                            </p>
                          </div>
                        ) : (
                          <div className="text-center">
                            <p className="text-sm text-text-secondary font-medium tracking-normal">
                              {isDragging ? 'Drop file here' : 'Drag & drop or click to browse'}
                            </p>
                            <p className="text-xs font-mono text-text-muted mt-1">
                              PDF files only, max 50MB
                            </p>
                          </div>
                        )}
                      </label>
                    </div>
                  </div>

                  {/* Title */}
                  <div>
                    <label
                      htmlFor="title"
                      className="block text-sm font-medium text-text-secondary mb-2 tracking-normal"
                    >
                      Title <span className="text-text-muted font-mono text-xs">(optional)</span>
                    </label>
                    <input
                      id="title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-4 py-3 bg-bg-surface border border-border-default rounded-md text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors tracking-normal"
                      placeholder="Defaults to filename"
                      disabled={loading}
                    />
                  </div>

                  {/* Description */}
                  <div>
                    <label
                      htmlFor="description"
                      className="block text-sm font-medium text-text-secondary mb-2 tracking-normal"
                    >
                      Description <span className="text-text-muted font-mono text-xs">(optional)</span>
                    </label>
                    <textarea
                      id="description"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={3}
                      className="w-full px-4 py-3 bg-bg-surface border border-border-default rounded-md text-text-primary placeholder-text-muted focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors resize-none tracking-normal"
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
                      className="flex-1 px-4 py-3 border border-border-default text-text-secondary font-medium rounded-md hover:border-accent-primary/30 hover:text-text-primary hover:bg-bg-hover transition-all duration-150 disabled:opacity-50 tracking-normal"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={loading || !selectedFile}
                      className="flex-1 px-4 py-3 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 tracking-normal"
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

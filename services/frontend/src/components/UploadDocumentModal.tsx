import { Fragment, useState, useRef, type FormEvent } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, DocumentArrowUpIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import { trackEvent } from '../lib/analytics'
import { validateFileSize, validateFileType, handleError } from '../lib/errorHandler'

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

      // Track analytics
      trackEvent.documentUploaded(projectId, documentId)

      // Auto-trigger RAG ingestion asynchronously (don't block the UI)
      api.rag.ingest(token, documentId).catch((ingestError: any) => {
        console.error('RAG ingestion failed:', ingestError)
      })

      toast.success('Document uploaded! Processing will complete in ~10-30 seconds.')

      // Reset form
      setSelectedFile(null)
      setTitle('')
      setDescription('')
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }

      onClose()
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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-lg bg-neutral-900 border border-neutral-800 p-6 shadow-xl transition-all">
                {/* Header */}
                <div className="flex items-center justify-between mb-6">
                  <Dialog.Title className="text-2xl font-serif font-semibold text-neutral-50">
                    Upload Document
                  </Dialog.Title>
                  <button
                    onClick={handleClose}
                    disabled={loading}
                    className="text-neutral-400 hover:text-neutral-200 transition-colors"
                  >
                    <XMarkIcon className="h-6 w-6" />
                  </button>
                </div>

                {/* Form */}
                <form onSubmit={handleSubmit} className="space-y-5">
                  {/* File Picker */}
                  <div>
                    <label className="block text-sm font-medium text-neutral-300 mb-2">
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
                        className="flex items-center gap-2 px-4 py-3 border border-neutral-700 rounded-lg hover:border-neutral-600 transition-colors cursor-pointer disabled:opacity-50"
                      >
                        <DocumentArrowUpIcon className="h-5 w-5 text-neutral-400" />
                        <span className="text-sm text-neutral-300 font-medium">
                          {selectedFile ? 'Change File' : 'Choose File'}
                        </span>
                      </label>
                      {selectedFile && (
                        <span className="text-sm text-neutral-400 truncate flex-1">
                          {selectedFile.name}
                        </span>
                      )}
                    </div>
                    <p className="mt-2 text-xs font-mono text-neutral-500">
                      PDF files only, max 50MB
                    </p>
                  </div>

                  {/* Title */}
                  <div>
                    <label
                      htmlFor="title"
                      className="block text-sm font-medium text-neutral-300 mb-2"
                    >
                      Title <span className="text-neutral-500 font-mono text-xs">(optional)</span>
                    </label>
                    <input
                      id="title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                      placeholder="Defaults to filename"
                      disabled={loading}
                    />
                  </div>

                  {/* Description */}
                  <div>
                    <label
                      htmlFor="description"
                      className="block text-sm font-medium text-neutral-300 mb-2"
                    >
                      Description <span className="text-neutral-500 font-mono text-xs">(optional)</span>
                    </label>
                    <textarea
                      id="description"
                      value={description}
                      onChange={(e) => setDescription(e.target.value)}
                      rows={3}
                      className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors resize-none"
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
                      className="flex-1 px-4 py-3 border border-neutral-700 text-neutral-300 font-medium rounded-lg hover:border-neutral-600 hover:text-neutral-50 transition-colors disabled:opacity-50"
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
  )
}

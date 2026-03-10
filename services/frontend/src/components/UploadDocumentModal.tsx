import { Fragment, useState, useRef, type FormEvent } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, DocumentArrowUpIcon, LockClosedIcon, ArrowUpTrayIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import { trackEvent } from '../lib/analytics'
import { validateFileSize, validateFileType, handleError, handleQuotaError } from '../lib/errorHandler'
import UploadSuccessModal from './UploadSuccessModal'

type TabId = 'pdf' | 'bibtex'

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
  const [activeTab, setActiveTab] = useState<TabId>('pdf')
  const [selectedFiles, setSelectedFiles] = useState<File[]>([])
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)
  const [showSuccessModal, setShowSuccessModal] = useState(false)
  const [uploadedCount, setUploadedCount] = useState(0)
  const [uploadedTitles, setUploadedTitles] = useState<string[]>([])
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef<HTMLInputElement>(null)
  const [bibtexFile, setBibtexFile] = useState<File | null>(null)
  const bibtexInputRef = useRef<HTMLInputElement>(null)

  const MAX_FILES = 10
  const MAX_SIZE_MB = 50

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (!e.target.files) return

    const filesArray = Array.from(e.target.files)

    // Validate file count
    if (filesArray.length > MAX_FILES) {
      toast.error(`Maximum ${MAX_FILES} files allowed per upload`)
      return
    }

    // Validate each file
    const validFiles: File[] = []
    for (const file of filesArray) {
      // Validate file type
      if (!validateFileType(file, ['pdf'])) {
        continue
      }

      // Validate file size
      if (!validateFileSize(file, MAX_SIZE_MB)) {
        continue
      }

      validFiles.push(file)
    }

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

    const filesArray = Array.from(e.dataTransfer.files)

    // Validate file count
    if (filesArray.length > MAX_FILES) {
      toast.error(`Maximum ${MAX_FILES} files allowed per upload`)
      return
    }

    // Filter and validate files
    const validFiles = filesArray.filter(file => {
      // Check file type
      if (file.type !== 'application/pdf') {
        return false
      }

      // Check file size (in bytes: 50MB = 50 * 1024 * 1024)
      if (file.size > MAX_SIZE_MB * 1024 * 1024) {
        toast.error(`${file.name} exceeds ${MAX_SIZE_MB}MB limit`)
        return false
      }

      return true
    })

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

      console.log(`[UPLOAD] Uploading ${selectedFiles.length} document(s)...`)

      // Upload all files in parallel
      const uploadPromises = selectedFiles.map(file =>
        api.documents.upload(token, file, {
          project_id: projectId,
          title: file.name.replace('.pdf', ''),
          description: description.trim() || undefined,
        })
      )

      const uploadResults = await Promise.all(uploadPromises)
      console.log(`[UPLOAD] ✓ All ${uploadResults.length} documents uploaded successfully`)

      // Track analytics for each upload
      uploadResults.forEach(result => {
        trackEvent.documentUploaded(projectId, result.document.id)
      })

      // Trigger RAG ingestion for all documents in parallel
      const ingestPromises = uploadResults.map(result => {
        console.log('[UPLOAD] Triggering RAG ingestion for document:', result.document.id)
        return api.rag.ingest(token, result.document.id).catch((ingestError: any) => {
          console.error('[UPLOAD] RAG ingestion failed for document:', result.document.id, ingestError)
        })
      })

      // Fire-and-forget for ingestion (don't wait)
      Promise.allSettled(ingestPromises)

      // Collect titles for success modal
      const titles = uploadResults.map(r => r.document.title)

      // Reset form
      setSelectedFiles([])
      setDescription('')
      setIsDragging(false)
      if (fileInputRef.current) {
        fileInputRef.current.value = ''
      }

      // Close upload modal and show success modal
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

  const handleBibtexSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!bibtexFile) {
      toast.error('Please select a .bib file')
      return
    }
    try {
      setLoading(true)
      const result = await api.documents.importBibtex(token, projectId, bibtexFile)
      setBibtexFile(null)
      if (bibtexInputRef.current) bibtexInputRef.current.value = ''
      onClose()
      onSuccess()
      setUploadedCount(result.imported)
      setUploadedTitles([])
      setShowSuccessModal(true)
      toast.success(`Imported ${result.imported} references from BibTeX file`)
    } catch (error: any) {
      handleError(error, 'importing BibTeX file')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    if (!loading) {
      setSelectedFiles([])
      setDescription('')
      setIsDragging(false)
      setBibtexFile(null)
      if (fileInputRef.current) fileInputRef.current.value = ''
      if (bibtexInputRef.current) bibtexInputRef.current.value = ''
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
                      Add Documents
                    </Dialog.Title>
                    <button
                      onClick={handleClose}
                      disabled={loading}
                      className="text-text-tertiary hover:text-accent-primary hover:bg-accent-light rounded-md p-2 transition-all duration-150"
                    >
                      <XMarkIcon className="h-6 w-6" />
                    </button>
                  </div>
                  {/* Tab switcher */}
                  <div className="flex gap-1 mt-4 bg-bg-elevated rounded-lg p-1 border border-border-default">
                    <button
                      type="button"
                      onClick={() => setActiveTab('pdf')}
                      className={`flex-1 py-2 px-3 rounded-md text-sm font-semibold transition-all duration-150 ${
                        activeTab === 'pdf'
                          ? 'bg-bg-surface text-text-primary border border-border-default shadow-xs'
                          : 'text-text-muted hover:text-text-secondary'
                      }`}
                    >
                      Upload PDF
                    </button>
                    <button
                      type="button"
                      onClick={() => setActiveTab('bibtex')}
                      className={`flex-1 py-2 px-3 rounded-md text-sm font-semibold transition-all duration-150 ${
                        activeTab === 'bibtex'
                          ? 'bg-bg-surface text-text-primary border border-border-default shadow-xs'
                          : 'text-text-muted hover:text-text-secondary'
                      }`}
                    >
                      Import from Zotero (.bib)
                    </button>
                  </div>
                </div>

                {/* BibTeX Import Tab */}
                {activeTab === 'bibtex' && (
                  <form onSubmit={handleBibtexSubmit} className="p-6 space-y-5">
                    <div className="rounded-md bg-bg-elevated p-4 border border-border-default">
                      <p className="text-sm text-text-secondary leading-relaxed">
                        Export your library from <span className="font-semibold text-text-primary">Zotero, Mendeley, or Endnote</span> as a .bib file, then import it here. All references are added instantly — no PDF required.
                      </p>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-2">
                        BibTeX File (.bib)
                      </label>
                      <div
                        className={`relative border-2 border-dashed rounded-md p-6 transition-all duration-150 ${
                          bibtexFile ? 'border-accent-primary/50 bg-accent-light/10' : 'border-border-default hover:border-accent-primary/30'
                        } ${loading ? 'opacity-50 cursor-not-allowed' : 'cursor-pointer'}`}
                      >
                        <input
                          ref={bibtexInputRef}
                          type="file"
                          accept=".bib"
                          onChange={(e) => setBibtexFile(e.target.files?.[0] || null)}
                          disabled={loading}
                          className="hidden"
                          id="bibtex-upload"
                        />
                        <label htmlFor="bibtex-upload" className="flex flex-col items-center gap-2 cursor-pointer">
                          <ArrowUpTrayIcon className={`h-10 w-10 ${bibtexFile ? 'text-accent-primary' : 'text-text-tertiary'}`} />
                          {bibtexFile ? (
                            <div className="text-center">
                              <p className="text-sm text-text-primary font-medium">{bibtexFile.name}</p>
                              <p className="text-xs text-text-muted font-mono mt-1">Click to change file</p>
                            </div>
                          ) : (
                            <div className="text-center">
                              <p className="text-sm text-text-secondary font-medium">Click to select .bib file</p>
                              <p className="text-xs font-mono text-text-muted mt-1">Exports from Zotero, Mendeley, Endnote</p>
                            </div>
                          )}
                        </label>
                      </div>
                    </div>
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
                        disabled={loading || !bibtexFile}
                        className="flex-1 px-4 py-3 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
                      >
                        {loading ? (
                          <>
                            <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent" />
                            Importing...
                          </>
                        ) : 'Import References'}
                      </button>
                    </div>
                  </form>
                )}

                {/* PDF Upload Tab */}
                {activeTab === 'pdf' && (
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
                        multiple
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
                        {selectedFiles.length > 0 ? (
                          <div className="text-center">
                            <p className="text-sm text-text-primary font-medium tracking-normal">
                              {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''} selected
                            </p>
                            <p className="text-xs text-text-muted mt-1 tracking-normal">
                              Click or drag to change files
                            </p>
                          </div>
                        ) : (
                          <div className="text-center">
                            <p className="text-sm text-text-secondary font-medium tracking-normal">
                              {isDragging ? 'Drop files here' : 'Drag & drop or click to browse'}
                            </p>
                            <p className="text-xs font-mono text-text-muted mt-1">
                              PDF files only, max {MAX_SIZE_MB}MB each, up to {MAX_FILES} files
                            </p>
                          </div>
                        )}
                      </label>
                    </div>
                  </div>

                  {/* Selected Files List */}
                  {selectedFiles.length > 0 && (
                    <div>
                      <label className="block text-sm font-medium text-text-secondary mb-2 tracking-normal">
                        Selected Files
                      </label>
                      <div className="space-y-2 max-h-48 overflow-y-auto bg-bg-elevated border border-border-default rounded-md p-3">
                        {selectedFiles.map((file, index) => (
                          <div
                            key={index}
                            className="flex items-center justify-between gap-3 p-2 bg-bg-surface border border-border-default rounded-md group hover:border-accent-primary/30 transition-colors"
                          >
                            <div className="flex-1 min-w-0">
                              <p className="text-sm text-text-primary font-medium truncate tracking-normal">
                                {file.name}
                              </p>
                              <p className="text-xs text-text-muted font-mono">
                                {(file.size / (1024 * 1024)).toFixed(2)} MB
                              </p>
                            </div>
                            <button
                              type="button"
                              onClick={() => removeFile(index)}
                              disabled={loading}
                              className="flex-shrink-0 text-text-muted hover:text-red-500 transition-colors p-1"
                            >
                              <XMarkIcon className="h-5 w-5" />
                            </button>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

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
                      disabled={loading || selectedFiles.length === 0}
                      className="flex-1 px-4 py-3 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 tracking-normal"
                    >
                      {loading ? (
                        <>
                          <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                          Uploading {selectedFiles.length} file{selectedFiles.length > 1 ? 's' : ''}...
                        </>
                      ) : (
                        <>
                          Upload {selectedFiles.length > 0 ? `${selectedFiles.length} ` : ''}Document{selectedFiles.length > 1 ? 's' : ''}
                        </>
                      )}
                    </button>
                  </div>
                </form>
                )}
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
      uploadedCount={uploadedCount}
      documentTitles={uploadedTitles}
    />
    </>
  )
}

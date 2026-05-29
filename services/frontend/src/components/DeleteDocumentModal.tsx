import { Fragment, useState } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'

interface DeleteDocumentModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  token: string
  documentId: string
  documentTitle: string
}

export default function DeleteDocumentModal({
  isOpen,
  onClose,
  onSuccess,
  token,
  documentId,
  documentTitle,
}: DeleteDocumentModalProps) {
  const [loading, setLoading] = useState(false)

  const handleDelete = async () => {
    try {
      setLoading(true)
      await api.documents.delete(token, documentId)
      toast.success('Document deleted successfully')
      onClose()
      onSuccess()
    } catch (error: any) {
      console.error('Failed to delete document:', error)
      toast.error(error.message || 'Failed to delete document')
    } finally {
      setLoading(false)
    }
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={onClose}>
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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-xl border border-border-default bg-bg-surface shadow-2xl transition-all">
                {/* Header */}
                <div className="border-b border-border-default px-5 py-4">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className="shrink-0">
                        <ExclamationTriangleIcon className="h-5 w-5 text-error" />
                      </div>
                      <div>
                        <Dialog.Title className="text-base font-semibold text-text-primary">
                          Delete Document
                        </Dialog.Title>
                      </div>
                    </div>
                    <button
                      onClick={onClose}
                      disabled={loading}
                      className="rounded-md p-1.5 text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
                    >
                      <XMarkIcon className="h-5 w-5" />
                    </button>
                  </div>
                </div>

                {/* Content */}
                <div className="p-5">
                  <div className="mb-5">
                    <p className="mb-2 text-sm font-medium text-text-secondary">
                      Are you sure you want to delete{' '}
                      <span className="font-semibold text-text-primary">{documentTitle}</span>?
                    </p>
                    <p className="text-sm leading-6 text-text-secondary">
                      This will permanently delete the document, its file, and all associated
                      embeddings. This action cannot be undone.
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-2 border-t border-border-default pt-4">
                    <button
                      type="button"
                      onClick={onClose}
                      disabled={loading}
                      className="flex-1 rounded-md border border-border-default px-3 py-2 text-sm font-semibold text-text-secondary transition-all duration-150 hover:bg-bg-hover hover:text-text-primary disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleDelete}
                      disabled={loading}
                      className="flex-1 rounded-md bg-error px-3 py-2 text-sm font-semibold text-white transition-all duration-150 hover:bg-error/90 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                      {loading ? 'Deleting...' : 'Delete Document'}
                    </button>
                  </div>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

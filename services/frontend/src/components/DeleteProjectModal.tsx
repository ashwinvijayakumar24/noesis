import { Fragment, useState } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { ExclamationTriangleIcon, XMarkIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import { trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'

interface DeleteProjectModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  token: string
  projectId: string
  projectTitle: string
}

export default function DeleteProjectModal({
  isOpen,
  onClose,
  onSuccess,
  token,
  projectId,
  projectTitle,
}: DeleteProjectModalProps) {
  const [loading, setLoading] = useState(false)

  const handleDelete = async () => {
    try {
      setLoading(true)
      await api.projects.delete(token, projectId)
      trackEvent.projectDeleted(projectId)
      toast.success('Project deleted successfully')
      onClose()
      onSuccess()
    } catch (error: any) {
      handleError(error, 'deleting project')
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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-lg bg-bg-surface border border-border-default shadow-xl transition-all">
                {/* Header */}
                <div className="px-6 py-5 border-b border-border-default">
                  <div className="flex items-start justify-between">
                    <div className="flex items-start gap-3">
                      <div className="shrink-0">
                        <ExclamationTriangleIcon className="h-6 w-6 text-red-500" />
                      </div>
                      <div>
                        <Dialog.Title className="text-2xl font-sans font-semibold text-text-primary tracking-normal">
                          Delete Project
                        </Dialog.Title>
                      </div>
                    </div>
                    <button
                      onClick={onClose}
                      disabled={loading}
                      className="text-text-tertiary hover:text-accent-primary hover:bg-accent-light rounded-md p-2 transition-all duration-150"
                    >
                      <XMarkIcon className="h-6 w-6" />
                    </button>
                  </div>
                </div>

                {/* Content */}
                <div className="p-6">
                  <div className="ml-9 mb-6">
                    <p className="text-text-secondary mb-2 tracking-normal">
                      Are you sure you want to delete <span className="font-semibold text-text-primary">{projectTitle}</span>?
                    </p>
                    <p className="text-sm text-text-tertiary tracking-normal">
                      This will permanently delete the project and all its documents. This action cannot be undone.
                    </p>
                  </div>

                  {/* Actions */}
                  <div className="flex gap-3">
                    <button
                      type="button"
                      onClick={onClose}
                      disabled={loading}
                      className="flex-1 px-4 py-3 border border-border-default text-text-secondary font-medium rounded-md hover:border-accent-primary/30 hover:text-text-primary hover:bg-bg-hover transition-all duration-150 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={handleDelete}
                      disabled={loading}
                      className="flex-1 px-4 py-3 bg-red-600 text-white font-semibold rounded-md hover:bg-red-700 hover:shadow-sm hover:-translate-y-px transition-all duration-150 disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {loading ? 'Deleting...' : 'Delete Project'}
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

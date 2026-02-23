import { Fragment } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, DocumentTextIcon } from '@heroicons/react/24/outline'
import DocumentOverview from './DocumentOverview'

interface DocumentDetailModalProps {
  isOpen: boolean
  onClose: () => void
  document: {
    id: string
    title: string
    status: string
  }
}

export default function DocumentDetailModal({ isOpen, onClose, document }: DocumentDetailModalProps) {

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
              <Dialog.Panel className="w-full max-w-5xl transform overflow-hidden rounded-lg bg-bg-surface border border-border-default shadow-xl transition-all max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-5 border-b border-border-default shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-accent-light rounded-md border border-accent-primary/30">
                      <DocumentTextIcon className="h-6 w-6 text-accent-primary" />
                    </div>
                    <div>
                      <Dialog.Title className="text-2xl font-sans font-semibold text-text-primary tracking-normal">
                        {document.title}
                      </Dialog.Title>
                      <p className="text-sm font-mono text-text-muted mt-1 capitalize tracking-normal">
                        Status: {document.status}
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={onClose}
                    className="text-text-tertiary hover:text-accent-primary hover:bg-accent-light rounded-md p-2 transition-all duration-150"
                  >
                    <XMarkIcon className="h-6 w-6" />
                  </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6">
                  <DocumentOverview documentId={document.id} />
                </div>

                {/* Footer */}
                <div className="px-6 py-4 bg-bg-hover border-t border-border-default flex justify-end shrink-0">
                  <button
                    onClick={onClose}
                    className="px-4 py-2 text-sm text-text-tertiary hover:text-accent-primary hover:bg-accent-light rounded-md transition-all duration-150"
                  >
                    Close
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

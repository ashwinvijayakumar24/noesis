import { Fragment } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { CheckCircleIcon, SparklesIcon, MagnifyingGlassIcon } from '@heroicons/react/24/outline'

interface UploadSuccessModalProps {
  isOpen: boolean
  onClose: () => void
  documentTitle: string
}

export default function UploadSuccessModal({ isOpen, onClose, documentTitle }: UploadSuccessModalProps) {
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
              <Dialog.Panel className="w-full max-w-lg transform overflow-hidden rounded-lg bg-bg-surface border border-border-default shadow-xl transition-all">
                {/* Success Header */}
                <div className="bg-bg-elevated border-b border-border-default px-8 py-6">
                  <div className="flex items-center gap-4">
                    <div className="flex-shrink-0">
                      <div className="h-16 w-16 bg-accent-light rounded-full flex items-center justify-center border-2 border-accent-primary/30">
                        <CheckCircleIcon className="h-9 w-9 text-accent-primary" />
                      </div>
                    </div>
                    <div className="flex-1">
                      <Dialog.Title className="text-2xl font-sans font-semibold text-text-primary mb-1 tracking-normal">
                        Upload Successful!
                      </Dialog.Title>
                      <p className="text-sm text-text-secondary font-medium tracking-normal">
                        {documentTitle}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Processing Info */}
                <div className="px-8 py-6 space-y-6">
                  {/* Main message */}
                  <div className="text-center">
                    <p className="text-lg text-text-secondary leading-relaxed tracking-normal">
                      Your document is being processed automatically. This typically takes{' '}
                      <span className="font-semibold text-text-primary">1-2 minutes</span>.
                    </p>
                  </div>

                  {/* Processing Steps */}
                  <div className="space-y-4">
                    <div className="flex items-start gap-4 p-4 bg-bg-hover rounded-md border border-border-default">
                      <div className="flex-shrink-0 mt-0.5">
                        <div className="h-10 w-10 bg-indigo-light rounded-md flex items-center justify-center border border-indigo-primary/30">
                          <MagnifyingGlassIcon className="h-6 w-6 text-indigo-primary" />
                        </div>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-sm font-semibold text-text-primary mb-1 tracking-normal">
                          RAG Ingestion
                        </h4>
                        <p className="text-sm text-text-tertiary tracking-normal">
                          Indexing document for semantic search and chat functionality
                        </p>
                      </div>
                      <div className="flex-shrink-0">
                        <div className="flex items-center gap-1.5">
                          <span className="relative flex h-3 w-3">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-indigo-primary opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-3 w-3 bg-indigo-primary"></span>
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-start gap-4 p-4 bg-bg-hover rounded-md border border-border-default">
                      <div className="flex-shrink-0 mt-0.5">
                        <div className="h-10 w-10 bg-teal-light rounded-md flex items-center justify-center border border-teal-primary/30">
                          <SparklesIcon className="h-6 w-6 text-teal-primary" />
                        </div>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-sm font-semibold text-text-primary mb-1 tracking-normal">
                          AI Analysis
                        </h4>
                        <p className="text-sm text-text-tertiary tracking-normal">
                          Extracting methodology, findings, claims, and key citations
                        </p>
                      </div>
                      <div className="flex-shrink-0">
                        <div className="flex items-center gap-1.5">
                          <span className="relative flex h-3 w-3">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-teal-primary opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-3 w-3 bg-teal-primary"></span>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Info Note */}
                  <div className="bg-amber-light border border-amber-primary/30 rounded-md p-4">
                    <p className="text-sm text-text-secondary tracking-normal">
                      <span className="font-semibold">Note:</span> You can close this window and continue working.
                      The document card will update automatically when processing is complete.
                    </p>
                  </div>
                </div>

                {/* Footer */}
                <div className="bg-bg-hover border-t border-border-default px-8 py-4">
                  <button
                    onClick={onClose}
                    className="w-full px-6 py-3 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px transition-all duration-150"
                  >
                    Got it, thanks!
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

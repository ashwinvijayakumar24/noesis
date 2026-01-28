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
              <Dialog.Panel className="w-full max-w-lg transform overflow-hidden rounded-2xl bg-surface border border-border-base shadow-2xl transition-all">
                {/* Success Header */}
                <div className="bg-gradient-to-br from-green-900/30 to-emerald-900/20 border-b border-green-700/30 px-8 py-6">
                  <div className="flex items-center gap-4">
                    <div className="flex-shrink-0">
                      <div className="h-16 w-16 bg-green-600/20 rounded-full flex items-center justify-center border-2 border-green-500/30">
                        <CheckCircleIcon className="h-9 w-9 text-green-400" />
                      </div>
                    </div>
                    <div className="flex-1">
                      <Dialog.Title className="text-2xl font-serif font-semibold text-text-primary mb-1">
                        Upload Successful!
                      </Dialog.Title>
                      <p className="text-sm text-green-300/80 font-medium">
                        {documentTitle}
                      </p>
                    </div>
                  </div>
                </div>

                {/* Processing Info */}
                <div className="px-8 py-6 space-y-6">
                  {/* Main message */}
                  <div className="text-center">
                    <p className="text-lg text-text-secondary leading-relaxed">
                      Your document is being processed automatically. This typically takes{' '}
                      <span className="font-semibold text-text-primary">1-2 minutes</span>.
                    </p>
                  </div>

                  {/* Processing Steps */}
                  <div className="space-y-4">
                    <div className="flex items-start gap-4 p-4 bg-surface-hover rounded-lg border border-border-subtle">
                      <div className="flex-shrink-0 mt-0.5">
                        <div className="h-10 w-10 bg-purple-600/20 rounded-lg flex items-center justify-center">
                          <MagnifyingGlassIcon className="h-6 w-6 text-purple-400" />
                        </div>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-sm font-semibold text-text-primary mb-1">
                          RAG Ingestion
                        </h4>
                        <p className="text-sm text-text-tertiary">
                          Indexing document for semantic search and chat functionality
                        </p>
                      </div>
                      <div className="flex-shrink-0">
                        <div className="flex items-center gap-1.5">
                          <span className="relative flex h-3 w-3">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-purple-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-3 w-3 bg-purple-500"></span>
                          </span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-start gap-4 p-4 bg-surface-hover rounded-lg border border-border-subtle">
                      <div className="flex-shrink-0 mt-0.5">
                        <div className="h-10 w-10 bg-blue-600/20 rounded-lg flex items-center justify-center">
                          <SparklesIcon className="h-6 w-6 text-blue-400" />
                        </div>
                      </div>
                      <div className="flex-1">
                        <h4 className="text-sm font-semibold text-text-primary mb-1">
                          AI Analysis
                        </h4>
                        <p className="text-sm text-text-tertiary">
                          Extracting methodology, findings, claims, and key citations
                        </p>
                      </div>
                      <div className="flex-shrink-0">
                        <div className="flex items-center gap-1.5">
                          <span className="relative flex h-3 w-3">
                            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                            <span className="relative inline-flex rounded-full h-3 w-3 bg-blue-500"></span>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>

                  {/* Info Note */}
                  <div className="bg-amber-900/20 border border-amber-600/30 rounded-lg p-4">
                    <p className="text-sm text-amber-200/90">
                      <span className="font-semibold">Note:</span> You can close this window and continue working.
                      The document card will update automatically when processing is complete.
                    </p>
                  </div>
                </div>

                {/* Footer */}
                <div className="bg-surface-hover border-t border-border-base px-8 py-4">
                  <button
                    onClick={onClose}
                    className="w-full px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
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

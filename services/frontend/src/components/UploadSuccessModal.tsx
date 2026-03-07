import { Fragment } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { CheckCircleIcon } from '@heroicons/react/24/outline'

interface UploadSuccessModalProps {
  isOpen: boolean
  onClose: () => void
  uploadedCount: number
  documentTitles: string[]
}

export default function UploadSuccessModal({
  isOpen,
  onClose,
  uploadedCount,
  documentTitles
}: UploadSuccessModalProps) {
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
                <div className="text-center space-y-6 p-8">
                  {/* Success Icon */}
                  <div className="mx-auto flex items-center justify-center h-16 w-16 rounded-full bg-accent-primary/10">
                    <CheckCircleIcon className="h-10 w-10 text-accent-primary" />
                  </div>

                  {/* Title */}
                  <div>
                    <h3 className="text-2xl font-semibold text-text-primary mb-2 tracking-normal">
                      Upload Successful!
                    </h3>
                    {uploadedCount > 1 ? (
                      <p className="text-text-secondary tracking-normal">
                        {uploadedCount} documents uploaded
                      </p>
                    ) : (
                      <p className="text-text-secondary tracking-normal">
                        {documentTitles[0] || 'Document uploaded'}
                      </p>
                    )}
                  </div>

                  {/* Processing Message */}
                  <p className="text-text-muted text-sm tracking-normal">
                    Your {uploadedCount > 1 ? 'documents are' : 'document is'} being processed automatically.
                    This typically takes <span className="font-semibold text-text-primary">1-2 minutes</span>.
                  </p>

                  {/* Note */}
                  <div className="bg-bg-elevated border border-border-default rounded-lg p-4">
                    <p className="text-sm text-text-tertiary tracking-normal">
                      <strong>Note:</strong> You can close this window and continue working.
                      The document card{uploadedCount > 1 ? 's' : ''} will update automatically when processing is complete.
                    </p>
                  </div>

                  {/* Close Button */}
                  <button
                    onClick={onClose}
                    className="w-full bg-accent-primary text-white py-3 rounded-lg hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px transition-all duration-150 font-semibold tracking-normal"
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

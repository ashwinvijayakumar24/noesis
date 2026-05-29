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
              <Dialog.Panel className="w-full max-w-md transform overflow-hidden rounded-xl border border-border-default bg-bg-surface shadow-2xl transition-all">
                <div className="space-y-5 p-5 text-center">
                  {/* Success Icon */}
                  <div className="mx-auto flex h-11 w-11 items-center justify-center rounded-lg border border-border-default bg-bg-elevated">
                    <CheckCircleIcon className="h-6 w-6 text-accent-primary" />
                  </div>

                  {/* Title */}
                  <div>
                    <h3 className="mb-1 text-base font-semibold text-text-primary">
                      Uploading & analyzing
                    </h3>
                    <p className="text-sm font-medium text-text-secondary">
                      This may take a few minutes
                    </p>
                  </div>

                  {/* Processing Message */}
                  <p className="text-sm leading-6 text-text-secondary">
                    {uploadedCount > 1 ? `${uploadedCount} papers are` : 'Your paper is'} being processed and analyzed automatically.
                    You can close this window — the cards will update when done.
                  </p>

                  {/* Note */}
                  <div className="rounded-lg border border-border-default bg-bg-void/45 p-3 text-left">
                    <p className="text-xs leading-5 text-text-secondary">
                      <strong>Note:</strong> You can close this window and continue working.
                      The document card{uploadedCount > 1 ? 's' : ''} will update automatically when processing is complete.
                    </p>
                  </div>

                  {/* Close Button */}
                  <button
                    onClick={onClose}
                    className="w-full rounded-md bg-accent-primary py-2 text-sm font-semibold text-white transition-all duration-150 hover:bg-accent-hover"
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

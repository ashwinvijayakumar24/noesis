import { Fragment, useState, type FormEvent } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon } from '@heroicons/react/24/outline'
import toast from 'react-hot-toast'
import { api } from '../lib/api'
import { trackEvent } from '../lib/analytics'
import { handleError } from '../lib/errorHandler'

interface CreateProjectModalProps {
  isOpen: boolean
  onClose: () => void
  onSuccess: () => void
  token: string
}

export default function CreateProjectModal({
  isOpen,
  onClose,
  onSuccess,
  token,
}: CreateProjectModalProps) {
  const [title, setTitle] = useState('')
  const [description, setDescription] = useState('')
  const [loading, setLoading] = useState(false)

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault()

    if (!title.trim()) {
      toast.error('Project title is required')
      return
    }

    try {
      setLoading(true)
      const result = await api.projects.create(token, {
        title: title.trim(),
        description: description.trim() || undefined,
      })
      trackEvent.projectCreated(result.id)
      toast.success('Project created successfully!')
      setTitle('')
      setDescription('')
      onClose()
      onSuccess()
    } catch (error: any) {
      handleError(error, 'creating project')
    } finally {
      setLoading(false)
    }
  }

  const handleClose = () => {
    if (!loading) {
      setTitle('')
      setDescription('')
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
          <div className="fixed inset-0 bg-black/80 backdrop-blur-sm" />
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
                    Create New Project
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
                  <div>
                    <label
                      htmlFor="title"
                      className="block text-sm font-medium text-neutral-300 mb-2"
                    >
                      Project Title
                    </label>
                    <input
                      id="title"
                      type="text"
                      value={title}
                      onChange={(e) => setTitle(e.target.value)}
                      className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                      placeholder="e.g., Machine Learning Research"
                      disabled={loading}
                      autoFocus
                    />
                  </div>

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
                      placeholder="Describe your research project..."
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
                      disabled={loading || !title.trim()}
                      className="flex-1 px-4 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {loading ? 'Creating...' : 'Create Project'}
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

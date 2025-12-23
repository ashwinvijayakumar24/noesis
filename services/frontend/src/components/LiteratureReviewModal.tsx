import { Fragment, useState } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, DocumentTextIcon, ArrowDownTrayIcon, SparklesIcon } from '@heroicons/react/24/outline'
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'
import ReactMarkdown from 'react-markdown'

interface LiteratureReviewModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
}

const STRUCTURES = [
  { id: 'chronological', name: 'Chronological', description: 'Organized by publication date' },
  { id: 'thematic', name: 'Thematic', description: 'Organized by themes and topics' },
  { id: 'methodological', name: 'Methodological', description: 'Organized by research methods' },
]

export default function LiteratureReviewModal({ isOpen, onClose, projectId }: LiteratureReviewModalProps) {
  const { session } = useAuthStore()
  const [structure, setStructure] = useState('thematic')
  const [theme, setTheme] = useState('')
  const [targetWords, setTargetWords] = useState(1500)
  const [generating, setGenerating] = useState(false)
  const [review, setReview] = useState<string | null>(null)
  const [metadata, setMetadata] = useState<any>(null)

  const handleGenerate = async () => {
    if (!session?.access_token) return

    setGenerating(true)
    setReview(null)

    try {
      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/literature-review/projects/${projectId}/generate`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({
            structure,
            theme: theme.trim() || null,
            target_words: targetWords
          }),
        }
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail?.message || errorData.detail || 'Failed to generate review')
      }

      const data = await response.json()
      setReview(data.review_body)
      setMetadata(data.metadata)
      toast.success('Literature review generated!')
    } catch (error: any) {
      console.error('Failed to generate review:', error)
      toast.error(error.message || 'Failed to generate review')
    } finally {
      setGenerating(false)
    }
  }

  const handleExport = async (format: 'pdf' | 'latex' | 'markdown') => {
    if (!session?.access_token) return

    try {
      toast.loading(`Exporting as ${format.toUpperCase()}...`)

      const response = await fetch(
        `${import.meta.env.VITE_API_URL || 'http://localhost:8000'}/literature-review/projects/${projectId}/generate/export?format=${format}`,
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${session.access_token}`,
          },
          body: JSON.stringify({
            structure,
            theme: theme.trim() || null,
            target_words: targetWords
          }),
        }
      )

      if (!response.ok) {
        throw new Error('Export failed')
      }

      // Download the file
      const blob = await response.blob()
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `literature_review_${structure}.${format === 'latex' ? 'tex' : format === 'markdown' ? 'md' : 'pdf'}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      toast.dismiss()
      toast.success(`Exported as ${format.toUpperCase()}`)
    } catch (error: any) {
      toast.dismiss()
      console.error('Export failed:', error)
      toast.error('Failed to export review')
    }
  }

  const handleCopyToClipboard = () => {
    if (!review) return

    navigator.clipboard.writeText(review)
    toast.success('Copied to clipboard!')
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
              <Dialog.Panel className="w-full max-w-5xl transform overflow-hidden rounded-lg bg-neutral-900 border border-neutral-800 shadow-2xl transition-all max-h-[90vh] flex flex-col">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-5 border-b border-neutral-800 shrink-0">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-accent-primary/10 rounded-lg">
                      <DocumentTextIcon className="h-6 w-6 text-accent-primary" />
                    </div>
                    <div>
                      <Dialog.Title className="text-2xl font-serif font-semibold text-neutral-50">
                        Literature Review Generator
                      </Dialog.Title>
                      <p className="text-sm text-neutral-500 mt-1">
                        AI-generated review with proper citations
                      </p>
                    </div>
                  </div>
                  <button
                    onClick={onClose}
                    className="text-neutral-400 hover:text-neutral-200 transition-colors"
                  >
                    <XMarkIcon className="h-6 w-6" />
                  </button>
                </div>

                {/* Content */}
                <div className="flex-1 overflow-y-auto p-6">
                  {!review ? (
                    /* Settings Form */
                    <div className="max-w-2xl mx-auto space-y-6">
                      {/* Structure Selection */}
                      <div>
                        <label className="block text-sm font-medium text-neutral-300 mb-3">
                          Review Structure
                        </label>
                        <div className="grid grid-cols-1 gap-3">
                          {STRUCTURES.map((struct) => (
                            <button
                              key={struct.id}
                              onClick={() => setStructure(struct.id)}
                              className={`text-left p-4 rounded-lg border-2 transition-colors ${
                                structure === struct.id
                                  ? 'border-accent-primary bg-accent-primary/10'
                                  : 'border-neutral-700 bg-neutral-900 hover:border-neutral-600'
                              }`}
                            >
                              <div className="font-semibold text-neutral-50">{struct.name}</div>
                              <div className="text-sm text-neutral-400 mt-1">{struct.description}</div>
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Theme (Optional) */}
                      <div>
                        <label className="block text-sm font-medium text-neutral-300 mb-2">
                          Focus Theme <span className="text-neutral-500 font-mono text-xs">(optional)</span>
                        </label>
                        <input
                          type="text"
                          value={theme}
                          onChange={(e) => setTheme(e.target.value)}
                          placeholder="e.g., Machine learning applications, Clinical outcomes"
                          className="w-full px-4 py-3 bg-neutral-950 border border-neutral-700 rounded-lg text-neutral-50 placeholder-neutral-500 focus:ring-2 focus:ring-accent-primary focus:border-transparent transition-colors"
                        />
                        <p className="text-xs font-mono text-neutral-500 mt-2">
                          Leave blank for general review of all papers
                        </p>
                      </div>

                      {/* Target Words */}
                      <div>
                        <label className="block text-sm font-medium text-neutral-300 mb-2">
                          Target Length: <span className="text-accent-primary">{targetWords}</span> words
                        </label>
                        <input
                          type="range"
                          min="500"
                          max="3000"
                          step="100"
                          value={targetWords}
                          onChange={(e) => setTargetWords(parseInt(e.target.value))}
                          className="w-full accent-accent-primary"
                        />
                        <div className="flex justify-between text-xs font-mono text-neutral-500 mt-2">
                          <span>500</span>
                          <span>1500 (standard)</span>
                          <span>3000</span>
                        </div>
                      </div>

                      {/* Generate Button */}
                      <button
                        onClick={handleGenerate}
                        disabled={generating}
                        className="w-full px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed"
                      >
                        {generating ? (
                          <>
                            <div className="h-5 w-5 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                            Generating Review...
                          </>
                        ) : (
                          <>
                            <SparklesIcon className="h-5 w-5" />
                            Generate Literature Review
                          </>
                        )}
                      </button>
                    </div>
                  ) : (
                    /* Review Display */
                    <div className="space-y-4">
                      {/* Metadata */}
                      <div className="bg-neutral-900/50 rounded-lg p-4 flex items-center justify-between">
                        <div className="text-sm font-mono text-neutral-400">
                          <span className="font-semibold text-neutral-300">{metadata?.structure}</span> review •{' '}
                          {metadata?.num_documents} documents • ~{targetWords} words
                        </div>
                        <div className="flex items-center gap-2">
                          <button
                            onClick={handleCopyToClipboard}
                            className="px-3 py-2 text-sm bg-neutral-800 text-neutral-300 rounded-lg hover:bg-neutral-700 transition-colors"
                          >
                            Copy
                          </button>
                          <button
                            onClick={() => handleExport('pdf')}
                            className="px-3 py-2 text-sm bg-accent-primary text-white rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-1"
                          >
                            <ArrowDownTrayIcon className="h-4 w-4" />
                            PDF
                          </button>
                          <button
                            onClick={() => handleExport('latex')}
                            className="px-3 py-2 text-sm bg-neutral-800 text-neutral-300 rounded-lg hover:bg-neutral-700 transition-colors"
                          >
                            LaTeX
                          </button>
                          <button
                            onClick={() => handleExport('markdown')}
                            className="px-3 py-2 text-sm bg-neutral-800 text-neutral-300 rounded-lg hover:bg-neutral-700 transition-colors"
                          >
                            Markdown
                          </button>
                        </div>
                      </div>

                      {/* Review Content */}
                      <div className="bg-neutral-900/30 rounded-lg p-6 prose prose-invert prose-sm max-w-none">
                        <ReactMarkdown
                          components={{
                            h1: ({ children }) => <h1 className="text-2xl font-serif font-bold mb-4 text-neutral-50">{children}</h1>,
                            h2: ({ children }) => <h2 className="text-xl font-serif font-bold mb-3 mt-6 text-neutral-50">{children}</h2>,
                            h3: ({ children }) => <h3 className="text-lg font-serif font-semibold mb-2 mt-4 text-neutral-100">{children}</h3>,
                            p: ({ children }) => <p className="mb-3 text-neutral-300 leading-relaxed">{children}</p>,
                            strong: ({ children }) => <strong className="font-bold text-neutral-50">{children}</strong>,
                            ul: ({ children }) => <ul className="list-disc list-outside ml-5 mb-3 space-y-1">{children}</ul>,
                            ol: ({ children }) => <ol className="list-decimal list-outside ml-5 mb-3 space-y-1">{children}</ol>,
                            li: ({ children }) => <li className="text-neutral-300">{children}</li>,
                          }}
                        >
                          {review}
                        </ReactMarkdown>
                      </div>

                      {/* Generate New Button */}
                      <button
                        onClick={() => setReview(null)}
                        className="w-full px-4 py-2 text-sm text-neutral-400 hover:text-neutral-50 transition-colors border border-neutral-700 rounded-lg hover:border-neutral-600"
                      >
                        Generate New Review
                      </button>
                    </div>
                  )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 bg-neutral-900/50 border-t border-neutral-800 flex justify-end shrink-0">
                  <button
                    onClick={onClose}
                    className="px-4 py-2 text-sm text-neutral-400 hover:text-neutral-50 transition-colors"
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

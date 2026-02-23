import { Fragment, useState, useEffect } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, Cog6ToothIcon, ArrowPathIcon, InformationCircleIcon } from '@heroicons/react/24/outline'
// import { api } from '../lib/api' // Disabled - RAG settings API removed
import { useAuthStore } from '../stores/authStore'
import toast from 'react-hot-toast'

interface RAGSettingsModalProps {
  isOpen: boolean
  onClose: () => void
  projectId: string
}

interface RAGSettings {
  chunk_size: number
  chunk_overlap: number
  embedding_model: string
  max_chunks: number
  similarity_threshold: number
}

export default function RAGSettingsModal({ isOpen, onClose, projectId }: RAGSettingsModalProps) {
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState<RAGSettings>({
    chunk_size: 1000,
    chunk_overlap: 150,
    embedding_model: 'text-embedding-3-small',
    max_chunks: 5,
    similarity_threshold: 0.0,
  })
  const [originalEmbeddingModel, _setOriginalEmbeddingModel] = useState<string>('text-embedding-3-small')

  useEffect(() => {
    if (isOpen && session?.access_token) {
      loadSettings()
    }
  }, [isOpen, projectId, session])

  const loadSettings = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      // TODO: api.ragSettings endpoints removed - to be re-implemented
      // const data = await api.ragSettings.get(session.access_token, projectId)
      // setSettings(data)
      // _setOriginalEmbeddingModel(data.embedding_model)
    } catch (error: any) {
      console.error('Failed to load RAG settings:', error)
      toast.error('Failed to load settings')
    } finally {
      setLoading(false)
    }
  }

  const handleSave = async () => {
    if (!session?.access_token) return

    // Check if embedding model changed
    const modelChanged = settings.embedding_model !== originalEmbeddingModel

    if (modelChanged) {
      const confirmed = confirm(
        `⚠️ EMBEDDING MODEL CHANGE WARNING\n\n` +
        `You are changing the embedding model from "${originalEmbeddingModel}" to "${settings.embedding_model}".\n\n` +
        `IMPORTANT: Existing documents will NOT be re-processed automatically. This means:\n\n` +
        `• Queries will only retrieve from documents that match the NEW model\n` +
        `• Documents embedded with "${originalEmbeddingModel}" will be incompatible\n` +
        `• You MUST re-upload all existing documents to apply this change\n\n` +
        `Are you sure you want to change the embedding model?`
      )

      if (!confirmed) {
        return
      }
    }

    try {
      setSaving(true)
      // TODO: api.ragSettings endpoints removed - to be re-implemented
      // await api.ragSettings.update(session.access_token, projectId, settings)
      toast.error('RAG settings feature temporarily disabled')
      onClose()
    } catch (error: any) {
      console.error('Failed to update RAG settings:', error)
      toast.error(error.message || 'Failed to update settings')
    } finally {
      setSaving(false)
    }
  }

  const handleReset = async () => {
    if (!session?.access_token) return

    if (!confirm('Reset all RAG settings to defaults? This will not affect existing documents.')) {
      return
    }

    try {
      setSaving(true)
      // TODO: api.ragSettings endpoints removed - to be re-implemented
      // const data = await api.ragSettings.reset(session.access_token, projectId)
      // setSettings(data.rag_settings)
      // _setOriginalEmbeddingModel(data.rag_settings.embedding_model)
      toast.error('RAG settings feature temporarily disabled')
    } catch (error: any) {
      console.error('Failed to reset RAG settings:', error)
      toast.error('Failed to reset settings')
    } finally {
      setSaving(false)
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
              <Dialog.Panel className="w-full max-w-2xl transform overflow-hidden rounded-lg bg-bg-surface border border-border-default shadow-xl transition-all">
                {/* Header */}
                <div className="flex items-center justify-between px-6 py-5 border-b border-border-default">
                  <div className="flex items-center gap-3">
                    <div className="p-2 bg-accent-light rounded-md border border-accent-primary/30">
                      <Cog6ToothIcon className="h-6 w-6 text-accent-primary" />
                    </div>
                    <div>
                      <Dialog.Title className="text-2xl font-sans font-semibold text-text-primary tracking-normal">
                        RAG Configuration
                      </Dialog.Title>
                      <p className="text-sm text-text-muted mt-1 tracking-normal">
                        Customize how documents are processed and searched
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

                {/* Warning Banner */}
                <div className="mx-6 mt-4 p-3 bg-amber-light border border-amber-primary/30 rounded-md flex gap-3">
                  <InformationCircleIcon className="h-5 w-5 text-amber-primary shrink-0 mt-0.5" />
                  <div className="text-sm text-text-secondary tracking-normal">
                    <strong>Note:</strong> Changing these settings only affects newly uploaded documents.
                    To apply changes to existing documents, you'll need to re-process them manually.
                  </div>
                </div>

                {/* Settings Content */}
                <div className="px-6 py-6 space-y-6">
                  {loading ? (
                    <div className="text-center py-8">
                      <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent"></div>
                      <p className="text-text-tertiary text-sm mt-3">Loading settings...</p>
                    </div>
                  ) : (
                    <>
                      {/* Chunk Size */}
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-2 tracking-normal">
                          Chunk Size: <span className="text-accent-primary">{settings.chunk_size}</span> tokens (~{Math.round(settings.chunk_size * 0.75)} words)
                        </label>
                        <input
                          type="range"
                          min="200"
                          max="2000"
                          step="50"
                          value={settings.chunk_size}
                          onChange={(e) => setSettings({ ...settings, chunk_size: parseInt(e.target.value) })}
                          className="w-full h-2 bg-bg-hover rounded-md appearance-none cursor-pointer accent-accent-primary"
                        />
                        <div className="mt-2 space-y-1">
                          <p className="text-xs text-text-tertiary">
                            <strong>Trade-offs:</strong>
                          </p>
                          <p className="text-xs font-mono text-text-muted">
                            • <strong>500-800 tokens:</strong> Best for specific, factual questions. More precise but may miss broader context.
                          </p>
                          <p className="text-xs font-mono text-text-muted">
                            • <strong>1000-1500 tokens:</strong> ⭐ Recommended for research papers. Captures full arguments and context for broad questions.
                          </p>
                          <p className="text-xs font-mono text-text-muted">
                            • <strong>1500+ tokens:</strong> Maximum context per chunk, but may include irrelevant information.
                          </p>
                        </div>
                      </div>

                      {/* Chunk Overlap */}
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-2">
                          Chunk Overlap: <span className="text-accent-primary">{settings.chunk_overlap}</span> tokens ({Math.round((settings.chunk_overlap / settings.chunk_size) * 100)}% overlap)
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="200"
                          step="10"
                          value={settings.chunk_overlap}
                          onChange={(e) => setSettings({ ...settings, chunk_overlap: parseInt(e.target.value) })}
                          className="w-full h-2 bg-bg-hover rounded-md appearance-none cursor-pointer accent-accent-primary"
                        />
                        <p className="text-xs font-mono text-text-muted mt-2">
                          Overlap between chunks to preserve context across boundaries. Recommended: 10-15% of chunk size (e.g., 150 tokens for 1000-token chunks).
                        </p>
                      </div>

                      {/* Embedding Model */}
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-2 tracking-normal">
                          Embedding Model
                          {settings.embedding_model !== originalEmbeddingModel && (
                            <span className="ml-2 text-xs text-amber-primary">⚠️ Changed</span>
                          )}
                        </label>
                        <select
                          value={settings.embedding_model}
                          onChange={(e) => setSettings({ ...settings, embedding_model: e.target.value })}
                          className={`w-full px-4 py-3 bg-bg-surface border rounded-md text-text-primary focus:ring-2 focus:ring-accent-primary focus:border-accent-primary transition-colors tracking-normal ${
                            settings.embedding_model !== originalEmbeddingModel
                              ? 'border-amber-primary/50'
                              : 'border-border-default'
                          }`}
                        >
                          <option value="text-embedding-3-small">text-embedding-3-small (Faster, cheaper) ⭐ Recommended</option>
                          <option value="text-embedding-3-large">text-embedding-3-large (Higher quality, 6.5x cost)</option>
                        </select>
                        <div className="mt-2 space-y-1">
                          <p className="text-xs text-text-tertiary">
                            <strong>Trade-offs:</strong>
                          </p>
                          <p className="text-xs font-mono text-text-muted">
                            • <strong>small:</strong> ⭐ $0.02/1M tokens, 62.3% accuracy, 2-3x faster. Best for most use cases.
                          </p>
                          <p className="text-xs font-mono text-text-muted">
                            • <strong>large:</strong> $0.13/1M tokens, 64.6% accuracy. Only use for highly specialized/technical content.
                          </p>
                          <p className="text-xs font-mono text-text-muted italic">
                            For research papers, the small model is typically sufficient. The ~2% accuracy gain rarely justifies 6.5x cost.
                          </p>
                        </div>
                        {settings.embedding_model !== originalEmbeddingModel && (
                          <div className="mt-2 p-2 bg-warning/10 border border-warning/30 rounded text-xs text-warning">
                            ⚠️ Changing models requires re-uploading all documents
                          </div>
                        )}
                      </div>

                      {/* Max Chunks */}
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-2">
                          Max Chunks Retrieved: <span className="text-accent-primary">{settings.max_chunks}</span>
                          <span className="text-text-muted text-xs font-mono ml-2">
                            (~{settings.max_chunks * settings.chunk_size} tokens total)
                          </span>
                        </label>
                        <input
                          type="range"
                          min="1"
                          max="20"
                          step="1"
                          value={settings.max_chunks}
                          onChange={(e) => setSettings({ ...settings, max_chunks: parseInt(e.target.value) })}
                          className="w-full h-2 bg-bg-hover rounded-md appearance-none cursor-pointer accent-accent-primary"
                        />
                        <p className="text-xs font-mono text-text-muted mt-2">
                          Number of chunks to retrieve per query. With 1000-token chunks, 5 chunks = ~5000 tokens of context. More chunks = more context but higher LLM costs.
                        </p>
                      </div>

                      {/* Similarity Threshold */}
                      <div>
                        <label className="block text-sm font-medium text-text-secondary mb-2">
                          Similarity Threshold: <span className="text-accent-primary">{settings.similarity_threshold.toFixed(2)}</span>
                        </label>
                        <input
                          type="range"
                          min="0"
                          max="1"
                          step="0.05"
                          value={settings.similarity_threshold}
                          onChange={(e) => setSettings({ ...settings, similarity_threshold: parseFloat(e.target.value) })}
                          className="w-full h-2 bg-bg-hover rounded-md appearance-none cursor-pointer accent-accent-primary"
                        />
                        <p className="text-xs font-mono text-text-muted mt-2">
                          Minimum similarity score (0-1). Higher = only very relevant results, lower = more results.
                        </p>
                      </div>
                    </>
                  )}
                </div>

                {/* Footer */}
                <div className="px-6 py-4 bg-bg-hover border-t border-border-default flex items-center justify-between">
                  <button
                    onClick={handleReset}
                    disabled={loading || saving}
                    className="flex items-center gap-2 px-4 py-2 text-sm text-text-tertiary hover:text-text-primary border border-border-default rounded-md hover:bg-bg-hover hover:border-accent-primary/30 transition-all duration-150 disabled:opacity-50"
                  >
                    <ArrowPathIcon className="h-4 w-4" />
                    Reset to Defaults
                  </button>
                  <div className="flex gap-3">
                    <button
                      onClick={onClose}
                      disabled={saving}
                      className="px-4 py-2 text-sm text-text-tertiary hover:text-accent-primary hover:bg-accent-light rounded-md transition-all duration-150 disabled:opacity-50"
                    >
                      Cancel
                    </button>
                    <button
                      onClick={handleSave}
                      disabled={loading || saving}
                      className="px-6 py-2 bg-accent-primary text-white font-semibold rounded-md hover:bg-accent-hover hover:shadow-sm hover:-translate-y-px transition-all duration-150 disabled:opacity-50 flex items-center gap-2"
                    >
                      {saving && (
                        <div className="h-4 w-4 animate-spin rounded-full border-2 border-solid border-white border-r-transparent"></div>
                      )}
                      Save Settings
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

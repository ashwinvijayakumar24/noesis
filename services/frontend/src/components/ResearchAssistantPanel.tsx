import { Fragment, useState } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, ChatBubbleLeftRightIcon } from '@heroicons/react/24/outline'

interface ResearchAssistantPanelProps {
  projectId: string
  token: string
  currentTab: string
  chatMessages: any[]
  chatInput: string
  setChatInput: (input: string) => void
  sendMessage: () => void
  isLoading: boolean
  clearChat: () => void
}

export default function ResearchAssistantPanel({
  projectId: _projectId,
  token: _token,
  currentTab,
  chatMessages,
  chatInput,
  setChatInput,
  sendMessage,
  isLoading,
  clearChat
}: ResearchAssistantPanelProps) {
  const [isOpen, setIsOpen] = useState(false)

  const getContextMessage = (tab: string) => {
    switch (tab) {
      case 'documents':
        return 'Ask questions about your uploaded research papers'
      case 'insights':
        return 'Explore cross-paper themes, trends, and gaps'
      case 'compass':
        return 'Get guidance on literature review structure and organization'
      case 'drafts':
        return 'Get feedback on your draft manuscript'
      case 'analytics':
        return 'Analyze citation patterns and paper relationships'
      default:
        return 'Ask questions about your research project'
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      if (chatInput.trim() && !isLoading) {
        sendMessage()
      }
    }
  }

  return (
    <>
      {/* Floating action button */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-6 right-6 z-40 bg-accent-primary hover:bg-accent-hover text-white rounded-full p-4 shadow-lg transition-all hover:scale-110 focus:outline-none focus:ring-2 focus:ring-accent-primary focus:ring-offset-2"
        aria-label="Open Research Assistant"
      >
        <ChatBubbleLeftRightIcon className="h-6 w-6" />
      </button>

      {/* Slide-out panel */}
      <Transition show={isOpen} as={Fragment}>
        <Dialog onClose={() => setIsOpen(false)} className="relative z-50">
          {/* Backdrop */}
          <Transition.Child
            as={Fragment}
            enter="ease-out duration-300"
            enterFrom="opacity-0"
            enterTo="opacity-100"
            leave="ease-in duration-200"
            leaveFrom="opacity-100"
            leaveTo="opacity-0"
          >
            <div className="fixed inset-0 bg-black/25 backdrop-blur-sm" />
          </Transition.Child>

          {/* Panel */}
          <Transition.Child
            as={Fragment}
            enter="transform transition ease-in-out duration-300"
            enterFrom="translate-x-full"
            enterTo="translate-x-0"
            leave="transform transition ease-in-out duration-300"
            leaveFrom="translate-x-0"
            leaveTo="translate-x-full"
          >
            <Dialog.Panel className="fixed right-0 top-0 h-screen w-full sm:w-[600px] bg-surface border-l border-border-base shadow-2xl flex flex-col">
              {/* Header */}
              <div className="border-b border-border-subtle px-6 py-4 flex items-center justify-between">
                <Dialog.Title className="text-xl font-semibold text-text-primary">
                  Research Assistant
                </Dialog.Title>
                <button
                  onClick={() => setIsOpen(false)}
                  className="text-text-tertiary hover:text-text-secondary transition-colors"
                >
                  <XMarkIcon className="h-5 w-5" />
                </button>
              </div>

              {/* Context banner */}
              <div className="bg-accent-primary/10 border-b border-accent-primary/30 px-6 py-3">
                <p className="text-sm text-text-secondary">
                  💡 Currently viewing: <span className="font-medium capitalize">{currentTab}</span> tab
                </p>
                <p className="text-xs text-text-tertiary mt-1">
                  {getContextMessage(currentTab)}
                </p>
              </div>

              {/* Chat messages */}
              <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
                {chatMessages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-center">
                    <ChatBubbleLeftRightIcon className="h-16 w-16 text-text-muted mb-4" />
                    <h3 className="text-lg font-medium text-text-primary mb-2">
                      Start a conversation
                    </h3>
                    <p className="text-sm text-text-tertiary max-w-md">
                      Ask questions about your research papers, get insights, or request help with your literature review.
                    </p>
                  </div>
                ) : (
                  chatMessages.map((msg, idx) => (
                    <div
                      key={idx}
                      className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                    >
                      <div
                        className={`max-w-[80%] rounded-lg px-4 py-3 ${
                          msg.role === 'user'
                            ? 'bg-accent-primary text-white'
                            : 'bg-surface-hover text-text-secondary border border-border-base'
                        }`}
                      >
                        <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="mt-2 pt-2 border-t border-border-subtle">
                            <p className="text-xs font-medium mb-1">Sources:</p>
                            <ul className="text-xs space-y-1">
                              {msg.sources.map((source: any, i: number) => (
                                <li key={i} className="truncate">
                                  📄 {source.title || source.document_id}
                                </li>
                              ))}
                            </ul>
                          </div>
                        )}
                      </div>
                    </div>
                  ))
                )}
              </div>

              {/* Input area */}
              <div className="border-t border-border-subtle px-6 py-4 bg-surface-hover">
                <div className="flex items-end gap-2">
                  <div className="flex-1">
                    <textarea
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Ask a question about your research..."
                      className="w-full px-4 py-3 bg-surface border border-border-base rounded-lg focus:outline-none focus:ring-2 focus:ring-accent-primary resize-none text-text-primary placeholder-text-muted"
                      rows={2}
                      disabled={isLoading}
                    />
                  </div>
                  <button
                    onClick={sendMessage}
                    disabled={!chatInput.trim() || isLoading}
                    className="px-4 py-3 bg-accent-primary text-white rounded-lg hover:bg-accent-hover transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  >
                    {isLoading ? (
                      <>
                        <svg className="animate-spin h-5 w-5" fill="none" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                        </svg>
                        <span className="hidden sm:inline">Thinking...</span>
                      </>
                    ) : (
                      <>
                        <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 19l9 2-9-18-9 18 9-2zm0 0v-8" />
                        </svg>
                        <span className="hidden sm:inline">Send</span>
                      </>
                    )}
                  </button>
                </div>
                {chatMessages.length > 0 && (
                  <button
                    onClick={clearChat}
                    className="mt-2 text-xs text-text-muted hover:text-text-secondary transition-colors"
                  >
                    Clear conversation
                  </button>
                )}
              </div>
            </Dialog.Panel>
          </Transition.Child>
        </Dialog>
      </Transition>
    </>
  )
}

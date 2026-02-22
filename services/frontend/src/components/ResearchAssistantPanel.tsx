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
      {/* Floating action button - Touch-friendly */}
      <button
        onClick={() => setIsOpen(true)}
        className="fixed bottom-4 right-4 sm:bottom-6 sm:right-6 z-40 bg-neon-pink hover:bg-neon-pink-bright text-white rounded-full p-4 sm:p-5 min-h-[56px] min-w-[56px] shadow-neon-glow transition-all duration-300 hover:scale-110 hover:shadow-neon-glow-lg focus:outline-none focus:ring-2 focus:ring-neon-pink focus:ring-offset-2 focus:ring-offset-bg-void"
        aria-label="Open Research Assistant"
      >
        <ChatBubbleLeftRightIcon className="h-6 w-6 sm:h-7 sm:w-7" />
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
            <div className="fixed inset-0 bg-black/60 backdrop-blur-md" />
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
            <Dialog.Panel className="fixed right-0 top-0 h-screen w-full sm:w-[480px] md:w-[600px] bg-bg-surface border-l-2 border-neon-pink/30 shadow-neon-glow-lg flex flex-col">
              {/* Header */}
              <div className="border-b border-border-base px-6 py-4 flex items-center justify-between bg-bg-elevated/50">
                <Dialog.Title className="text-2xl font-display font-bold text-text-primary">
                  Research Assistant
                </Dialog.Title>
                <button
                  onClick={() => setIsOpen(false)}
                  className="text-text-secondary hover:text-neon-pink transition-all duration-200 hover:rotate-90"
                >
                  <XMarkIcon className="h-6 w-6" />
                </button>
              </div>

              {/* Context banner */}
              <div className="bg-neon-pink/10 border-b border-neon-pink/30 px-6 py-3">
                <p className="text-sm text-text-primary font-medium">
                  💡 Currently viewing: <span className="font-display font-bold capitalize text-neon-pink">{currentTab}</span> tab
                </p>
                <p className="text-xs text-text-secondary mt-1">
                  {getContextMessage(currentTab)}
                </p>
              </div>

              {/* Chat messages */}
              <div className="flex-1 overflow-y-auto px-6 py-4 space-y-6">
                {chatMessages.length === 0 ? (
                  <div className="flex flex-col items-center justify-center h-full text-center">
                    <div className="bg-neon-pink/10 p-6 rounded-full mb-4">
                      <ChatBubbleLeftRightIcon className="h-16 w-16 text-neon-pink" />
                    </div>
                    <h3 className="text-xl font-display font-bold text-text-primary mb-2">
                      Start a conversation
                    </h3>
                    <p className="text-sm text-text-secondary max-w-md leading-relaxed">
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
                        className={`max-w-[85%] rounded-2xl px-5 py-3 ${
                          msg.role === 'user'
                            ? 'bg-neon-pink/10 text-text-primary border border-neon-pink/30 rounded-br-sm'
                            : 'bg-bg-elevated text-text-primary border border-border-base rounded-bl-sm'
                        }`}
                      >
                        <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                        {msg.sources && msg.sources.length > 0 && (
                          <div className="mt-3 pt-3 border-t border-border-base">
                            <p className="text-xs font-semibold text-neon-pink mb-2">Sources:</p>
                            <ul className="text-xs space-y-1.5">
                              {msg.sources.map((source: any, i: number) => (
                                <li key={i} className="truncate text-text-secondary flex items-start gap-2">
                                  <span className="text-neon-pink">📄</span>
                                  <span>{source.title || source.document_id}</span>
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
              <div className="border-t border-border-base px-6 py-4 bg-bg-elevated/50">
                <div className="flex items-end gap-3">
                  <div className="flex-1">
                    <textarea
                      value={chatInput}
                      onChange={(e) => setChatInput(e.target.value)}
                      onKeyDown={handleKeyDown}
                      placeholder="Ask a question about your research..."
                      className="w-full px-4 py-3 bg-bg-surface border border-border-base rounded-xl focus:outline-none focus:border-neon-pink focus:shadow-focus-pink resize-none text-text-primary placeholder-text-muted transition-all duration-200"
                      rows={2}
                      disabled={isLoading}
                    />
                  </div>
                  <button
                    onClick={sendMessage}
                    disabled={!chatInput.trim() || isLoading}
                    className="px-5 py-3 bg-neon-pink text-white rounded-xl hover:bg-neon-pink-bright hover:shadow-neon-glow transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2 font-semibold"
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
                    className="mt-3 text-xs text-text-muted hover:text-neon-pink transition-colors font-medium"
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

import { useState } from 'react'
import {
  ChevronUpIcon,
  ChevronDownIcon,
  PaperAirplaneIcon
} from '@heroicons/react/24/outline'
import ChatMessage from '../ChatMessage'

interface ChatBoxProps {
  messages: any[]
  input: string
  setInput: (value: string) => void
  onSendMessage: () => void
  isStreaming: boolean
  streamingMessage: string
  includeDrafts: boolean
  setIncludeDrafts: (value: boolean) => void
  messagesEndRef: React.RefObject<HTMLDivElement>
}

export default function ChatBox({
  messages,
  input,
  setInput,
  onSendMessage,
  isStreaming,
  streamingMessage,
  includeDrafts,
  setIncludeDrafts,
  messagesEndRef
}: ChatBoxProps) {
  const [isExpanded, setIsExpanded] = useState(false)

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      onSendMessage()
    }
  }

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* Header */}
      <button
        onClick={() => setIsExpanded(!isExpanded)}
        className="flex-shrink-0 p-3 border-b border-border-subtle hover:bg-surface-hover transition-colors flex items-center justify-between"
      >
        <div className="flex items-center gap-2">
          <svg className="h-5 w-5 text-cyan-400" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 10h.01M12 10h.01M16 10h.01M9 16H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-5l-5 5v-5z" />
          </svg>
          <h3 className="text-sm font-semibold text-text-primary">Chat</h3>
          {messages.length > 0 && (
            <span className="px-2 py-0.5 text-xs bg-cyan-500/10 text-cyan-400 rounded-full font-mono">
              {messages.length}
            </span>
          )}
        </div>
        {isExpanded ? (
          <ChevronDownIcon className="h-4 w-4 text-text-tertiary" />
        ) : (
          <ChevronUpIcon className="h-4 w-4 text-text-tertiary" />
        )}
      </button>

      {/* Chat History (when expanded) */}
      {isExpanded && (
        <div className="flex-1 overflow-y-auto p-3 space-y-3 scrollbar-thin scrollbar-thumb-border-base scrollbar-track-transparent">
          {messages.length === 0 && !streamingMessage && (
            <div className="text-center py-8">
              <p className="text-sm text-text-muted">
                Ask questions about your documents
              </p>
            </div>
          )}

          {messages.map((message) => (
            <ChatMessage
              key={message.id}
              role={message.role}
              content={message.content}
              sources={message.sources}
            />
          ))}

          {streamingMessage && (
            <ChatMessage
              role="assistant"
              content={streamingMessage}
              isStreaming={true}
            />
          )}

          <div ref={messagesEndRef} />
        </div>
      )}

      {/* Input Area */}
      <div className="flex-shrink-0 p-3 border-t border-border-subtle bg-surface">
        {/* Include Drafts Toggle */}
        <div className="mb-2">
          <label className="flex items-center gap-2 text-xs text-text-tertiary hover:text-text-secondary cursor-pointer">
            <input
              type="checkbox"
              checked={includeDrafts}
              onChange={(e) => setIncludeDrafts(e.target.checked)}
              className="rounded border-border-base text-accent-primary focus:ring-accent-primary"
            />
            Include drafts in search
          </label>
        </div>

        {/* Input Field */}
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={isExpanded ? "Ask a question..." : "Chat with documents..."}
            disabled={isStreaming}
            rows={isExpanded ? 2 : 1}
            className="flex-1 px-3 py-2 bg-bg-base border border-border-base rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary resize-none"
          />
          <button
            onClick={onSendMessage}
            disabled={!input.trim() || isStreaming}
            className="flex-shrink-0 p-2 bg-accent-primary text-white rounded-lg hover:bg-accent-hover disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {isStreaming ? (
              <div className="h-5 w-5 animate-spin rounded-full border-2 border-white border-t-transparent" />
            ) : (
              <PaperAirplaneIcon className="h-5 w-5" />
            )}
          </button>
        </div>

        {!isExpanded && messages.length > 0 && (
          <p className="text-xs text-text-muted mt-2 text-center">
            Click header to view {messages.length} message{messages.length !== 1 ? 's' : ''}
          </p>
        )}
      </div>
    </div>
  )
}

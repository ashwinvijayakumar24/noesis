import { useState } from 'react'
import { ChevronDownIcon, ChevronUpIcon, DocumentTextIcon } from '@heroicons/react/24/outline'
import ReactMarkdown from 'react-markdown'

interface Source {
  citation_number?: number
  document_id: string
  document_title: string
  chunk_id: string
  similarity?: number
  content_preview?: string
  source_type?: 'draft' | 'literature'  // NEW: distinguish between draft and literature
  source_icon?: string  // NEW: emoji indicator (📄 or 📚)
}

interface ChatMessageProps {
  role: 'user' | 'assistant'
  content: string
  sources?: Source[]
  isStreaming?: boolean
}

// Citation component with hover tooltip
function Citation({ number, source }: { number: number; source?: Source }) {
  const [showTooltip, setShowTooltip] = useState(false)

  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <sup className="inline-block px-1 py-0.5 text-xs font-medium text-pink-400 hover:text-pink-300 cursor-pointer transition">
        [{number}]
      </sup>
      {showTooltip && source && (
        <div className="absolute z-50 bottom-full left-0 mb-2 w-64 p-3 bg-surface border border-pink-500/30 rounded-lg shadow-xl text-xs">
          <div className="font-semibold text-pink-400 mb-1 flex items-center gap-1">
            {source.source_icon && <span>{source.source_icon}</span>}
            {source.document_title}
          </div>
          {source.source_type && (
            <div className="text-xs text-text-tertiary mb-1">
              {source.source_type === 'draft' ? 'From your draft' : 'From literature'}
            </div>
          )}
          <div className="text-text-secondary">{source.content_preview}</div>
          {source.similarity && (
            <div className="text-text-muted mt-1 text-[10px]">
              {Math.round(source.similarity * 100)}% match
            </div>
          )}
        </div>
      )}
    </span>
  )
}

export default function ChatMessage({ role, content, sources, isStreaming }: ChatMessageProps) {
  const [showSources, setShowSources] = useState(false)

  const isUser = role === 'user'

  // Parse content to extract citations and build a map
  const parseCitationsFromContent = (text: string): Set<number> => {
    const citationPattern = /\[(\d+)\]/g
    const citations = new Set<number>()
    let match
    while ((match = citationPattern.exec(text)) !== null) {
      citations.add(parseInt(match[1]))
    }
    return citations
  }

  const usedCitations = parseCitationsFromContent(content)

  // Get sources that were actually cited
  const citedSources = sources?.filter(s => s.citation_number && usedCitations.has(s.citation_number)) || []

  // Group sources by document
  const groupedSources = sources?.reduce((acc, source) => {
    const docId = source.document_id
    if (!acc[docId]) {
      acc[docId] = {
        document_id: docId,
        document_title: source.document_title,
        chunks: [],
      }
    }
    acc[docId].chunks.push(source)
    return acc
  }, {} as Record<string, { document_id: string; document_title: string; chunks: Source[] }>)

  const uniqueDocuments = groupedSources ? Object.values(groupedSources) : []

  return (
    <div className="w-full">
      {/* Role Label */}
      <div className="mb-2">
        <span className={`text-base font-semibold ${isUser ? 'text-text-secondary' : 'text-pink-400'}`}>
          {isUser ? 'You' : 'Noesis'}
        </span>
      </div>

      {/* Message Content */}
      <div className="w-full">
        {/* Message Card */}
        <div
          className={`${
            isUser
              ? 'text-text-primary text-base'
              : 'bg-surface border border-border-base rounded-lg px-4 py-3 text-text-primary'
          }`}
        >
          <div className="text-base prose prose-invert prose-base max-w-none leading-relaxed">
            <ReactMarkdown
              components={{
                // Paragraphs - handle citations within text
                p: ({ children }) => {
                  const processChildren = (child: any): any => {
                    if (typeof child === 'string') {
                      // Replace citation markers [1], [2], etc. with Citation components
                      const parts = child.split(/(\[\d+\])/)
                      return parts.map((part, idx) => {
                        const match = part.match(/\[(\d+)\]/)
                        if (match) {
                          const citationNum = parseInt(match[1])
                          const source = sources?.find(s => s.citation_number === citationNum)
                          return <Citation key={`cite-${citationNum}-${idx}`} number={citationNum} source={source} />
                        }
                        return part
                      })
                    }
                    return child
                  }

                  return (
                    <p className="mb-3 last:mb-0 leading-relaxed text-base">
                      {Array.isArray(children) ? children.map(processChildren) : processChildren(children)}
                    </p>
                  )
                },
                // Bold text
                strong: ({ children }) => <strong className="font-bold text-text-primary">{children}</strong>,
                // Italic text
                em: ({ children }) => <em className="italic">{children}</em>,
                // Lists - improved spacing and formatting
                ul: ({ children }) => <ul className="list-disc list-outside ml-5 mb-3 space-y-1 text-base">{children}</ul>,
                ol: ({ children }) => <ol className="list-decimal list-outside ml-5 mb-3 space-y-1 text-base">{children}</ol>,
                li: ({ children }) => {
                  // Process children to handle nested content
                  const processChildren = (child: any): any => {
                    if (typeof child === 'string') {
                      const parts = child.split(/(\[\d+\])/)
                      return parts.map((part, idx) => {
                        const match = part.match(/\[(\d+)\]/)
                        if (match) {
                          const citationNum = parseInt(match[1])
                          const source = sources?.find(s => s.citation_number === citationNum)
                          return <Citation key={`cite-${citationNum}-${idx}`} number={citationNum} source={source} />
                        }
                        return part
                      })
                    }
                    return child
                  }

                  return (
                    <li className="leading-relaxed">
                      {Array.isArray(children) ? children.map(processChildren) : processChildren(children)}
                    </li>
                  )
                },
                // Code
                code: ({ children }) => <code className="bg-surface px-1.5 py-0.5 rounded text-pink-300">{children}</code>,
                // Links
                a: ({ href, children }) => (
                  <a href={href} className="text-pink-300 hover:text-pink-200 underline" target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
                // Headings - improved hierarchy and spacing
                h1: ({ children }) => <h1 className="text-2xl font-serif font-bold mb-3 mt-4 first:mt-0 text-text-primary">{children}</h1>,
                h2: ({ children }) => <h2 className="text-xl font-serif font-bold mb-2 mt-3 first:mt-0 text-text-primary">{children}</h2>,
                h3: ({ children }) => <h3 className="text-lg font-serif font-semibold mb-2 mt-2 first:mt-0 text-text-primary">{children}</h3>,
                h4: ({ children }) => <h4 className="text-base font-serif font-semibold mb-1 mt-2 first:mt-0 text-text-secondary">{children}</h4>,
                // Blockquotes
                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-pink-500 pl-4 my-3 italic text-text-secondary">
                    {children}
                  </blockquote>
                ),
                // Horizontal rule
                hr: () => <hr className="my-4 border-border-subtle" />,
              }}
            >
              {content}
            </ReactMarkdown>
            {isStreaming && <span className="inline-block w-1 h-4 ml-1 bg-current animate-pulse" />}

            {/* References Section */}
            {!isStreaming && citedSources.length > 0 && (
              <div className="mt-4 pt-3 border-t border-border-subtle">
                <div className="text-xs font-semibold text-text-tertiary mb-2">References:</div>
                <div className="space-y-1.5">
                  {citedSources.map((source) => (
                    <div
                      key={source.citation_number}
                      className="text-xs flex items-start gap-2 p-2 rounded transition hover:bg-surface-active/30"
                    >
                      <span className="font-mono text-pink-400 shrink-0">[{source.citation_number}]</span>
                      <div className="flex-1">
                        <div className="text-text-secondary font-medium flex items-center gap-1">
                          {source.source_icon && <span>{source.source_icon}</span>}
                          {source.document_title}
                        </div>
                        {source.source_type && (
                          <div className="text-text-tertiary text-[10px] mt-0.5">
                            {source.source_type === 'draft' ? 'From your draft' : 'From literature'}
                          </div>
                        )}
                        {source.similarity && (
                          <div className="text-text-muted mt-0.5">
                            {Math.round(source.similarity * 100)}% relevance
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Sources Section (AI only) */}
        {!isUser && sources && sources.length > 0 && (
          <div className="mt-4">
            <button
              onClick={() => setShowSources(!showSources)}
              className="flex items-center gap-2 text-xs text-text-tertiary hover:text-text-secondary transition"
            >
              {showSources ? (
                <ChevronUpIcon className="h-4 w-4" />
              ) : (
                <ChevronDownIcon className="h-4 w-4" />
              )}
              <DocumentTextIcon className="h-4 w-4" />
              <span>
                {uniqueDocuments.length} document{uniqueDocuments.length !== 1 ? 's' : ''} • {sources.length} chunk{sources.length !== 1 ? 's' : ''}
              </span>
            </button>

            {showSources && (
              <div className="mt-3 space-y-2">
                {uniqueDocuments.map((doc) => (
                  <div
                    key={doc.document_id}
                    className="text-xs bg-surface border border-border-base rounded-lg overflow-hidden"
                  >
                    {/* Document Header */}
                    <div className="px-3 py-2 bg-surface-hover border-b border-border-base flex items-center gap-2">
                      <DocumentTextIcon className="h-4 w-4 text-pink-400" />
                      <span className="text-text-secondary font-medium">{doc.document_title || 'Unknown Document'}</span>
                      <span className="ml-auto text-text-muted">
                        {doc.chunks.length} chunk{doc.chunks.length !== 1 ? 's' : ''}
                      </span>
                    </div>

                    {/* Chunks */}
                    <div className="px-3 py-2 space-y-1">
                      {doc.chunks.map((chunk, idx) => (
                        <div key={chunk.chunk_id || idx} className="text-text-tertiary flex items-center gap-2">
                          <span className="w-1 h-1 rounded-full bg-border-base"></span>
                          <span>Chunk {idx + 1}</span>
                          {chunk.similarity && (
                            <span className="ml-auto text-text-muted">
                              {Math.round(chunk.similarity * 100)}% match
                            </span>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

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

// Citation component with hover tooltip (neon-brutalist)
function Citation({ number, source }: { number: number; source?: Source }) {
  const [showTooltip, setShowTooltip] = useState(false)

  return (
    <span
      className="relative inline-block"
      onMouseEnter={() => setShowTooltip(true)}
      onMouseLeave={() => setShowTooltip(false)}
    >
      <sup className="inline-block px-1.5 py-0.5 text-xs font-mono font-bold text-accent-primary hover:text-accent-primary-bright cursor-pointer transition-colors duration-200">
        [{number}]
      </sup>
      {showTooltip && source && (
        <div className="absolute z-50 bottom-full left-0 mb-2 w-80 p-4 bg-bg-surface border-2 border-accent-primary/30 rounded-xl shadow-lg text-xs animate-fade-in-up">
          <div className="font-sans font-semibold text-accent-primary mb-2 flex items-center gap-2">
            {source.source_icon && <span className="text-base">{source.source_icon}</span>}
            <span className="line-clamp-1">{source.document_title}</span>
          </div>
          {source.source_type && (
            <div className="text-xs text-text-muted mb-2 font-mono uppercase tracking-wide">
              {source.source_type === 'draft' ? 'From your draft' : 'From literature'}
            </div>
          )}
          <div className="text-text-secondary leading-relaxed line-clamp-3">{source.content_preview}</div>
          {source.similarity && (
            <div className="mt-3 pt-2 border-t border-border-default">
              <div className="flex items-center justify-between">
                <span className="text-text-muted font-mono text-[10px] uppercase">Relevance</span>
                <span className="text-accent-primary font-mono font-bold">{Math.round(source.similarity * 100)}%</span>
              </div>
              <div className="h-1.5 bg-bg-void rounded-full overflow-hidden mt-1">
                <div
                  className="h-full bg-gradient-to-r from-accent-primary to-accent-teal transition-all duration-150"
                  style={{ width: `${Math.round(source.similarity * 100)}%` }}
                />
              </div>
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
      <div className="mb-3">
        <span className={`text-lg font-sans font-bold ${isUser ? 'text-text-secondary' : 'text-accent-primary'}`}>
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
              : 'bg-bg-elevated border border-border-default rounded-lg px-6 py-4 text-text-primary'
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
                code: ({ children }) => <code className="bg-bg-void px-2 py-1 rounded-md text-accent-primary font-mono text-sm border border-accent-primary/30">{children}</code>,
                // Links
                a: ({ href, children }) => (
                  <a href={href} className="text-accent-primary hover:text-accent-primary-bright underline decoration-accent-primary/30 hover:decoration-accent-primary transition-all duration-200" target="_blank" rel="noopener noreferrer">
                    {children}
                  </a>
                ),
                // Headings - gradient text and better spacing
                h1: ({ children }) => <h1 className="text-2xl font-sans font-bold mb-3 mt-4 first:mt-0 bg-gradient-to-r from-accent-primary to-accent-teal bg-clip-text text-transparent">{children}</h1>,
                h2: ({ children }) => <h2 className="text-xl font-sans font-bold mb-2 mt-3 first:mt-0 bg-gradient-to-r from-accent-primary to-accent-purple bg-clip-text text-transparent">{children}</h2>,
                h3: ({ children }) => <h3 className="text-lg font-sans font-semibold mb-2 mt-2 first:mt-0 text-accent-primary">{children}</h3>,
                h4: ({ children }) => <h4 className="text-base font-sans font-semibold mb-1 mt-2 first:mt-0 text-text-primary">{children}</h4>,
                // Blockquotes
                blockquote: ({ children }) => (
                  <blockquote className="border-l-4 border-accent-primary pl-4 my-3 italic text-text-secondary bg-accent-primary/5 py-2 rounded-r-lg">
                    {children}
                  </blockquote>
                ),
                // Horizontal rule
                hr: () => <hr className="my-4 border-border-default" />,
              }}
            >
              {content}
            </ReactMarkdown>
            {isStreaming && <span className="inline-block w-1 h-4 ml-1 bg-current animate-pulse" />}

            {/* References Section */}
            {!isStreaming && citedSources.length > 0 && (
              <div className="mt-4 pt-4 border-t border-border-default">
                <div className="text-sm font-sans font-semibold text-accent-primary mb-3">References:</div>
                <div className="space-y-2">
                  {citedSources.map((source) => (
                    <div
                      key={source.citation_number}
                      className="text-xs flex items-start gap-3 p-3 rounded-lg bg-bg-surface border border-border-default hover:border-accent-primary/30 transition-all duration-200"
                    >
                      <span className="font-mono font-bold text-accent-primary shrink-0">[{source.citation_number}]</span>
                      <div className="flex-1">
                        <div className="text-text-primary font-medium flex items-center gap-2 mb-1">
                          {source.source_icon && <span className="text-base">{source.source_icon}</span>}
                          <span>{source.document_title}</span>
                        </div>
                        {source.source_type && (
                          <div className="text-text-muted text-[10px] font-mono uppercase tracking-wide mb-1">
                            {source.source_type === 'draft' ? 'From your draft' : 'From literature'}
                          </div>
                        )}
                        {source.similarity && (
                          <div className="flex items-center gap-2 mt-1">
                            <div className="flex-1 h-1 bg-bg-void rounded-full overflow-hidden">
                              <div
                                className="h-full bg-gradient-to-r from-accent-primary to-accent-teal"
                                style={{ width: `${Math.round(source.similarity * 100)}%` }}
                              />
                            </div>
                            <span className="text-accent-primary font-mono font-bold text-[10px]">
                              {Math.round(source.similarity * 100)}%
                            </span>
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
              className="flex items-center gap-2 text-sm text-text-secondary hover:text-accent-primary transition-colors duration-200 font-medium"
            >
              {showSources ? (
                <ChevronUpIcon className="h-5 w-5" />
              ) : (
                <ChevronDownIcon className="h-5 w-5" />
              )}
              <DocumentTextIcon className="h-5 w-5" />
              <span>
                {uniqueDocuments.length} document{uniqueDocuments.length !== 1 ? 's' : ''} • {sources.length} chunk{sources.length !== 1 ? 's' : ''}
              </span>
            </button>

            {showSources && (
              <div className="mt-3 space-y-3">
                {uniqueDocuments.map((doc) => (
                  <div
                    key={doc.document_id}
                    className="text-xs bg-bg-surface border border-border-default rounded-xl overflow-hidden"
                  >
                    {/* Document Header */}
                    <div className="px-4 py-3 bg-bg-elevated border-b border-border-default flex items-center gap-3">
                      <DocumentTextIcon className="h-5 w-5 text-accent-primary" />
                      <span className="text-text-primary font-sans font-semibold flex-1">{doc.document_title || 'Unknown Document'}</span>
                      <span className="text-text-muted font-mono text-xs">
                        {doc.chunks.length} chunk{doc.chunks.length !== 1 ? 's' : ''}
                      </span>
                    </div>

                    {/* Chunks */}
                    <div className="px-4 py-3 space-y-2">
                      {doc.chunks.map((chunk, idx) => (
                        <div key={chunk.chunk_id || idx} className="text-text-secondary flex items-center gap-3 pl-2">
                          <span className="w-1.5 h-1.5 rounded-full bg-accent-primary"></span>
                          <span className="flex-1">Chunk {idx + 1}</span>
                          {chunk.similarity && (
                            <span className="font-mono font-bold text-accent-primary text-xs">
                              {Math.round(chunk.similarity * 100)}%
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

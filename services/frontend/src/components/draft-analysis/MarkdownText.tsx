import type { ReactNode } from 'react'

interface MarkdownTextProps {
  text: string
  className?: string
  as?: 'span' | 'p'
}

type Segment =
  | { type: 'text'; value: string }
  | { type: 'bold' | 'italic'; value: string }

const INLINE_MARKDOWN_RE = /(\*\*[^*]+\*\*|__[^_]+__|\*[^*\s][^*]*[^*\s]\*|_[^_\s][^_]*[^_\s]_)/g

function parseInlineMarkdown(text: string): Segment[] {
  const segments: Segment[] = []
  let cursor = 0

  for (const match of text.matchAll(INLINE_MARKDOWN_RE)) {
    const raw = match[0]
    const index = match.index ?? 0

    if (index > cursor) {
      segments.push({ type: 'text', value: text.slice(cursor, index) })
    }

    if ((raw.startsWith('**') && raw.endsWith('**')) || (raw.startsWith('__') && raw.endsWith('__'))) {
      segments.push({ type: 'bold', value: raw.slice(2, -2) })
    } else {
      segments.push({ type: 'italic', value: raw.slice(1, -1) })
    }

    cursor = index + raw.length
  }

  if (cursor < text.length) {
    segments.push({ type: 'text', value: text.slice(cursor) })
  }

  return segments
}

function renderSegments(text: string): ReactNode[] {
  return parseInlineMarkdown(text).map((segment, index) => {
    if (segment.type === 'bold') {
      return <strong key={index} className="font-semibold text-text-primary">{segment.value}</strong>
    }
    if (segment.type === 'italic') {
      return <em key={index} className="italic">{segment.value}</em>
    }
    return segment.value
  })
}

export default function MarkdownText({ text, className, as = 'span' }: MarkdownTextProps) {
  const content = renderSegments(text || '')

  if (as === 'p') {
    return <p className={className}>{content}</p>
  }

  return <span className={className}>{content}</span>
}

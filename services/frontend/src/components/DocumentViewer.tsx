import { useState, useEffect, useRef, useImperativeHandle, forwardRef, useMemo } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/esm/Page/AnnotationLayer.css'
import 'react-pdf/dist/esm/Page/TextLayer.css'
import { MagnifyingGlassPlusIcon, MagnifyingGlassMinusIcon, ChevronLeftIcon, ChevronRightIcon } from '@heroicons/react/24/outline'

// Configure PDF.js worker
pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

interface Annotation {
  id?: string
  line_number?: number
  char_start?: number
  char_end?: number
  text_snippet?: string
  color?: string
  // Enhanced location tracking fields
  section_id?: string
  char_offset_from_section?: number
  pdf_coordinates?: {
    page: number
    x: number
    y: number
    width: number
    height: number
  }
  match_confidence?: number
}

interface DocumentViewerProps {
  fileUrl: string
  fileType: string
  annotation?: Annotation | null
  onLineClick?: (lineNumber: number) => void
  authToken?: string
}

export interface DocumentViewerRef {
  scrollToLine: (lineNumber: number) => void
}

// Fuzzy text matching utility (Levenshtein distance)
const fuzzyMatch = (text: string, snippet: string, threshold = 0.8): { start: number, end: number } | null => {
  const normalizeText = (s: string) => s.toLowerCase().trim().replace(/\s+/g, ' ')
  const normalized = normalizeText(text)
  const normalizedSnippet = normalizeText(snippet)

  // Try exact match first
  const exactIndex = normalized.indexOf(normalizedSnippet)
  if (exactIndex !== -1) {
    return { start: exactIndex, end: exactIndex + normalizedSnippet.length }
  }

  // Sliding window for fuzzy match
  const windowSize = normalizedSnippet.length
  let bestMatch = { similarity: 0, start: -1, end: -1 }

  for (let i = 0; i <= normalized.length - windowSize; i++) {
    const window = normalized.substring(i, i + windowSize)
    const similarity = calculateSimilarity(window, normalizedSnippet)
    if (similarity > bestMatch.similarity) {
      bestMatch = { similarity, start: i, end: i + windowSize }
    }
  }

  return bestMatch.similarity >= threshold
    ? { start: bestMatch.start, end: bestMatch.end }
    : null
}

// Levenshtein similarity (1.0 = perfect match, 0.0 = no match)
const calculateSimilarity = (s1: string, s2: string): number => {
  const longer = s1.length > s2.length ? s1 : s2
  const shorter = s1.length > s2.length ? s2 : s1

  if (longer.length === 0) return 1.0

  const editDistance = levenshteinDistance(longer, shorter)
  return (longer.length - editDistance) / longer.length
}

const levenshteinDistance = (s1: string, s2: string): number => {
  const matrix = Array.from({ length: s2.length + 1 }, (_, i) => [i])
  matrix[0] = Array.from({ length: s1.length + 1 }, (_, i) => i)

  for (let i = 1; i <= s2.length; i++) {
    for (let j = 1; j <= s1.length; j++) {
      const cost = s1[j - 1] === s2[i - 1] ? 0 : 1
      matrix[i][j] = Math.min(
        matrix[i - 1][j] + 1,
        matrix[i][j - 1] + 1,
        matrix[i - 1][j - 1] + cost
      )
    }
  }

  return matrix[s2.length][s1.length]
}

const DocumentViewer = forwardRef<DocumentViewerRef, DocumentViewerProps>((
  { fileUrl, fileType, annotation, onLineClick, authToken },
  ref
) => {
  const [numPages, setNumPages] = useState<number>(0)
  const [currentPage, setCurrentPage] = useState<number>(1)
  const [scale, setScale] = useState<number>(1.0)
  const [lines, setLines] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const lineRefs = useRef<(HTMLDivElement | null)[]>([])

  // Debug logging
  console.log('[DocumentViewer] Rendering with props:', { fileUrl, fileType, hasAnnotation: !!annotation })

  // Memoize file and options props to prevent unnecessary reloads
  const fileConfig = useMemo(() => ({
    url: fileUrl,
    httpHeaders: authToken ? { 'Authorization': `Bearer ${authToken}` } : undefined
  }), [fileUrl, authToken])

  const pdfOptions = useMemo(() => ({
    cMapUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/standard_fonts/`,
  }), [])

  const onDocumentLoadSuccess = ({ numPages }: { numPages: number }) => {
    console.log('[DocumentViewer] PDF loaded successfully with', numPages, 'pages')
    setNumPages(numPages)
    setLoading(false)
  }

  const onDocumentLoadError = (error: Error) => {
    console.error('[DocumentViewer] Error loading document:', error)
    console.error('[DocumentViewer] File URL:', fileUrl)
    console.error('[DocumentViewer] File Type:', fileType)
    setLoading(false)
  }

  // Load text content for TXT files
  useEffect(() => {
    if (fileType === 'text/plain' || fileType === 'txt') {
      console.log('[DocumentViewer] Loading TXT file from URL:', fileUrl.substring(0, 100) + '...')
      const loadTextContent = async () => {
        try {
          const response = await fetch(fileUrl)
          if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`)
          }
          const text = await response.text()
          setLines(text.split('\n'))
          setLoading(false)
          console.log('[DocumentViewer] ✓ TXT file loaded successfully, lines:', text.split('\n').length)
        } catch (error) {
          console.error('[DocumentViewer] ✗ Error loading text file:', error)
          console.error('[DocumentViewer] Failed URL:', fileUrl)
          setLines(['Error loading file. Please check browser console for details.'])
          setLoading(false)
        }
      }
      loadTextContent()
    } else if (fileType === 'application/pdf' || fileType === 'pdf') {
      // For PDFs, set loading to false immediately so the PDF viewer can render
      // The PDF component has its own loading state
      setLoading(false)
    } else {
      // For other file types, also set loading to false
      setLoading(false)
    }
  }, [fileUrl, fileType])

  // Expose scrollToLine via ref
  useImperativeHandle(ref, () => ({
    scrollToLine: (lineNumber: number) => {
      const lineRef = lineRefs.current[lineNumber - 1]
      if (lineRef) {
        lineRef.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }
    }
  }))

  // Auto-scroll when annotation changes
  useEffect(() => {
    if (annotation) {
      // Strategy 1: Section-based scrolling (future implementation)
      // TODO: Implement section-based scrolling when sections are rendered

      // Strategy 2: PDF coordinate-based scrolling (future implementation)
      // TODO: Implement PDF coordinate-based scrolling

      // Strategy 3: Line-based scrolling (fallback)
      if (annotation.line_number) {
        const lineRef = lineRefs.current[annotation.line_number - 1]
        if (lineRef) {
          lineRef.scrollIntoView({ behavior: 'smooth', block: 'center' })
        }
      }
    }
  }, [annotation])

  const zoomIn = () => {
    setScale((prev) => Math.min(2.0, prev + 0.1))
  }

  const zoomOut = () => {
    setScale((prev) => Math.max(0.5, prev - 0.1))
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-white rounded-lg border border-border-default">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary"></div>
          <p className="mt-2 text-sm text-text-tertiary">Loading document...</p>
        </div>
      </div>
    )
  }

  if (fileType === 'text/plain' || fileType === 'txt') {
    return (
      <div className="h-full flex flex-col bg-white rounded-lg border border-border-default">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-default bg-surface">
          <span className="text-xs text-text-tertiary font-mono">TXT Document ({lines.length} lines)</span>
          <div className="flex items-center gap-2">
            <button
              onClick={zoomOut}
              className="p-1 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors"
              title="Zoom Out"
            >
              <MagnifyingGlassMinusIcon className="h-4 w-4" />
            </button>
            <span className="text-xs text-text-muted font-mono">{Math.round(scale * 100)}%</span>
            <button
              onClick={zoomIn}
              className="p-1 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors"
              title="Zoom In"
            >
              <MagnifyingGlassPlusIcon className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* Line-by-line Content with Highlighting */}
        <div className="flex-1 overflow-auto bg-bg-base" style={{ fontSize: `${scale}em` }}>
          {lines.map((line, index) => {
            const lineNumber = index + 1
            const isHighlightLine = annotation && annotation.line_number === lineNumber

            let highlightRange: { start: number, end: number } | null = null
            if (isHighlightLine) {
              // First try exact character positions
              if (annotation.char_start !== undefined && annotation.char_end !== undefined) {
                highlightRange = { start: annotation.char_start, end: annotation.char_end }
              } else if (annotation.text_snippet) {
                // Fallback to fuzzy matching with text_snippet
                highlightRange = fuzzyMatch(line, annotation.text_snippet)
              }
            }

            return (
              <div
                key={lineNumber}
                ref={el => { lineRefs.current[index] = el }}
                onClick={() => onLineClick?.(lineNumber)}
                className={`flex border-b border-border-default ${
                  isHighlightLine ? 'bg-yellow-50' : 'hover:bg-surface-hover'
                } ${onLineClick ? 'cursor-pointer' : ''} transition-colors`}
              >
                <span className="px-4 py-1 text-text-muted select-none min-w-[60px] text-right font-mono text-xs">
                  {lineNumber}
                </span>
                <span className="px-4 py-1 flex-1 font-mono text-sm">
                  {highlightRange && annotation ? (
                    <>
                      {line.substring(0, highlightRange.start)}
                      <mark className={`${
                        annotation.color
                          ? `bg-${annotation.color}-200 ring-2 ring-${annotation.color}-400`
                          : 'bg-yellow-200 ring-2 ring-yellow-400'
                      } rounded px-0.5`}>
                        {line.substring(highlightRange.start, highlightRange.end)}
                      </mark>
                      {line.substring(highlightRange.end)}
                    </>
                  ) : (
                    line || '\u00A0' // Non-breaking space for empty lines
                  )}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (fileType === 'application/pdf' || fileType === 'pdf') {
    const goToPreviousPage = () => setCurrentPage(prev => Math.max(1, prev - 1))
    const goToNextPage = () => setCurrentPage(prev => Math.min(numPages, prev + 1))

    return (
      <div className="h-full flex flex-col bg-surface rounded-lg border border-border-default">
        {/* Toolbar */}
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-default bg-surface">
          <span className="text-xs text-text-tertiary font-mono">
            {numPages > 0 ? `Page ${currentPage} of ${numPages}` : 'Loading...'}
          </span>

          <div className="flex items-center gap-2">
            <button
              onClick={zoomOut}
              className="p-1 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors"
              title="Zoom Out"
            >
              <MagnifyingGlassMinusIcon className="h-4 w-4" />
            </button>
            <span className="text-xs text-text-muted font-mono">{Math.round(scale * 100)}%</span>
            <button
              onClick={zoomIn}
              className="p-1 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors"
              title="Zoom In"
            >
              <MagnifyingGlassPlusIcon className="h-4 w-4" />
            </button>
          </div>
        </div>

        {/* PDF Content - Single Page with Navigation */}
        <div className="flex-1 overflow-auto bg-surface">
          <div className="flex flex-col items-center min-h-full p-4">
            <div className="flex-1 flex items-start justify-center w-full">
              <Document
                key={fileUrl}
                file={fileConfig}
                onLoadSuccess={onDocumentLoadSuccess}
                onLoadError={onDocumentLoadError}
                options={pdfOptions}
                loading={
                  <div className="text-center py-12">
                    <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary"></div>
                    <p className="mt-2 text-xs text-text-tertiary">Loading PDF...</p>
                  </div>
                }
                error={
                  <div className="text-center py-12">
                    <p className="text-error font-medium">Failed to load PDF</p>
                    <p className="text-xs text-text-tertiary mt-2">Please try refreshing the page</p>
                  </div>
                }
              >
                <Page
                  pageNumber={currentPage}
                  scale={scale}
                  renderTextLayer={true}
                  renderAnnotationLayer={true}
                  className="shadow-lg"
                />
              </Document>
            </div>

            {/* Page Navigation Arrows */}
            {numPages > 1 && (
              <div className="flex items-center gap-4 mt-4 pb-4">
                <button
                  onClick={goToPreviousPage}
                  disabled={currentPage === 1}
                  className={`
                    flex items-center gap-2 px-4 py-2 rounded-lg border font-medium transition-colors
                    ${currentPage === 1
                      ? 'border-slate-700 text-slate-600 cursor-not-allowed'
                      : 'border-slate-600 text-slate-300 hover:bg-slate-800 hover:border-slate-500'
                    }
                  `}
                  title="Previous Page"
                >
                  <ChevronLeftIcon className="h-4 w-4" />
                  <span className="text-sm">Previous</span>
                </button>

                <span className="text-sm text-slate-400 font-mono">
                  {currentPage} / {numPages}
                </span>

                <button
                  onClick={goToNextPage}
                  disabled={currentPage === numPages}
                  className={`
                    flex items-center gap-2 px-4 py-2 rounded-lg border font-medium transition-colors
                    ${currentPage === numPages
                      ? 'border-slate-700 text-slate-600 cursor-not-allowed'
                      : 'border-slate-600 text-slate-300 hover:bg-slate-800 hover:border-slate-500'
                    }
                  `}
                  title="Next Page"
                >
                  <span className="text-sm">Next</span>
                  <ChevronRightIcon className="h-4 w-4" />
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex items-center justify-center h-full bg-white rounded-lg border border-border-default">
      <p className="text-text-tertiary">Unsupported file type: {fileType}</p>
    </div>
  )
})

DocumentViewer.displayName = 'DocumentViewer'

export default DocumentViewer

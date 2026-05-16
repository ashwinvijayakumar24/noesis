import { useState, useEffect, useRef, useImperativeHandle, forwardRef, useMemo, useCallback } from 'react'
import { Document, Page, pdfjs } from 'react-pdf'
import 'react-pdf/dist/esm/Page/AnnotationLayer.css'
import 'react-pdf/dist/esm/Page/TextLayer.css'
import { MagnifyingGlassPlusIcon, MagnifyingGlassMinusIcon, XMarkIcon } from '@heroicons/react/24/outline'

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`

export interface PdfCoordinates {
  page: number
  x: number
  y: number
  width: number
  height: number
}

interface Annotation {
  id?: string
  line_number?: number
  char_start?: number
  char_end?: number
  text_snippet?: string
  color?: string
  section_id?: string
  char_offset_from_section?: number
  pdf_coordinates?: PdfCoordinates
  match_confidence?: number
}

interface DocumentViewerProps {
  fileUrl: string
  fileType: string
  annotation?: Annotation | null
  onLineClick?: (lineNumber: number) => void
  authToken?: string
  initialScale?: number
}

export interface DocumentViewerRef {
  scrollToLine: (lineNumber: number) => void
  scrollToPage: (page: number) => void
  highlightText: (snippet: string, page?: number, headingMode?: boolean) => void
  highlightRegion: (coordinates: PdfCoordinates) => void
  clearHighlight: () => void
}

// ─── Extracted page structure ────────────────────────────────────────────────
interface ExtractedPage {
  concat: string    // full text joined (lowercase) — for page-level search
  items: string[]   // individual pdf.js text items — for span-level search
}

interface PdfPageDimensions {
  width: number
  height: number
}

// ─── Client-side search ───────────────────────────────────────────────────────
// Normalize the way pdf.js does: collapse whitespace, strip soft hyphens.
function normalizeForSearch(s: string): string {
  return s
    .replace(/­/g, '')   // soft hyphen
    .replace(/\s+/g, ' ')
    .toLowerCase()
    .trim()
}

// Find the shortest substring of `snippet` that fits inside a single pdf.js span
// on some page. Returns { target, pageNum } or null.
function findBestTarget(
  snippet: string,
  pages: ExtractedPage[],
): { target: string; pageNum: number } | null {
  const norm = normalizeForSearch(snippet)

  // Candidates: try from start of snippet with decreasing lengths,
  // then sliding windows from later positions (to skip analytical preamble).
  const candidates: string[] = []
  for (const len of [40, 30, 20, 15, 10]) {
    if (norm.slice(0, len).length >= 8) candidates.push(norm.slice(0, len))
  }
  // Sliding windows starting at 1/4 and 1/2 of the snippet (skip preamble like "The author argues")
  const q = Math.floor(norm.length / 4)
  const h = Math.floor(norm.length / 2)
  for (const start of [q, h]) {
    for (const len of [30, 20, 15]) {
      const c = norm.slice(start, start + len)
      if (c.length >= 8) candidates.push(c)
    }
  }

  for (const candidate of candidates) {
    for (let p = 0; p < pages.length; p++) {
      // Check single-item match first (guarantees highlight works in one span)
      const itemMatch = pages[p].items.some(item =>
        normalizeForSearch(item).includes(candidate)
      )
      if (itemMatch) return { target: candidate, pageNum: p + 1 }

      // Fall back: concatenated text match (span may split across items but worth trying)
      if (pages[p].concat.includes(candidate)) {
        return { target: candidate, pageNum: p + 1 }
      }
    }
  }
  return null
}

// ─── TXT fuzzy match (Levenshtein) ──────────────────────────────────────────
const fuzzyMatch = (text: string, snippet: string, threshold = 0.8): { start: number; end: number } | null => {
  const norm = (s: string) => s.toLowerCase().trim().replace(/\s+/g, ' ')
  const t = norm(text)
  const q = norm(snippet)
  const exact = t.indexOf(q)
  if (exact !== -1) return { start: exact, end: exact + q.length }
  const ws = q.length
  let best = { sim: 0, start: -1, end: -1 }
  for (let i = 0; i <= t.length - ws; i++) {
    const w = t.substring(i, i + ws)
    const longer = w.length > q.length ? w : q
    const shorter = w.length > q.length ? q : w
    if (longer.length === 0) continue
    const mat = Array.from({ length: shorter.length + 1 }, (_, r) =>
      Array.from({ length: longer.length + 1 }, (_, c) => (r === 0 ? c : c === 0 ? r : 0))
    )
    for (let r = 1; r <= shorter.length; r++) {
      for (let c = 1; c <= longer.length; c++) {
        mat[r][c] = shorter[r - 1] === longer[c - 1]
          ? mat[r - 1][c - 1]
          : 1 + Math.min(mat[r - 1][c], mat[r][c - 1], mat[r - 1][c - 1])
      }
    }
    const sim = (longer.length - mat[shorter.length][longer.length]) / longer.length
    if (sim > best.sim) best = { sim, start: i, end: i + ws }
  }
  return best.sim >= threshold ? { start: best.start, end: best.end } : null
}

// ─── Scroll helpers ──────────────────────────────────────────────────────────
function scrollToMark(pageDiv: HTMLDivElement, maxMs = 2500) {
  const t0 = Date.now()
  const id = setInterval(() => {
    const m = pageDiv.querySelector('mark')
    if (m) { clearInterval(id); m.scrollIntoView({ behavior: 'smooth', block: 'center' }) }
    else if (Date.now() - t0 > maxMs) clearInterval(id)
  }, 80)
}

function scrollToMarkAcrossPages(divs: (HTMLDivElement | null)[], maxMs = 3500) {
  const t0 = Date.now()
  const id = setInterval(() => {
    for (const div of divs) {
      if (!div) continue
      const m = div.querySelector('mark')
      if (m) { clearInterval(id); m.scrollIntoView({ behavior: 'smooth', block: 'center' }); return }
    }
    if (Date.now() - t0 > maxMs) clearInterval(id)
  }, 80)
}

// ─── Component ───────────────────────────────────────────────────────────────
const DocumentViewer = forwardRef<DocumentViewerRef, DocumentViewerProps>((
  { fileUrl, fileType, annotation, onLineClick, authToken, initialScale = 1.0 },
  ref,
) => {
  const [numPages, setNumPages] = useState(0)
  const [currentPage, setCurrentPage] = useState(1)
  const [scale, setScale] = useState(initialScale)
  const [lines, setLines] = useState<string[]>([])
  const [loading, setLoading] = useState(true)

  // Highlight state
  const [activeSnippet, setActiveSnippet] = useState<string | null>(null)
  const [activeSearchTarget, setActiveSearchTarget] = useState<string>('')
  const [searchAllPages, setSearchAllPages] = useState(false)
  const [headingSearchMode, setHeadingSearchMode] = useState(false)
  const [highlightedLines, setHighlightedLines] = useState<Set<number>>(new Set())
  const [activeRegion, setActiveRegion] = useState<PdfCoordinates | null>(null)
  const [pageDimensions, setPageDimensions] = useState<Record<number, PdfPageDimensions>>({})

  // Client-side extracted page text (same extractor as the renderer → perfect match)
  const [extractedPages, setExtractedPages] = useState<ExtractedPage[]>([])
  // Pending highlight: if highlightText called before extraction finishes, replay after.
  const pendingHighlightRef = useRef<{ snippet: string; pageHint?: number; headingMode: boolean } | null>(null)

  const lineRefs = useRef<(HTMLDivElement | null)[]>([])
  const pageRefs = useRef<(HTMLDivElement | null)[]>([])

  useEffect(() => {
    setScale(initialScale)
  }, [initialScale])

  // ── Extract text from all pages using pdf.js (same engine as the renderer) ──
  const extractPageTexts = useCallback(async (pdf: any) => {
    const pages: ExtractedPage[] = []
    for (let i = 1; i <= pdf.numPages; i++) {
      try {
        const page = await pdf.getPage(i)
        const content = await page.getTextContent()
        const items: string[] = content.items
          .map((item: any) => (item.str as string) ?? '')
          .filter(Boolean)
        pages.push({ concat: items.map(s => normalizeForSearch(s)).join(' '), items })
      } catch {
        pages.push({ concat: '', items: [] })
      }
    }
    setExtractedPages(pages)

    // Replay any pending highlight that arrived before extraction finished
    if (pendingHighlightRef.current) {
      const { snippet, pageHint, headingMode } = pendingHighlightRef.current
      pendingHighlightRef.current = null
      applyHighlight(snippet, pageHint, headingMode, pages)
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const onDocumentLoadSuccess = useCallback((pdf: any) => {
    setNumPages(pdf.numPages)
    setLoading(false)
    extractPageTexts(pdf)
  }, [extractPageTexts])

  const onDocumentLoadError = (error: Error) => {
    console.error('[DocumentViewer] Error loading document:', error)
    setLoading(false)
  }

  const onPageLoadSuccess = useCallback((page: any) => {
    const viewport = page.getViewport({ scale: 1 })
    const pageNumber = page.pageNumber
    setPageDimensions(prev => {
      const next = { width: viewport.width, height: viewport.height }
      const existing = prev[pageNumber]
      if (existing && existing.width === next.width && existing.height === next.height) {
        return prev
      }
      return { ...prev, [pageNumber]: next }
    })
  }, [])

  // ── Core highlight logic ──────────────────────────────────────────────────
  const applyHighlight = useCallback((
    snippet: string,
    pageHint: number | undefined,
    isHeadingMode: boolean,
    pages: ExtractedPage[],
  ) => {
    setActiveRegion(null)
    setActiveSnippet(snippet || null)
    setHeadingSearchMode(isHeadingMode)

    if (!snippet) {
      setActiveSearchTarget('')
      setSearchAllPages(false)
      return
    }

    // For section headings: use heading mode (exact span match)
    if (isHeadingMode) {
      setActiveSearchTarget(normalizeForSearch(snippet).slice(0, 40))
      setSearchAllPages(true)
      setTimeout(() => scrollToMarkAcrossPages(pageRefs.current), 100)
      return
    }

    // Client-side search: find best single-span target + correct page
    if (pages.length > 0) {
      const result = findBestTarget(snippet, pages)
      if (result) {
        setActiveSearchTarget(result.target)
        setSearchAllPages(false)
        setCurrentPage(result.pageNum)
        const idx = result.pageNum - 1
        setTimeout(() => {
          const div = pageRefs.current[idx]
          if (!div) return
          div.scrollIntoView({ behavior: 'smooth', block: 'start' })
          scrollToMark(div)
        }, 150)
        return
      }
    }

    // Fallback: use hint page or search all pages with first-40-chars target
    const fallbackTarget = normalizeForSearch(snippet).slice(0, 40)
    setActiveSearchTarget(fallbackTarget)
    if (pageHint) {
      setSearchAllPages(false)
      const idx = Math.max(0, Math.min((numPages || 1) - 1, pageHint - 1))
      setCurrentPage(pageHint)
      setTimeout(() => {
        const div = pageRefs.current[idx]
        if (!div) return
        div.scrollIntoView({ behavior: 'smooth', block: 'start' })
        if (snippet) scrollToMark(div)
      }, 100)
    } else {
      setSearchAllPages(true)
      setTimeout(() => scrollToMarkAcrossPages(pageRefs.current), 100)
    }
  }, [numPages])

  // ── Load TXT files ────────────────────────────────────────────────────────
  useEffect(() => {
    if (fileType === 'text/plain' || fileType === 'txt') {
      const load = async () => {
        try {
          const r = await fetch(fileUrl)
          if (!r.ok) throw new Error(`HTTP ${r.status}`)
          setLines((await r.text()).split('\n'))
          setLoading(false)
        } catch {
          setLines(['Error loading file.'])
          setLoading(false)
        }
      }
      load()
    } else {
      setLoading(false)
    }
  }, [fileUrl, fileType])

  // ── TXT line highlighting ─────────────────────────────────────────────────
  useEffect(() => {
    if (!activeSnippet || lines.length === 0) { setHighlightedLines(new Set()); return }
    const matched = new Set<number>()
    lines.forEach((line, i) => { if (fuzzyMatch(line, activeSnippet)) matched.add(i + 1) })
    setHighlightedLines(matched)
  }, [activeSnippet, lines])

  // ── Imperative API ────────────────────────────────────────────────────────
  useImperativeHandle(ref, () => ({
    scrollToLine: (lineNumber: number) => {
      lineRefs.current[lineNumber - 1]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    },
    scrollToPage: (page: number) => {
      const idx = Math.max(0, Math.min((numPages || 1) - 1, page - 1))
      setCurrentPage(page)
      pageRefs.current[idx]?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    },
    highlightText: (snippet: string, page?: number, headingMode = false) => {
      if (extractedPages.length === 0 && (fileType === 'application/pdf' || fileType === 'pdf')) {
        // Extraction not done yet — queue and replay after extraction
        pendingHighlightRef.current = { snippet, pageHint: page, headingMode }
        return
      }
      applyHighlight(snippet, page, headingMode, extractedPages)
    },
    highlightRegion: (coordinates: PdfCoordinates) => {
      const page = Math.max(1, coordinates.page)
      setActiveRegion(coordinates)
      setActiveSnippet(null)
      setActiveSearchTarget('')
      setSearchAllPages(false)
      setHeadingSearchMode(false)
      setCurrentPage(page)
      setTimeout(() => {
        const div = pageRefs.current[page - 1]
        div?.scrollIntoView({ behavior: 'smooth', block: 'center' })
      }, 120)
    },
    clearHighlight: () => {
      setActiveSnippet(null)
      setActiveSearchTarget('')
      setSearchAllPages(false)
      setHeadingSearchMode(false)
      setActiveRegion(null)
    },
  }))

  // Clear highlight when annotation removed
  useEffect(() => {
    if (annotation?.line_number) {
      lineRefs.current[annotation.line_number - 1]?.scrollIntoView({ behavior: 'smooth', block: 'center' })
    } else if (!annotation) {
      setActiveSnippet(null)
      setActiveSearchTarget('')
      setSearchAllPages(false)
      setHeadingSearchMode(false)
      setActiveRegion(null)
    }
  }, [annotation])

  // ── PDF customTextRenderer ────────────────────────────────────────────────
  // Uses activeSearchTarget (found via client-side extraction) — guaranteed to be
  // in a single span on currentPage. Falls back to substring mode on heading mode.
  const customTextRenderer = useMemo(() => {
    if (!activeSnippet || !activeSearchTarget) return undefined
    const target = activeSearchTarget // already normalized
    if (target.length < 4) return undefined
    const HL = 'background-color:rgba(253,224,71,0.65);border-radius:2px;padding:0 1px;color:inherit'

    return ({ str }: { str: string }) => {
      if (str.length < 2) return str
      const lStr = normalizeForSearch(str)

      if (searchAllPages && headingSearchMode) {
        // Heading mode: span text must be close to section name
        const t = lStr.trim()
        const sLen = str.trim().length
        const match =
          t === target ||
          (t.endsWith(target) && sLen <= target.length + 12) ||
          (t.startsWith(target) && sLen <= target.length + 4)
        if (!match) return str
        return `<mark style="${HL}">${str}</mark>`
      }

      // Substring mode: find target within this span
      const idx = lStr.indexOf(target)
      if (idx === -1) return str
      // Map back to original string offsets (normalizeForSearch may differ in length
      // only due to soft hyphens; safe to use idx directly for typical content)
      const before = str.slice(0, idx)
      const matched = str.slice(idx, idx + target.length)
      const after = str.slice(idx + target.length)
      return `${before}<mark style="${HL}">${matched}</mark>${after}`
    }
  }, [activeSnippet, activeSearchTarget, searchAllPages, headingSearchMode])

  const fileConfig = useMemo(() => ({
    url: fileUrl,
    httpHeaders: authToken ? { Authorization: `Bearer ${authToken}` } : undefined,
  }), [fileUrl, authToken])

  const pdfOptions = useMemo(() => ({
    cMapUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/cmaps/`,
    cMapPacked: true,
    standardFontDataUrl: `https://unpkg.com/pdfjs-dist@${pdfjs.version}/standard_fonts/`,
  }), [])

  const zoomIn = () => setScale(p => Math.min(2.0, p + 0.1))
  const zoomOut = () => setScale(p => Math.max(0.5, p - 0.1))

  // ── Render ────────────────────────────────────────────────────────────────
  if (loading) {
    return (
      <div className="flex items-center justify-center h-full bg-white rounded-lg border border-border-default">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary" />
          <p className="mt-2 text-sm text-text-tertiary">Loading document...</p>
        </div>
      </div>
    )
  }

  if (fileType === 'text/plain' || fileType === 'txt') {
    return (
      <div className="h-full flex flex-col bg-white rounded-lg border border-border-default">
        <div className="flex items-center justify-between px-4 py-2 border-b border-border-default bg-surface">
          <span className="text-xs text-text-tertiary font-mono">TXT Document ({lines.length} lines)</span>
          <div className="flex items-center gap-2">
            <button onClick={zoomOut} className="p-1 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors">
              <MagnifyingGlassMinusIcon className="h-4 w-4" />
            </button>
            <span className="text-xs text-text-muted font-mono">{Math.round(scale * 100)}%</span>
            <button onClick={zoomIn} className="p-1 text-text-tertiary hover:text-text-primary hover:bg-surface-hover rounded transition-colors">
              <MagnifyingGlassPlusIcon className="h-4 w-4" />
            </button>
          </div>
        </div>
        <div className="flex-1 overflow-auto bg-bg-base" style={{ fontSize: `${scale}em` }}>
          {lines.map((line, index) => {
            const lineNumber = index + 1
            const isHighlight = (annotation?.line_number === lineNumber) || highlightedLines.has(lineNumber)
            let hlRange: { start: number; end: number } | null = null
            if (isHighlight) {
              if (annotation?.char_start != null && annotation?.char_end != null) {
                hlRange = { start: annotation.char_start, end: annotation.char_end }
              } else {
                const q = activeSnippet ?? annotation?.text_snippet ?? null
                if (q) hlRange = fuzzyMatch(line, q)
              }
            }
            return (
              <div
                key={lineNumber}
                ref={el => { lineRefs.current[index] = el }}
                onClick={() => onLineClick?.(lineNumber)}
                className={`flex border-b border-border-default ${isHighlight ? 'bg-yellow-50' : 'hover:bg-surface-hover'} ${onLineClick ? 'cursor-pointer' : ''} transition-colors`}
              >
                <span className="px-4 py-1 text-text-muted select-none min-w-[60px] text-right font-mono text-xs">{lineNumber}</span>
                <span className="px-4 py-1 flex-1 font-mono text-sm">
                  {hlRange && annotation ? (
                    <>
                      {line.substring(0, hlRange.start)}
                      <mark className={annotation.color ? `bg-${annotation.color}-200 ring-2 ring-${annotation.color}-400 rounded px-0.5` : 'bg-yellow-200 ring-2 ring-yellow-400 rounded px-0.5'}>
                        {line.substring(hlRange.start, hlRange.end)}
                      </mark>
                      {line.substring(hlRange.end)}
                    </>
                  ) : line || ' '}
                </span>
              </div>
            )
          })}
        </div>
      </div>
    )
  }

  if (fileType === 'application/pdf' || fileType === 'pdf') {
    return (
      <div className="h-full flex flex-col bg-bg-surface border border-border-default rounded-lg overflow-hidden">
        <div className="shrink-0 flex items-center justify-between px-4 py-2 border-b border-border-default bg-bg-elevated">
          <div className="flex items-center gap-3">
            <span className="text-xs text-text-secondary font-mono">
              {numPages > 0 ? `${numPages} pages` : 'Loading...'}
            </span>
            {extractedPages.length === 0 && numPages > 0 && (
              <span className="text-xs text-text-muted italic">Indexing text…</span>
            )}
            {(activeSnippet || activeRegion) && (
              <button
                onClick={() => {
                  setActiveSnippet(null)
                  setActiveSearchTarget('')
                  setActiveRegion(null)
                }}
                className="flex items-center gap-1 text-xs text-text-muted hover:text-text-primary transition-colors duration-150 border border-border-default rounded px-1.5 py-0.5"
              >
                <XMarkIcon className="h-3 w-3" />
                Clear
              </button>
            )}
          </div>
          <div className="flex items-center gap-2">
            <button onClick={zoomOut} className="p-1 text-text-secondary hover:text-text-primary hover:bg-bg-hover rounded transition-colors duration-fast">
              <MagnifyingGlassMinusIcon className="h-4 w-4" />
            </button>
            <span className="text-xs text-text-muted font-mono w-10 text-center">{Math.round(scale * 100)}%</span>
            <button onClick={zoomIn} className="p-1 text-text-secondary hover:text-text-primary hover:bg-bg-hover rounded transition-colors duration-fast">
              <MagnifyingGlassPlusIcon className="h-4 w-4" />
            </button>
          </div>
        </div>

        <div className="flex-1 overflow-auto bg-bg-void">
          <Document
            key={fileUrl}
            file={fileConfig}
            onLoadSuccess={onDocumentLoadSuccess}
            onLoadError={onDocumentLoadError}
            options={pdfOptions}
            loading={
              <div className="text-center py-12">
                <div className="inline-block animate-spin rounded-full h-8 w-8 border-b-2 border-accent-primary" />
                <p className="mt-2 text-xs text-text-secondary">Loading PDF...</p>
              </div>
            }
            error={
              <div className="text-center py-12">
                <p className="text-error font-semibold">Failed to load PDF</p>
                <p className="text-xs text-text-secondary mt-2">Please try refreshing the page</p>
              </div>
            }
          >
            <div className="flex flex-col items-center gap-4 py-6 px-2">
              {numPages > 0 && Array.from({ length: numPages }, (_, i) => (
                <div key={i + 1} ref={el => { pageRefs.current[i] = el }} className="relative">
                  <span className="absolute -top-0.5 right-0 text-[10px] text-text-muted/40 font-mono select-none">
                    {i + 1}
                  </span>
                  {activeRegion?.page === i + 1 && pageDimensions[i + 1] && (
                    <div
                      className="pointer-events-none absolute z-10 rounded-sm border-2 border-yellow-300 bg-yellow-300/20 shadow-[0_0_0_1px_rgba(250,204,21,0.35)]"
                      style={{
                        left: `${(activeRegion.x / pageDimensions[i + 1].width) * 100}%`,
                        top: `${(activeRegion.y / pageDimensions[i + 1].height) * 100}%`,
                        width: `${(activeRegion.width / pageDimensions[i + 1].width) * 100}%`,
                        height: `${(activeRegion.height / pageDimensions[i + 1].height) * 100}%`,
                      }}
                    />
                  )}
                  <Page
                    pageNumber={i + 1}
                    scale={scale}
                    renderTextLayer={true}
                    renderAnnotationLayer={true}
                    onLoadSuccess={onPageLoadSuccess}
                    className="shadow-xl"
                    customTextRenderer={
                      (searchAllPages || i + 1 === currentPage) ? customTextRenderer : undefined
                    }
                  />
                </div>
              ))}
            </div>
          </Document>
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

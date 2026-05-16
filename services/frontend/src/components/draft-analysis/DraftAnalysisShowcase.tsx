import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ShieldCheckIcon,
  DocumentTextIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { AnimatePresence, motion } from 'framer-motion'
import DocumentViewer, { type DocumentViewerRef } from '../DocumentViewer'
import ReviewerFeedbackList from './ReviewerFeedbackList'
import TopActionItems from './TopActionItems'
import {
  SHOWCASE_ACTION_ITEMS,
  SHOWCASE_CLAIMS,
  SHOWCASE_COUNTS,
  SHOWCASE_DOCUMENT,
  SHOWCASE_DRAFT_META,
  SHOWCASE_FEEDBACK,
  SHOWCASE_GAPS,
  SHOWCASE_READINESS,
  SHOWCASE_TAB_CATEGORY_MAP,
  SHOWCASE_TAB_FOCUS,
  SHOWCASE_TABS,
  type ShowcaseClaim,
  type ShowcaseFeedbackItem,
  type ShowcaseGap,
  type ShowcaseTabId,
} from './draftAnalysisShowcaseFixture'

interface DraftAnalysisShowcaseProps {
  activeTab?: ShowcaseTabId
  onTabChange?: (tab: ShowcaseTabId) => void
  variant?: 'preview' | 'full'
  showDocumentPane?: boolean
}

function SummaryMetric({
  label,
  value,
  note,
}: {
  label: string
  value: string
  note: string
}) {
  return (
    <div className="rounded-lg border border-border-default bg-bg-elevated px-4 py-3">
      <p className="text-[10px] font-semibold uppercase tracking-[0.14em] text-text-muted">{label}</p>
      <p className="mt-2 text-2xl font-semibold text-text-primary">{value}</p>
      <p className="mt-1 text-xs text-text-secondary">{note}</p>
    </div>
  )
}

export default function DraftAnalysisShowcase({
  activeTab: controlledTab,
  onTabChange,
  variant = 'full',
  showDocumentPane = true,
}: DraftAnalysisShowcaseProps) {
  const isPreview = variant === 'preview'
  const [internalTab, setInternalTab] = useState<ShowcaseTabId>('analysis')
  const activeTab = controlledTab ?? internalTab

  const [claims, setClaims] = useState<ShowcaseClaim[]>(SHOWCASE_CLAIMS)
  const [gaps, setGaps] = useState<ShowcaseGap[]>(SHOWCASE_GAPS)
  const [feedback, setFeedback] = useState<ShowcaseFeedbackItem[]>(SHOWCASE_FEEDBACK)
  const [statusFilter, setStatusFilter] = useState<'new' | 'saved' | 'dismissed'>('new')
  const [annotation, setAnnotation] = useState<{
    id?: string
    line_number?: number
    text_snippet?: string
    section_type?: string
    section_location?: string
    color?: string
  } | null>(null)

  const viewerRef = useRef<DocumentViewerRef>(null)

  const issueLookup = useMemo(() => {
    const lookup = new Map<string, ShowcaseClaim | ShowcaseGap | ShowcaseFeedbackItem>()
    claims.forEach((item) => lookup.set(`claim:${item.id}`, item))
    gaps.forEach((item) => lookup.set(`gap:${item.id}`, item))
    feedback.forEach((item) => lookup.set(`feedback:${item.id}`, item))
    return lookup
  }, [claims, gaps, feedback])

  const setActiveIssue = (issue?: ShowcaseClaim | ShowcaseGap | ShowcaseFeedbackItem) => {
    if (!issue) return
    setAnnotation({
      id: issue.id,
      line_number: issue.line_number,
      text_snippet: issue.text_snippet,
      section_type: issue.section_type,
      section_location: 'section_location' in issue ? issue.section_location : undefined,
      color: 'yellow',
    })
  }

  useEffect(() => {
    setStatusFilter('new')
    const focus = SHOWCASE_TAB_FOCUS[activeTab]
    const issue = issueLookup.get(`${focus.type}:${focus.id}`)
    setActiveIssue(issue)
  }, [activeTab, issueLookup])

  const handleTabChange = (tab: ShowcaseTabId) => {
    if (onTabChange) {
      onTabChange(tab)
      return
    }
    setInternalTab(tab)
  }

  const handleStatusChange = (
    id: string,
    type: 'claim' | 'gap' | 'feedback',
    nextStatus: 'new' | 'saved' | 'dismissed',
  ) => {
    if (type === 'claim') {
      setClaims((current) => current.map((item) => (item.id === id ? { ...item, status: nextStatus } : item)))
      return
    }
    if (type === 'gap') {
      setGaps((current) => current.map((item) => (item.id === id ? { ...item, status: nextStatus } : item)))
      return
    }
    setFeedback((current) => current.map((item) => (item.id === id ? { ...item, status: nextStatus } : item)))
  }

  const handleViewInDocument = (payload: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
  }) => {
    setAnnotation({
      id: `${payload.line_number ?? 'manual'}-${payload.text_snippet ?? payload.section_type ?? 'jump'}`,
      line_number: payload.line_number,
      text_snippet: payload.text_snippet ?? payload.content_text,
      section_type: payload.section_type,
      section_location: payload.section_location,
      color: 'yellow',
    })

    if (payload.line_number) {
      viewerRef.current?.scrollToLine(payload.line_number)
    }
  }

  const addressedCount = [...claims, ...gaps, ...feedback].filter((item) => item.status === 'saved').length
  const liveCounts = {
    claims: claims.length,
    gaps: gaps.length,
    feedback: feedback.filter((item) => item.feedback_type !== 'strength').length,
  }

  return (
    <div className="overflow-hidden rounded-xl border border-border-default bg-bg-surface shadow-2xl">
      <div className="flex items-center gap-3 border-b border-border-default bg-bg-elevated px-4 py-3">
        <div className="flex gap-1.5 shrink-0">
          <div className="h-2.5 w-2.5 rounded-full bg-red-500" />
          <div className="h-2.5 w-2.5 rounded-full bg-yellow-500" />
          <div className="h-2.5 w-2.5 rounded-full bg-green-500" />
        </div>

        <div className="flex flex-wrap gap-1">
          {SHOWCASE_TABS.map((tab) => (
            <button
              key={tab.id}
              onClick={() => handleTabChange(tab.id)}
              className={`rounded-md px-3 py-1.5 text-xs font-semibold transition-colors duration-150 ${
                activeTab === tab.id
                  ? 'border border-border-default bg-bg-surface text-text-primary'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      <div className={`border-b border-border-default bg-bg-surface px-5 ${isPreview ? 'py-3' : 'py-4'}`}>
        <div className="flex flex-wrap items-start justify-between gap-4">
          {!isPreview && (
            <div className="space-y-3">
              <div>
                <div className="flex items-center gap-2">
                  <span className="inline-flex items-center gap-1.5 rounded-full border border-success/20 bg-success/10 px-3 py-1 text-sm font-semibold text-success">
                    <ShieldCheckIcon className="h-4 w-4" />
                    {SHOWCASE_DRAFT_META.privacyLabel}
                  </span>
                  <span className="text-sm text-text-secondary">{SHOWCASE_DRAFT_META.privacyNote}</span>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-bg-elevated px-3 py-1.5 text-sm text-text-secondary">
                  <DocumentTextIcon className="h-4 w-4" />
                  <span className="font-medium">Paper type:</span>
                  <span className="text-text-primary">{SHOWCASE_DRAFT_META.paperType}</span>
                </span>
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-border-default bg-bg-elevated px-3 py-1.5 text-sm text-text-secondary">
                  <SparklesIcon className="h-4 w-4" />
                  <span className="font-medium">Citation style:</span>
                  <span className="text-text-primary">{SHOWCASE_DRAFT_META.citationStyle}</span>
                </span>
              </div>
            </div>
          )}

          <div className="grid min-w-[320px] grid-cols-3 gap-2">
            <SummaryMetric label="Readiness" value={`${SHOWCASE_READINESS.score}/100`} note={SHOWCASE_READINESS.verdict} />
            <SummaryMetric label="Claims" value={String(liveCounts.claims)} note={`${SHOWCASE_COUNTS.missingCitations} missing citations`} />
            <SummaryMetric label="Coverage" value={String(liveCounts.gaps)} note={`${SHOWCASE_COUNTS.coverageGaps} targeted gaps`} />
          </div>
        </div>
      </div>

      <div className={`${showDocumentPane ? `grid ${isPreview ? 'min-h-[520px] lg:grid-cols-[minmax(340px,0.7fr)_minmax(0,1.3fr)]' : 'min-h-[720px] lg:grid-cols-[minmax(380px,0.78fr)_minmax(0,1.22fr)]'}` : isPreview ? 'min-h-[430px]' : 'min-h-[560px]'}`}>
        <div className={`flex flex-col bg-bg-surface ${showDocumentPane ? 'border-r border-border-default' : ''} ${isPreview ? 'min-h-[430px]' : showDocumentPane ? 'min-h-[720px]' : 'min-h-[560px]'}`}>
          {!isPreview && (
            <div className="shrink-0 border-b border-border-default px-4 py-4">
              <TopActionItems actions={SHOWCASE_ACTION_ITEMS} />
              <div className="grid grid-cols-3 gap-2">
                <SummaryMetric label="Actioned" value={String(addressedCount)} note="Resolved during this review pass" />
                <SummaryMetric label="Feedback" value={String(liveCounts.feedback)} note={`${SHOWCASE_COUNTS.weakArguments} argument issues`} />
                <SummaryMetric label="Questions" value={String(SHOWCASE_COUNTS.reviewerQuestions)} note="Reviewer prompts to answer" />
              </div>
            </div>
          )}

          <AnimatePresence mode="wait">
            <motion.div
              key={activeTab}
              initial={{ opacity: 0, y: 6 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.16 }}
              className="min-h-0 flex-1"
            >
              <ReviewerFeedbackList
                claims={claims}
                gaps={gaps}
                feedback={feedback}
                readinessScore={SHOWCASE_READINESS.score}
                statusFilter={statusFilter}
                onStatusFilterChange={setStatusFilter}
                onStatusChange={handleStatusChange}
                onViewInDocument={showDocumentPane ? handleViewInDocument : undefined}
                fileType={SHOWCASE_DOCUMENT.fileType}
                initialCategory={SHOWCASE_TAB_CATEGORY_MAP[activeTab]}
                maxVisibleItems={isPreview ? 1 : showDocumentPane ? 3 : 4}
                compactPreview={isPreview}
              />
            </motion.div>
          </AnimatePresence>
        </div>

        {showDocumentPane && (
          <div className={`flex flex-col bg-bg-elevated ${isPreview ? 'min-h-[520px]' : 'min-h-[720px]'}`}>
            <div className="border-b border-border-default px-4 py-3">
              <p className="text-sm font-semibold text-text-primary">{SHOWCASE_DOCUMENT.title}</p>
              <p className="mt-1 text-xs text-text-secondary">{SHOWCASE_DOCUMENT.subtitle}</p>
            </div>

            <div className={`flex-1 ${isPreview ? 'p-3' : 'p-4'}`}>
              <DocumentViewer
                ref={viewerRef}
                fileUrl={SHOWCASE_DOCUMENT.fileUrl}
                fileType={SHOWCASE_DOCUMENT.fileType}
                annotation={annotation}
                initialScale={isPreview ? 0.82 : 0.74}
              />
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeftIcon,
  DocumentTextIcon,
  ShieldCheckIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import { handleError } from '../lib/errorHandler'
import { useAuthStore } from '../stores/authStore'
import DocumentViewer, { type DocumentViewerRef } from '../components/DocumentViewer'
import ReviewerFeedbackList from '../components/draft-analysis/ReviewerFeedbackList'
import { ProgressIndicator, useEstimatedProgress } from '../components/ui/ProgressIndicator'
import { useAnalysisStream } from '../hooks/useAnalysisStream'
import FeedbackButton from '../components/FeedbackButton'
import toast from 'react-hot-toast'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  section_location: string
  section_type?: string
  importance_score: number
  confidence_score?: number
  requires_citation: boolean
  existing_citations: string[]
  supporting_literature?: any
  line_number?: number
  status: 'new' | 'saved' | 'dismissed'
}

interface Gap {
  id: string
  gap_type: string
  description: string
  priority: 'high' | 'medium' | 'low'
  section_type?: string
  suggested_papers: any[]
  has_relevant_literature?: boolean
  line_number?: number
  status: 'new' | 'saved' | 'dismissed'
}

interface Feedback {
  id: string
  feedback_type: string
  severity: string
  priority: 'high' | 'medium' | 'low'
  reviewer_persona?: string
  section_type?: string
  feedback_text: string
  suggestions: string[]
  section_reference?: string
  line_number?: number
  status: 'new' | 'saved' | 'dismissed'
}

interface Draft {
  id: string
  title: string
  version: number
  file_url: string
  file_type: string
  status: string
  paper_type?: string
  citation_style?: string
  created_at: string
  updated_at: string
}

interface FeedbackCounts {
  total_claims: number
  claims_needing_citation: number
  total_gaps: number
  critical_gaps: number
  total_feedback: number
  critical_feedback: number
}

interface Annotation {
  id: string
  type: 'claim' | 'feedback' | 'gap'
  line_number: number
  char_start?: number
  char_end?: number
  text_snippet?: string
  section_location?: string
  color: string
}

interface EditingIssue {
  text?: string
  issue?: string
  suggestion?: string
  section?: string
  location?: string
  note?: string
  severity?: string
}

interface EditingFeedback {
  grammar_issues: EditingIssue[]
  citation_issues: EditingIssue[]
  formatting_issues: EditingIssue[]
  structural_notes: EditingIssue[]
}

interface CarryoverBadge {
  label: string
  tone: 'warning' | 'accent'
}

type ActiveTab = 'overview' | 'editing' | 'feedback' | 'gaps'

const EMPTY_EDITING_FEEDBACK: EditingFeedback = {
  grammar_issues: [],
  citation_issues: [],
  formatting_issues: [],
  structural_notes: [],
}

const PAPER_TYPE_LABELS: Record<string, string> = {
  journal_article: 'Journal article',
  conference_paper: 'Conference paper',
  thesis: 'Thesis',
  dissertation: 'Dissertation',
  preprint: 'Preprint',
}

const CITATION_STYLE_LABELS: Record<string, string> = {
  apa: 'APA',
  mla: 'MLA',
  chicago: 'Chicago',
  ieee: 'IEEE',
  vancouver: 'Vancouver',
  other: 'Other / mixed',
}

const normalizeIssueList = (value: unknown): EditingIssue[] => (
  Array.isArray(value) ? value.filter(Boolean) as EditingIssue[] : []
)

const normalizeComparisonText = (value: string): string => (
  value
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim()
)

const DRAFT_PROGRESS_STEPS = [
  { key: 'uploaded', label: 'Queued' },
  { key: 'extracting_text', label: 'Extracting text' },
  { key: 'stage1_editing', label: 'Stage 1 editing review' },
  { key: 'reviewer1_feedback', label: 'Reviewer 1 feedback' },
  { key: 'reviewer2_feedback', label: 'Reviewer 2 feedback' },
  { key: 'coverage_gaps', label: 'Coverage gaps' },
  { key: 'finalizing', label: 'Finalizing' },
]

export function extractEditingFeedbackPayload(analysisResponse: any): EditingFeedback {
  const raw = (
    analysisResponse?.analysis?.analysis?.editing_feedback
    ?? analysisResponse?.analysis?.editing_feedback
    ?? analysisResponse?.analysis?.analysis_metadata?.editing_feedback
    ?? analysisResponse?.editing_feedback
    ?? {}
  )

  return {
    grammar_issues: normalizeIssueList(raw.grammar_issues),
    citation_issues: normalizeIssueList(raw.citation_issues),
    formatting_issues: normalizeIssueList(raw.formatting_issues),
    structural_notes: normalizeIssueList(raw.structural_notes),
  }
}

export function buildCarryoverBadgeMap(
  feedbackItems: Array<Pick<Feedback, 'id' | 'feedback_text'>>,
  latestComparison: any,
): Record<string, CarryoverBadge> {
  const trackedItems = Array.isArray(latestComparison?.feedback_tracked)
    ? latestComparison.feedback_tracked
    : []

  if (trackedItems.length === 0) {
    return {}
  }

  const badgeByStatus: Record<string, CarryoverBadge | null> = {
    still_pending: { label: 'Carryover from previous version', tone: 'warning' },
    partially_addressed: { label: 'Partially addressed in revision', tone: 'accent' },
    resolved: null,
    new_issue: null,
  }

  const map: Record<string, CarryoverBadge> = {}

  feedbackItems.forEach((item) => {
    const current = normalizeComparisonText(item.feedback_text)
    if (!current) return

    const match = trackedItems.find((tracked: any) => {
      const candidate = normalizeComparisonText(tracked?.feedback_text || '')
      if (!candidate) return false
      return current === candidate || current.includes(candidate) || candidate.includes(current)
    })

    const badge = badgeByStatus[match?.resolution_status]
    if (match && badge) {
      map[item.id] = badge
    }
  })

  return map
}

export default function DraftAnalysis() {
  const { projectId, draftId } = useParams<{ projectId: string; draftId: string }>()
  const navigate = useNavigate()
  const { session } = useAuthStore()
  const token = session?.access_token
  const documentViewerRef = useRef<DocumentViewerRef>(null)

  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [signedFileUrl, setSignedFileUrl] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ActiveTab>('overview')
  const [activeAnnotation, setActiveAnnotation] = useState<Annotation | null>(null)
  const [claims, setClaims] = useState<Claim[]>([])
  const [gaps, setGaps] = useState<Gap[]>([])
  const [feedback, setFeedback] = useState<Feedback[]>([])
  const [editingFeedback, setEditingFeedback] = useState<EditingFeedback>(EMPTY_EDITING_FEEDBACK)
  const [counts, setCounts] = useState<FeedbackCounts>({
    total_claims: 0,
    claims_needing_citation: 0,
    total_gaps: 0,
    critical_gaps: 0,
    total_feedback: 0,
    critical_feedback: 0,
  })
  const [readinessScore, setReadinessScore] = useState<number | null>(null)
  const [verdict, setVerdict] = useState<string | null>(null)
  const [priorityActions, setPriorityActions] = useState<string[]>([])
  const [latestComparison, setLatestComparison] = useState<any>(null)

  const checkAnalysisStatusRef = useRef<(() => Promise<void>) | null>(null)
  const { progress: estimatedProgress } = useEstimatedProgress(180)
  const stream = useAnalysisStream(
    draftId ?? null,
    draft?.status === 'processing' || draft?.status === 'uploaded',
  )

  const fetchSignedUrl = useCallback(async () => {
    if (!draftId || !token) return
    try {
      const urlResponse = await api.drafts.getSignedUrl(token, draftId)
      setSignedFileUrl(urlResponse.signed_url)
    } catch (error) {
      console.error('Failed to fetch signed URL:', error)
    }
  }, [draftId, token])

  const fetchAllFeedback = useCallback(async () => {
    if (!draftId || !token) return
    try {
      const [newData, savedData, dismissedData] = await Promise.all([
        api.drafts.getAllFeedback(token, draftId, 'new', true),
        api.drafts.getAllFeedback(token, draftId, 'saved', false),
        api.drafts.getAllFeedback(token, draftId, 'dismissed', false),
      ])

      setClaims([
        ...(newData.claims || []),
        ...(savedData.claims || []),
        ...(dismissedData.claims || []),
      ])
      setGaps([
        ...(newData.gaps || []),
        ...(savedData.gaps || []),
        ...(dismissedData.gaps || []),
      ])
      setFeedback([
        ...(newData.feedback || []),
        ...(savedData.feedback || []),
        ...(dismissedData.feedback || []),
      ])
      setCounts(newData.counts)
      setReadinessScore(newData.readiness_score)
      setVerdict(newData.verdict)
    } catch (error) {
      console.error('Failed to fetch all feedback:', error)
    }
  }, [draftId, token])

  const handleStatusChange = useCallback(async (
    feedbackId: string,
    feedbackType: 'claim' | 'gap' | 'feedback',
    newStatus: 'new' | 'saved' | 'dismissed',
  ) => {
    if (!draftId || !token) return
    try {
      await api.drafts.updateFeedbackStatus(token, draftId, feedbackId, feedbackType, newStatus)
      toast.success(newStatus === 'saved' ? 'Feedback saved' : 'Feedback dismissed')
      await fetchAllFeedback()
    } catch (error) {
      handleError(error)
      toast.error('Failed to update feedback status')
    }
  }, [draftId, token, fetchAllFeedback])

  // Extract the most "verbatim-likely" phrase from a claim/feedback text.
  // Prefers numbers/percentages (likely exact) then short quoted phrases.
  const extractSearchPhrase = (text: string): string => {
    const numbers = text.match(/\d[\d,]*\.?\d*\s*%|\d+\.\d+/g)
    if (numbers && numbers[0].length >= 3) return numbers[0]
    const quoted = text.match(/"([^"]{6,35})"/)?.[1]
    if (quoted) return quoted
    return text
  }

  const handleViewInDocument = useCallback((item: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
  }) => {
    const isPdf = draft?.file_type === 'application/pdf' || draft?.file_type === 'pdf'
    if (isPdf) {
      if (item.text_snippet && item.line_number) {
        // Best case: verbatim snippet + page → snippet mode on that page
        const page = Math.ceil(item.line_number / 55)
        documentViewerRef.current?.highlightText(item.text_snippet, page, false)
      } else if (item.text_snippet) {
        // Snippet but no page: substring search across all pages (NOT heading mode)
        documentViewerRef.current?.highlightText(item.text_snippet, undefined, false)
      } else if (item.line_number) {
        // No snippet: jump to estimated page, try to find content_text as substring
        const page = Math.ceil(item.line_number / 55)
        const searchTerm = item.content_text ? extractSearchPhrase(item.content_text) : ''
        documentViewerRef.current?.highlightText(searchTerm, page, false)
      } else {
        // Section only: heading mode — look for the section heading span
        const raw = item.section_type || item.section_location || ''
        const heading = raw.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase())
        if (heading) documentViewerRef.current?.highlightText(heading, undefined, true)
      }
    } else {
      if (item.line_number) {
        documentViewerRef.current?.scrollToLine(item.line_number)
      }
      documentViewerRef.current?.highlightText(item.content_text || '', undefined, false)
    }
  }, [draft?.file_type])

  const checkAnalysisStatus = useCallback(async () => {
    if (!draftId || !token) return
    try {
      const response = await api.drafts.getAnalysis(token, draftId)
      setEditingFeedback(extractEditingFeedbackPayload(response))

      if (response.status === 'analyzed') {
        if (response.priority_actions?.length) {
          setPriorityActions(response.priority_actions)
        }
        if (response.readiness_score !== undefined) {
          setReadinessScore(response.readiness_score)
        }
        if (response.verdict) {
          setVerdict(response.verdict)
        }

        const draftData = await api.drafts.get(token, draftId)
        setDraft(draftData)
        api.drafts.assignSections(token, draftId).catch(() => {}) // fire-and-forget: section mapping is non-blocking
        await fetchAllFeedback()
        setLoading(false)
      } else if (response.status === 'failed') {
        const draftData = await api.drafts.get(token, draftId)
        setDraft(draftData)
        setLoading(false)
        toast.error('Draft analysis failed')
      }
    } catch {
      // Keep polling while analysis is pending.
    }
  }, [draftId, token, fetchAllFeedback])

  useEffect(() => {
    const init = async () => {
      if (!draftId || !token) return
      setLoading(true)

      try {
        const [draftData, analysisResponse, comparisonsResponse] = await Promise.all([
          api.drafts.get(token, draftId),
          api.drafts.getAnalysis(token, draftId),
          projectId ? api.drafts.listComparisons(token, projectId).catch(() => null) : Promise.resolve(null),
        ])

        setEditingFeedback(extractEditingFeedbackPayload(analysisResponse))

        if (analysisResponse?.priority_actions?.length) {
          setPriorityActions(analysisResponse.priority_actions)
        }
        if (analysisResponse?.readiness_score !== undefined) {
          setReadinessScore(analysisResponse.readiness_score)
        }
        if (analysisResponse?.verdict) {
          setVerdict(analysisResponse.verdict)
        }

        if (comparisonsResponse?.comparisons?.length) {
          const myComparison = comparisonsResponse.comparisons.find(
            (comparison: any) => comparison.draft_v2_id === draftId || comparison.draft_v1_id === draftId,
          )

          if (myComparison) {
            try {
              const detail = await api.drafts.getComparison(token, myComparison.comparison_id)
              setLatestComparison({
                ...detail,
                v1Id: detail.draft_v1_id ?? myComparison.draft_v1_id,
                v2Id: detail.draft_v2_id ?? myComparison.draft_v2_id,
              })
            } catch {
              setLatestComparison({
                ...myComparison,
                v1Id: myComparison.draft_v1_id,
                v2Id: myComparison.draft_v2_id,
              })
            }
          }
        }

        setDraft(draftData)
        fetchSignedUrl()

        if (draftData.status === 'analyzed') {
          api.drafts.assignSections(token, draftId).catch(() => {}) // fire-and-forget
          await fetchAllFeedback()
        }
      } catch (error) {
        handleError(error)
        toast.error('Failed to load draft')
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [draftId, token, projectId, fetchSignedUrl, fetchAllFeedback])

  useEffect(() => {
    if (draft?.status === 'processing' || draft?.status === 'uploaded') {
      checkAnalysisStatusRef.current = checkAnalysisStatus
      const interval = setInterval(checkAnalysisStatus, 3000)
      return () => clearInterval(interval)
    }
  }, [draft?.status, checkAnalysisStatus])

  useEffect(() => {
    if (stream.complete) checkAnalysisStatusRef.current?.()
  }, [stream.complete])

if (loading) {
    return (
      <div className="min-h-screen bg-bg-void flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent mb-4" />
          <p className="text-text-secondary">Loading draft analysis...</p>
        </div>
      </div>
    )
  }

  if (!draft) {
    return (
      <div className="min-h-screen bg-bg-void flex items-center justify-center">
        <div className="text-center">
          <p className="text-text-secondary mb-4">Draft not found</p>
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="text-accent-primary hover:opacity-80 transition-opacity"
          >
            Return to Project
          </button>
        </div>
      </div>
    )
  }

  if (draft.status === 'processing' || draft.status === 'uploaded') {
    const currentStepIndex = stream.step
      ? Math.max(DRAFT_PROGRESS_STEPS.findIndex((step) => step.key === stream.step), 0)
      : 0
    return (
      <div className="min-h-screen bg-bg-void flex items-center justify-center p-6">
        <div className="max-w-2xl w-full">
          <ProgressIndicator
            progress={stream.progress > 0 ? stream.progress : estimatedProgress}
            status={stream.message || 'Analyzing Draft'}
            steps={DRAFT_PROGRESS_STEPS.map((step, index) => ({
              label: step.label,
              completed: index < currentStepIndex,
              active: index === currentStepIndex,
            }))}
          />
          <p className="mt-4 text-center text-sm text-text-secondary">
            Running Stage 1 editing checks, identifying coverage gaps, and generating reviewer feedback...
          </p>
          <p className="mt-2 text-center text-xs text-text-muted">
            Private by default. Your files stay in your workspace and are not used to train models.
          </p>
        </div>
      </div>
    )
  }

  if (draft.status === 'failed') {
    return (
      <div className="min-h-screen bg-bg-void flex items-center justify-center">
        <div className="text-center">
          <p className="text-error mb-4">Draft analysis failed</p>
          <p className="text-text-muted text-sm mb-4">Please try uploading the draft again.</p>
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="text-accent-primary hover:opacity-80 transition-opacity"
          >
            Return to Project
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-void flex flex-col">
      <header className="bg-bg-surface border-b border-border-default px-4 py-4 sm:px-6">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="flex items-start gap-4">
            <button
              onClick={() => navigate(`/projects/${projectId}`)}
              className="mt-0.5 p-2 text-text-muted hover:text-text-primary rounded-md hover:bg-bg-elevated transition-colors duration-150"
            >
              <ArrowLeftIcon className="h-5 w-5" />
            </button>
            <div>
              <div className="flex flex-wrap items-center gap-2 text-sm text-text-muted">
                <Link to="/projects" className="hover:text-text-primary transition-colors duration-150">
                  Projects
                </Link>
                <span>/</span>
                <Link to={`/projects/${projectId}`} className="hover:text-text-primary transition-colors duration-150">
                  Project
                </Link>
                <span>/</span>
                <span className="text-text-secondary">Draft Analysis</span>
              </div>
              <h1 className="text-xl font-semibold text-text-primary mt-1">
                {draft.title}
                {draft.version > 1 && (
                  <span className="ml-2 text-sm text-text-muted">v{draft.version}</span>
                )}
              </h1>
              <div className="mt-3 flex flex-wrap items-center gap-2">
                <span className="inline-flex items-center gap-1.5 rounded-lg border border-teal-primary/20 bg-teal-primary/10 px-2.5 py-1 text-xs font-semibold text-teal-primary">
                  <ShieldCheckIcon className="h-3.5 w-3.5" />
                  Private draft analysis
                </span>
                <span className="text-xs text-text-secondary">
                  Only you can access this draft. It is not shared and is not used to train models.
                </span>
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <ContextChip
                  icon={DocumentTextIcon}
                  label="Paper type"
                  value={PAPER_TYPE_LABELS[draft.paper_type || 'journal_article'] || 'Journal article'}
                />
                <ContextChip
                  icon={SparklesIcon}
                  label="Citation style"
                  value={CITATION_STYLE_LABELS[draft.citation_style || 'apa'] || 'APA'}
                />
              </div>
            </div>
          </div>
          <FeedbackButton
            featureType="draft_analysis"
            contextId={draftId}
          />
        </div>
      </header>

      <main className="flex-1 overflow-hidden">
        <div className="flex h-[calc(100vh-120px)] flex-col xl:flex-row">
          {/* LEFT: Feedback list — independent scroll inside component */}
          <div className="xl:w-1/2 xl:shrink-0 flex flex-col border-b border-border-default xl:border-b-0 xl:border-r xl:h-full min-h-[50vh] xl:min-h-0">
            {activeTab === 'editing' ? (
              <div className="flex flex-col h-full">
                <div className="shrink-0 flex items-center gap-3 px-4 py-3 border-b border-border-default bg-bg-surface">
                  <button
                    onClick={() => setActiveTab('overview')}
                    className="text-xs text-text-muted hover:text-text-primary transition-colors duration-150"
                  >
                    ← Back
                  </button>
                  <span className="text-sm font-semibold text-text-primary">Editing Review</span>
                </div>
                <div className="flex-1 overflow-y-auto p-4">
                  <EditingReviewTab
                    editingFeedback={editingFeedback}
                    paperType={draft.paper_type}
                    citationStyle={draft.citation_style}
                  />
                </div>
              </div>
            ) : (
              <ReviewerFeedbackList
                claims={claims}
                gaps={gaps}
                feedback={feedback}
                readinessScore={readinessScore}
                onStatusChange={handleStatusChange}
                onViewInDocument={handleViewInDocument}
                fileType={draft.file_type}
                onOpenEditingReview={() => setActiveTab('editing')}
              />
            )}
          </div>

          {/* RIGHT: Document — independent scroll inside DocumentViewer */}
          <div className="flex-1 flex flex-col overflow-hidden xl:h-full">
            {signedFileUrl ? (
              <DocumentViewer
                ref={documentViewerRef}
                fileUrl={signedFileUrl}
                fileType={draft.file_type}
                annotation={activeAnnotation}
              />
            ) : (
              <div className="flex items-center justify-center h-full">
                <div className="text-center">
                  <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent mb-4" />
                  <p className="text-text-secondary">Loading document...</p>
                </div>
              </div>
            )}
          </div>
        </div>
      </main>
    </div>
  )
}

function ContextChip({
  icon: Icon,
  label,
  value,
}: {
  icon: typeof ShieldCheckIcon
  label: string
  value: string
}) {
  return (
    <span className="inline-flex items-center gap-2 rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary">
      <Icon className="h-3.5 w-3.5 text-text-muted" />
      <span className="text-text-muted">{label}:</span>
      <span className="font-semibold text-text-primary">{value}</span>
    </span>
  )
}

function EditingReviewTab({
  editingFeedback,
  paperType,
  citationStyle,
}: {
  editingFeedback: EditingFeedback
  paperType?: string
  citationStyle?: string
}) {
  const sections = [
    {
      key: 'grammar',
      title: 'Grammar & spelling',
      count: editingFeedback.grammar_issues.length,
      description: 'Mechanical issues that affect readability and polish.',
      items: editingFeedback.grammar_issues,
    },
    {
      key: 'citation',
      title: 'Citation style',
      count: editingFeedback.citation_issues.length,
      description: 'Formatting issues against the selected citation style.',
      items: editingFeedback.citation_issues,
    },
    {
      key: 'formatting',
      title: 'Formatting',
      count: editingFeedback.formatting_issues.length,
      description: 'Heading, list, caption, and layout inconsistencies.',
      items: editingFeedback.formatting_issues,
    },
    {
      key: 'structure',
      title: 'Structure',
      count: editingFeedback.structural_notes.length,
      description: 'High-level notes tied to the paper type and section flow.',
      items: editingFeedback.structural_notes,
    },
  ]

  const totalIssues = sections.reduce((sum, section) => sum + section.count, 0)

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-border-default bg-bg-surface p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <h3 className="text-sm font-semibold text-text-primary">Stage 1 editing review</h3>
            <p className="mt-1 text-sm text-text-secondary leading-relaxed">
              This pass focuses on grammar, citation compliance, formatting, and paper-type structure before intellectual peer review.
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary">
              {PAPER_TYPE_LABELS[paperType || 'journal_article'] || 'Journal article'}
            </span>
            <span className="rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary">
              {CITATION_STYLE_LABELS[citationStyle || 'apa'] || 'APA'}
            </span>
          </div>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {sections.map((section) => (
          <div key={section.key} className="rounded-lg border border-border-default bg-bg-surface p-4">
            <p className="text-xs uppercase tracking-wide text-text-muted">{section.title}</p>
            <p className="mt-2 text-2xl font-semibold text-text-primary">{section.count}</p>
            <p className="mt-2 text-xs text-text-secondary leading-relaxed">{section.description}</p>
          </div>
        ))}
      </div>

      {totalIssues === 0 ? (
        <div className="rounded-lg border border-border-default bg-bg-surface p-6 text-center">
          <p className="text-sm font-semibold text-text-primary">No Stage 1 issues flagged</p>
          <p className="mt-1 text-sm text-text-secondary">
            The draft looks mechanically clean based on the current editing pass.
          </p>
        </div>
      ) : (
        <div className="space-y-4">
          {sections.map((section) => (
            <div key={section.key} className="rounded-lg border border-border-default bg-bg-surface p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <h4 className="text-sm font-semibold text-text-primary">{section.title}</h4>
                  <p className="mt-1 text-xs text-text-secondary">{section.description}</p>
                </div>
                <span className="rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs font-semibold text-text-secondary">
                  {section.count}
                </span>
              </div>

              {section.items.length > 0 ? (
                <div className="mt-4 space-y-3">
                  {section.items.map((item, index) => (
                    <div key={`${section.key}-${index}`} className="rounded-lg border border-border-default bg-bg-elevated p-3">
                      {(item.section || item.location) && (
                        <p className="mb-1 text-xs font-semibold text-text-muted">
                          {item.section || item.location}
                        </p>
                      )}
                      {(item.text || item.note) && (
                        <p className="text-sm text-text-primary leading-relaxed">
                          {item.text || item.note}
                        </p>
                      )}
                      {item.issue && (
                        <p className="mt-2 text-xs text-text-secondary">
                          <span className="font-semibold text-text-primary">Issue:</span> {item.issue}
                        </p>
                      )}
                      {item.suggestion && (
                        <p className="mt-1 text-xs text-text-secondary">
                          <span className="font-semibold text-text-primary">Suggested fix:</span> {item.suggestion}
                        </p>
                      )}
                      {item.severity && (
                        <span className="mt-2 inline-flex rounded-lg border border-border-default bg-bg-void px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-text-muted">
                          {item.severity}
                        </span>
                      )}
                    </div>
                  ))}
                </div>
              ) : (
                <p className="mt-4 text-sm text-text-muted">No issues flagged in this category.</p>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

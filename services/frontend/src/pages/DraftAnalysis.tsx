import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import {
  ArrowLeftIcon,
  DocumentTextIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import { handleError } from '../lib/errorHandler'
import { useAuthStore } from '../stores/authStore'
import DocumentViewer, { type DocumentViewerRef, type PdfCoordinates } from '../components/DocumentViewer'
import ReviewerFeedbackList from '../components/draft-analysis/ReviewerFeedbackList'
import EditingPassTab from '../components/draft-analysis/EditingPassTab'
import { ProgressIndicator, useEstimatedProgress } from '../components/ui/ProgressIndicator'
import { useAnalysisStream } from '../hooks/useAnalysisStream'
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
  text_snippet?: string
  pdf_coordinates?: PdfCoordinates
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
  text_snippet?: string
  pdf_coordinates?: PdfCoordinates
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
  text_snippet?: string
  pdf_coordinates?: PdfCoordinates
  status: 'new' | 'saved' | 'dismissed'
}

interface RevisionTask {
  id: string
  source_type: string
  task_type: string
  severity: string
  priority: 'high' | 'medium' | 'low'
  section?: string
  anchor_text?: string
  problem: string
  why_it_matters?: string
  suggested_action: string
  source_ids?: string[]
  line_number?: number
  page_number?: number
  paragraph_index?: number
  suggested_sources?: any[]
  text_snippet?: string
  pdf_coordinates?: PdfCoordinates
  match_confidence?: number
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


type ActiveTab = 'editing_pass' | 'peer_review'
type FeedbackStatusFilter = 'new' | 'saved' | 'dismissed'

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

const DRAFT_PROGRESS_STEPS = [
  { key: 'uploaded', label: 'Queued' },
  { key: 'extracting_text', label: 'Extracting text' },
  { key: 'stage1_editing', label: 'Editing pass' },
  { key: 'editor_pass', label: 'Editorial desk check' },
  { key: 'reviewer_panel', label: 'Reviewer panel' },
  { key: 'meta_review', label: 'Meta reviewer synthesis' },
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

export default function DraftAnalysis() {
  const { projectId, draftId } = useParams<{ projectId: string; draftId: string }>()
  const navigate = useNavigate()
  const { session } = useAuthStore()
  const token = session?.access_token
  const documentViewerRef = useRef<DocumentViewerRef>(null)

  const [loading, setLoading] = useState(true)
  const [feedbackLoading, setFeedbackLoading] = useState(false)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [signedFileUrl, setSignedFileUrl] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<ActiveTab>('peer_review')
  const [statusFilter, setStatusFilter] = useState<FeedbackStatusFilter>('new')
  const [claims, setClaims] = useState<Claim[]>([])
  const [gaps, setGaps] = useState<Gap[]>([])
  const [feedback, setFeedback] = useState<Feedback[]>([])
  const [revisionTasks, setRevisionTasks] = useState<RevisionTask[]>([])
  const [editingFeedback, setEditingFeedback] = useState<EditingFeedback>(EMPTY_EDITING_FEEDBACK)
  const [readinessScore, setReadinessScore] = useState<number | null>(null)
  const [editorDecision, setEditorDecision] = useState<any | null>(null)
  const [reviewerPanel, setReviewerPanel] = useState<any[]>([])
  const [metaReview, setMetaReview] = useState<any | null>(null)
  const feedbackCacheRef = useRef<Partial<Record<FeedbackStatusFilter, {
    claims: Claim[]
    gaps: Gap[]
    feedback: Feedback[]
    revisionTasks: RevisionTask[]
    readinessScore: number | null
  }>>>({})
  const checkAnalysisStatusRef = useRef<(() => Promise<void>) | null>(null)
  const { progress: estimatedProgress } = useEstimatedProgress(180)
  const stream = useAnalysisStream(
    draftId ?? null,
    draft?.status === 'processing' || draft?.status === 'uploaded',
  )

  const fetchFeedbackForStatus = useCallback(async (
    nextStatus: FeedbackStatusFilter,
    force = false,
  ) => {
    if (!draftId || !token) return
    const cached = feedbackCacheRef.current[nextStatus]
    if (!force && cached) {
      setClaims(cached.claims)
      setGaps(cached.gaps)
      setFeedback(cached.feedback)
      setRevisionTasks(cached.revisionTasks)
      setReadinessScore(cached.readinessScore)
      return
    }

    try {
      setFeedbackLoading(true)
      const actionableOnly = nextStatus === 'new'
      const data = await api.drafts.getAllFeedback(token, draftId, nextStatus, actionableOnly)
      const payload = {
        claims: data.claims || [],
        gaps: data.gaps || [],
        feedback: data.feedback || [],
        revisionTasks: data.revision_tasks || [],
        readinessScore: data.readiness_score ?? null,
      }
      feedbackCacheRef.current[nextStatus] = payload
      setClaims(payload.claims)
      setGaps(payload.gaps)
      setFeedback(payload.feedback)
      setRevisionTasks(payload.revisionTasks)
      setReadinessScore(payload.readinessScore)
    } catch (error) {
      console.error('Failed to fetch all feedback:', error)
    } finally {
      setFeedbackLoading(false)
    }
  }, [draftId, token])

  const handleStatusChange = useCallback(async (
    feedbackId: string,
    feedbackType: 'claim' | 'gap' | 'feedback' | 'task',
    newStatus: 'new' | 'saved' | 'dismissed',
  ) => {
    if (!draftId || !token) return
    try {
      await api.drafts.updateFeedbackStatus(token, draftId, feedbackId, feedbackType, newStatus)
      toast.success(newStatus === 'saved' ? 'Feedback saved' : 'Feedback dismissed')
      feedbackCacheRef.current = {}
      await fetchFeedbackForStatus(statusFilter, true)
    } catch (error) {
      handleError(error)
      toast.error('Failed to update feedback status')
    }
  }, [draftId, token, fetchFeedbackForStatus, statusFilter])

  const handleViewInDocument = useCallback((item: {
    line_number?: number
    content_text?: string
    text_snippet?: string
    section_type?: string
    section_location?: string
    pdf_coordinates?: PdfCoordinates
    page_number?: number
  }) => {
    const isPdf = draft?.file_type === 'application/pdf' || draft?.file_type === 'pdf'
    if (isPdf) {
      if (item.pdf_coordinates) {
        documentViewerRef.current?.highlightRegion(item.pdf_coordinates)
      } else if (item.page_number) {
        documentViewerRef.current?.scrollToPage(item.page_number)
      } else {
        toast('Exact location unavailable for this item yet. Reanalyze the draft to regenerate anchors.', {
          icon: 'ℹ️',
          duration: 3000,
        })
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
      setEditorDecision(response?.editor_decision ?? null)
      setReviewerPanel(response?.reviewer_panel ?? [])
      setMetaReview(response?.meta_review ?? null)

      if (response.status === 'analyzed') {
        if (response.readiness_score !== undefined) {
          setReadinessScore(response.readiness_score)
        }

        const draftData = await api.drafts.get(token, draftId)
        setDraft(draftData)
        setLoading(false)
        void fetchFeedbackForStatus(statusFilter, true)
      } else if (response.status === 'failed') {
        const draftData = await api.drafts.get(token, draftId)
        setDraft(draftData)
        setLoading(false)
        toast.error('Draft analysis failed')
      }
    } catch {
      // Keep polling while analysis is pending.
    }
  }, [draftId, token, fetchFeedbackForStatus, statusFilter])

  useEffect(() => {
    const init = async () => {
      if (!draftId || !token) return
      setLoading(true)

      try {
        const [draftData, analysisResponse] = await Promise.all([
          api.drafts.get(token, draftId),
          api.drafts.getAnalysis(token, draftId),
        ])

        setEditingFeedback(extractEditingFeedbackPayload(analysisResponse))
        setEditorDecision(analysisResponse?.editor_decision ?? null)
        setReviewerPanel(analysisResponse?.reviewer_panel ?? [])
        setMetaReview(analysisResponse?.meta_review ?? null)

        if (analysisResponse?.readiness_score !== undefined) {
          setReadinessScore(analysisResponse.readiness_score)
        }

        setDraft(draftData)
        setSignedFileUrl(draftData.file_url ?? null)

        if (draftData.status === 'analyzed') {
          void fetchFeedbackForStatus(statusFilter)
        }
      } catch (error) {
        handleError(error)
        toast.error('Failed to load draft')
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [draftId, token, fetchFeedbackForStatus, statusFilter])

  useEffect(() => {
    if (draft?.status === 'analyzed') {
      void fetchFeedbackForStatus(statusFilter)
    }
  }, [draft?.status, statusFilter, fetchFeedbackForStatus])

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
                  label="Citation style"
                  value={CITATION_STYLE_LABELS[draft.citation_style || 'apa'] || 'APA'}
                />
              </div>
            </div>
          </div>
        </div>
      </header>

      <main className="flex-1 overflow-hidden">
        <div className="flex h-[calc(100vh-120px)] flex-col xl:flex-row">
          {/* LEFT: Two-pass panel */}
          <div className="xl:w-1/2 xl:shrink-0 flex flex-col border-b border-border-default xl:border-b-0 xl:border-r xl:h-full min-h-[50vh] xl:min-h-0">
            {/* Tab bar */}
            <div className="shrink-0 flex border-b border-border-default bg-bg-surface">
              {(['peer_review', 'editing_pass'] as const).map((tab) => {
                const isActive = activeTab === tab
                const label = tab === 'peer_review' ? 'Peer Review' : 'Editing Pass'
                return (
                  <button
                    key={tab}
                    onClick={() => setActiveTab(tab)}
                    className={`px-4 py-3 text-sm font-semibold border-b-2 transition-colors duration-fast ${
                      isActive
                        ? 'border-accent-primary text-text-primary'
                        : 'border-transparent text-text-muted hover:text-text-secondary'
                    }`}
                  >
                    {label}
                  </button>
                )
              })}
            </div>

            {/* Tab content */}
            {activeTab === 'editing_pass' ? (
              <EditingPassTab
                editingFeedback={editingFeedback}
                editorDecision={editorDecision}
                paperType={draft.paper_type}
                citationStyle={draft.citation_style}
              />
            ) : (
              <ReviewerFeedbackList
                claims={claims}
                gaps={gaps}
                feedback={feedback}
                revisionTasks={revisionTasks}
                readinessScore={readinessScore}
                loading={feedbackLoading}
                statusFilter={statusFilter}
                onStatusFilterChange={setStatusFilter}
                onStatusChange={handleStatusChange}
                onViewInDocument={handleViewInDocument}
                fileType={draft.file_type}
                editorDecision={editorDecision}
                reviewerPanel={reviewerPanel}
                metaReview={metaReview}
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
                annotation={null}
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
  icon?: typeof ShieldCheckIcon
  label: string
  value: string
}) {
  return (
    <span className="inline-flex items-center gap-2 rounded-lg border border-border-default bg-bg-elevated px-2.5 py-1 text-xs text-text-secondary">
      {Icon && <Icon className="h-3.5 w-3.5 text-text-muted" />}
      <span className="text-text-muted">{label}:</span>
      <span className="font-semibold text-text-primary">{value}</span>
    </span>
  )
}

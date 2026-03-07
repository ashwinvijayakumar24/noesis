import { useState, useEffect, useCallback, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { ArrowLeftIcon, XMarkIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import { handleError } from '../lib/errorHandler'
import { useAuthStore } from '../stores/authStore'
import DocumentViewer, { type DocumentViewerRef } from '../components/DocumentViewer'
import DraftHealthSummary from '../components/draft-analysis/DraftHealthSummary'
import TopActionItems from '../components/draft-analysis/TopActionItems'
import VersionProgressCard from '../components/draft-analysis/VersionProgressCard'
import SectionNavigation from '../components/draft-analysis/SectionNavigation'
import SectionFeedbackTabs from '../components/draft-analysis/SectionFeedbackTabs'
import { ProgressIndicator, useEstimatedProgress } from '../components/ui/ProgressIndicator'
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
  created_at: string
  updated_at: string
}

interface SectionCount {
  section_type: string
  new_count: number
  saved_count: number
  dismissed_count: number
  total_count: number
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

export default function DraftAnalysis() {
  const { projectId, draftId } = useParams<{ projectId: string; draftId: string }>()
  const navigate = useNavigate()
  const { session } = useAuthStore()
  const token = session?.access_token
  const documentViewerRef = useRef<DocumentViewerRef>(null)

  // State
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [signedFileUrl, setSignedFileUrl] = useState<string | null>(null)
  const [activeSection, setActiveSection] = useState<string>('introduction')
  const [sectionSummary, setSectionSummary] = useState<SectionCount[]>([])
  const [sectionFeedback, setSectionFeedback] = useState<{
    claims: Claim[]
    gaps: Gap[]
    feedback: Feedback[]
  }>({ claims: [], gaps: [], feedback: [] })
  const [priorityActions, setPriorityActions] = useState<string[]>([])
  const [latestComparison, setLatestComparison] = useState<any>(null)
  const [activeAnnotation, setActiveAnnotation] = useState<Annotation | null>(null)
  const [sectionsAssigned, setSectionsAssigned] = useState(false)

  // Progress tracking for initial analysis
  const checkAnalysisStatusRef = useRef<(() => Promise<void>) | null>(null)
  const { progress: estimatedProgress } = useEstimatedProgress(180) // Estimated 3 minutes for analysis

  // Fetch draft details (metadata only, signed URL loaded separately)
  const fetchDraft = useCallback(async () => {
    if (!draftId || !token) return

    try {
      const draft = await api.drafts.get(token, draftId)
      setDraft(draft)
    } catch (error) {
      handleError(error)
      toast.error('Failed to load draft')
    }
  }, [draftId, token])

  // Fetch signed URL separately (non-blocking)
  const fetchSignedUrl = useCallback(async () => {
    if (!draftId || !token) return

    try {
      const urlResponse = await api.drafts.getSignedUrl(token, draftId)
      setSignedFileUrl(urlResponse.signed_url)
    } catch (error) {
      console.error('Failed to fetch signed URL:', error)
    }
  }, [draftId, token])

  // Fetch section summary (feedback counts per section)
  const fetchSectionSummary = useCallback(async () => {
    if (!draftId || !token) return

    try {
      const response = await api.drafts.getSectionSummary(token, draftId)
      setSectionSummary(response.sections)

      // Auto-select first section with feedback (only if no section is active)
      if (response.sections.length > 0 && !activeSection) {
        setActiveSection(response.sections[0].section_type)
      }
    } catch (error) {
      console.error('Failed to fetch section summary:', error)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draftId, token])

  // Fetch feedback for a specific section
  const fetchSectionFeedback = useCallback(async (sectionType: string, status: string = 'new') => {
    if (!draftId || !token) return

    try {
      const response = await api.drafts.getFeedbackBySection(token, draftId, sectionType, status)

      setSectionFeedback({
        claims: response.claims || [],
        gaps: response.gaps || [],
        feedback: response.feedback || []
      })
    } catch (error) {
      console.error('Failed to fetch section feedback:', error)
      toast.error('Failed to load feedback for this section')
    }
  }, [draftId, token])

  // Assign sections (auto-migration for old drafts) — silent, runs on every analyzed draft load
  const assignSections = useCallback(async () => {
    if (!draftId || !token || sectionsAssigned) return

    try {
      await api.drafts.assignSections(token, draftId)
      setSectionsAssigned(true)
      // No toast — this is automatic and silent
    } catch (error) {
      console.error('Failed to assign sections:', error)
    }
  }, [draftId, token, sectionsAssigned])

  // Update feedback status (save/dismiss)
  const handleStatusChange = useCallback(async (
    feedbackId: string,
    feedbackType: 'claim' | 'gap' | 'feedback',
    newStatus: 'new' | 'saved' | 'dismissed'
  ) => {
    if (!draftId || !token) return

    try {
      await api.drafts.updateFeedbackStatus(token, draftId, feedbackId, feedbackType, newStatus)

      toast.success(newStatus === 'saved' ? 'Feedback saved' : 'Feedback dismissed')

      // Refresh section summary and current section feedback
      await fetchSectionSummary()
      await fetchSectionFeedback(activeSection)
    } catch (error) {
      handleError(error)
      toast.error('Failed to update feedback status')
    }
  }, [draftId, token, activeSection, fetchSectionSummary, fetchSectionFeedback])

  // View in document (scroll to line)
  const handleViewInDocument = useCallback((lineNumber: number) => {
    if (!lineNumber) return

    // Create annotation for highlighting
    setActiveAnnotation({
      id: `line-${lineNumber}`,
      type: 'claim',
      line_number: lineNumber,
      color: 'blue'
    })

    // Scroll to line in document viewer
    if (documentViewerRef.current) {
      documentViewerRef.current.scrollToLine(lineNumber)
    }
  }, [])

  // Handle section change
  const handleSectionChange = useCallback((sectionType: string) => {
    setActiveSection(sectionType)
    setActiveAnnotation(null) // Clear annotation when changing sections
  }, [])

  // Check analysis status (for processing drafts)
  const checkAnalysisStatus = useCallback(async () => {
    if (!draftId || !token) return

    try {
      const response = await api.drafts.getAnalysis(token, draftId)

      if (response.status === 'analyzed') {
        if (response.priority_actions?.length) {
          setPriorityActions(response.priority_actions)
        }
        await fetchDraft()
        await assignSections()
        await fetchSectionSummary()
        setLoading(false)
      } else if (response.status === 'failed') {
        setLoading(false)
        toast.error('Draft analysis failed')
      }
    } catch (error) {
      // Analysis not ready yet, keep polling
    }
  }, [draftId, token, fetchDraft, assignSections, fetchSectionSummary])

  // Initial load - OPTIMIZED: Parallel requests
  useEffect(() => {
    const init = async () => {
      if (!draftId || !token) return

      setLoading(true)

      try {
        // Fetch draft metadata, section summary, analysis, and comparisons in parallel
        const [draftData, summaryResponse, analysisResponse, comparisonsResponse] = await Promise.all([
          api.drafts.get(token, draftId),
          api.drafts.getSectionSummary(token, draftId),
          api.drafts.getAnalysis(token, draftId),
          projectId ? api.drafts.listComparisons(token, projectId).catch(() => null) : Promise.resolve(null)
        ])

        if (analysisResponse?.priority_actions?.length) {
          setPriorityActions(analysisResponse.priority_actions)
        }

        // Find the most recent comparison involving this draft
        if (comparisonsResponse?.comparisons?.length) {
          const myComparison = comparisonsResponse.comparisons.find(
            (c: any) => c.draft_v2_id === draftId || c.draft_v1_id === draftId
          )
          if (myComparison) {
            try {
              const detail = await api.drafts.getComparison(token, myComparison.comparison_id)
              setLatestComparison(detail)
            } catch {
              // Comparison detail not critical
            }
          }
        }

        setDraft(draftData)

        // Load signed URL in background (non-blocking)
        fetchSignedUrl()

        if (draftData.status === 'analyzed') {
          // Ensure sections are assigned (silent, idempotent)
          await assignSections()

          // Re-fetch summary after assignment to get correct section types
          const updatedSummary = await api.drafts.getSectionSummary(token, draftId)
          const sections = updatedSummary.sections
          setSectionSummary(sections)

          // Pre-fetch feedback for the first section so health score is correct from first render
          const firstSection = sections.length > 0 ? sections[0].section_type : 'introduction'
          setActiveSection(firstSection)
          const feedbackResponse = await api.drafts.getFeedbackBySection(token, draftId, firstSection, 'new')
          setSectionFeedback({
            claims: feedbackResponse.claims || [],
            gaps: feedbackResponse.gaps || [],
            feedback: feedbackResponse.feedback || []
          })
        } else {
          setSectionSummary(summaryResponse.sections)
          if (summaryResponse.sections.length > 0) {
            setActiveSection(summaryResponse.sections[0].section_type)
          }
        }
      } catch (error) {
        handleError(error)
        toast.error('Failed to load draft')
      } finally {
        setLoading(false)
      }
    }

    init()
  }, [draftId, token, assignSections, fetchSignedUrl])

  // Load section feedback when user switches sections (after initial load)
  useEffect(() => {
    if (activeSection && draft?.status === 'analyzed' && !loading) {
      fetchSectionFeedback(activeSection)
    }
  }, [activeSection]) // eslint-disable-line react-hooks/exhaustive-deps

  // Poll for analysis completion
  useEffect(() => {
    if (draft?.status === 'processing' || draft?.status === 'uploaded') {
      checkAnalysisStatusRef.current = checkAnalysisStatus

      const interval = setInterval(checkAnalysisStatus, 3000)
      return () => clearInterval(interval)
    }
  }, [draft?.status, checkAnalysisStatus])

  // Loading state
  if (loading) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-500 border-r-transparent mb-4"></div>
          <p className="text-slate-300">Loading draft analysis...</p>
        </div>
      </div>
    )
  }

  // Draft not found
  if (!draft) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-slate-300 mb-4">Draft not found</p>
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="text-blue-400 hover:text-blue-300"
          >
            Return to Project
          </button>
        </div>
      </div>
    )
  }

  // Processing state
  if (draft.status === 'processing' || draft.status === 'uploaded') {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center p-6">
        <div className="max-w-2xl w-full">
          <ProgressIndicator
            progress={estimatedProgress}
            status="Analyzing Draft"
          />
          <p className="mt-4 text-center text-sm text-text-secondary">
            Extracting claims, identifying coverage gaps, and generating reviewer feedback...
          </p>
        </div>
      </div>
    )
  }

  // Failed state
  if (draft.status === 'failed') {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-400 mb-4">Draft analysis failed</p>
          <p className="text-slate-400 text-sm mb-4">Please try uploading the draft again.</p>
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="text-blue-400 hover:text-blue-300"
          >
            Return to Project
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 flex flex-col">
      {/* Header with Breadcrumbs */}
      <header className="bg-slate-900 border-b border-slate-800 px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="p-2 text-slate-400 hover:text-slate-200 rounded-md hover:bg-slate-800 transition-colors"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div>
            <div className="flex items-center gap-2 text-sm text-slate-500">
              <Link to="/projects" className="hover:text-slate-300 transition-colors">
                Projects
              </Link>
              <span>/</span>
              <Link to={`/projects/${projectId}`} className="hover:text-slate-300 transition-colors">
                Project
              </Link>
              <span>/</span>
              <span className="text-slate-300">Draft Analysis</span>
            </div>
            <h1 className="text-xl font-semibold text-slate-100 mt-1">
              {draft.title}
              {draft.version > 1 && (
                <span className="ml-2 text-sm text-slate-400">v{draft.version}</span>
              )}
            </h1>
          </div>
        </div>
        <FeedbackButton
          featureType="draft_analysis"
          contextId={draftId}
        />
      </header>

      {/* Main Content: Document Viewer + Analysis */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left: Document Viewer */}
        <div className="w-1/2 border-r border-slate-800 flex flex-col bg-slate-950">
          <div className="px-4 py-3 border-b border-slate-800 bg-slate-900">
            <h2 className="text-sm font-medium text-slate-200">Document</h2>
          </div>
          <div className="flex-1 overflow-hidden">
            {/* Annotation Legend */}
            {activeAnnotation && (
              <div className="flex items-center gap-4 px-4 py-2 bg-slate-900 border-b border-slate-800 text-xs">
                <span className="text-slate-400">Active Highlight:</span>
                <div className="flex items-center gap-2">
                  <div className="w-3 h-3 rounded bg-blue-500/30 border border-blue-500" />
                  <span className="text-slate-300">
                    {activeAnnotation.type.toUpperCase()} - Line {activeAnnotation.line_number}
                  </span>
                </div>
                <button
                  onClick={() => setActiveAnnotation(null)}
                  className="ml-auto flex items-center gap-1 px-2 py-1 text-slate-400 hover:text-slate-200 transition-colors"
                >
                  <XMarkIcon className="h-3 w-3" />
                  Clear
                </button>
              </div>
            )}

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
                  <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-blue-500 border-r-transparent mb-4"></div>
                  <p className="text-slate-300">Loading document...</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Section-Based Analysis */}
        <div className="w-1/2 flex flex-col bg-slate-950 overflow-hidden">
          {/* Top Action Items + Version Progress + Health Summary */}
          <div className="px-4 pt-4 shrink-0">
            <TopActionItems actions={priorityActions} />
            {latestComparison && (
              <VersionProgressCard
                projectId={projectId!}
                comparisonId={latestComparison.comparison_id}
                improvementScore={latestComparison.improvement_score}
                feedbackTracked={latestComparison.feedback_tracked || []}
                narrative={latestComparison.narrative}
                v1Id={latestComparison.stats ? latestComparison.detailed_changes?.metadata?.draft_v1_id ?? '' : ''}
                v2Id={draftId!}
              />
            )}
            <DraftHealthSummary
              draft={draft}
              claims={sectionFeedback.claims}
              gaps={sectionFeedback.gaps}
              feedback={sectionFeedback.feedback}
              addressedItems={[]}
              onReanalyze={() => {}} // Disabled - no re-analyze functionality
              isReanalyzing={false}
            />
          </div>

          {/* Section Navigation + Feedback Panels */}
          <div className="flex-1 flex gap-4 p-4 overflow-hidden">
            {/* Left Sidebar: Section Navigation */}
            <div className="w-64 shrink-0">
              <SectionNavigation
                sections={sectionSummary}
                activeSection={activeSection}
                onSectionChange={handleSectionChange}
              />
            </div>

            {/* Right Panel: Section Feedback Tabs */}
            <div className="flex-1 overflow-y-auto">
              <SectionFeedbackTabs
                sectionType={activeSection}
                claims={sectionFeedback.claims}
                gaps={sectionFeedback.gaps}
                feedback={sectionFeedback.feedback}
                onStatusChange={handleStatusChange}
                onViewInDocument={handleViewInDocument}
              />
            </div>
          </div>
        </div>
      </main>
    </div>
  )
}

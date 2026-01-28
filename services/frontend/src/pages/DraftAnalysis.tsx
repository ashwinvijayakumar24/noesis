import { useState, useEffect, useCallback, useMemo, useRef } from 'react'
import { useParams, useNavigate, Link, useSearchParams } from 'react-router-dom'
import { Tab } from '@headlessui/react'
import { ArrowLeftIcon, DocumentTextIcon, BeakerIcon, ExclamationTriangleIcon, XMarkIcon, ListBulletIcon, LinkIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import { handleError } from '../lib/errorHandler'
import { useAuthStore } from '../stores/authStore'
import DocumentViewer, { type DocumentViewerRef } from '../components/DocumentViewer'
import FeedbackPanel from '../components/draft-analysis/FeedbackPanel'
import GapsPanel from '../components/draft-analysis/GapsPanel'
import ClaimsPanel from '../components/draft-analysis/ClaimsPanel'
import CitationsPanel from '../components/draft-analysis/CitationsPanel'
import DraftHealthSummary from '../components/draft-analysis/DraftHealthSummary'
import ActionItems from '../components/draft-analysis/ActionItems'
import AnalysisFilters, { type FilterState } from '../components/draft-analysis/AnalysisFilters'
import { ProgressIndicator, useEstimatedProgress } from '../components/ui/ProgressIndicator'
import { useProgressTracker } from '../hooks/useProgressTracker'
import toast from 'react-hot-toast'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  section_location: string
  importance_score: number
  requires_citation: boolean
  existing_citations: string[]
  line_number?: number
  char_start?: number
  char_end?: number
  text_snippet?: string
}

interface Gap {
  id: string
  gap_type: string
  description: string
  priority: string
  suggested_papers: any[]
  line_number?: number
  char_start?: number
  char_end?: number
  text_snippet?: string
}

interface Feedback {
  id: string
  feedback_type: string
  severity: string
  feedback_text: string
  suggestions: string[]
  section_reference?: string
  line_number?: number
  char_start?: number
  char_end?: number
  text_snippet?: string
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
  const [searchParams, setSearchParams] = useSearchParams()

  // State
  const [loading, setLoading] = useState(true)
  const [draft, setDraft] = useState<Draft | null>(null)
  const [signedFileUrl, setSignedFileUrl] = useState<string | null>(null)
  const [claims, setClaims] = useState<Claim[]>([])
  const [gaps, setGaps] = useState<Gap[]>([])
  const [feedback, setFeedback] = useState<Feedback[]>([])
  const [generatingSuggestions, setGeneratingSuggestions] = useState<string | null>(null)
  const [isRegeneratingAll, setIsRegeneratingAll] = useState(false)
  const [isReanalyzing, setIsReanalyzing] = useState(false)
  const [showActionItems, setShowActionItems] = useState(true)

  // Progress tracking with localStorage persistence
  const { addressedItems, toggleAddressed } = useProgressTracker(draftId)

  // Filter state
  const [filters, setFilters] = useState<FilterState>({
    severityFilter: (searchParams.get('severity') as FilterState['severityFilter']) || 'all',
    priorityFilter: (searchParams.get('priority') as FilterState['priorityFilter']) || 'all',
    claimTypeFilter: searchParams.get('claimType') || 'all',
    citationStatusFilter: (searchParams.get('citationStatus') as FilterState['citationStatusFilter']) || 'all',
    searchQuery: searchParams.get('search') || ''
  })

  // Active tab state (from URL or default to 0)
  const [selectedTab, setSelectedTab] = useState(parseInt(searchParams.get('tab') || '0', 10))

  // Progress tracking for draft analysis (estimated 90 seconds - longer than documents)
  const { progress, elapsedTime, estimatedTimeRemaining } = useEstimatedProgress(90)

  // Annotation state for clickable highlights
  const [activeAnnotation, setActiveAnnotation] = useState<Annotation | null>(null)
  const documentViewerRef = useRef<DocumentViewerRef>(null)

  // Color getter functions for annotations
  const getSeverityColor = (severity: string): string => {
    switch (severity) {
      case 'critical': return 'red'
      case 'major': return 'orange'
      case 'minor': return 'yellow'
      case 'suggestion': return 'blue'
      default: return 'gray'
    }
  }

  const getClaimColor = (claim: Claim): string => {
    if (claim.requires_citation && (!claim.existing_citations || claim.existing_citations.length === 0)) {
      return 'red' // Missing citations
    }
    if (claim.existing_citations && claim.existing_citations.length > 0) {
      return 'blue' // Has citations
    }
    return 'green' // Original contribution
  }

  const getGapColor = (): string => 'purple'

  const loadDraftData = useCallback(async () => {
    if (!draftId || !token) return

    try {
      setLoading(true)

      console.log('[DRAFT-ANALYSIS-PAGE] Loading draft data for draftId:', draftId)

      // Load draft metadata and analysis results in parallel
      const [draftData, claimsData, gapsData, feedbackData] = await Promise.all([
        api.drafts.get(token, draftId),
        api.drafts.getClaims(token, draftId).catch(() => ({ claims: [] })),
        api.drafts.getGaps(token, draftId).catch(() => ({ gaps: [] })),
        api.drafts.getFeedback(token, draftId).catch(() => ({ feedback: [] })),
      ])

      console.log('[DRAFT-ANALYSIS-PAGE] Draft data:', draftData)
      console.log('[DRAFT-ANALYSIS-PAGE] Claims:', claimsData.claims?.length || 0)

      // Normalize claims data
      const normalizedClaims = (claimsData.claims || []).map((claim: any) => ({
        ...claim,
        existing_citations: Array.isArray(claim.existing_citations)
          ? claim.existing_citations
          : (claim.existing_citations ? [claim.existing_citations] : []),
        requires_citation: claim.requires_citation !== null && claim.requires_citation !== undefined
          ? Boolean(claim.requires_citation)
          : true,
      }))

      setDraft(draftData)
      setClaims(normalizedClaims)
      setGaps(gapsData.gaps || [])
      setFeedback(feedbackData.feedback || [])

      // Fetch signed URL for private bucket access
      try {
        console.log('[DRAFT-ANALYSIS-PAGE] Fetching signed URL for draft:', draftId)
        const signedUrlResponse = await fetch(
          `${import.meta.env.VITE_API_URL}/drafts/${draftId}/signed-url`,
          {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          }
        )

        console.log('[DRAFT-ANALYSIS-PAGE] Signed URL response status:', signedUrlResponse.status)

        if (signedUrlResponse.ok) {
          const responseData = await signedUrlResponse.json()
          console.log('[DRAFT-ANALYSIS-PAGE] Signed URL response data:', responseData)
          const { signed_url } = responseData
          if (signed_url) {
            setSignedFileUrl(signed_url)
            console.log('[DRAFT-ANALYSIS-PAGE] ✓ Using signed URL:', signed_url.substring(0, 100) + '...')
          } else {
            console.error('[DRAFT-ANALYSIS-PAGE] ✗ No signed_url in response, using public URL')
            setSignedFileUrl(draftData.file_url)
          }
        } else {
          const errorText = await signedUrlResponse.text()
          console.error('[DRAFT-ANALYSIS-PAGE] ✗ Failed to fetch signed URL:', signedUrlResponse.status, errorText)
          setSignedFileUrl(draftData.file_url)
        }
      } catch (urlError) {
        console.error('[DRAFT-ANALYSIS-PAGE] ✗ Exception fetching signed URL:', urlError)
        setSignedFileUrl(draftData.file_url)
      }
    } catch (error: any) {
      console.error('[DRAFT-ANALYSIS-PAGE] Error loading draft:', error)
      handleError(error, 'loading draft analysis')
    } finally {
      setLoading(false)
    }
  }, [token, draftId])

  useEffect(() => {
    console.log('[DRAFT-ANALYSIS-PAGE] useEffect triggered - draftId:', draftId, 'token:', token ? 'present' : 'missing')
    if (draftId && token) {
      loadDraftData()
    }
  }, [draftId, token, loadDraftData])

  const handleFindSuggestions = async (claim: Claim) => {
    if (!projectId || !draftId || !token) return

    try {
      setGeneratingSuggestions(claim.id)
      toast.loading('Finding relevant citations...')

      await api.citations.generateSuggestions(token, {
        claim_text: claim.claim_text,
        project_id: projectId,
        draft_id: draftId,
        existing_citations: claim.existing_citations || [],
        max_suggestions: 5
      })

      toast.dismiss()
      toast.success('Citation suggestions found! Check the Citations tab.')
    } catch (error: any) {
      toast.dismiss()
      handleError(error, 'finding citation suggestions')
    } finally {
      setGeneratingSuggestions(null)
    }
  }

  const handleRegenerateAllCitations = async () => {
    if (!projectId || !draftId || !token) return

    try {
      setIsRegeneratingAll(true)
      toast.loading('Regenerating all citation suggestions...')

      // Generate suggestions for all claims that need citations
      const claimsNeedingCitations = claims.filter(c => c.requires_citation === true)

      if (claimsNeedingCitations.length === 0) {
        toast.dismiss()
        toast.success('No claims need citations!')
        return
      }

      // Generate suggestions for each claim in parallel
      await Promise.all(
        claimsNeedingCitations.map(claim =>
          api.citations.generateSuggestions(token, {
            claim_text: claim.claim_text,
            project_id: projectId,
            draft_id: draftId,
            existing_citations: claim.existing_citations || [],
            max_suggestions: 5
          })
        )
      )

      toast.dismiss()
      toast.success(`Generated citation suggestions for ${claimsNeedingCitations.length} claims! Check the Citations tab.`)
    } catch (error: any) {
      toast.dismiss()
      handleError(error, 'regenerating citation suggestions')
    } finally {
      setIsRegeneratingAll(false)
    }
  }

  const handleReanalyze = async () => {
    if (!draftId || !token) return

    try {
      setIsReanalyzing(true)
      toast.loading('Re-analyzing draft...')
      await api.drafts.analyze(token, draftId)
      toast.dismiss()
      toast.success('Analysis started! This may take 1-2 minutes.')
      // Reload data after a delay
      setTimeout(() => loadDraftData(), 3000)
    } catch (error: any) {
      toast.dismiss()
      handleError(error, 're-analyzing draft')
    } finally {
      setIsReanalyzing(false)
    }
  }

  // Handle viewing an action item in the document
  const handleViewActionInDocument = (item: any) => {
    if (item.line_number) {
      documentViewerRef.current?.scrollToLine(item.line_number)
    }
  }

  // Click handlers for annotations
  const handleFeedbackClick = (feedback: Feedback) => {
    if (feedback.line_number) {
      const annotation: Annotation = {
        id: feedback.id,
        type: 'feedback',
        line_number: feedback.line_number,
        char_start: feedback.char_start,
        char_end: feedback.char_end,
        text_snippet: feedback.text_snippet,
        section_location: feedback.section_reference,
        color: getSeverityColor(feedback.severity)
      }
      setActiveAnnotation(annotation)
      documentViewerRef.current?.scrollToLine(feedback.line_number)
    }
  }

  const handleGapClick = (gap: Gap) => {
    if (gap.line_number) {
      const annotation: Annotation = {
        id: gap.id,
        type: 'gap',
        line_number: gap.line_number,
        char_start: gap.char_start,
        char_end: gap.char_end,
        text_snippet: gap.text_snippet,
        section_location: gap.gap_type,
        color: getGapColor()
      }
      setActiveAnnotation(annotation)
      documentViewerRef.current?.scrollToLine(gap.line_number)
    }
  }

  const handleClaimClick = (claim: Claim) => {
    if (claim.line_number) {
      const annotation: Annotation = {
        id: claim.id,
        type: 'claim',
        line_number: claim.line_number,
        char_start: claim.char_start,
        char_end: claim.char_end,
        text_snippet: claim.text_snippet,
        section_location: claim.section_location,
        color: getClaimColor(claim)
      }
      setActiveAnnotation(annotation)
      documentViewerRef.current?.scrollToLine(claim.line_number)
    }
  }

  // Update URL params when filters change
  const handleFiltersChange = (newFilters: FilterState) => {
    setFilters(newFilters)

    const params = new URLSearchParams(searchParams)

    // Update filter params
    if (newFilters.severityFilter !== 'all') {
      params.set('severity', newFilters.severityFilter)
    } else {
      params.delete('severity')
    }

    if (newFilters.priorityFilter !== 'all') {
      params.set('priority', newFilters.priorityFilter)
    } else {
      params.delete('priority')
    }

    if (newFilters.claimTypeFilter !== 'all') {
      params.set('claimType', newFilters.claimTypeFilter)
    } else {
      params.delete('claimType')
    }

    if (newFilters.citationStatusFilter !== 'all') {
      params.set('citationStatus', newFilters.citationStatusFilter)
    } else {
      params.delete('citationStatus')
    }

    if (newFilters.searchQuery) {
      params.set('search', newFilters.searchQuery)
    } else {
      params.delete('search')
    }

    setSearchParams(params, { replace: true })
  }

  // Update URL params when tab changes
  const handleTabChange = (index: number) => {
    setSelectedTab(index)
    const params = new URLSearchParams(searchParams)
    params.set('tab', index.toString())
    setSearchParams(params, { replace: true })
  }

  // Get unique claim types for filter dropdown
  const claimTypes = useMemo(() => {
    const types = new Set(claims.map(c => c.claim_type))
    return Array.from(types).sort()
  }, [claims])

  // Get active tab name for filter component
  const tabNames = ['feedback', 'gaps', 'claims', 'citations']
  const activeTab = tabNames[selectedTab]

  // Apply filters to data
  const filteredFeedback = useMemo(() => {
    let result = feedback

    if (filters.severityFilter !== 'all') {
      result = result.filter(f => f.severity === filters.severityFilter)
    }

    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase()
      result = result.filter(f =>
        f.feedback_text.toLowerCase().includes(query) ||
        f.feedback_type.toLowerCase().includes(query)
      )
    }

    return result
  }, [feedback, filters])

  const filteredGaps = useMemo(() => {
    let result = gaps

    if (filters.priorityFilter !== 'all') {
      result = result.filter(g => g.priority === filters.priorityFilter)
    }

    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase()
      result = result.filter(g =>
        g.description.toLowerCase().includes(query) ||
        g.gap_type.toLowerCase().includes(query)
      )
    }

    return result
  }, [gaps, filters])

  const filteredClaims = useMemo(() => {
    let result = claims

    if (filters.claimTypeFilter !== 'all') {
      result = result.filter(c => c.claim_type === filters.claimTypeFilter)
    }

    if (filters.citationStatusFilter !== 'all') {
      if (filters.citationStatusFilter === 'missing') {
        result = result.filter(c => c.requires_citation && (!c.existing_citations || c.existing_citations.length === 0))
      } else if (filters.citationStatusFilter === 'has_citations') {
        result = result.filter(c => c.existing_citations && c.existing_citations.length > 0)
      } else if (filters.citationStatusFilter === 'original') {
        result = result.filter(c => !c.requires_citation)
      }
    }

    if (filters.searchQuery) {
      const query = filters.searchQuery.toLowerCase()
      result = result.filter(c =>
        c.claim_text.toLowerCase().includes(query) ||
        c.claim_type.toLowerCase().includes(query) ||
        c.section_location.toLowerCase().includes(query)
      )
    }

    return result
  }, [claims, filters])

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-primary"></div>
          <p className="mt-4 text-text-secondary">Loading draft analysis...</p>
        </div>
      </div>
    )
  }

  if (!draft) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <div className="text-center">
          <ExclamationTriangleIcon className="h-16 w-16 text-error mx-auto" />
          <h2 className="mt-4 text-xl font-serif font-semibold text-text-primary">Draft not found</h2>
          <p className="mt-2 text-text-secondary">The draft you're looking for doesn't exist or has been deleted.</p>
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="mt-6 px-4 py-2 bg-surface border border-border-base text-text-primary rounded-lg hover:bg-surface-hover transition-colors"
          >
            Back to Project
          </button>
        </div>
      </div>
    )
  }

  if (draft.status === 'processing' || draft.status === 'uploaded') {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center p-6">
        <div className="max-w-2xl w-full">
          <ProgressIndicator
            progress={progress}
            status="Analyzing Your Draft"
            estimatedTimeRemaining={estimatedTimeRemaining}
            showElapsedTime={true}
            steps={[
              {
                label: 'Extracting document structure',
                description: 'Analyzing sections, paragraphs, and formatting',
                completed: elapsedTime > 10,
                active: elapsedTime <= 10
              },
              {
                label: 'Identifying claims and assertions',
                description: 'Finding key arguments, hypotheses, and statements',
                completed: elapsedTime > 30,
                active: elapsedTime > 10 && elapsedTime <= 30
              },
              {
                label: 'Analyzing citations and references',
                description: 'Mapping claims to supporting literature',
                completed: elapsedTime > 50,
                active: elapsedTime > 30 && elapsedTime <= 50
              },
              {
                label: 'Detecting coverage gaps',
                description: 'Identifying areas needing additional literature',
                completed: elapsedTime > 70,
                active: elapsedTime > 50 && elapsedTime <= 70
              },
              {
                label: 'Generating expert feedback',
                description: 'Creating reviewer-style critique and suggestions',
                completed: false,
                active: elapsedTime > 70
              }
            ]}
          />
          <div className="mt-8 text-center">
            <p className="text-sm text-text-muted">You can safely leave this page. Analysis continues in the background.</p>
            <button
              onClick={() => navigate(`/projects/${projectId}`)}
              className="mt-4 px-4 py-2 bg-surface border border-border-base text-text-primary rounded-lg hover:bg-surface-hover transition-colors"
            >
              Back to Project
            </button>
          </div>
        </div>
      </div>
    )
  }

  if (draft.status === 'failed') {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <div className="text-center">
          <ExclamationTriangleIcon className="h-16 w-16 text-error mx-auto" />
          <h2 className="mt-4 text-xl font-serif font-semibold text-text-primary">Analysis failed</h2>
          <p className="mt-2 text-text-secondary">Draft analysis failed. Please try analyzing again.</p>
          <div className="mt-6 flex items-center justify-center gap-3">
            <button
              onClick={() => {
                if (draftId && token) {
                  api.drafts.analyze(token, draftId).then(() => {
                    toast.success('Analysis started!')
                    setTimeout(() => loadDraftData(), 2000)
                  })
                }
              }}
              className="px-4 py-2 bg-accent-primary text-white rounded-lg hover:bg-accent-hover transition-colors"
            >
              Retry Analysis
            </button>
            <button
              onClick={() => navigate(`/projects/${projectId}`)}
              className="px-4 py-2 bg-surface border border-border-base text-text-primary rounded-lg hover:bg-surface-hover transition-colors"
            >
              Back to Project
            </button>
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-bg-base flex flex-col">
      {/* Header with Breadcrumbs */}
      <header className="bg-surface border-b border-border-base px-6 py-4 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="p-2 text-text-tertiary hover:text-text-primary rounded-md hover:bg-surface-hover transition-colors"
          >
            <ArrowLeftIcon className="h-5 w-5" />
          </button>
          <div>
            <div className="flex items-center gap-2 text-sm text-text-muted font-mono">
              <Link to="/projects" className="hover:text-text-primary transition-colors">
                Projects
              </Link>
              <span>/</span>
              <Link to={`/projects/${projectId}`} className="hover:text-text-primary transition-colors">
                Project
              </Link>
              <span>/</span>
              <span className="text-text-secondary">Drafts</span>
            </div>
            <h1 className="text-xl font-serif font-semibold text-text-primary mt-1">
              {draft.title}
              {draft.version > 1 && (
                <span className="ml-2 text-sm text-text-muted font-mono">v{draft.version}</span>
              )}
            </h1>
          </div>
        </div>
        <div className="flex items-center gap-3">
          {/* TODO: Add Export and Compare Versions buttons */}
        </div>
      </header>

      {/* Main Content: 50/50 Split */}
      <main className="flex-1 flex overflow-hidden">
        {/* Left: Document Viewer */}
        <div className="w-1/2 border-r border-border-base flex flex-col bg-bg-base">
          <div className="px-4 py-3 border-b border-border-base bg-surface">
            <h2 className="text-sm font-medium text-text-primary font-mono">Document</h2>
          </div>
          <div className="flex-1 overflow-hidden">
            {/* Annotation Legend - shows when annotation is active */}
            {activeAnnotation && (
              <div className="flex items-center gap-4 px-4 py-2 bg-surface border-b border-border-base text-xs">
                <span className="text-text-muted font-mono">Active Highlight:</span>
                <div className="flex items-center gap-2">
                  <div className={`w-3 h-3 rounded bg-${activeAnnotation.color}-200 border border-${activeAnnotation.color}-400`} />
                  <span className="font-mono text-text-secondary">
                    {activeAnnotation.type.toUpperCase()} - Line {activeAnnotation.line_number}
                  </span>
                </div>
                <button
                  onClick={() => setActiveAnnotation(null)}
                  className="ml-auto flex items-center gap-1 px-2 py-1 text-text-muted hover:text-text-primary transition-colors"
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
                  <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-solid border-accent-primary border-r-transparent mb-4"></div>
                  <p className="text-text-secondary">Loading draft file...</p>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Right: Analysis Tabs */}
        <div className="w-1/2 flex flex-col bg-bg-base overflow-hidden">
          {/* Health Summary at Top */}
          <div className="px-4 pt-4 shrink-0">
            <DraftHealthSummary
              draft={draft}
              claims={claims}
              gaps={gaps}
              feedback={feedback}
              addressedItems={addressedItems}
              onReanalyze={handleReanalyze}
              isReanalyzing={isReanalyzing}
            />
          </div>

          {/* Action Items Toggle */}
          <div className="px-4 pb-2 shrink-0">
            <button
              onClick={() => setShowActionItems(!showActionItems)}
              className="flex items-center gap-2 text-sm text-text-secondary hover:text-text-primary transition-colors"
            >
              <ListBulletIcon className="h-4 w-4" />
              {showActionItems ? 'Hide' : 'Show'} Action Items
            </button>
          </div>

          {/* Collapsible Action Items */}
          {showActionItems && (
            <div className="px-4 pb-4 shrink-0 max-h-[300px] overflow-y-auto">
              <ActionItems
                claims={claims}
                gaps={gaps}
                feedback={feedback}
                addressedItems={addressedItems}
                onToggleAddressed={toggleAddressed}
                onViewInDocument={handleViewActionInDocument}
                onViewSuggestions={handleFindSuggestions}
              />
            </div>
          )}

          <Tab.Group selectedIndex={selectedTab} onChange={handleTabChange}>
            <Tab.List className="flex gap-2 px-6 py-4 border-b border-border-base bg-surface shrink-0">
              <Tab className={({ selected }) =>
                `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  selected
                    ? 'bg-accent-primary text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                }`
              }>
                <div className="flex items-center gap-2">
                  <ExclamationTriangleIcon className="h-4 w-4" />
                  <span>Feedback</span>
                  <span className="px-2 py-0.5 bg-bg-base rounded-full text-xs">
                    {filteredFeedback.length}
                  </span>
                </div>
              </Tab>
              <Tab className={({ selected }) =>
                `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  selected
                    ? 'bg-accent-primary text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                }`
              }>
                <div className="flex items-center gap-2">
                  <BeakerIcon className="h-4 w-4" />
                  <span>Coverage Gaps</span>
                  <span className="px-2 py-0.5 bg-bg-base rounded-full text-xs">
                    {filteredGaps.length}
                  </span>
                </div>
              </Tab>
              <Tab className={({ selected }) =>
                `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  selected
                    ? 'bg-accent-primary text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                }`
              }>
                <div className="flex items-center gap-2">
                  <DocumentTextIcon className="h-4 w-4" />
                  <span>Claims</span>
                  <span className="px-2 py-0.5 bg-bg-base rounded-full text-xs">
                    {filteredClaims.length}
                  </span>
                </div>
              </Tab>
              <Tab className={({ selected }) =>
                `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  selected
                    ? 'bg-accent-primary text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                }`
              }>
                <div className="flex items-center gap-2">
                  <LinkIcon className="h-4 w-4" />
                  <span>Citations</span>
                </div>
              </Tab>
            </Tab.List>

            {/* Filters */}
            <AnalysisFilters
              filters={filters}
              onFiltersChange={handleFiltersChange}
              claimTypes={claimTypes}
              activeTab={activeTab}
            />

            <Tab.Panels className="flex-1 overflow-y-auto">
              <Tab.Panel className="p-6">
                <FeedbackPanel
                  feedback={filteredFeedback}
                  onFeedbackClick={handleFeedbackClick}
                />
              </Tab.Panel>
              <Tab.Panel className="p-6">
                <GapsPanel
                  gaps={filteredGaps}
                  onGapClick={handleGapClick}
                />
              </Tab.Panel>
              <Tab.Panel className="p-6">
                <ClaimsPanel
                  claims={filteredClaims}
                  onRegenerateAll={handleRegenerateAllCitations}
                  isRegenerating={isRegeneratingAll}
                  onClaimClick={handleClaimClick}
                />
              </Tab.Panel>
              <Tab.Panel className="p-0">
                {token && draftId && projectId ? (
                  <CitationsPanel
                    token={token}
                    draftId={draftId}
                    projectId={projectId}
                  />
                ) : (
                  <div className="text-center py-12">
                    <p className="text-text-tertiary">Loading...</p>
                  </div>
                )}
              </Tab.Panel>
            </Tab.Panels>
          </Tab.Group>
        </div>
      </main>
    </div>
  )
}

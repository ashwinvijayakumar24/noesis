import { useState, useEffect, useCallback } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { Tab } from '@headlessui/react'
import { ArrowLeftIcon, DocumentTextIcon, BeakerIcon, LightBulbIcon, ExclamationTriangleIcon, BookOpenIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import { handleError } from '../lib/errorHandler'
import { useAuthStore } from '../stores/authStore'
import DocumentViewer from '../components/DocumentViewer'
import { Badge } from '../components/ui/Badge'
import InlineAlert from '../components/ui/InlineAlert'
import { ProgressIndicator } from '../components/ui/ProgressIndicator'

interface Document {
  id: string
  title: string
  file_url: string
  file_type: string
  status: string
  analysis: DocumentAnalysis | null
  progress?: {
    stage?: string
    label?: string
    percent?: number
    retrying?: boolean
  }
  error_detail?: {
    title?: string
    message?: string
    details?: string[]
  }
  created_at: string
  updated_at: string
}

interface DocumentAnalysis {
  executive_summary?: string
  research_problem?: string
  key_questions?: string[]
  methodology?: {
    approach?: string
    techniques?: string[]
    dataset?: string
  }
  key_findings?: string[]
  results?: {
    summary?: string
    metrics?: string[]
  }
  limitations?: string[]
  future_work?: string[]
  key_citations?: Array<{
    authors?: string
    year?: string
    title?: string
    relevance?: string
  }>
}

export default function DocumentAnalysis() {
  const { projectId, documentId } = useParams<{ projectId: string; documentId: string }>()
  const navigate = useNavigate()
  const { session } = useAuthStore()
  const token = session?.access_token

  const [loading, setLoading] = useState(true)
  const [document, setDocument] = useState<Document | null>(null)
  const [selectedTab, setSelectedTab] = useState(0)

  const documentProgressSteps = [
    { key: 'queued', label: 'Queued' },
    { key: 'parsing_pdf', label: 'Parsing PDF' },
    { key: 'extracting_structure', label: 'Extracting structure' },
    { key: 'running_analysis', label: 'Running analysis' },
    { key: 'generating_embeddings', label: 'Saving evidence' },
    { key: 'finalizing', label: 'Finalizing' },
  ]

  const loadDocumentData = useCallback(async () => {
    if (!documentId || !token) return

    try {
      setLoading(true)

      const documentData = await api.documents.get(token, documentId)

      setDocument(documentData)

      // Auto-trigger analysis if not analyzed yet
      if (!documentData.analysis && documentData.status !== 'analyzing' && documentData.status !== 'failed') {
        try {
          await api.documents.analyze(token, documentId)
          // Update status to analyzing
          setDocument({ ...documentData, status: 'analyzing' })
        } catch (analyzeError: any) {
          console.error('[DOCUMENT-ANALYSIS-PAGE] Failed to trigger analysis:', analyzeError)
        }
      }
    } catch (error: any) {
      console.error('[DOCUMENT-ANALYSIS-PAGE] Error loading document:', error)
      handleError(error, 'loading document analysis')
    } finally {
      setLoading(false)
    }
  }, [token, documentId])

  useEffect(() => {
    if (documentId && token) {
      loadDocumentData()
    }
  }, [documentId, token, loadDocumentData])

  // Poll for analysis completion when status is analyzing
  useEffect(() => {
    if (!document || document.status !== 'analyzing') return

    const pollInterval = setInterval(async () => {
      try {
        const documentData = await api.documents.get(token!, documentId!)
        setDocument(documentData)

        // Stop polling when analysis is complete or failed
        if (documentData.status === 'analyzed' || documentData.status === 'failed') {
          clearInterval(pollInterval)
        }
      } catch (error) {
        console.error('[DOCUMENT-ANALYSIS-PAGE] Polling error:', error)
      }
    }, 3000) // Poll every 3 seconds

    return () => {
      clearInterval(pollInterval)
    }
  }, [document?.status, documentId, token])

  const handleTabChange = (index: number) => {
    setSelectedTab(index)
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-primary"></div>
          <p className="mt-4 text-text-secondary">Loading document analysis...</p>
        </div>
      </div>
    )
  }

  if (!document) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <div className="text-center">
          <DocumentTextIcon className="h-16 w-16 text-text-muted mx-auto" />
          <h2 className="mt-4 text-xl font-serif font-semibold text-text-primary">Document not found</h2>
          <p className="mt-2 text-text-secondary">The document you're looking for doesn't exist.</p>
          <button
            onClick={() => navigate(`/projects/${projectId}`)}
            className="mt-6 px-4 py-2 bg-accent-primary text-white rounded-lg hover:bg-accent-hover transition-colors"
          >
            Back to Project
          </button>
        </div>
      </div>
    )
  }

  const analysis = document.analysis as DocumentAnalysis | null

  // Safety check: If analysis is null but status is 'analyzed', there's a data inconsistency
  // This can happen if old documents were analyzed before the field validation was added
  if (document.status === 'analyzed' && !analysis) {
    console.warn('[DOCUMENT-ANALYSIS-PAGE] Document marked as analyzed but has no analysis data')
    // Show as if analysis is missing - will trigger auto-analysis
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-primary"></div>
          <h2 className="mt-4 text-xl font-serif font-semibold text-text-primary">Re-analyzing document</h2>
          <p className="mt-2 text-text-secondary">
            Analysis data is missing. Triggering re-analysis...
          </p>
          <button
            onClick={() => {
              // Force re-analysis
              api.documents.analyze(token!, documentId!).then(() => {
                loadDocumentData()
              })
            }}
            className="mt-6 px-4 py-2 bg-accent-primary text-white rounded-lg hover:bg-accent-hover transition-colors"
          >
            Retry Analysis
          </button>
        </div>
      </div>
    )
  }

  // Use backend proxy URL instead of direct Supabase URL for better security
  const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'
  const proxyFileUrl = `${API_URL}/documents/${documentId}/file`

  if (document.status === 'failed') {
    const details = Array.isArray(document.error_detail?.details) ? document.error_detail.details : []
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <div className="max-w-lg text-center space-y-4">
          <ExclamationTriangleIcon className="h-16 w-16 text-error mx-auto" />
          <h2 className="mt-4 text-xl font-serif font-semibold text-text-primary">Analysis failed</h2>
          <p className="mt-2 text-text-secondary">Document analysis failed. Please try analyzing again.</p>
          {document.error_detail && (
            <InlineAlert
              title={document.error_detail.title || 'Analysis failed'}
              message={document.error_detail.message || 'We could not analyze this PDF.'}
              details={details}
            />
          )}
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

  if (document.status === 'analyzing' || document.status === 'processing') {
    const currentStage = document.progress?.stage
    const currentStageIndex = currentStage
      ? documentProgressSteps.findIndex((item) => item.key === currentStage)
      : 0
    const steps = documentProgressSteps.map((step) => ({
      label: step.label,
      completed: currentStageIndex > -1 ? documentProgressSteps.findIndex((item) => item.key === step.key) < currentStageIndex : false,
      active: currentStage ? step.key === currentStage : step.key === 'queued',
    }))
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center px-4">
        <div className="w-full max-w-2xl space-y-4">
          <ProgressIndicator
            progress={document.progress?.percent ?? 15}
            status={document.progress?.retrying ? 'Processing and retrying' : 'Processing document'}
            steps={steps}
            showElapsedTime
          />
          <InlineAlert
            tone="info"
            title="Private by default"
            message="Your files stay in your workspace and are not used to train models."
          />
          <button
            onClick={loadDocumentData}
            className="px-4 py-2 bg-accent-primary text-white rounded-lg hover:bg-accent-hover transition-colors"
          >
            Refresh Status
          </button>
        </div>
      </div>
    )
  }

  // Final safety check: If analysis is still null at this point, show loading
  // This handles edge cases where status is 'ready' but analysis hasn't started yet
  if (!analysis) {
    return (
      <div className="min-h-screen bg-bg-base flex items-center justify-center">
        <div className="text-center">
          <div className="inline-block animate-spin rounded-full h-12 w-12 border-b-2 border-accent-primary"></div>
          <h2 className="mt-4 text-xl font-serif font-semibold text-text-primary">Preparing analysis</h2>
          <p className="mt-2 text-text-secondary">
            Analysis is being prepared. This will only take a moment.
          </p>
          <button
            onClick={loadDocumentData}
            className="mt-6 px-4 py-2 bg-accent-primary text-white rounded-lg hover:bg-accent-hover transition-colors"
          >
            Refresh
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="h-screen flex flex-col bg-bg-base">
      {/* Header */}
      <header className="border-b border-border-base bg-surface px-6 py-4 flex items-center justify-between">
        <div className="flex items-center gap-4">
          <Link
            to={`/projects/${projectId}`}
            className="p-2 hover:bg-surface-hover rounded-lg transition-colors"
          >
            <ArrowLeftIcon className="h-5 w-5 text-text-secondary" />
          </Link>
          <div>
            <div className="flex items-center gap-2 text-xs text-text-tertiary font-mono">
              <Link to="/projects" className="hover:text-text-primary transition-colors">
                Projects
              </Link>
              <span>/</span>
              <Link to={`/projects/${projectId}`} className="hover:text-text-primary transition-colors">
                Project
              </Link>
              <span>/</span>
              <span className="text-text-secondary">Document Analysis</span>
            </div>
            <h1 className="text-xl font-serif font-semibold text-text-primary mt-1">
              {document.title}
            </h1>
          </div>
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
            <DocumentViewer
              fileUrl={proxyFileUrl}
              fileType={document.file_type}
              authToken={token}
            />
          </div>
        </div>

        {/* Right: Analysis Tabs */}
        <div className="w-1/2 flex flex-col bg-bg-base overflow-hidden">
          <Tab.Group as="div" className="flex flex-col flex-1 min-h-0" selectedIndex={selectedTab} onChange={handleTabChange}>
            <Tab.List className="flex gap-2 px-6 py-4 border-b border-border-base bg-surface shrink-0">
              <Tab className={({ selected }) =>
                `px-4 py-2 text-sm font-medium rounded-lg transition-colors ${
                  selected
                    ? 'bg-accent-primary text-white'
                    : 'text-text-secondary hover:text-text-primary hover:bg-surface-hover'
                }`
              }>
                <div className="flex items-center gap-2">
                  <DocumentTextIcon className="h-4 w-4" />
                  <span>Overview</span>
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
                  <span>Methodology</span>
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
                  <LightBulbIcon className="h-4 w-4" />
                  <span>Findings</span>
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
                  <BookOpenIcon className="h-4 w-4" />
                  <span>Citations</span>
                </div>
              </Tab>
            </Tab.List>

            <Tab.Panels className="flex-1 min-h-0">
              {/* Overview Tab */}
              <Tab.Panel className="h-full overflow-y-auto p-6 space-y-6">
                {/* Executive Summary */}
                {analysis.executive_summary && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Executive Summary
                    </h3>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      {analysis.executive_summary}
                    </p>
                  </div>
                )}

                {/* Research Problem */}
                {analysis.research_problem && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Research Problem
                    </h3>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      {analysis.research_problem}
                    </p>
                  </div>
                )}

                {/* Key Questions */}
                {analysis.key_questions && analysis.key_questions.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Research Questions
                    </h3>
                    <ul className="space-y-2">
                      {analysis.key_questions.map((question, idx) => (
                        <li key={idx} className="flex gap-3 text-sm text-text-secondary">
                          <span className="text-accent-primary font-mono">{idx + 1}.</span>
                          <span>{question}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Limitations */}
                {analysis.limitations && analysis.limitations.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Limitations
                    </h3>
                    <ul className="space-y-2">
                      {analysis.limitations.map((limitation, idx) => (
                        <li key={idx} className="flex gap-2 text-sm text-text-secondary">
                          <span className="text-text-muted">•</span>
                          <span>{limitation}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Future Work */}
                {analysis.future_work && analysis.future_work.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Future Directions
                    </h3>
                    <ul className="space-y-2">
                      {analysis.future_work.map((work, idx) => (
                        <li key={idx} className="flex gap-2 text-sm text-text-secondary">
                          <span className="text-text-muted">•</span>
                          <span>{work}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Tab.Panel>

              {/* Methodology Tab */}
              <Tab.Panel className="h-full overflow-y-auto p-6 space-y-6">
                {analysis.methodology?.approach && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Approach
                    </h3>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      {analysis.methodology.approach}
                    </p>
                  </div>
                )}

                {analysis.methodology?.techniques && analysis.methodology.techniques.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Techniques Used
                    </h3>
                    <div className="flex flex-wrap gap-2">
                      {analysis.methodology.techniques.map((technique, idx) => (
                        <Badge key={idx} variant="info">
                          {technique}
                        </Badge>
                      ))}
                    </div>
                  </div>
                )}

                {analysis.methodology?.dataset && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Dataset
                    </h3>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      {analysis.methodology.dataset}
                    </p>
                  </div>
                )}
              </Tab.Panel>

              {/* Findings Tab */}
              <Tab.Panel className="h-full overflow-y-auto p-6 space-y-6">
                {/* Key Findings */}
                {analysis.key_findings && analysis.key_findings.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Key Findings
                    </h3>
                    <ul className="space-y-3">
                      {analysis.key_findings.map((finding, idx) => (
                        <li key={idx} className="border-l-2 border-accent-primary pl-4 py-2">
                          <p className="text-sm text-text-secondary">{finding}</p>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}

                {/* Results Summary */}
                {analysis.results?.summary && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Results Summary
                    </h3>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      {analysis.results.summary}
                    </p>
                  </div>
                )}

                {/* Metrics */}
                {analysis.results?.metrics && analysis.results.metrics.length > 0 && (
                  <div>
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-3">
                      Performance Metrics
                    </h3>
                    <ul className="space-y-2">
                      {analysis.results.metrics.map((metric, idx) => (
                        <li key={idx} className="flex gap-2 text-sm text-text-secondary">
                          <span className="text-accent-primary">→</span>
                          <span className="font-mono">{metric}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </Tab.Panel>

              {/* Citations Tab */}
              <Tab.Panel className="h-full overflow-y-auto p-6">
                {analysis.key_citations && analysis.key_citations.length > 0 ? (
                  <div className="space-y-4">
                    <h3 className="text-sm font-medium text-text-tertiary font-mono mb-4">
                      Key Citations ({analysis.key_citations.length})
                    </h3>
                    {analysis.key_citations.map((citation, idx) => (
                      <div key={idx} className="border border-border-base rounded-lg p-4 bg-surface-hover">
                        <div className="flex items-start gap-3">
                          <span className="text-xs font-mono text-text-muted mt-1">[{idx + 1}]</span>
                          <div className="flex-1">
                            <h4 className="text-sm font-medium text-text-primary mb-1">
                              {citation.title || 'Untitled'}
                            </h4>
                            <p className="text-xs text-text-tertiary font-mono mb-2">
                              {citation.authors} ({citation.year})
                            </p>
                            {citation.relevance && (
                              <p className="text-sm text-text-secondary">
                                <span className="font-medium text-text-tertiary">Relevance:</span> {citation.relevance}
                              </p>
                            )}
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                ) : (
                  <div className="text-center py-12">
                    <BookOpenIcon className="h-12 w-12 text-text-muted mx-auto" />
                    <p className="mt-4 text-text-secondary">No key citations extracted</p>
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

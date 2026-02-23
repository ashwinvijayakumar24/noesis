import { useState, useEffect } from 'react'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'
import {
  BeakerIcon,
  LightBulbIcon,
  ExclamationTriangleIcon,
  ArrowPathIcon,
  CheckCircleIcon,
  XCircleIcon,
  DocumentTextIcon
} from '@heroicons/react/24/outline'
import { SkeletonInsight, SkeletonList } from './ui/Skeleton'
import { ProgressIndicator, useEstimatedProgress } from './ui/ProgressIndicator'

interface DocumentOverviewProps {
  documentId: string
  onTriggerAnalysis?: () => void
}

interface Analysis {
  executive_summary: string
  research_problem: string
  key_questions: string[]
  methodology: {
    approach: string
    techniques: string[]
    dataset: string
  }
  key_findings: string[]
  results: {
    summary: string
    metrics: string[]
  }
  limitations: string[]
  future_work: string[]
  key_citations: Array<{
    authors: string
    year: string
    title: string
    relevance: string
  }>
  analysis_metadata?: {
    model: string
    processing_time_seconds: number
    timestamp: string
    tokens_used: number
  }
}

export default function DocumentOverview({ documentId, onTriggerAnalysis }: DocumentOverviewProps) {
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [status, setStatus] = useState<'not_analyzed' | 'analyzing' | 'analyzed' | 'failed'>('not_analyzed')
  const [analysis, setAnalysis] = useState<Analysis | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pollingIntervalId, setPollingIntervalId] = useState<ReturnType<typeof setInterval> | null>(null)

  // Progress tracking for analysis (estimated 30 seconds)
  const { progress, elapsedTime, estimatedTimeRemaining, complete: completeProgress, reset: resetProgress } = useEstimatedProgress(30)

  // Reset all state when documentId changes
  useEffect(() => {
    setLoading(true)
    setStatus('not_analyzed')
    setAnalysis(null)
    setError(null)

    // Clear any existing polling
    if (pollingIntervalId) {
      clearInterval(pollingIntervalId)
      setPollingIntervalId(null)
    }
  }, [documentId])

  // Load analysis when component mounts or documentId changes
  useEffect(() => {
    if (session?.access_token && documentId) {
      loadAnalysis()
    }

    // Cleanup polling on unmount or when documentId changes
    return () => {
      if (pollingIntervalId) {
        clearInterval(pollingIntervalId)
        setPollingIntervalId(null)
      }
    }
  }, [documentId, session?.access_token])

  const loadAnalysis = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      const data = await api.documents.getAnalysis(session.access_token, documentId)

      setStatus(data.status)

      if (data.status === 'analyzed') {
        setAnalysis(data.analysis)
        setError(null)
        completeProgress()
        // Stop polling if it's running
        if (pollingIntervalId) {
          clearInterval(pollingIntervalId)
          setPollingIntervalId(null)
        }
      } else if (data.status === 'analyzing') {
        // Start polling ONLY if not already polling
        if (!pollingIntervalId) {
          const interval = setInterval(async () => {
            try {
              const pollData = await api.documents.getAnalysis(session.access_token, documentId)
              setStatus(pollData.status)

              if (pollData.status === 'analyzed') {
                setAnalysis(pollData.analysis)
                setError(null)
                completeProgress()
                clearInterval(interval)
                setPollingIntervalId(null)
              } else if (pollData.status === 'failed') {
                setError(pollData.error || 'Analysis failed')
                clearInterval(interval)
                setPollingIntervalId(null)
              }
            } catch (pollErr: any) {
              console.error('Polling error:', pollErr)
            }
          }, 3000) // Poll every 3 seconds
          setPollingIntervalId(interval)
        }
      } else if (data.status === 'failed') {
        setError(data.error || 'Analysis failed')
        if (pollingIntervalId) {
          clearInterval(pollingIntervalId)
          setPollingIntervalId(null)
        }
      }
    } catch (err: any) {
      console.error('Failed to load analysis:', err)
      setError(err.message || 'Failed to load analysis')
      setStatus('failed')
    } finally {
      setLoading(false)
    }
  }

  const handleAnalyze = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      setError(null)
      resetProgress()

      // Clear any existing polling first
      if (pollingIntervalId) {
        clearInterval(pollingIntervalId)
        setPollingIntervalId(null)
      }

      await api.documents.analyze(session.access_token, documentId)

      // Set status to analyzing
      setStatus('analyzing')

      // Start polling
      const interval = setInterval(async () => {
        try {
          const pollData = await api.documents.getAnalysis(session.access_token, documentId)
          setStatus(pollData.status)

          if (pollData.status === 'analyzed') {
            setAnalysis(pollData.analysis)
            setError(null)
            completeProgress()
            clearInterval(interval)
            setPollingIntervalId(null)
          } else if (pollData.status === 'failed') {
            setError(pollData.error || 'Analysis failed')
            clearInterval(interval)
            setPollingIntervalId(null)
          }
        } catch (pollErr: any) {
          console.error('Polling error:', pollErr)
        }
      }, 3000)
      setPollingIntervalId(interval)

      if (onTriggerAnalysis) {
        onTriggerAnalysis()
      }
    } catch (err: any) {
      console.error('Failed to start analysis:', err)
      setError(err.message || 'Failed to start analysis')
      setStatus('failed')
    } finally {
      setLoading(false)
    }
  }

  if (loading && status === 'not_analyzed') {
    return (
      <div className="space-y-6">
        <SkeletonList count={5} ItemComponent={SkeletonInsight} />
      </div>
    )
  }

  if (status === 'not_analyzed') {
    return (
      <div className="bg-surface rounded-lg border border-border-default p-8 text-center">
        <div className="max-w-md mx-auto">
          <div className="h-16 w-16 mx-auto mb-4 rounded-full bg-accent-primary/10 flex items-center justify-center">
            <DocumentTextIcon className="h-8 w-8 text-accent-primary" />
          </div>
          <h3 className="text-xl font-sans font-semibold text-text-primary mb-2">
            AI-Powered Paper Analysis
          </h3>
          <p className="text-text-tertiary mb-6">
            Get instant structured insights including methodology, findings, limitations, and key citations in just 30 seconds.
          </p>
          <button
            onClick={handleAnalyze}
            className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors mx-auto"
          >
            Analyze This Paper
          </button>
        </div>
      </div>
    )
  }

  if (status === 'analyzing') {
    return (
      <div className="max-w-3xl mx-auto">
        <ProgressIndicator
          progress={progress}
          status="Analyzing Paper with AI"
          estimatedTimeRemaining={estimatedTimeRemaining}
          showElapsedTime={true}
          steps={[
            {
              label: 'Extracting document structure',
              description: 'Identifying sections, headings, and content blocks',
              completed: elapsedTime > 5,
              active: elapsedTime <= 5
            },
            {
              label: 'Analyzing methodology and findings',
              description: 'Understanding research approach and key results',
              completed: elapsedTime > 15,
              active: elapsedTime > 5 && elapsedTime <= 15
            },
            {
              label: 'Extracting citations and references',
              description: 'Identifying key papers and their relevance',
              completed: elapsedTime > 25,
              active: elapsedTime > 15 && elapsedTime <= 25
            },
            {
              label: 'Generating structured insights',
              description: 'Creating comprehensive analysis report',
              completed: false,
              active: elapsedTime > 25
            }
          ]}
        />
      </div>
    )
  }

  if (status === 'failed') {
    return (
      <div className="bg-surface rounded-lg border border-red-900/50 p-8 text-center">
        <div className="max-w-md mx-auto">
          <XCircleIcon className="h-16 w-16 text-red-500 mx-auto mb-4" />
          <h3 className="text-xl font-sans font-semibold text-text-primary mb-2">
            Analysis Failed
          </h3>
          <p className="text-text-tertiary mb-4">
            {error || 'The analysis could not be completed. Please try again.'}
          </p>
          <button
            onClick={handleAnalyze}
            className="px-6 py-3 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2 mx-auto"
          >
            <ArrowPathIcon className="h-5 w-5" />
            Retry Analysis
          </button>
        </div>
      </div>
    )
  }

  // status === 'analyzed'
  if (!analysis) return null

  return (
    <div className="space-y-6">
      {/* Success Banner */}
      <div className="bg-green-900/20 border border-green-600/30 rounded-lg p-4 flex items-start gap-3">
        <CheckCircleIcon className="h-6 w-6 text-green-400 shrink-0 mt-0.5" />
        <div className="flex-1">
          <h4 className="text-green-200 font-medium">Analysis Complete</h4>
          <p className="text-green-300/70 text-sm mt-1">
            Processed in {analysis.analysis_metadata?.processing_time_seconds || 'N/A'}s
          </p>
        </div>
      </div>

      {/* Executive Summary */}
      <div className="bg-surface rounded-lg border border-border-default p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-accent-primary/10 rounded-lg">
            <DocumentTextIcon className="h-5 w-5 text-accent-primary" />
          </div>
          <h3 className="text-lg font-sans font-semibold text-text-primary">Executive Summary</h3>
        </div>
        <p className="text-text-secondary leading-relaxed">{analysis.executive_summary}</p>
      </div>

      {/* Research Problem */}
      <div className="bg-surface rounded-lg border border-border-default p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-blue-600/20 rounded-lg">
            <ExclamationTriangleIcon className="h-5 w-5 text-blue-400" />
          </div>
          <h3 className="text-lg font-sans font-semibold text-text-primary">Research Problem</h3>
        </div>
        <p className="text-text-secondary leading-relaxed">{analysis.research_problem}</p>

        {analysis.key_questions && analysis.key_questions.length > 0 && (
          <div className="mt-4">
            <h4 className="text-sm font-medium text-text-tertiary mb-2">Key Research Questions:</h4>
            <ul className="list-disc list-outside ml-5 space-y-1">
              {analysis.key_questions.map((q, i) => (
                <li key={i} className="text-text-secondary leading-relaxed">{q}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Methodology */}
      <div className="bg-surface rounded-lg border border-border-default p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-purple-600/20 rounded-lg">
            <BeakerIcon className="h-5 w-5 text-purple-400" />
          </div>
          <h3 className="text-lg font-sans font-semibold text-text-primary">Methodology</h3>
        </div>
        <p className="text-text-secondary leading-relaxed mb-4">{analysis.methodology.approach}</p>

        {analysis.methodology.techniques && analysis.methodology.techniques.length > 0 && (
          <div className="mb-4">
            <h4 className="text-sm font-medium text-text-tertiary mb-2">Techniques Used:</h4>
            <div className="flex flex-wrap gap-2">
              {analysis.methodology.techniques.map((tech, i) => (
                <span key={i} className="px-3 py-1 bg-purple-900/30 text-purple-200 rounded-full text-sm">
                  {tech}
                </span>
              ))}
            </div>
          </div>
        )}

        {analysis.methodology.dataset && analysis.methodology.dataset !== 'Not applicable' && (
          <div>
            <h4 className="text-sm font-medium text-text-tertiary mb-2">Dataset:</h4>
            <p className="text-text-secondary">{analysis.methodology.dataset}</p>
          </div>
        )}
      </div>

      {/* Key Findings */}
      {analysis.key_findings && analysis.key_findings.length > 0 && (
        <div className="bg-surface rounded-lg border border-border-default p-6">
          <div className="flex items-center gap-3 mb-4">
            <div className="p-2 bg-emerald-600/20 rounded-lg">
              <LightBulbIcon className="h-5 w-5 text-emerald-400" />
            </div>
            <h3 className="text-lg font-sans font-semibold text-text-primary">Key Findings</h3>
          </div>
          <ul className="list-disc list-outside ml-5 space-y-2">
            {analysis.key_findings.map((finding, i) => (
              <li key={i} className="text-text-secondary leading-relaxed">{finding}</li>
            ))}
          </ul>
        </div>
      )}

      {/* Results */}
      <div className="bg-surface rounded-lg border border-border-default p-6">
        <div className="flex items-center gap-3 mb-4">
          <div className="p-2 bg-amber-600/20 rounded-lg">
            <CheckCircleIcon className="h-5 w-5 text-amber-400" />
          </div>
          <h3 className="text-lg font-sans font-semibold text-text-primary">Results</h3>
        </div>
        <p className="text-text-secondary leading-relaxed mb-4">{analysis.results.summary}</p>

        {analysis.results.metrics && analysis.results.metrics.length > 0 && (
          <div>
            <h4 className="text-sm font-medium text-text-tertiary mb-2">Key Metrics:</h4>
            <ul className="list-disc list-outside ml-5 space-y-1">
              {analysis.results.metrics.map((metric, i) => (
                <li key={i} className="text-text-secondary">{metric}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Limitations & Future Work */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {analysis.limitations && analysis.limitations.length > 0 && analysis.limitations[0] !== 'Not mentioned in the paper' && (
          <div className="bg-surface rounded-lg border border-border-default p-6">
            <h3 className="text-lg font-sans font-semibold text-text-primary mb-4">Limitations</h3>
            <ul className="list-disc list-outside ml-5 space-y-1">
              {analysis.limitations.map((lim, i) => (
                <li key={i} className="text-text-secondary">{lim}</li>
              ))}
            </ul>
          </div>
        )}

        {analysis.future_work && analysis.future_work.length > 0 && analysis.future_work[0] !== 'Not mentioned in the paper' && (
          <div className="bg-surface rounded-lg border border-border-default p-6">
            <h3 className="text-lg font-sans font-semibold text-text-primary mb-4">Future Work</h3>
            <ul className="list-disc list-outside ml-5 space-y-1">
              {analysis.future_work.map((work, i) => (
                <li key={i} className="text-text-secondary">{work}</li>
              ))}
            </ul>
          </div>
        )}
      </div>

      {/* Key Citations */}
      {analysis.key_citations && analysis.key_citations.length > 0 && (
        <div className="bg-surface rounded-lg border border-border-default p-6">
          <h3 className="text-lg font-sans font-semibold text-text-primary mb-4">Key Citations</h3>
          <div className="space-y-4">
            {analysis.key_citations.map((citation, i) => (
              <div key={i} className="border-l-4 border-accent-primary pl-4">
                <p className="text-text-secondary font-medium">
                  {citation.authors} ({citation.year})
                </p>
                <p className="text-text-secondary italic">{citation.title}</p>
                <p className="text-text-tertiary text-sm mt-1">{citation.relevance}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

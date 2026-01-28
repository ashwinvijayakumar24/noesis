import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { DocumentTextIcon, TrashIcon, ArrowDownTrayIcon, ExclamationTriangleIcon, CheckCircleIcon, ExclamationCircleIcon } from '@heroicons/react/24/outline'
import { api } from '../lib/api'
import toast from 'react-hot-toast'
import { handleError } from '../lib/errorHandler'
import { Badge, type BadgeVariant } from './ui/Badge'
import { SkeletonListItem, SkeletonList } from './ui/Skeleton'

interface Draft {
  id: string
  title: string
  version: number
  file_type: string
  file_url: string
  status: string
  created_at: string
  updated_at: string
}

interface DraftMetrics {
  claims_count: number
  claims_needing_citation: number
  gaps_count: number
  critical_gaps: number
  feedback_count: number
  critical_feedback: number
  major_feedback: number
  health_score: number // 0-100
  health_status: 'good' | 'needs_work' | 'critical'
}

interface DraftsPanelProps {
  token: string
  projectId: string
  refreshTrigger?: number
  onDraftsLoaded?: (count: number) => void
}

export default function DraftsPanel({ token, projectId, refreshTrigger, onDraftsLoaded }: DraftsPanelProps) {
  const navigate = useNavigate()
  const [drafts, setDrafts] = useState<Draft[]>([])
  const [loading, setLoading] = useState(true)
  const [draftMetrics, setDraftMetrics] = useState<Record<string, DraftMetrics>>({})

  // Fetch metrics for analyzed drafts
  const loadDraftMetrics = async (draftId: string) => {
    try {
      const [claimsData, gapsData, feedbackData] = await Promise.all([
        api.drafts.getClaims(token, draftId).catch(() => ({ claims: [] })),
        api.drafts.getGaps(token, draftId).catch(() => ({ gaps: [] })),
        api.drafts.getFeedback(token, draftId).catch(() => ({ feedback: [] })),
      ])

      const claims = claimsData.claims || []
      const gaps = gapsData.gaps || []
      const feedback = feedbackData.feedback || []

      const claimsNeedingCitation = claims.filter((c: any) =>
        c.requires_citation && (!c.existing_citations || c.existing_citations.length === 0)
      ).length

      const criticalGaps = gaps.filter((g: any) => g.priority === 'critical' || g.priority === 'high').length
      const criticalFeedback = feedback.filter((f: any) => f.severity === 'critical').length
      const majorFeedback = feedback.filter((f: any) => f.severity === 'major').length

      // Calculate health score (0-100)
      let healthScore = 100
      healthScore -= claimsNeedingCitation * 5 // -5 per missing citation
      healthScore -= criticalGaps * 15 // -15 per critical gap
      healthScore -= criticalFeedback * 10 // -10 per critical feedback
      healthScore -= majorFeedback * 5 // -5 per major feedback
      healthScore = Math.max(0, Math.min(100, healthScore))

      const healthStatus: 'good' | 'needs_work' | 'critical' =
        healthScore >= 70 ? 'good' :
        healthScore >= 40 ? 'needs_work' : 'critical'

      const metrics: DraftMetrics = {
        claims_count: claims.length,
        claims_needing_citation: claimsNeedingCitation,
        gaps_count: gaps.length,
        critical_gaps: criticalGaps,
        feedback_count: feedback.length,
        critical_feedback: criticalFeedback,
        major_feedback: majorFeedback,
        health_score: healthScore,
        health_status: healthStatus
      }

      setDraftMetrics(prev => ({ ...prev, [draftId]: metrics }))
    } catch (error) {
      console.error('[DRAFTS-PANEL] Error loading metrics for draft:', draftId, error)
    }
  }

  const loadDrafts = async () => {
    try {
      setLoading(true)
      const data = await api.drafts.list(token, projectId)
      console.log('[DRAFTS-PANEL] API response:', data)
      console.log('[DRAFTS-PANEL] Drafts array:', data.drafts)
      console.log('[DRAFTS-PANEL] Number of drafts:', data.drafts?.length || 0)
      const draftsList = data.drafts || []
      setDrafts(draftsList)

      // Notify parent of draft count
      if (onDraftsLoaded) {
        onDraftsLoaded(draftsList.length)
      }

      // Load metrics for analyzed drafts
      const analyzedDrafts = draftsList.filter((d: Draft) => d.status === 'analyzed')
      analyzedDrafts.forEach((d: Draft) => loadDraftMetrics(d.id))
    } catch (error: any) {
      console.error('[DRAFTS-PANEL] Error loading drafts:', error)
      handleError(error, 'loading drafts')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadDrafts()
  }, [token, projectId, refreshTrigger])

  // Poll for status updates if there are processing drafts
  useEffect(() => {
    const hasProcessingDrafts = drafts.some(
      (draft) => draft.status === 'processing' || draft.status === 'uploaded'
    )

    if (!hasProcessingDrafts) return

    const pollInterval = setInterval(() => {
      console.log('[DRAFTS-PANEL] Polling for status updates...')
      // Silent reload - update state without triggering loading state
      api.drafts.list(token, projectId).then(data => {
        setDrafts(data.drafts || [])
      }).catch(error => {
        console.error('[DRAFTS-PANEL] Polling error:', error)
      })
    }, 5000) // Poll every 5 seconds

    return () => {
      clearInterval(pollInterval)
    }
  }, [drafts, token, projectId])

  const handleDelete = async (draftId: string, title: string) => {
    if (!confirm(`Are you sure you want to delete "${title}"?`)) {
      return
    }

    try {
      await api.drafts.delete(token, draftId)
      toast.success('Draft deleted successfully')
      loadDrafts()
    } catch (error: any) {
      handleError(error, 'deleting draft')
    }
  }

  const handleViewAnalysis = (draftId: string) => {
    navigate(`/projects/${projectId}/drafts/${draftId}`)
  }

  const handleAnalyze = async (draftId: string) => {
    try {
      toast.loading('Starting analysis...')
      await api.drafts.analyze(token, draftId)
      toast.dismiss()
      toast.success('Analysis started! This may take 1-2 minutes.')
      // Reload drafts to update status
      setTimeout(() => loadDrafts(), 2000)
    } catch (error: any) {
      toast.dismiss()
      handleError(error, 'analyzing draft')
    }
  }

  const handleExport = async (draftId: string, title: string, format: string) => {
    try {
      toast.loading(`Exporting as ${format.toUpperCase()}...`)

      // Handle PDF export differently (binary format)
      if (format === 'pdf') {
        const response = await fetch(
          `${import.meta.env.VITE_API_URL}/drafts/${draftId}/export-pdf`,
          {
            headers: {
              'Authorization': `Bearer ${token}`
            }
          }
        )

        toast.dismiss()

        if (!response.ok) {
          throw new Error('Failed to generate PDF')
        }

        // Get the blob and download
        const blob = await response.blob()
        const url = window.URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `${title.replace(/ /g, '_')}_analysis.pdf`
        document.body.appendChild(a)
        a.click()
        window.URL.revokeObjectURL(url)
        document.body.removeChild(a)

        toast.success('PDF report downloaded successfully')
        return
      }

      // Handle text-based exports (JSON, Markdown, Text)
      const data = await api.drafts.export(token, draftId, format)
      toast.dismiss()

      // Create blob and download
      const blob = new Blob([data.content], { type: 'text/plain' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = data.filename || `${title}_analysis.${format}`
      document.body.appendChild(a)
      a.click()
      window.URL.revokeObjectURL(url)
      document.body.removeChild(a)

      toast.success('Analysis exported successfully')
    } catch (error: any) {
      toast.dismiss()
      handleError(error, 'exporting analysis')
    }
  }

  const getStatusBadge = (status: string): BadgeVariant => {
    switch (status) {
      case 'analyzed':
        return 'success'
      case 'processing':
      case 'uploaded':
        return 'warning'
      case 'failed':
        return 'error'
      default:
        return 'neutral'
    }
  }

  const getFileTypeIcon = (status: string) => {
    const colorClass = status.toLowerCase() === 'analyzed' ? 'text-slate-300' :
                       status.toLowerCase() === 'processing' || status.toLowerCase() === 'uploaded' ? 'text-amber-700' :
                       status.toLowerCase() === 'failed' ? 'text-red-500' :
                       'text-slate-400'
    return <DocumentTextIcon className={`h-5 w-5 ${colorClass}`} />
  }

  // Helper function to get colored left border based on status
  const getDraftBorderColor = (status: string): string => {
    switch (status.toLowerCase()) {
      case 'analyzed':
        return 'border-l-4 border-l-slate-500'
      case 'processing':
      case 'uploaded':
        return 'border-l-4 border-l-amber-700'
      case 'failed':
        return 'border-l-4 border-l-red-600'
      default:
        return 'border-l-4 border-l-slate-600'
    }
  }

  if (loading) {
    return <SkeletonList count={4} ItemComponent={SkeletonListItem} />
  }

  if (drafts.length === 0) {
    return (
      <div className="text-center py-12 bg-bg-base rounded-lg border-2 border-dashed border-border-base">
        <DocumentTextIcon className="mx-auto h-12 w-12 text-text-tertiary" />
        <h3 className="mt-2 text-sm font-medium text-text-primary">No drafts yet</h3>
        <p className="mt-1 text-sm text-text-tertiary">
          Upload your research draft to get expert feedback and analysis
        </p>
      </div>
    )
  }

  // Helper to get health badge color and icon
  const getHealthBadge = (status: 'good' | 'needs_work' | 'critical') => {
    switch (status) {
      case 'good':
        return {
          bgColor: 'bg-emerald-800',
          textColor: 'text-emerald-200',
          borderColor: 'border-emerald-600',
          icon: <CheckCircleIcon className="h-4 w-4" />,
          label: 'Good'
        }
      case 'needs_work':
        return {
          bgColor: 'bg-amber-800',
          textColor: 'text-amber-200',
          borderColor: 'border-amber-600',
          icon: <ExclamationTriangleIcon className="h-4 w-4" />,
          label: 'Needs Work'
        }
      case 'critical':
        return {
          bgColor: 'bg-red-800',
          textColor: 'text-red-200',
          borderColor: 'border-red-600',
          icon: <ExclamationCircleIcon className="h-4 w-4" />,
          label: 'Critical'
        }
    }
  }

  return (
    <>
      <div className="space-y-3">
        {drafts.map((draft) => {
          const metrics = draftMetrics[draft.id]
          const healthBadge = metrics ? getHealthBadge(metrics.health_status) : null

          return (
            <div
              key={draft.id}
              onClick={() => draft.status === 'analyzed' ? handleViewAnalysis(draft.id) : undefined}
              className={`bg-surface border border-border-base rounded-lg p-4 transition-all ${getDraftBorderColor(draft.status)} ${
                draft.status === 'analyzed'
                  ? 'cursor-pointer hover:border-border-subtle hover:bg-surface-hover hover:shadow-lg hover:shadow-red-600/20'
                  : ''
              }`}
            >
              <div className="flex items-start justify-between">
                <div className="flex items-start space-x-3 flex-1">
                  {getFileTypeIcon(draft.status)}
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center gap-2 mb-1 flex-wrap">
                      <h3 className="text-sm font-medium text-text-primary truncate">
                        {draft.title}
                      </h3>
                      {draft.version > 1 && (
                        <span className="text-xs text-text-muted font-mono">
                          v{draft.version}
                        </span>
                      )}
                      <Badge variant={getStatusBadge(draft.status)}>
                        {draft.status === 'analyzed' ? 'Processed' : draft.status.charAt(0).toUpperCase() + draft.status.slice(1).toLowerCase()}
                      </Badge>

                      {/* Health Badge for analyzed drafts */}
                      {draft.status === 'analyzed' && healthBadge && (
                        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-xs font-medium ${healthBadge.bgColor} ${healthBadge.textColor} border ${healthBadge.borderColor}`}>
                          {healthBadge.icon}
                          {healthBadge.label}
                        </span>
                      )}
                    </div>

                    {/* Basic info */}
                    <p className="text-xs text-text-muted font-mono mb-2">
                      {draft.file_type.toUpperCase()} • {new Date(draft.created_at).toLocaleDateString()}
                    </p>

                    {/* Metrics row for analyzed drafts */}
                    {draft.status === 'analyzed' && metrics && (
                      <div className="flex items-center gap-4 text-xs">
                        <span className="flex items-center gap-1 text-text-secondary">
                          <span className="font-mono">{metrics.claims_count}</span> claims
                          {metrics.claims_needing_citation > 0 && (
                            <span className="text-amber-500">({metrics.claims_needing_citation} need cite)</span>
                          )}
                        </span>
                        <span className="flex items-center gap-1 text-text-secondary">
                          <span className="font-mono">{metrics.gaps_count}</span> gaps
                          {metrics.critical_gaps > 0 && (
                            <span className="text-red-400">({metrics.critical_gaps} critical)</span>
                          )}
                        </span>
                        <span className="flex items-center gap-1 text-text-secondary">
                          <span className="font-mono">{metrics.feedback_count}</span> feedback
                          {metrics.critical_feedback > 0 && (
                            <span className="text-red-400">({metrics.critical_feedback} critical)</span>
                          )}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

                <div className="flex items-center gap-2 ml-4" onClick={(e) => e.stopPropagation()}>
                  {draft.status === 'processing' && (
                    <div className="flex items-center gap-2">
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-accent-primary"></div>
                      <span className="text-xs text-text-secondary font-mono">Analyzing...</span>
                    </div>
                  )}
                  {draft.status === 'analyzed' && (
                    <div className="relative group">
                      <button
                        className="p-2 text-text-tertiary hover:bg-surface rounded-md transition-colors"
                        title="Export Analysis"
                      >
                        <ArrowDownTrayIcon className="h-4 w-4" />
                      </button>
                      <div className="absolute right-0 mt-2 w-48 bg-bg-base border border-border-base rounded-md shadow-lg opacity-0 invisible group-hover:opacity-100 group-hover:visible transition-all z-10">
                        <button
                          onClick={() => handleExport(draft.id, draft.title, 'pdf')}
                          className="block w-full text-left px-4 py-2 text-sm text-text-secondary hover:bg-surface font-mono font-semibold"
                        >
                          Export as PDF
                        </button>
                        <button
                          onClick={() => handleExport(draft.id, draft.title, 'markdown')}
                          className="block w-full text-left px-4 py-2 text-sm text-text-secondary hover:bg-surface font-mono"
                        >
                          Export as Markdown
                        </button>
                        <button
                          onClick={() => handleExport(draft.id, draft.title, 'json')}
                          className="block w-full text-left px-4 py-2 text-sm text-text-secondary hover:bg-surface font-mono"
                        >
                          Export as JSON
                        </button>
                        <button
                          onClick={() => handleExport(draft.id, draft.title, 'text')}
                          className="block w-full text-left px-4 py-2 text-sm text-text-secondary hover:bg-surface font-mono"
                        >
                          Export as Text
                        </button>
                      </div>
                    </div>
                  )}
                  {draft.status === 'uploaded' && (
                    <button
                      onClick={() => handleAnalyze(draft.id)}
                      className="px-3 py-1 text-xs font-medium text-text-primary bg-surface hover:bg-surface-hover rounded border border-border-subtle transition-colors"
                    >
                      Analyze
                    </button>
                  )}
                  {draft.status === 'failed' && (
                    <button
                      onClick={() => handleAnalyze(draft.id)}
                      className="px-3 py-1 text-xs font-medium text-text-primary bg-surface hover:bg-surface-hover rounded border border-border-subtle transition-colors"
                    >
                      Retry
                    </button>
                  )}
                  <button
                    onClick={() => handleDelete(draft.id, draft.title)}
                    className="p-2 text-text-tertiary hover:text-text-primary hover:bg-surface rounded-md transition-colors"
                    title="Delete Draft"
                  >
                    <TrashIcon className="h-4 w-4" />
                  </button>
                </div>
              </div>
            </div>
          )
        })}
      </div>

    </>
  )
}

import { useEffect, useState } from 'react'
import toast from 'react-hot-toast'
import {
  ArrowPathIcon,
  ArrowTopRightOnSquareIcon,
  CheckCircleIcon,
  DocumentMagnifyingGlassIcon,
  DocumentTextIcon,
  ExclamationTriangleIcon,
  LightBulbIcon,
  PlusIcon,
  SparklesIcon,
  XCircleIcon,
} from '@heroicons/react/24/outline'

import { api } from '../../lib/api'
import { getApiErrorDetail, getApiErrorDetailsList } from '../../lib/apiErrors'
import { useAuthStore } from '../../stores/authStore'
import InlineAlert from '../ui/InlineAlert'
import { ProgressIndicator } from '../ui/ProgressIndicator'
import {
  formatQuotaLabel,
  getKeyInsightDetails,
  markRecommendationSaved,
  normalizeLiteratureMapResponse,
  type CoverageItem,
  type LiteratureMapResponse,
  type RecommendationRecord,
} from './literatureMap'

const API_BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

interface InsightsTabProps {
  projectId: string
  onDocumentSaved?: () => void
}

function SourcePapers({ papers }: { papers?: string[] }) {
  if (!papers || papers.length === 0) return null

  return (
    <div className="flex flex-wrap gap-2">
      {papers.map((paper) => (
        <span
          key={paper}
          className="inline-flex items-center rounded-lg border border-border-default bg-bg-elevated px-2 py-1 text-xs text-text-secondary"
        >
          {paper}
        </span>
      ))}
    </div>
  )
}

function CoverageList({ items, emptyLabel }: { items: CoverageItem[]; emptyLabel: string }) {
  if (items.length === 0) {
    return <p className="text-sm text-text-tertiary">{emptyLabel}</p>
  }

  return (
    <div className="space-y-2">
      {items.map((item) => (
        <div key={item.label} className="flex items-center justify-between gap-3">
          <span className="text-sm text-text-secondary">{item.label}</span>
          <span className="text-xs font-mono text-text-muted">{item.count}</span>
        </div>
      ))}
    </div>
  )
}

function RecommendationChip({
  recommendation,
  isSaving,
  onSave,
}: {
  recommendation: RecommendationRecord
  isSaving: boolean
  onSave: (recommendationId: string) => void
}) {
  const metaBits = [
    recommendation.year ? String(recommendation.year) : null,
    recommendation.journal_name ?? null,
    recommendation.citation_count ? `${recommendation.citation_count} citations` : null,
  ].filter(Boolean)

  return (
    <div className="rounded-xl border border-border-default bg-bg-surface p-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-text-primary line-clamp-2">{recommendation.title}</p>
          {metaBits.length > 0 && (
            <p className="mt-1 text-xs text-text-tertiary">{metaBits.join(' · ')}</p>
          )}
        </div>
        {recommendation.bib_saved ? (
          <span className="rounded-lg border border-border-default px-2 py-1 text-xs text-text-muted">
            Saved
          </span>
        ) : (
          <button
            onClick={() => onSave(recommendation.id)}
            disabled={isSaving}
            className="inline-flex h-11 shrink-0 items-center gap-1 rounded-lg bg-accent-primary px-3 text-sm font-semibold text-white transition-colors hover:bg-accent-hover disabled:opacity-50"
          >
            {isSaving ? (
              <span className="h-3 w-3 animate-spin rounded-full border border-white/40 border-t-white" />
            ) : (
              <PlusIcon className="h-3.5 w-3.5" />
            )}
            {isSaving ? 'Saving…' : 'Save'}
          </button>
        )}
      </div>

      {recommendation.relevance_reason && (
        <p className="mt-2 text-xs text-text-tertiary">{recommendation.relevance_reason}</p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {recommendation.paper_url && (
          <a
            href={recommendation.paper_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-11 items-center gap-1 rounded-lg border border-border-default px-3 text-sm text-text-secondary transition-colors hover:text-text-primary"
          >
            <ArrowTopRightOnSquareIcon className="h-3.5 w-3.5" />
            Paper
          </a>
        )}
        {recommendation.pdf_url && (
          <a
            href={recommendation.pdf_url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex h-11 items-center gap-1 rounded-lg border border-border-default px-3 text-sm text-text-secondary transition-colors hover:text-text-primary"
          >
            <DocumentTextIcon className="h-3.5 w-3.5" />
            PDF
          </a>
        )}
      </div>
    </div>
  )
}

export default function InsightsTab({ projectId, onDocumentSaved }: InsightsTabProps) {
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(true)
  const [isRefreshing, setIsRefreshing] = useState(false)
  const [status, setStatus] = useState<LiteratureMapResponse['status']>('not_analyzed')
  const [error, setError] = useState<string | null>(null)
  const [payload, setPayload] = useState<LiteratureMapResponse | null>(null)
  const [savingIds, setSavingIds] = useState<Set<string>>(new Set())
  const progress = (payload as any)?.progress
  const errorDetail = (payload as any)?.error_detail

  const progressSteps = [
    { key: 'queued', label: 'Queued' },
    { key: 'collecting_papers', label: 'Collecting papers' },
    { key: 'building_snapshot', label: 'Building snapshot' },
    { key: 'synthesizing_overview', label: 'Synthesizing overview' },
    { key: 'grouping_recommendations', label: 'Grouping recommendations' },
    { key: 'finalizing', label: 'Finalizing' },
  ]

  useEffect(() => {
    if (!session?.access_token || !projectId) return

    void loadInsights(true)
  }, [projectId, session?.access_token])

  useEffect(() => {
    if (status !== 'analyzing') return

    const interval = window.setInterval(() => {
      void loadInsights(false)
    }, 3000)

    return () => window.clearInterval(interval)
  }, [status, projectId, session?.access_token])

  async function loadInsights(showSpinner: boolean) {
    if (!session?.access_token) return

    try {
      if (showSpinner) {
        setLoading(true)
      }

      const response = normalizeLiteratureMapResponse(
        await api.projects.getInsights(session.access_token, projectId),
      )

      setPayload(response)
      setStatus(response.status)
      setError(null)
    } catch (err: any) {
      console.error('Failed to load Literature Map:', err)
      const detail = getApiErrorDetail(err)
      setError(detail?.message || err.message || 'Failed to load Literature Map')
    } finally {
      if (showSpinner) {
        setLoading(false)
      }
    }
  }

  async function handleAnalyze() {
    if (!session?.access_token || isRefreshing) return

    try {
      setIsRefreshing(true)
      const response = await api.projects.analyzeInsights(session.access_token, projectId)
      setStatus('analyzing')
      if (response.quota && payload) {
        setPayload({
          ...payload,
          quota: response.quota,
          status: 'analyzing',
          is_stale: false,
        })
      }
    } catch (err: any) {
      const quotaDetail = getApiErrorDetail(err)
      if (err?.status === 429 && quotaDetail?.message) {
        toast.error(quotaDetail.message)
      } else {
        toast.error(quotaDetail?.message || err.message || 'Failed to start Literature Map analysis.')
      }
    } finally {
      setIsRefreshing(false)
    }
  }

  async function handleSaveRecommendation(recommendationId: string) {
    if (!session?.access_token) return

    setSavingIds((prev) => new Set(prev).add(recommendationId))
    try {
      const response = await fetch(
        `${API_BASE}/paper-recommendations/projects/${projectId}/save-discovered/${recommendationId}`,
        {
          method: 'POST',
          headers: { Authorization: `Bearer ${session.access_token}` },
        },
      )

      if (!response.ok) {
        const errorData = await response.json().catch(() => ({}))
        throw new Error(errorData.detail || `Request failed (${response.status})`)
      }

      setPayload((current) => (
        current ? markRecommendationSaved(current, recommendationId) : current
      ))
      toast.success('Paper saved to Literature.')
      onDocumentSaved?.()
      await loadInsights(false)
    } catch (err: any) {
      toast.error(err.message || 'Failed to save paper.')
    } finally {
      setSavingIds((prev) => {
        const next = new Set(prev)
        next.delete(recommendationId)
        return next
      })
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center py-12">
        <div className="text-center">
          <div className="inline-block h-8 w-8 animate-spin rounded-full border-4 border-accent-primary border-r-transparent" />
          <p className="mt-3 text-sm text-text-tertiary">Loading Literature Map...</p>
        </div>
      </div>
    )
  }

  if (status === 'failed') {
    const details = getApiErrorDetailsList(errorDetail)
    return (
      <div className="rounded-xl border border-border-default bg-bg-surface p-8">
        <XCircleIcon className="mx-auto h-12 w-12 text-error" />
        <h3 className="mt-4 text-center text-xl font-semibold text-text-primary">Literature Map failed</h3>
        <p className="mt-2 text-center text-sm text-text-tertiary">
          {error || payload?.message || 'The Literature Map could not be generated.'}
        </p>
        {errorDetail && (
          <div className="mt-4">
            <InlineAlert
              title={errorDetail.title || 'Literature Map failed'}
              message={errorDetail.message || 'We could not generate the Literature Map.'}
              details={details}
            />
          </div>
        )}
        <button
          onClick={handleAnalyze}
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-accent-primary px-4 py-2 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
        >
          <ArrowPathIcon className="h-4 w-4" />
          Retry
        </button>
      </div>
    )
  }

  if (status === 'analyzing') {
    const currentStageIndex = progress?.stage
      ? progressSteps.findIndex((step) => step.key === progress.stage)
      : 0
    return (
      <div className="rounded-xl border border-border-default bg-bg-surface p-8">
        <ProgressIndicator
          progress={progress?.percent ?? 15}
          status={progress?.retrying ? 'Building and retrying Literature Map' : 'Building Literature Map'}
          steps={progressSteps.map((step, index) => ({
            label: step.label,
            completed: index < currentStageIndex,
            active: index === currentStageIndex,
          }))}
          showElapsedTime
        />
        <div className="mt-4">
          <InlineAlert
            tone="info"
            title="Private by default"
            message="Your files stay in your workspace and are not used to train models."
          />
        </div>
      </div>
    )
  }

  if (!payload || status === 'not_analyzed' || !payload.insights) {
    return (
      <div className="rounded-xl border border-border-default bg-bg-surface p-8 text-center">
        <div className="mx-auto flex h-16 w-16 items-center justify-center rounded-xl bg-bg-elevated">
          <LightBulbIcon className="h-8 w-8 text-accent-primary" />
        </div>
        <h3 className="mt-4 text-xl font-semibold text-text-primary">Generate your Literature Map</h3>
        <p className="mx-auto mt-2 max-w-xl text-sm text-text-tertiary">
          Get a coverage snapshot, evidence-grounded field overview, and targeted gaps and conflicts from your analyzed literature.
        </p>
        <p className="mt-3 text-xs text-text-muted">
          {formatQuotaLabel(payload?.quota ?? {
            used: 0,
            limit: null,
            remaining: null,
            is_unlimited: true,
          })}
        </p>
        <button
          onClick={handleAnalyze}
          className="mt-6 inline-flex items-center gap-2 rounded-lg bg-accent-primary px-5 py-2.5 text-sm font-semibold text-white transition-colors hover:bg-accent-hover"
        >
          <DocumentMagnifyingGlassIcon className="h-4 w-4" />
          Generate Literature Map
        </button>
      </div>
    )
  }

  const insights = payload.insights
  const coverageSnapshot = insights.coverage_snapshot
  const keyInsightDetails = getKeyInsightDetails(payload)

  return (
    <div className="space-y-6">
      <div className="rounded-xl border border-border-default bg-bg-surface p-5">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <div className="flex items-center gap-2">
              <SparklesIcon className="h-5 w-5 text-accent-primary" />
              <h3 className="text-xl font-semibold text-text-primary">Literature Map</h3>
            </div>
            <p className="mt-2 text-sm text-text-tertiary">
              Last updated {payload.insights_updated_at ? new Date(payload.insights_updated_at).toLocaleString() : 'just now'}
            </p>
            <p className="mt-1 text-xs text-text-muted">{formatQuotaLabel(payload.quota)}</p>
          </div>

          <button
            onClick={handleAnalyze}
            disabled={isRefreshing}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-lg border border-border-default px-4 text-sm font-semibold text-text-primary transition-colors hover:border-accent-primary/40 hover:text-accent-primary disabled:opacity-50"
          >
            <ArrowPathIcon className={`h-4 w-4 ${isRefreshing ? 'animate-spin' : ''}`} />
            {isRefreshing ? 'Refreshing…' : 'Refresh Literature Map'}
          </button>
        </div>

        {payload.is_stale ? (
          <div className="mt-4 flex items-start gap-3 rounded-xl border border-warning/30 bg-warning/10 p-4">
            <ExclamationTriangleIcon className="mt-0.5 h-5 w-5 shrink-0 text-warning" />
            <div>
              <p className="font-semibold text-text-primary">Literature changed since the last map run</p>
              <p className="mt-1 text-sm text-text-secondary">
                {payload.stale_reason === 'document_count_changed'
                  ? 'The number of analyzed papers changed.'
                  : payload.stale_reason === 'documents_changed'
                    ? 'At least one paper was updated after the last run.'
                    : 'The analyzed paper set changed after the last run.'}
              </p>
            </div>
          </div>
        ) : (
          <div className="mt-4 flex items-start gap-3 rounded-xl border border-border-default bg-bg-elevated p-4">
            <CheckCircleIcon className="mt-0.5 h-5 w-5 shrink-0 text-success" />
            <div>
              <p className="font-semibold text-text-primary">Current with your analyzed library</p>
              <p className="mt-1 text-sm text-text-secondary">
                Based on {insights.analysis_metadata?.num_papers_analyzed ?? coverageSnapshot.paper_count} analyzed papers.
              </p>
            </div>
          </div>
        )}
      </div>

      <section className="rounded-xl border border-border-default bg-bg-surface p-5">
        <h4 className="text-lg font-semibold text-text-primary">Coverage Snapshot</h4>
        <div className="mt-4 grid gap-4 lg:grid-cols-4">
          <div className="rounded-xl border border-border-default bg-bg-elevated p-4">
            <p className="text-xs uppercase tracking-wide text-text-muted">Papers</p>
            <p className="mt-2 text-2xl font-semibold text-text-primary">{coverageSnapshot.paper_count}</p>
          </div>
          <div className="rounded-xl border border-border-default bg-bg-elevated p-4">
            <p className="text-xs uppercase tracking-wide text-text-muted">Year span</p>
            <p className="mt-2 text-lg font-semibold text-text-primary">
              {coverageSnapshot.year_range.min && coverageSnapshot.year_range.max
                ? `${coverageSnapshot.year_range.min}–${coverageSnapshot.year_range.max}`
                : 'Not available'}
            </p>
          </div>
          <div className="rounded-xl border border-border-default bg-bg-elevated p-4">
            <p className="text-xs uppercase tracking-wide text-text-muted">Top methods</p>
            <div className="mt-3">
              <CoverageList items={coverageSnapshot.top_methods} emptyLabel="No dominant method pattern yet." />
            </div>
          </div>
          <div className="rounded-xl border border-border-default bg-bg-elevated p-4">
            <p className="text-xs uppercase tracking-wide text-text-muted">Top venues / contexts</p>
            <div className="mt-3 space-y-4">
              <CoverageList items={coverageSnapshot.top_venues} emptyLabel="No venue metadata yet." />
              <CoverageList items={coverageSnapshot.top_contexts} emptyLabel="No study contexts yet." />
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-xl border border-border-default bg-bg-surface p-5">
        <h4 className="text-lg font-semibold text-text-primary">Field Overview</h4>
        {insights.summary && (
          <p className="mt-3 rounded-xl border border-border-default bg-bg-elevated p-4 text-sm leading-relaxed text-text-secondary">
            {insights.summary}
          </p>
        )}

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          {keyInsightDetails.map((detail) => (
            <div key={detail.statement} className="rounded-xl border border-border-default bg-bg-elevated p-4">
              <p className="text-sm font-semibold text-text-primary">{detail.statement}</p>
              {detail.rationale && (
                <p className="mt-2 text-sm text-text-secondary">{detail.rationale}</p>
              )}
              <div className="mt-3">
                <SourcePapers papers={detail.source_papers} />
              </div>
            </div>
          ))}
        </div>

        <div className="mt-5 grid gap-4 xl:grid-cols-2">
          <div className="rounded-xl border border-border-default bg-bg-elevated p-4">
            <h5 className="text-sm font-semibold text-text-primary">Themes</h5>
            <div className="mt-3 space-y-3">
              {(insights.common_themes ?? []).slice(0, 4).map((theme) => (
                <div key={theme.theme} className="rounded-lg border border-border-default bg-bg-surface p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-text-primary">{theme.theme}</p>
                    <span className="text-xs font-mono text-text-muted">{theme.frequency}</span>
                  </div>
                  <p className="mt-2 text-sm text-text-secondary">{theme.description}</p>
                  <div className="mt-3">
                    <SourcePapers papers={theme.source_papers} />
                  </div>
                </div>
              ))}
            </div>
          </div>

          <div className="rounded-xl border border-border-default bg-bg-elevated p-4">
            <h5 className="text-sm font-semibold text-text-primary">Method patterns</h5>
            <div className="mt-3 space-y-3">
              {(insights.methodological_patterns ?? []).slice(0, 4).map((pattern) => (
                <div key={pattern.methodology} className="rounded-lg border border-border-default bg-bg-surface p-3">
                  <div className="flex items-center justify-between gap-3">
                    <p className="text-sm font-semibold text-text-primary">{pattern.methodology}</p>
                    <span className="text-xs font-mono text-text-muted">{pattern.usage_count}</span>
                  </div>
                  <p className="mt-2 text-sm text-text-secondary">{pattern.description}</p>
                  <div className="mt-3">
                    <SourcePapers papers={pattern.source_papers} />
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </section>

      {payload.summary_recommendations.length > 0 && (
        <section className="rounded-xl border border-border-default bg-bg-surface p-5">
          <h4 className="text-lg font-semibold text-text-primary">Recommended Papers</h4>
          <p className="mt-2 text-sm text-text-tertiary">
            Suggested papers tied to your current literature map.
          </p>
          <div className="mt-4 grid gap-3 lg:grid-cols-2">
            {payload.summary_recommendations.map((recommendation) => (
              <RecommendationChip
                key={recommendation.id}
                recommendation={recommendation}
                isSaving={savingIds.has(recommendation.id)}
                onSave={handleSaveRecommendation}
              />
            ))}
          </div>
        </section>
      )}

      <section className="rounded-xl border border-border-default bg-bg-surface p-5">
        <h4 className="text-lg font-semibold text-text-primary">Gaps & Conflicts</h4>

        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="space-y-4">
            {(insights.research_gaps ?? []).map((gap) => (
              <div key={gap.title} className="rounded-xl border border-border-default bg-bg-elevated p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="text-sm font-semibold text-text-primary">{gap.title}</p>
                  <span className="rounded-lg border border-border-default px-2 py-1 text-xs text-text-muted">
                    {gap.category}
                  </span>
                </div>
                <p className="mt-2 text-sm text-text-secondary">{gap.description}</p>
                {gap.suggested_directions && gap.suggested_directions.length > 0 && (
                  <ul className="mt-3 space-y-1 text-sm text-text-tertiary">
                    {gap.suggested_directions.map((direction) => (
                      <li key={direction}>• {direction}</li>
                    ))}
                  </ul>
                )}
                <div className="mt-3">
                  <SourcePapers papers={gap.source_papers} />
                </div>
                {payload.gap_recommendations_by_title[gap.title]?.length > 0 && (
                  <div className="mt-4 space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Suggested papers</p>
                    {payload.gap_recommendations_by_title[gap.title].map((recommendation) => (
                      <RecommendationChip
                        key={recommendation.id}
                        recommendation={recommendation}
                        isSaving={savingIds.has(recommendation.id)}
                        onSave={handleSaveRecommendation}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>

          <div className="space-y-4">
            {(insights.conflicting_findings ?? []).map((conflict) => (
              <div key={conflict.topic} className="rounded-xl border border-border-default bg-bg-elevated p-4">
                <p className="text-sm font-semibold text-text-primary">{conflict.topic}</p>
                <div className="mt-3 grid gap-3 md:grid-cols-2">
                  <div className="rounded-lg border border-border-default bg-bg-surface p-3">
                    <p className="text-xs uppercase tracking-wide text-text-muted">Side A</p>
                    <p className="mt-2 text-sm text-text-secondary">{conflict.side_a.position}</p>
                  </div>
                  <div className="rounded-lg border border-border-default bg-bg-surface p-3">
                    <p className="text-xs uppercase tracking-wide text-text-muted">Side B</p>
                    <p className="mt-2 text-sm text-text-secondary">{conflict.side_b.position}</p>
                  </div>
                </div>
                {conflict.resolution && (
                  <p className="mt-3 text-sm text-text-secondary">{conflict.resolution}</p>
                )}
                <div className="mt-3">
                  <SourcePapers papers={conflict.source_papers} />
                </div>
                {payload.conflict_recommendations_by_topic[conflict.topic]?.length > 0 && (
                  <div className="mt-4 space-y-3">
                    <p className="text-xs font-semibold uppercase tracking-wide text-text-muted">Suggested papers</p>
                    {payload.conflict_recommendations_by_topic[conflict.topic].map((recommendation) => (
                      <RecommendationChip
                        key={recommendation.id}
                        recommendation={recommendation}
                        isSaving={savingIds.has(recommendation.id)}
                        onSave={handleSaveRecommendation}
                      />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </section>
    </div>
  )
}

export interface RecommendationRecord {
  id: string
  title: string
  abstract?: string | null
  authors?: string[]
  year?: number | null
  source?: 'semantic_scholar' | 'arxiv' | 'pubmed'
  paper_url?: string | null
  pdf_url?: string | null
  citation_count?: number | null
  journal_name?: string | null
  relevance_score?: number
  relevance_reason?: string | null
  bib_saved?: boolean
  status?: string
}

export interface CoverageItem {
  label: string
  count: number
}

export interface CoverageSnapshot {
  paper_count: number
  year_range: {
    min: number | null
    max: number | null
  }
  top_methods: CoverageItem[]
  top_venues: CoverageItem[]
  top_contexts: CoverageItem[]
}

export interface LiteratureMapQuota {
  used: number
  limit: number | null
  remaining: number | null
  is_unlimited: boolean
}

export interface LiteratureMapResponse {
  status: 'not_analyzed' | 'analyzing' | 'analyzed' | 'failed'
  message?: string
  is_stale: boolean
  stale_reason?: string | null
  insights_updated_at?: string | null
  latest_document_updated_at?: string | null
  quota: LiteratureMapQuota
  insights?: {
    summary?: string
    key_insights?: string[]
    key_insight_details?: Array<{
      statement: string
      source_papers?: string[]
      rationale?: string
    }>
    research_gaps?: Array<{
      category: string
      title: string
      description: string
      supporting_evidence?: string[]
      suggested_directions?: string[]
      source_papers?: string[]
    }>
    common_themes?: Array<{
      theme: string
      frequency: number
      description: string
      paper_titles?: string[]
      source_papers?: string[]
    }>
    methodological_patterns?: Array<{
      methodology: string
      usage_count: number
      description: string
      variations?: string[]
      source_papers?: string[]
    }>
    conflicting_findings?: Array<{
      topic: string
      resolution?: string
      source_papers?: string[]
      side_a: {
        position: string
        papers?: string[]
        evidence?: string
      }
      side_b: {
        position: string
        papers?: string[]
        evidence?: string
      }
    }>
    coverage_snapshot?: CoverageSnapshot
    analysis_metadata?: {
      num_papers_analyzed?: number
      timestamp?: string | null
    }
  } | null
  summary_recommendations: RecommendationRecord[]
  gap_recommendations_by_title: Record<string, RecommendationRecord[]>
  conflict_recommendations_by_topic: Record<string, RecommendationRecord[]>
}

function asArray<T>(value: T[] | undefined | null): T[] {
  return Array.isArray(value) ? value : []
}

export function normalizeLiteratureMapResponse(data: Partial<LiteratureMapResponse>): LiteratureMapResponse {
  const normalizedInsights = data.insights
    ? {
        ...data.insights,
        summary: data.insights.summary ?? '',
        key_insights: asArray(data.insights.key_insights),
        key_insight_details: asArray(data.insights.key_insight_details),
        research_gaps: asArray(data.insights.research_gaps),
        common_themes: asArray(data.insights.common_themes),
        methodological_patterns: asArray(data.insights.methodological_patterns),
        conflicting_findings: asArray(data.insights.conflicting_findings),
        coverage_snapshot: data.insights.coverage_snapshot ?? {
          paper_count: data.insights.analysis_metadata?.num_papers_analyzed ?? 0,
          year_range: { min: null, max: null },
          top_methods: [],
          top_venues: [],
          top_contexts: [],
        },
      }
    : null

  return {
    status: data.status ?? 'not_analyzed',
    message: data.message,
    is_stale: data.is_stale ?? false,
    stale_reason: data.stale_reason ?? null,
    insights_updated_at: data.insights_updated_at ?? null,
    latest_document_updated_at: data.latest_document_updated_at ?? null,
    quota: data.quota ?? {
      used: 0,
      limit: null,
      remaining: null,
      is_unlimited: true,
    },
    insights: normalizedInsights,
    summary_recommendations: asArray(data.summary_recommendations),
    gap_recommendations_by_title: data.gap_recommendations_by_title ?? {},
    conflict_recommendations_by_topic: data.conflict_recommendations_by_topic ?? {},
  }
}

export function getKeyInsightDetails(response: LiteratureMapResponse) {
  const details = response.insights?.key_insight_details ?? []
  if (details.length > 0) {
    return details
  }

  return (response.insights?.key_insights ?? []).map(statement => ({
    statement,
    source_papers: [],
    rationale: '',
  }))
}

export function formatQuotaLabel(quota: LiteratureMapQuota): string {
  if (quota.is_unlimited || quota.limit == null) {
    return 'Unlimited refreshes'
  }

  return `${quota.used} of ${quota.limit} refreshes used today`
}

export function markRecommendationSaved(
  response: LiteratureMapResponse,
  recommendationId: string,
): LiteratureMapResponse {
  const markSaved = (recommendation: RecommendationRecord) =>
    recommendation.id === recommendationId
      ? { ...recommendation, bib_saved: true }
      : recommendation

  return {
    ...response,
    summary_recommendations: response.summary_recommendations.map(markSaved),
    gap_recommendations_by_title: Object.fromEntries(
      Object.entries(response.gap_recommendations_by_title).map(([key, records]) => [
        key,
        records.map(markSaved),
      ]),
    ),
    conflict_recommendations_by_topic: Object.fromEntries(
      Object.entries(response.conflict_recommendations_by_topic).map(([key, records]) => [
        key,
        records.map(markSaved),
      ]),
    ),
  }
}

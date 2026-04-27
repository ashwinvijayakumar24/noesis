import { describe, expect, it } from 'vitest'

import {
  formatQuotaLabel,
  getKeyInsightDetails,
  markRecommendationSaved,
  normalizeLiteratureMapResponse,
} from './literatureMap'

describe('literatureMap helpers', () => {
  it('normalizes legacy payloads without new optional fields', () => {
    const response = normalizeLiteratureMapResponse({
      status: 'analyzed',
      is_stale: false,
      quota: {
        used: 2,
        limit: 5,
        remaining: 3,
        is_unlimited: false,
      },
      insights: {
        summary: 'Summary',
        key_insights: ['Insight A'],
        analysis_metadata: { num_papers_analyzed: 3 },
      },
    })

    expect(response.insights?.coverage_snapshot?.paper_count).toBe(3)
    expect(response.insights?.research_gaps).toEqual([])
    expect(getKeyInsightDetails(response)).toEqual([
      { statement: 'Insight A', source_papers: [], rationale: '' },
    ])
  })

  it('formats quota labels for limited and unlimited plans', () => {
    expect(formatQuotaLabel({
      used: 4,
      limit: 5,
      remaining: 1,
      is_unlimited: false,
    })).toBe('4 of 5 refreshes used today')

    expect(formatQuotaLabel({
      used: 0,
      limit: null,
      remaining: null,
      is_unlimited: true,
    })).toBe('Unlimited refreshes')
  })

  it('marks a recommendation as saved across summary and inline mappings', () => {
    const response = normalizeLiteratureMapResponse({
      status: 'analyzed',
      is_stale: false,
      quota: {
        used: 0,
        limit: null,
        remaining: null,
        is_unlimited: true,
      },
      insights: { summary: '' },
      summary_recommendations: [{ id: 'rec-1', title: 'Paper 1', bib_saved: false }],
      gap_recommendations_by_title: {
        Gap: [{ id: 'rec-1', title: 'Paper 1', bib_saved: false }],
      },
      conflict_recommendations_by_topic: {
        Topic: [{ id: 'rec-1', title: 'Paper 1', bib_saved: false }],
      },
    })

    const updated = markRecommendationSaved(response, 'rec-1')

    expect(updated.summary_recommendations[0].bib_saved).toBe(true)
    expect(updated.gap_recommendations_by_title.Gap[0].bib_saved).toBe(true)
    expect(updated.conflict_recommendations_by_topic.Topic[0].bib_saved).toBe(true)
  })
})

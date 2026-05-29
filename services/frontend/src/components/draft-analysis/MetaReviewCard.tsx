import { useState } from 'react'
import {
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
  ExclamationTriangleIcon,
  LightBulbIcon,
} from '@heroicons/react/24/outline'
import MarkdownText from './MarkdownText'

interface MetaReview {
  overall_recommendation: 'accept' | 'minor_revision' | 'major_revision' | 'reject'
  decision_rationale: string
  must_address: string[]
  nice_to_address: string[]
  consensus_strengths: string[]
  consensus_weaknesses: string[]
  reviewer_agreement_level: 'high' | 'medium' | 'low'
  score_summary: Record<string, number>
}

interface MetaReviewCardProps {
  metaReview: MetaReview | Record<string, unknown>
}

const RECOMMENDATION_STYLES: Record<string, { label: string; text: string }> = {
  accept:          { label: 'Accept',          text: 'text-success' },
  minor_revision:  { label: 'Minor Revision',  text: 'text-warning' },
  major_revision:  { label: 'Major Revision',  text: 'text-warning' },
  reject:          { label: 'Reject',          text: 'text-error' },
}

const AGREEMENT_COLORS: Record<string, string> = {
  high: 'text-success',
  medium: 'text-warning',
  low: 'text-error',
}

const REVIEWER_LABELS: Record<string, string> = {
  novelty: 'Novelty',
  methodology: 'Methods',
  coverage: 'Coverage',
  literature_positioning: 'Literature & Positioning',
  clarity: 'Clarity',
}

function asStringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : []
}

function normalizeMetaReview(raw: MetaReview | Record<string, unknown>): MetaReview {
  const row = (raw ?? {}) as Record<string, unknown>
  const nested = (row.meta_review && typeof row.meta_review === 'object')
    ? row.meta_review as Record<string, unknown>
    : row

  const recommendation = String(
    nested.overall_recommendation ?? row.overall_recommendation ?? 'major_revision'
  ) as MetaReview['overall_recommendation']
  const agreement = String(
    nested.reviewer_agreement_level ?? row.reviewer_agreement_level ?? 'medium'
  ) as MetaReview['reviewer_agreement_level']

  return {
    overall_recommendation: recommendation,
    decision_rationale: String(nested.decision_rationale ?? row.decision_rationale ?? ''),
    must_address: asStringArray(nested.must_address ?? row.must_address),
    nice_to_address: asStringArray(nested.nice_to_address ?? row.nice_to_address),
    consensus_strengths: asStringArray(nested.consensus_strengths ?? row.consensus_strengths),
    consensus_weaknesses: asStringArray(nested.consensus_weaknesses ?? row.consensus_weaknesses),
    reviewer_agreement_level: agreement,
    score_summary: (
      nested.score_summary && typeof nested.score_summary === 'object'
        ? nested.score_summary
        : row.score_summary && typeof row.score_summary === 'object'
          ? row.score_summary
          : {}
    ) as Record<string, number>,
  }
}

export default function MetaReviewCard({ metaReview }: MetaReviewCardProps) {
  const [expanded, setExpanded] = useState(false)
  const meta = normalizeMetaReview(metaReview)
  const rec = RECOMMENDATION_STYLES[meta.overall_recommendation] ?? {
    label: meta.overall_recommendation,
    text: 'text-text-secondary',
  }
  const agreementColor = AGREEMENT_COLORS[meta.reviewer_agreement_level] ?? 'text-text-muted'

  const scores = meta.score_summary ?? {}

  return (
    <div className="rounded-xl border border-border-default bg-bg-surface overflow-hidden">
      <button
        onClick={() => setExpanded((value) => !value)}
        className="flex w-full items-center justify-between border-b border-border-default px-4 py-3 text-left transition-colors duration-fast hover:bg-bg-elevated"
      >
        <div className="flex min-w-0 items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-text-secondary">
            Area Chair Summary
          </span>
          <span className={`shrink-0 text-xs font-semibold ${rec.text}`}>
            {rec.label}
          </span>
        </div>
        {expanded
          ? <ChevronUpIcon className="h-4 w-4 shrink-0 text-text-muted" />
          : <ChevronDownIcon className="h-4 w-4 shrink-0 text-text-muted" />
        }
      </button>

      <div className="px-4 py-3 space-y-4">
        {Object.keys(scores).length > 0 && (
          <div className="flex flex-wrap gap-3">
            {Object.entries(scores).map(([rid, rating]) => (
              <div key={rid} className="flex flex-col items-center gap-0.5">
                <span className="text-xs text-text-muted">{REVIEWER_LABELS[rid] ?? rid}</span>
                <span className="text-sm font-semibold text-text-primary">{rating}<span className="text-text-muted font-normal">/10</span></span>
              </div>
            ))}
            <div className="flex flex-col items-center gap-0.5 ml-auto">
              <span className="text-xs text-text-muted">Agreement</span>
              <span className={`text-sm font-semibold capitalize ${agreementColor}`}>
                {meta.reviewer_agreement_level}
              </span>
            </div>
          </div>
        )}

        {/* Rationale */}
        {meta.decision_rationale && (
          <MarkdownText
            as="p"
            text={meta.decision_rationale}
            className={`text-sm text-text-secondary leading-relaxed ${expanded ? '' : 'line-clamp-5'}`}
          />
        )}

        {expanded && (
          <>
            <div className="grid gap-4 sm:grid-cols-2">
              {meta.must_address.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-error mb-1.5 flex items-center gap-1">
                    <ExclamationTriangleIcon className="h-3.5 w-3.5" />
                    Must Address
                  </p>
                  <ul className="space-y-1">
                    {meta.must_address.map((item, i) => (
                      <li key={i} className="text-xs text-text-secondary leading-relaxed">
                        • <MarkdownText text={item} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {meta.consensus_strengths.length > 0 && (
                <div>
                  <p className="text-xs font-semibold text-success mb-1.5 flex items-center gap-1">
                    <CheckCircleIcon className="h-3.5 w-3.5" />
                    Consensus Strengths
                  </p>
                  <ul className="space-y-1">
                    {meta.consensus_strengths.map((s, i) => (
                      <li key={i} className="text-xs text-text-secondary leading-relaxed">
                        • <MarkdownText text={s} />
                      </li>
                    ))}
                  </ul>
                </div>
              )}
            </div>

            {meta.nice_to_address.length > 0 && (
              <div>
                <p className="text-xs font-semibold text-text-muted mb-1.5 flex items-center gap-1">
                  <LightBulbIcon className="h-3.5 w-3.5" />
                  Nice to Address
                </p>
                <ul className="space-y-1">
                  {meta.nice_to_address.map((item, i) => (
                    <li key={i} className="text-xs text-text-secondary leading-relaxed">
                      • <MarkdownText text={item} />
                    </li>
                  ))}
                </ul>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}

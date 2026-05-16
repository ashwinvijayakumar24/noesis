import { ExclamationTriangleIcon, CheckCircleIcon, LightBulbIcon } from '@heroicons/react/24/outline'
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
  metaReview: MetaReview
}

const RECOMMENDATION_STYLES: Record<string, { label: string; bg: string; text: string }> = {
  accept:          { label: 'Accept',          bg: 'bg-green-900/30',  text: 'text-green-400' },
  minor_revision:  { label: 'Minor Revision',  bg: 'bg-yellow-900/30', text: 'text-yellow-400' },
  major_revision:  { label: 'Major Revision',  bg: 'bg-orange-900/30', text: 'text-orange-400' },
  reject:          { label: 'Reject',          bg: 'bg-red-900/30',    text: 'text-red-400' },
}

const AGREEMENT_COLORS: Record<string, string> = {
  high: 'text-green-400',
  medium: 'text-yellow-400',
  low: 'text-red-400',
}

const REVIEWER_LABELS: Record<string, string> = {
  novelty: 'Novelty',
  methodology: 'Methods',
  coverage: 'Coverage',
  clarity: 'Clarity',
}

export default function MetaReviewCard({ metaReview }: MetaReviewCardProps) {
  const rec = RECOMMENDATION_STYLES[metaReview.overall_recommendation] ?? {
    label: metaReview.overall_recommendation,
    bg: 'bg-bg-elevated',
    text: 'text-text-secondary',
  }
  const agreementColor = AGREEMENT_COLORS[metaReview.reviewer_agreement_level] ?? 'text-text-muted'

  const scores = metaReview.score_summary ?? {}

  return (
    <div className="rounded-xl border border-border-default bg-bg-surface overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-border-default flex items-center justify-between">
        <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
          Area Chair Summary
        </span>
        <span className={`text-xs font-semibold px-2 py-0.5 rounded-md ${rec.bg} ${rec.text}`}>
          {rec.label}
        </span>
      </div>

      <div className="px-4 py-3 space-y-4">
        {/* Score row */}
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
                {metaReview.reviewer_agreement_level}
              </span>
            </div>
          </div>
        )}

        {/* Rationale */}
        {metaReview.decision_rationale && (
          <MarkdownText
            as="p"
            text={metaReview.decision_rationale}
            className="text-sm text-text-secondary leading-relaxed"
          />
        )}

        {/* Two-column: must address + consensus strengths */}
        <div className="grid grid-cols-2 gap-4">
          {metaReview.must_address.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-red-400 mb-1.5 flex items-center gap-1">
                <ExclamationTriangleIcon className="h-3.5 w-3.5" />
                Must Address
              </p>
              <ul className="space-y-1">
                {metaReview.must_address.map((item, i) => (
                  <li key={i} className="text-xs text-text-secondary leading-relaxed">
                    • <MarkdownText text={item} />
                  </li>
                ))}
              </ul>
            </div>
          )}

          {metaReview.consensus_strengths.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-green-400 mb-1.5 flex items-center gap-1">
                <CheckCircleIcon className="h-3.5 w-3.5" />
                Consensus Strengths
              </p>
              <ul className="space-y-1">
                {metaReview.consensus_strengths.map((s, i) => (
                  <li key={i} className="text-xs text-text-secondary leading-relaxed">
                    • <MarkdownText text={s} />
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>

        {/* Nice to address */}
        {metaReview.nice_to_address.length > 0 && (
          <div>
            <p className="text-xs font-semibold text-text-muted mb-1.5 flex items-center gap-1">
              <LightBulbIcon className="h-3.5 w-3.5" />
              Nice to Address
            </p>
            <ul className="space-y-1">
              {metaReview.nice_to_address.map((item, i) => (
                <li key={i} className="text-xs text-text-secondary leading-relaxed">
                  • <MarkdownText text={item} />
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

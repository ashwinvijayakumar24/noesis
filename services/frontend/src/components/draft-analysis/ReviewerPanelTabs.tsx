import { useState } from 'react'
import {
  QuestionMarkCircleIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  ChevronUpIcon,
} from '@heroicons/react/24/outline'
import MarkdownText from './MarkdownText'

interface ReviewerOutput {
  reviewer_id: 'methodology' | 'literature_positioning' | 'clarity' | 'novelty' | 'coverage'
  summary: string
  strengths: string[]
  weaknesses: string[]
  questions_to_authors: string[]
  limitations_to_address: string[]
  issues?: Array<{
    issue_type: string
    section_reference?: string
    anchor_text?: string
    problem: string
    why_it_matters: string
    suggested_action: string
    confidence?: number
  }>
  rating: number
  confidence: number
  recommendation: 'accept' | 'minor_revision' | 'major_revision' | 'reject'
}

interface ReviewerPanelTabsProps {
  reviewers: ReviewerOutput[]
}

const REVIEWER_META: Record<string, { label: string; subtitle: string }> = {
  novelty:     { label: 'Novelty & Contribution', subtitle: 'Significance vs. prior work' },
  methodology: { label: 'Methodology',            subtitle: 'Technical soundness' },
  coverage:    { label: 'Literature Coverage',    subtitle: 'Related work & citations' },
  literature_positioning: { label: 'Literature & Positioning', subtitle: 'Contribution, prior work & missing context' },
  clarity:     { label: 'Clarity & Presentation', subtitle: 'Writing & reproducibility' },
}

const REC_STYLES: Record<string, { label: string; text: string }> = {
  accept:         { label: 'Accept',          text: 'text-success' },
  minor_revision: { label: 'Minor Revision',  text: 'text-warning' },
  major_revision: { label: 'Major Revision',  text: 'text-warning' },
  reject:         { label: 'Reject',          text: 'text-error' },
}

function ratingColor(rating: number): string {
  if (rating >= 7) return 'text-success'
  if (rating >= 5) return 'text-warning'
  return 'text-error'
}

const TAB_ORDER = ['methodology', 'literature_positioning', 'clarity', 'novelty', 'coverage']

export default function ReviewerPanelTabs({ reviewers }: ReviewerPanelTabsProps) {
  const [expandedId, setExpandedId] = useState<string | null>(null)

  const sorted = TAB_ORDER
    .map(id => reviewers.find(r => r.reviewer_id === id))
    .filter((r): r is ReviewerOutput => r !== undefined)

  if (sorted.length === 0) return null

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-text-muted uppercase tracking-wider px-1">
        Reviewer Summaries
      </p>
      {sorted.map((reviewer) => {
        const meta = REVIEWER_META[reviewer.reviewer_id] ?? { label: reviewer.reviewer_id, subtitle: '' }
        const rec = REC_STYLES[reviewer.recommendation] ?? { label: reviewer.recommendation, text: 'text-text-muted' }
        const isExpanded = expandedId === reviewer.reviewer_id

        return (
          <div key={reviewer.reviewer_id} className="rounded-xl border border-border-default bg-bg-surface overflow-hidden">
            <button
              onClick={() => setExpandedId(isExpanded ? null : reviewer.reviewer_id)}
              className="w-full flex items-center justify-between px-4 py-3 hover:bg-bg-elevated transition-colors duration-fast text-left"
            >
              <div className="flex items-center gap-2 min-w-0">
                <span className="text-sm font-semibold text-text-primary truncate">{meta.label}</span>
                <span className={`hidden shrink-0 text-xs font-semibold sm:inline ${rec.text}`}>
                  {rec.label}
                </span>
              </div>
              <div className="flex items-center gap-3 shrink-0 ml-3">
                <span className={`text-sm font-semibold ${ratingColor(reviewer.rating)}`}>
                  {reviewer.rating}<span className="text-text-muted text-xs font-normal">/10</span>
                </span>
                {isExpanded
                  ? <ChevronUpIcon className="h-4 w-4 text-text-muted" />
                  : <ChevronDownIcon className="h-4 w-4 text-text-muted" />
                }
              </div>
            </button>

            {isExpanded && (
              <div className="border-t border-border-default px-4 py-3 space-y-4">
                {/* Mobile rec badge */}
                <div className="sm:hidden">
                  <span className={`text-xs font-semibold ${rec.text}`}>
                    {rec.label}
                  </span>
                  <span className="ml-2 text-xs text-text-muted">Confidence: {reviewer.confidence}/5</span>
                </div>

                <div className="hidden sm:flex items-center gap-2 text-xs text-text-muted">
                  <span>{meta.subtitle}</span>
                  <span>·</span>
                  <span>Confidence: {reviewer.confidence}/5</span>
                </div>

                {reviewer.summary && (
                  <MarkdownText
                    as="p"
                    text={reviewer.summary}
                    className="text-sm text-text-secondary leading-relaxed"
                  />
                )}

                {reviewer.issues && reviewer.issues.length > 0 && (
                  <div className="border-t border-border-default pt-3">
                    <p className="text-xs font-semibold text-text-secondary flex items-center gap-1">
                      <ExclamationTriangleIcon className="h-3.5 w-3.5" />
                      {reviewer.issues.length} issue{reviewer.issues.length === 1 ? '' : 's'} consolidated below
                    </p>
                    <p className="mt-1 text-xs text-text-muted">
                      The actionable problem, rationale, and next step for each reviewer concern are in the durable task queue.
                    </p>
                  </div>
                )}

                {(reviewer.strengths.length > 0 || reviewer.weaknesses.length > 0) && (
                  <div className="grid grid-cols-2 gap-4">
                    {reviewer.strengths.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-success mb-1.5 flex items-center gap-1">
                          <CheckCircleIcon className="h-3.5 w-3.5" />
                          Strengths
                        </p>
                        <ul className="space-y-1">
                          {reviewer.strengths.map((s, i) => (
                            <li key={i} className="text-xs text-text-secondary leading-relaxed">
                              + <MarkdownText text={s} />
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                    {reviewer.weaknesses.length > 0 && (
                      <div>
                        <p className="text-xs font-semibold text-error mb-1.5 flex items-center gap-1">
                          <ExclamationTriangleIcon className="h-3.5 w-3.5" />
                          Weaknesses
                        </p>
                        <ul className="space-y-1">
                          {reviewer.weaknesses.map((w, i) => (
                            <li key={i} className="text-xs text-text-secondary leading-relaxed">
                              - <MarkdownText text={w} />
                            </li>
                          ))}
                        </ul>
                      </div>
                    )}
                  </div>
                )}

                {reviewer.questions_to_authors.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-text-muted mb-1.5 flex items-center gap-1">
                      <QuestionMarkCircleIcon className="h-3.5 w-3.5" />
                      Questions to Authors
                    </p>
                    <ol className="space-y-1 list-decimal list-inside">
                      {reviewer.questions_to_authors.map((q, i) => (
                        <li key={i} className="text-xs text-text-secondary leading-relaxed">
                          <MarkdownText text={q} />
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                {reviewer.limitations_to_address.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-text-muted mb-1.5">Limitations to Address</p>
                    <ul className="space-y-1">
                      {reviewer.limitations_to_address.map((l, i) => (
                        <li key={i} className="text-xs text-text-secondary leading-relaxed">
                          • <MarkdownText text={l} />
                        </li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        )
      })}
    </div>
  )
}

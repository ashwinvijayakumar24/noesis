import { useState } from 'react'
import { CheckCircleIcon, ExclamationTriangleIcon, ChevronDownIcon, ChevronUpIcon } from '@heroicons/react/24/outline'

interface EditorDecision {
  proceed_to_review: boolean
  fatal_flaws: string[]
  scope_appropriate: boolean
  writing_quality: 'publishable' | 'needs_revision' | 'major_revision'
  notes: string
}

interface EditorDecisionCardProps {
  decision: EditorDecision
}

const QUALITY_LABELS: Record<string, { label: string; color: string }> = {
  publishable: { label: 'Publishable', color: 'text-green-400' },
  needs_revision: { label: 'Needs Revision', color: 'text-yellow-400' },
  major_revision: { label: 'Major Revision Needed', color: 'text-red-400' },
}

export default function EditorDecisionCard({ decision }: EditorDecisionCardProps) {
  const [expanded, setExpanded] = useState(false)
  const quality = QUALITY_LABELS[decision.writing_quality] ?? { label: decision.writing_quality, color: 'text-text-secondary' }
  const passed = decision.proceed_to_review

  return (
    <div className="rounded-xl border border-border-default bg-bg-surface overflow-hidden">
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between px-4 py-3 hover:bg-bg-elevated transition-colors duration-fast"
      >
        <div className="flex items-center gap-3">
          {passed
            ? <CheckCircleIcon className="h-4 w-4 text-green-400 shrink-0" />
            : <ExclamationTriangleIcon className="h-4 w-4 text-red-400 shrink-0" />
          }
          <span className="text-xs font-semibold text-text-secondary uppercase tracking-wider">
            Editorial Desk Check
          </span>
          <span className={`text-xs font-semibold ${quality.color}`}>
            {quality.label}
          </span>
          {!passed && (
            <span className="text-xs text-red-400 font-semibold">— Desk Reject</span>
          )}
        </div>
        {expanded
          ? <ChevronUpIcon className="h-4 w-4 text-text-muted" />
          : <ChevronDownIcon className="h-4 w-4 text-text-muted" />
        }
      </button>

      {expanded && (
        <div className="border-t border-border-default px-4 py-3 space-y-3">
          {decision.notes && (
            <p className="text-sm text-text-secondary">{decision.notes}</p>
          )}

          {decision.fatal_flaws.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-red-400 mb-1">Fatal Flaws</p>
              <ul className="space-y-1">
                {decision.fatal_flaws.map((f, i) => (
                  <li key={i} className="text-sm text-text-secondary flex gap-2">
                    <ExclamationTriangleIcon className="h-3.5 w-3.5 text-red-400 shrink-0 mt-0.5" />
                    {f}
                  </li>
                ))}
              </ul>
            </div>
          )}

          <div className="flex gap-4 text-xs text-text-muted">
            <span>Scope fit: <span className={decision.scope_appropriate ? 'text-green-400' : 'text-red-400'}>{decision.scope_appropriate ? 'Yes' : 'No'}</span></span>
          </div>
        </div>
      )}
    </div>
  )
}

import { useState } from 'react'
import { ChevronDownIcon, ChevronUpIcon, ExclamationTriangleIcon } from '@heroicons/react/24/outline'

interface Pattern {
  pattern_name: string
  frequency: number
  root_cause: string
  targeted_advice: string
}

interface RecurringPatternsProps {
  patterns: Pattern[]
  overallObservation: string | null
  loading?: boolean
}

export default function RecurringPatterns({ patterns, overallObservation, loading }: RecurringPatternsProps) {
  const [expanded, setExpanded] = useState(false)

  if (loading) {
    return (
      <div className="bg-bg-surface border border-border-default rounded-xl p-5">
        <div className="flex items-center gap-2 mb-3">
          <div className="h-4 w-4 bg-border-default rounded animate-pulse" />
          <div className="h-4 w-40 bg-border-default rounded animate-pulse" />
        </div>
        <div className="space-y-2">
          <div className="h-3 w-full bg-border-default rounded animate-pulse" />
          <div className="h-3 w-3/4 bg-border-default rounded animate-pulse" />
        </div>
      </div>
    )
  }

  if (patterns.length === 0) {
    return (
      <div className="bg-bg-surface border border-border-default rounded-xl p-5">
        <div className="flex items-center gap-2 mb-2">
          <ExclamationTriangleIcon className="h-4 w-4 text-text-tertiary" />
          <h3 className="text-sm font-semibold text-text-primary">Recurring Patterns</h3>
        </div>
        <p className="text-xs text-text-tertiary">
          {overallObservation || 'No recurring issues detected across versions — good progress!'}
        </p>
      </div>
    )
  }

  return (
    <div className="bg-bg-surface border border-border-default rounded-xl overflow-hidden">
      {/* Header — always visible */}
      <button
        onClick={() => setExpanded(v => !v)}
        className="w-full flex items-center justify-between p-5 hover:bg-white/[0.02] transition-colors"
      >
        <div className="flex items-center gap-2">
          <ExclamationTriangleIcon className="h-4 w-4 text-amber-400" />
          <h3 className="text-sm font-semibold text-text-primary">Recurring Patterns</h3>
          <span className="text-xs text-text-tertiary bg-bg-base border border-border-default rounded-full px-2 py-0.5">
            {patterns.length} pattern{patterns.length > 1 ? 's' : ''}
          </span>
        </div>
        {expanded
          ? <ChevronUpIcon className="h-4 w-4 text-text-tertiary" />
          : <ChevronDownIcon className="h-4 w-4 text-text-tertiary" />
        }
      </button>

      {/* Collapsed preview — overall observation */}
      {!expanded && overallObservation && (
        <p className="px-5 pb-4 text-xs text-text-secondary leading-relaxed -mt-2">
          {overallObservation}
        </p>
      )}

      {/* Expanded content */}
      {expanded && (
        <div className="px-5 pb-5 space-y-3 border-t border-border-default pt-4">
          {overallObservation && (
            <p className="text-xs text-text-secondary leading-relaxed italic border-l-2 border-amber-400/50 pl-3">
              {overallObservation}
            </p>
          )}

          {patterns.map((pattern, i) => (
            <div key={i} className="bg-bg-base border border-border-default rounded-lg p-4">
              <div className="flex items-start justify-between gap-2 mb-2">
                <span className="text-sm font-semibold text-text-primary">{pattern.pattern_name}</span>
                <span className="text-xs text-amber-400 font-semibold shrink-0 bg-amber-400/10 border border-amber-400/20 rounded-full px-2 py-0.5">
                  ×{pattern.frequency}
                </span>
              </div>
              <p className="text-xs text-text-tertiary leading-relaxed mb-2">
                <span className="text-text-secondary font-semibold">Why it recurs: </span>
                {pattern.root_cause}
              </p>
              <p className="text-xs text-text-secondary leading-relaxed">
                <span className="text-accent-primary font-semibold">Fix: </span>
                {pattern.targeted_advice}
              </p>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

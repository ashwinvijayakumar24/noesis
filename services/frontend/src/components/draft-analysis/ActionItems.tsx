import { useMemo, useState } from 'react'
import {
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
  InformationCircleIcon,
  CheckIcon,
  CheckCircleIcon,
  ChevronDownIcon,
  SparklesIcon,
  EyeIcon
} from '@heroicons/react/24/outline'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  section_location: string
  importance_score: number
  requires_citation: boolean
  existing_citations: string[]
  line_number?: number
  char_start?: number
  char_end?: number
}

interface Gap {
  id: string
  gap_type: string
  description: string
  priority: string
  line_number?: number
}

interface Feedback {
  id: string
  feedback_type: string
  severity: string
  feedback_text: string
  suggestions: string[]
  section_reference?: string
  line_number?: number
}

interface ActionItem {
  id: string
  type: 'claim' | 'gap' | 'feedback'
  severity: 'critical' | 'major' | 'minor'
  title: string
  description: string
  suggestion?: string
  section?: string
  line_number?: number
  originalData: Claim | Gap | Feedback
}

interface ActionItemsProps {
  claims: Claim[]
  gaps: Gap[]
  feedback: Feedback[]
  addressedItems: string[]
  onToggleAddressed: (itemId: string) => void
  onViewInDocument: (item: ActionItem) => void
  onViewSuggestions?: (claim: Claim) => void | Promise<void>
}

export default function ActionItems({
  claims,
  gaps,
  feedback,
  addressedItems,
  onToggleAddressed,
  onViewInDocument,
  onViewSuggestions
}: ActionItemsProps) {
  const [showAddressed, setShowAddressed] = useState(false)
  const [expandedSeverity, setExpandedSeverity] = useState<Record<string, boolean>>({
    critical: true,
    major: true,
    minor: false
  })

  // Aggregate all action items
  const actionItems = useMemo(() => {
    const items: ActionItem[] = []

    // Claims needing citation
    claims
      .filter(c => c.requires_citation && (!c.existing_citations || c.existing_citations.length === 0))
      .forEach(claim => {
        items.push({
          id: `claim-${claim.id}`,
          type: 'claim',
          severity: 'major',
          title: 'Missing citation for claim',
          description: claim.claim_text.substring(0, 150) + (claim.claim_text.length > 150 ? '...' : ''),
          section: claim.section_location,
          line_number: claim.line_number,
          originalData: claim
        })
      })

    // Coverage gaps
    gaps.forEach(gap => {
      const severity: 'critical' | 'major' | 'minor' =
        gap.priority === 'critical' || gap.priority === 'high' ? 'critical' :
        gap.priority === 'medium' ? 'major' : 'minor'

      items.push({
        id: `gap-${gap.id}`,
        type: 'gap',
        severity,
        title: `Coverage gap: ${gap.gap_type}`,
        description: gap.description.substring(0, 150) + (gap.description.length > 150 ? '...' : ''),
        line_number: gap.line_number,
        originalData: gap
      })
    })

    // Feedback items
    feedback
      .filter(f => f.severity === 'critical' || f.severity === 'major')
      .forEach(fb => {
        items.push({
          id: `feedback-${fb.id}`,
          type: 'feedback',
          severity: fb.severity as 'critical' | 'major',
          title: fb.feedback_type.replace(/_/g, ' '),
          description: fb.feedback_text.substring(0, 150) + (fb.feedback_text.length > 150 ? '...' : ''),
          suggestion: fb.suggestions?.[0],
          section: fb.section_reference,
          line_number: fb.line_number,
          originalData: fb
        })
      })

    // Sort by severity
    const severityOrder = { critical: 0, major: 1, minor: 2 }
    return items.sort((a, b) => severityOrder[a.severity] - severityOrder[b.severity])
  }, [claims, gaps, feedback])

  // Separate addressed and pending items
  const pendingItems = actionItems.filter(item => !addressedItems.includes(item.id))
  const addressedItemsList = actionItems.filter(item => addressedItems.includes(item.id))

  // Group by severity
  const groupedItems = useMemo(() => {
    const grouped: Record<string, ActionItem[]> = {
      critical: [],
      major: [],
      minor: []
    }

    pendingItems.forEach(item => {
      grouped[item.severity].push(item)
    })

    return grouped
  }, [pendingItems])

  const getSeverityConfig = (severity: string) => {
    switch (severity) {
      case 'critical':
        return {
          bgColor: 'bg-red-900/20',
          borderColor: 'border-red-700/50',
          textColor: 'text-red-400',
          icon: <ExclamationCircleIcon className="h-5 w-5" />,
          label: 'Critical'
        }
      case 'major':
        return {
          bgColor: 'bg-amber-900/20',
          borderColor: 'border-amber-700/50',
          textColor: 'text-amber-400',
          icon: <ExclamationTriangleIcon className="h-5 w-5" />,
          label: 'Major'
        }
      default:
        return {
          bgColor: 'bg-blue-900/20',
          borderColor: 'border-blue-700/50',
          textColor: 'text-blue-400',
          icon: <InformationCircleIcon className="h-5 w-5" />,
          label: 'Minor'
        }
    }
  }

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'claim':
        return <SparklesIcon className="h-4 w-4 text-purple-400" />
      case 'gap':
        return <ExclamationTriangleIcon className="h-4 w-4 text-orange-400" />
      default:
        return <InformationCircleIcon className="h-4 w-4 text-blue-400" />
    }
  }

  return (
    <div className="bg-surface rounded-lg border border-border-base overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-border-base bg-surface-hover/50">
        <div className="flex items-center gap-2">
          <h3 className="font-medium text-text-primary">Priority Actions</h3>
          <span className="px-2 py-0.5 text-xs font-mono bg-surface rounded-full text-text-secondary">
            {pendingItems.length} remaining
          </span>
        </div>
        <button
          onClick={() => setShowAddressed(!showAddressed)}
          className="text-xs text-text-muted hover:text-text-secondary transition-colors"
        >
          {showAddressed ? 'Hide' : 'Show'} addressed ({addressedItemsList.length})
        </button>
      </div>

      {/* Action Items List */}
      <div className="divide-y divide-border-base">
        {['critical', 'major', 'minor'].map(severity => {
          const items = groupedItems[severity]
          if (items.length === 0) return null

          const config = getSeverityConfig(severity)
          const isExpanded = expandedSeverity[severity]

          return (
            <div key={severity}>
              {/* Severity Section Header */}
              <button
                onClick={() => setExpandedSeverity(prev => ({ ...prev, [severity]: !prev[severity] }))}
                className={`w-full flex items-center justify-between px-4 py-2 ${config.bgColor} hover:opacity-90 transition-opacity`}
              >
                <div className="flex items-center gap-2">
                  <span className={config.textColor}>{config.icon}</span>
                  <span className={`text-sm font-medium ${config.textColor}`}>
                    {config.label} ({items.length})
                  </span>
                </div>
                <ChevronDownIcon
                  className={`h-4 w-4 ${config.textColor} transition-transform ${isExpanded ? 'rotate-180' : ''}`}
                />
              </button>

              {/* Items in this severity */}
              {isExpanded && (
                <div className="divide-y divide-border-subtle">
                  {items.map(item => (
                    <div
                      key={item.id}
                      className="px-4 py-3 hover:bg-surface-hover/50 transition-colors"
                    >
                      <div className="flex items-start gap-3">
                        {/* Checkbox */}
                        <button
                          onClick={() => onToggleAddressed(item.id)}
                          className={`mt-0.5 flex-shrink-0 h-5 w-5 rounded border-2 transition-colors ${
                            addressedItems.includes(item.id)
                              ? 'bg-emerald-600 border-emerald-600'
                              : 'border-border-subtle hover:border-text-muted'
                          }`}
                        >
                          {addressedItems.includes(item.id) && (
                            <CheckIcon className="h-4 w-4 text-white" />
                          )}
                        </button>

                        {/* Content */}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            {getTypeIcon(item.type)}
                            <span className="text-sm font-medium text-text-primary capitalize">
                              {item.title}
                            </span>
                            {item.section && (
                              <span className="text-xs text-text-muted font-mono">
                                [{item.section}]
                              </span>
                            )}
                          </div>
                          <p className="text-sm text-text-secondary mb-2">{item.description}</p>

                          {item.suggestion && (
                            <p className="text-xs text-text-muted italic mb-2">
                              Suggestion: {item.suggestion}
                            </p>
                          )}

                          {/* Action buttons */}
                          <div className="flex items-center gap-2">
                            {item.line_number && (
                              <button
                                onClick={() => onViewInDocument(item)}
                                className="flex items-center gap-1 px-2 py-1 text-xs text-text-muted hover:text-text-primary bg-surface hover:bg-surface-hover rounded transition-colors"
                              >
                                <EyeIcon className="h-3 w-3" />
                                View in Document
                              </button>
                            )}

                            {item.type === 'claim' && onViewSuggestions && (
                              <button
                                onClick={() => onViewSuggestions(item.originalData as Claim)}
                                className="flex items-center gap-1 px-2 py-1 text-xs text-purple-400 hover:text-purple-300 bg-purple-900/20 hover:bg-purple-900/30 rounded transition-colors"
                              >
                                <SparklesIcon className="h-3 w-3" />
                                Find Citations
                              </button>
                            )}

                            <button
                              onClick={() => onToggleAddressed(item.id)}
                              className="flex items-center gap-1 px-2 py-1 text-xs text-text-muted hover:text-emerald-400 bg-surface hover:bg-emerald-900/20 rounded transition-colors"
                            >
                              <CheckIcon className="h-3 w-3" />
                              Mark Addressed
                            </button>
                          </div>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          )
        })}

        {/* Addressed Items */}
        {showAddressed && addressedItemsList.length > 0 && (
          <div>
            <div className="px-4 py-2 bg-emerald-900/10">
              <span className="text-sm font-medium text-emerald-400">
                Addressed ({addressedItemsList.length})
              </span>
            </div>
            <div className="divide-y divide-border-subtle">
              {addressedItemsList.map(item => (
                <div
                  key={item.id}
                  className="px-4 py-3 opacity-60 hover:opacity-80 transition-opacity"
                >
                  <div className="flex items-start gap-3">
                    <button
                      onClick={() => onToggleAddressed(item.id)}
                      className="mt-0.5 flex-shrink-0 h-5 w-5 rounded border-2 bg-emerald-600 border-emerald-600"
                    >
                      <CheckIcon className="h-4 w-4 text-white" />
                    </button>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        {getTypeIcon(item.type)}
                        <span className="text-sm text-text-secondary line-through">
                          {item.title}
                        </span>
                      </div>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Empty State */}
        {pendingItems.length === 0 && (
          <div className="px-4 py-8 text-center">
            <CheckCircleIcon className="h-12 w-12 text-emerald-500 mx-auto mb-3" />
            <h4 className="text-lg font-medium text-text-primary mb-1">All caught up!</h4>
            <p className="text-sm text-text-secondary">
              You've addressed all the priority action items.
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

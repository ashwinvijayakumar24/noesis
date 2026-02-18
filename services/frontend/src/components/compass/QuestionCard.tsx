type QuestionCategory = 'conflict' | 'gap' | 'pattern' | 'positioning' | 'methodology' | 'temporal' | 'cross_domain' | 'evidence'

interface QuestionCardProps {
  /** The question text */
  question: string
  /** Question category */
  category: QuestionCategory
  /** Optional requirements/suggested directions */
  requirements?: string[]
  /** Additional class names */
  className?: string
}

export default function QuestionCard({
  question,
  category,
  requirements,
  className = ''
}: QuestionCardProps) {
  // Category display name and color
  const getCategoryInfo = () => {
    const info: Record<QuestionCategory, { label: string; className: string }> = {
      conflict: {
        label: 'Conflict Resolution',
        className: 'bg-[#991b1b] text-white border-[#991b1b]'
      },
      gap: {
        label: 'Gap Bridging',
        className: 'bg-[#92400e] text-white border-[#92400e]'
      },
      pattern: {
        label: 'Pattern Analysis',
        className: 'bg-[#1e40af] text-white border-[#1e40af]'
      },
      positioning: {
        label: 'Research Positioning',
        className: 'bg-[#166534] text-white border-[#166534]'
      },
      methodology: {
        label: 'Methodological Synthesis',
        className: 'bg-[#6b21a8] text-white border-[#6b21a8]'
      },
      temporal: {
        label: 'Temporal Evolution',
        className: 'bg-[#9a3412] text-white border-[#9a3412]'
      },
      cross_domain: {
        label: 'Cross-Domain',
        className: 'bg-[#155e75] text-white border-[#155e75]'
      },
      evidence: {
        label: 'Evidence Weighting',
        className: 'bg-[#9f1239] text-white border-[#9f1239]'
      }
    }
    return info[category] || { label: category, className: 'bg-[#334155] text-white border-[#334155]' }
  }

  const categoryInfo = getCategoryInfo()

  return (
    <div className={`rounded-lg border border-border-subtle bg-surface/50 hover:border-border-base transition-all ${className}`}>
      <div className="p-4 space-y-3">
        {/* Category badge */}
        <div className={`inline-flex px-2 py-1 rounded text-xs font-mono border ${categoryInfo.className}`}>
          {categoryInfo.label}
        </div>

        {/* Question text */}
        <p className="text-base text-text-primary leading-relaxed">
          {question}
        </p>

        {/* Suggested directions */}
        {requirements && requirements.length > 0 && (
          <div className="pt-2 border-t border-border-subtle">
            <div className="text-xs font-semibold text-text-muted mb-2">Suggested Directions:</div>
            <ul className="space-y-1.5">
              {requirements.map((req, i) => (
                <li key={i} className="text-sm text-text-secondary flex items-start gap-2">
                  <span className="text-accent-primary mt-0.5">•</span>
                  <span>{req}</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  )
}

import {
  ExclamationTriangleIcon,
  ShieldCheckIcon,
  ExclamationCircleIcon,
  CheckCircleIcon
} from '@heroicons/react/24/outline'

interface OverviewScoreCardProps {
  readinessScore: number | null
  verdict: string | null
  counts: {
    total_claims: number
    claims_needing_citation: number
    total_gaps: number
    critical_gaps: number
    total_feedback: number
    critical_feedback: number
  }
}

const VERDICT_CONFIG: Record<string, {
  label: string
  color: string
  bgColor: string
  borderColor: string
  icon: typeof ExclamationTriangleIcon
}> = {
  'major_revisions': {
    label: 'Major Revisions',
    color: 'text-error',
    bgColor: 'bg-error/10',
    borderColor: 'border-error/20',
    icon: ExclamationCircleIcon,
  },
  'needs_work': {
    label: 'Needs Work',
    color: 'text-warning',
    bgColor: 'bg-warning/10',
    borderColor: 'border-warning/20',
    icon: ExclamationTriangleIcon,
  },
  'minor_revisions': {
    label: 'Minor Revisions',
    color: 'text-info',
    bgColor: 'bg-info/10',
    borderColor: 'border-info/20',
    icon: ShieldCheckIcon,
  },
  'strong_submission': {
    label: 'Strong Submission',
    color: 'text-success',
    bgColor: 'bg-success/10',
    borderColor: 'border-success/20',
    icon: CheckCircleIcon,
  },
}

function getVerdictFromScore(score: number | null, verdict: string | null) {
  if (verdict && VERDICT_CONFIG[verdict]) return verdict
  if (score === null) return 'needs_work'
  if (score >= 80) return 'strong_submission'
  if (score >= 60) return 'minor_revisions'
  if (score >= 40) return 'needs_work'
  return 'major_revisions'
}

export default function OverviewScoreCard({ readinessScore, verdict, counts }: OverviewScoreCardProps) {
  const resolvedVerdict = getVerdictFromScore(readinessScore, verdict)
  const config = VERDICT_CONFIG[resolvedVerdict] || VERDICT_CONFIG['needs_work']
  const VerdictIcon = config.icon
  const score = readinessScore ?? 0

  return (
    <div className="bg-bg-surface border border-border-default rounded-xl p-5">
      {/* Score + Verdict */}
      <div className="flex items-center gap-4 mb-4">
        <div className={`flex items-center justify-center w-16 h-16 rounded-xl ${config.bgColor} border ${config.borderColor}`}>
          <span className={`text-2xl font-semibold ${config.color}`}>{score}</span>
        </div>
        <div className="flex-1">
          <div className="flex items-center gap-2 mb-1">
            <VerdictIcon className={`w-4 h-4 ${config.color}`} />
            <span className={`text-sm font-semibold ${config.color}`}>{config.label}</span>
          </div>
          <p className="text-xs text-text-muted">
            Readiness score out of 100
          </p>
        </div>
      </div>

      {/* Three metric boxes */}
      <div className="grid grid-cols-3 gap-2">
        <div className="bg-bg-void rounded-lg px-3 py-2.5">
          <p className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-1.5">Claims</p>
          <p className="text-xl font-semibold text-text-primary leading-none mb-1">
            {counts.total_claims}
          </p>
          <p className={`text-xs font-medium ${counts.claims_needing_citation > 0 ? 'text-warning' : 'text-success'}`}>
            {counts.claims_needing_citation > 0
              ? `${counts.claims_needing_citation} need citation`
              : 'all supported'}
          </p>
        </div>

        <div className="bg-bg-void rounded-lg px-3 py-2.5">
          <p className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-1.5">Gaps</p>
          <p className="text-xl font-semibold text-text-primary leading-none mb-1">
            {counts.total_gaps}
          </p>
          <p className={`text-xs font-medium ${counts.critical_gaps > 0 ? 'text-error' : 'text-success'}`}>
            {counts.critical_gaps > 0
              ? `${counts.critical_gaps} critical`
              : 'none critical'}
          </p>
        </div>

        <div className="bg-bg-void rounded-lg px-3 py-2.5">
          <p className="text-[10px] font-semibold text-text-tertiary uppercase tracking-wider mb-1.5">Feedback</p>
          <p className="text-xl font-semibold text-text-primary leading-none mb-1">
            {counts.total_feedback}
          </p>
          <p className={`text-xs font-medium ${counts.critical_feedback > 0 ? 'text-error' : 'text-success'}`}>
            {counts.critical_feedback > 0
              ? `${counts.critical_feedback} critical`
              : 'no critical issues'}
          </p>
        </div>
      </div>
    </div>
  )
}

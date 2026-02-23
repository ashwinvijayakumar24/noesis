import { DocumentTextIcon, ArrowPathIcon } from '@heroicons/react/24/outline'
import { Badge } from '../ui/Badge'
import { Button } from '../ui/Button'

interface Claim {
  id: string
  claim_text: string
  claim_type: string
  section_location: string
  importance_score: number
  requires_citation: boolean
  existing_citations: string[]
}

interface ClaimsPanelProps {
  claims: Claim[]
  onRegenerateAll: () => Promise<void>
  isRegenerating: boolean
  onClaimClick?: (claim: Claim) => void
}

export default function ClaimsPanel({
  claims,
  onRegenerateAll,
  isRegenerating,
  onClaimClick
}: ClaimsPanelProps) {
  if (claims.length === 0) {
    return (
      <div className="text-center py-12">
        <DocumentTextIcon className="h-12 w-12 text-text-muted mx-auto" />
        <p className="mt-4 text-text-secondary">No claims extracted yet</p>
        <p className="mt-1 text-sm text-text-muted">
          Make sure your draft has been analyzed first
        </p>
      </div>
    )
  }

  // Count claims that need citations
  const claimsNeedingCitations = claims.filter(c => c.requires_citation === true).length

  return (
    <div className="space-y-4">
      {/* Header with Regenerate All button */}
      <div className="flex items-center justify-between pb-3 border-b border-border-default">
        <div className="flex items-center gap-3">
          <span className="text-sm font-medium text-text-secondary">
            {claims.length} claims extracted
          </span>
          {claimsNeedingCitations > 0 && (
            <Badge variant="error">
              {claimsNeedingCitations} missing citations
            </Badge>
          )}
        </div>
        <Button
          variant="primary"
          size="sm"
          onClick={onRegenerateAll}
          disabled={isRegenerating}
          className="shadow-lg"
        >
          <ArrowPathIcon className={`h-4 w-4 ${isRegenerating ? 'animate-spin' : ''}`} />
          {isRegenerating ? 'Regenerating...' : 'Regenerate All Citations'}
        </Button>
      </div>

      {/* Claims List */}
      <div className="space-y-3">
        {claims
          .sort((a, b) => b.importance_score - a.importance_score)
          .map((claim) => {
            const hasExistingCitations = Array.isArray(claim.existing_citations) && claim.existing_citations.length > 0
            const requiresCitation = claim.requires_citation === true

            return (
              <div
                key={claim.id}
                onClick={() => onClaimClick?.(claim)}
                className={`border border-border-default rounded-lg p-3 bg-surface-hover transition-all ${
                  onClaimClick ? 'cursor-pointer hover:border-border-default hover:shadow-lg hover:shadow-red-600/20' : ''
                }`}
              >
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xs font-medium text-text-tertiary font-mono uppercase">
                    {claim.claim_type}
                  </span>
                  <span className="text-xs text-text-muted font-mono">
                    {claim.section_location}
                  </span>
                  <div className="flex-1" />
                  <span className="text-xs text-text-muted font-mono">
                    Importance: {(claim.importance_score * 100).toFixed(0)}%
                  </span>
                </div>
                <p className="text-sm text-text-secondary mb-2">{claim.claim_text}</p>

                {/* Citation Status Badges (no buttons) */}
                {hasExistingCitations ? (
                  <div className="flex items-center gap-2 text-xs text-text-muted mt-2">
                    <span className="font-mono">Citations:</span>
                    <span className="font-mono">{claim.existing_citations.join(', ')}</span>
                  </div>
                ) : requiresCitation ? (
                  <Badge variant="error" className="mt-2">
                    MISSING CITATIONS
                  </Badge>
                ) : (
                  <Badge variant="neutral" className="mt-2">
                    ORIGINAL CONTRIBUTION
                  </Badge>
                )}
              </div>
            )
          })}
      </div>
    </div>
  )
}

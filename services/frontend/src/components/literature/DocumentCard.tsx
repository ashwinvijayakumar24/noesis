import { useNavigate } from 'react-router-dom'
import { DocumentTextIcon, TrashIcon } from '@heroicons/react/24/outline'
import { Badge, type BadgeVariant } from '../ui/Badge'

interface DocumentCardProps {
  document: {
    id: string
    title: string
    status: string
    created_at: string
    file_type?: string
  }
  projectId: string
  onDelete: (id: string, title: string) => void
}

// Helper function to get status badge variant and label
const getStatusBadge = (status: string): { variant: BadgeVariant; label: string; animate: boolean } => {
  const statusLower = status.toLowerCase()
  switch (statusLower) {
    case 'processing':
    case 'uploaded':
      return { variant: 'warning', label: 'Processing', animate: true }
    case 'analyzing':
      return { variant: 'warning', label: 'Analyzing', animate: true }
    case 'failed':
      return { variant: 'error', label: 'Failed', animate: false }
    case 'analyzed':
      return { variant: 'success', label: 'Processed', animate: false }
    default:
      return { variant: 'neutral', label: status.charAt(0).toUpperCase() + status.slice(1).toLowerCase(), animate: false }
  }
}

// Helper function to get icon color based on status
const getIconColor = (status: string): string => {
  const statusLower = status.toLowerCase()
  switch (statusLower) {
    case 'failed':
      return 'text-error'
    case 'processing':
    case 'uploaded':
    case 'analyzing':
      return 'text-warning'
    case 'ready':
      return 'text-text-muted'
    case 'analyzed':
      return 'text-success'
    default:
      return 'text-text-tertiary'
  }
}

// Helper function to get border color based on status
const getBorderColor = (status: string): string => {
  const statusLower = status.toLowerCase()
  switch (statusLower) {
    case 'failed':
      return 'border-error/60 group-hover:border-error'
    case 'processing':
    case 'uploaded':
    case 'analyzing':
      return 'border-warning/60 group-hover:border-warning'
    case 'ready':
      return 'border-border-default'
    case 'analyzed':
      return 'border-success/60 group-hover:border-success'
    default:
      return 'border-border-default'
  }
}

export default function DocumentCard({ document, projectId, onDelete }: DocumentCardProps) {
  const navigate = useNavigate()
  const statusBadge = getStatusBadge(document.status)
  const iconColor = getIconColor(document.status)
  const borderColor = getBorderColor(document.status)
  const isAnalyzed = document.status.toLowerCase() === 'analyzed'

  const handleClick = () => {
    if (isAnalyzed) {
      navigate(`/projects/${projectId}/documents/${document.id}`)
    }
  }

  const handleDelete = (e: React.MouseEvent) => {
    e.stopPropagation()
    onDelete(document.id, document.title)
  }

  return (
    <div
      onClick={handleClick}
      className={`group bg-bg-surface rounded-lg border-2 border-border-default p-6 transition-all duration-150 ${
        isAnalyzed
          ? 'hover:border-accent-primary/30 hover:-translate-y-1 hover:shadow-card-lift cursor-pointer'
          : 'cursor-default'
      }`}
    >
      <div className="flex items-start gap-4">
        {/* Document Icon */}
        <div className="shrink-0">
          <div className={`h-16 w-16 bg-bg-hover rounded-xl flex items-center justify-center border-2 transition-all duration-150 ${borderColor}`}>
            <DocumentTextIcon className={`h-9 w-9 transition-all duration-150 ${iconColor} ${isAnalyzed ? 'group-hover:scale-110' : ''}`} />
          </div>
        </div>

        {/* Document Info */}
        <div className="flex-1 min-w-0">
          <div className="flex items-start justify-between gap-3 mb-3">
            <div className="flex-1 min-w-0">
              <h4 className="font-sans font-semibold text-lg text-text-primary mb-2 line-clamp-2 group-hover:text-accent-primary transition-colors duration-150">
                {document.title}
              </h4>
              <div className="flex items-center gap-3 text-sm font-mono text-text-muted">
                <span className="flex items-center gap-1.5">
                  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M8 7V3m8 4V3m-9 8h10M5 21h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v12a2 2 0 002 2z" />
                  </svg>
                  {new Date(document.created_at).toLocaleDateString('en-US', {
                    year: 'numeric',
                    month: 'short',
                    day: 'numeric',
                  })}
                </span>
              </div>
            </div>

            {/* Status Badge & Delete Button */}
            <div className="flex items-center gap-2">
              {/* Status Badge */}
              <Badge variant={statusBadge.variant}>
                {statusBadge.animate && (
                  <span className="relative flex h-2 w-2 mr-1">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-warning opacity-75"></span>
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-warning"></span>
                  </span>
                )}
                {statusBadge.label}
              </Badge>

              {/* Delete Button */}
              <button
                onClick={handleDelete}
                className="p-2 text-text-muted hover:text-error hover:bg-error/10 rounded-lg transition-all duration-200 opacity-0 group-hover:opacity-100"
                title="Delete document"
              >
                <TrashIcon className="h-5 w-5" />
              </button>
            </div>
          </div>

          {/* Processing message for non-analyzed documents */}
          {!isAnalyzed && document.status.toLowerCase() !== 'failed' && (
            <div className="mt-3 pt-3 border-t border-border-default">
              <p className="text-sm text-text-secondary">
                {document.status.toLowerCase() === 'processing' || document.status.toLowerCase() === 'uploaded'
                  ? 'Document is being processed...'
                  : 'Analyzing document structure and content...'}
              </p>
            </div>
          )}

          {/* Error message for failed documents */}
          {document.status.toLowerCase() === 'failed' && (
            <div className="mt-3 pt-3 border-t border-error/30">
              <p className="text-sm text-error">
                Failed to process document. Please try uploading again.
              </p>
            </div>
          )}

          {/* Click hint for analyzed documents */}
          {isAnalyzed && (
            <div className="mt-3 pt-3 border-t border-border-default opacity-0 group-hover:opacity-100 transition-opacity duration-150">
              <p className="text-sm text-accent-primary font-medium">
                Click to view analysis →
              </p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

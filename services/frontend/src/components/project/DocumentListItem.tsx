import { Badge, type BadgeVariant } from '../ui/Badge'

interface Document {
  id: string
  title: string
  file_url: string
  status: string
  created_at: string
}

interface DocumentListItemProps {
  document: Document
  onClick: () => void
}

// Helper function to get status badge variant and label
const getStatusBadge = (status: string): { variant: BadgeVariant; label: string; animate: boolean } => {
  const statusLower = status.toLowerCase()
  switch (statusLower) {
    case 'processing':
    case 'uploaded':
    case 'ready':  // Backend intermediate state - treat as processing
      return { variant: 'warning', label: 'Processing', animate: true }
    case 'analyzing':
      return { variant: 'warning', label: 'Analyzing', animate: true }
    case 'failed':
      return { variant: 'error', label: 'Failed', animate: false }
    case 'analyzed':
      return { variant: 'success', label: 'Processed', animate: false }
    default:
      return { variant: 'success', label: 'Processed', animate: false }
  }
}

// Helper function to get status indicator color
const getStatusColor = (status: string): string => {
  const statusLower = status.toLowerCase()
  switch (statusLower) {
    case 'processing':
    case 'uploaded':
    case 'ready':  // Backend intermediate state - treat as processing
      return 'bg-amber-400 animate-pulse'
    case 'analyzing':
      return 'bg-amber-400 animate-pulse'
    case 'failed':
      return 'bg-red-500'
    case 'analyzed':
      return 'bg-green-400'
    default:
      return 'bg-blue-400'
  }
}

export default function DocumentListItem({ document, onClick }: DocumentListItemProps) {
  const statusBadge = getStatusBadge(document.status)
  const statusColor = getStatusColor(document.status)

  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-2 rounded-lg hover:bg-surface-hover transition-colors group"
    >
      <div className="flex items-start gap-2">
        {/* Status Indicator */}
        <div className={`w-2 h-2 rounded-full mt-1.5 flex-shrink-0 ${statusColor}`} />

        {/* Document Info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm text-text-primary font-medium truncate group-hover:text-accent-primary transition-colors">
            {document.title}
          </p>
          <div className="flex items-center gap-2 mt-0.5">
            <Badge
              variant={statusBadge.variant}
              className="text-xs"
            >
              {statusBadge.label}
            </Badge>
          </div>
        </div>
      </div>
    </button>
  )
}

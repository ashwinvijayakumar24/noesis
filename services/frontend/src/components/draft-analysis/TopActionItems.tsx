import { ExclamationCircleIcon } from '@heroicons/react/24/outline'

interface TopActionItemsProps {
  actions: string[]
}

export default function TopActionItems({ actions }: TopActionItemsProps) {
  if (!actions || actions.length === 0) return null

  const top3 = actions.slice(0, 3)

  return (
    <div className="bg-bg-surface border border-border-default rounded-xl p-4 mb-3">
      <div className="flex items-center gap-2 mb-3">
        <ExclamationCircleIcon className="h-4 w-4 text-accent-primary shrink-0" />
        <h3 className="text-sm font-semibold text-text-primary">Top Action Items</h3>
      </div>
      <ol className="space-y-2.5">
        {top3.map((action, i) => (
          <li key={i} className="flex items-start gap-3">
            <span className="flex-shrink-0 w-4 h-4 text-xs font-semibold text-accent-primary mt-0.5">
              {i + 1}.
            </span>
            <span className="text-sm text-text-secondary leading-snug">{action}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

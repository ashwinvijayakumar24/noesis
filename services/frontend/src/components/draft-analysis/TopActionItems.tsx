import { ExclamationCircleIcon } from '@heroicons/react/24/outline'

interface TopActionItemsProps {
  actions: string[]
}

export default function TopActionItems({ actions }: TopActionItemsProps) {
  if (!actions || actions.length === 0) return null

  const top3 = actions.slice(0, 3)

  return (
    <div className="bg-accent-primary/8 border border-accent-primary/30 rounded-xl p-4 mb-3">
      <div className="flex items-center gap-2 mb-3">
        <ExclamationCircleIcon className="h-4 w-4 text-accent-primary shrink-0" />
        <h3 className="text-sm font-semibold text-accent-primary">Top Action Items</h3>
      </div>
      <ol className="space-y-2">
        {top3.map((action, i) => (
          <li key={i} className="flex items-start gap-2.5">
            <span className="flex-shrink-0 w-5 h-5 rounded-full bg-accent-primary/20 text-accent-primary text-xs font-semibold flex items-center justify-center mt-0.5">
              {i + 1}
            </span>
            <span className="text-sm text-text-secondary leading-snug">{action}</span>
          </li>
        ))}
      </ol>
    </div>
  )
}

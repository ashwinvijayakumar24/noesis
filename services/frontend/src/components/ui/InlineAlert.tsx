import { ExclamationTriangleIcon, InformationCircleIcon } from '@heroicons/react/24/outline'

type Tone = 'error' | 'info'

export default function InlineAlert({
  title,
  message,
  details = [],
  tone = 'error',
}: {
  title: string
  message: string
  details?: string[]
  tone?: Tone
}) {
  const palette = tone === 'error'
    ? {
        icon: ExclamationTriangleIcon,
        wrapper: 'border-amber-500/30 bg-amber-500/10',
        title: 'text-amber-200',
        text: 'text-amber-100/90',
      }
    : {
        icon: InformationCircleIcon,
        wrapper: 'border-border-default bg-bg-elevated',
        title: 'text-text-primary',
        text: 'text-text-secondary',
      }

  const Icon = palette.icon

  return (
    <div className={`rounded-xl border p-4 ${palette.wrapper}`}>
      <div className="flex gap-3">
        <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${palette.title}`} />
        <div className="min-w-0">
          <p className={`text-sm font-semibold ${palette.title}`}>{title}</p>
          <p className={`mt-1 text-sm ${palette.text}`}>{message}</p>
          {details.length > 0 && (
            <div className={`mt-2 space-y-1 text-xs ${palette.text}`}>
              {details.map((detail) => (
                <p key={detail}>{detail}</p>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

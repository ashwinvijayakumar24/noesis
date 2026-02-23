import { type ReactNode } from 'react'
import { ChevronDownIcon } from '@heroicons/react/24/outline'

interface SectionHeaderProps {
  title: string
  icon: ReactNode
  iconBg: string
  iconColor: string
  iconBorderColor?: string
  expanded: boolean
  onToggle: () => void
  badge?: number
  children: ReactNode
}

export default function SectionHeader({
  title,
  icon,
  iconBg,
  iconColor,
  iconBorderColor = 'border-transparent',
  expanded,
  onToggle,
  badge,
  children
}: SectionHeaderProps) {
  return (
    <div className="bg-surface rounded-lg border border-border-default overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between p-4 hover:bg-surface-hover transition-colors text-left"
      >
        <div className="flex items-center gap-3">
          <div className={`p-2 ${iconBg} rounded-lg border-2 ${iconBorderColor}`}>
            <span className={iconColor}>{icon}</span>
          </div>
          <h3 className="font-sans font-semibold text-text-primary">{title}</h3>
          {badge !== undefined && badge > 0 && (
            <span className="px-2 py-0.5 text-xs font-mono bg-surface-hover rounded-full text-text-secondary">
              {badge}
            </span>
          )}
        </div>
        <ChevronDownIcon
          className={`h-5 w-5 text-text-muted transition-transform duration-200 ${
            expanded ? 'rotate-180' : ''
          }`}
        />
      </button>
      {expanded && (
        <div className="px-4 pb-4 border-t border-border-default pt-4">
          {children}
        </div>
      )}
    </div>
  )
}

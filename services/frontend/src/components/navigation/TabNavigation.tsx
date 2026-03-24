import type { ReactNode } from 'react'

export interface Tab {
  id: string
  label: string
  icon?: ReactNode
  badgeCount?: number
  badgeVariant?: 'neutral' | 'primary' | 'warning' | 'success'
  isProcessing?: boolean
  colorScheme?: 'crimson' | 'amber' | 'emerald' | 'violet'
}

export interface TabNavigationProps {
  tabs: Tab[]
  activeTab: string
  onTabChange: (tabId: string) => void
  className?: string
}

const colorSchemes: Record<NonNullable<Tab['colorScheme']>, { active: string; hover: string; badge: string }> = {
  crimson: {
    active: 'border-accent-primary text-accent-primary bg-accent-primary/8',
    hover: 'hover:text-accent-primary/80 hover:bg-accent-primary/5',
    badge: 'bg-accent-primary/15 text-accent-primary',
  },
  amber: {
    active: 'border-amber-400 text-amber-400 bg-amber-400/8',
    hover: 'hover:text-amber-400 hover:bg-amber-400/5',
    badge: 'bg-amber-400/15 text-amber-300',
  },
  emerald: {
    active: 'border-emerald-400 text-emerald-400 bg-emerald-400/8',
    hover: 'hover:text-emerald-400 hover:bg-emerald-400/5',
    badge: 'bg-emerald-400/15 text-emerald-300',
  },
  violet: {
    active: 'border-violet-400 text-violet-400 bg-violet-400/8',
    hover: 'hover:text-violet-400 hover:bg-violet-400/5',
    badge: 'bg-violet-400/15 text-violet-300',
  },
}

export function TabNavigation({ tabs, activeTab, onTabChange, className = '' }: TabNavigationProps) {
  return (
    <div className={`border-b border-border-default ${className}`}>
      <div className="flex w-full">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id
          const scheme = colorSchemes[tab.colorScheme ?? 'crimson']

          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`
                flex-1 relative flex items-center justify-center gap-2 px-3 py-3.5 min-h-[52px]
                text-sm font-semibold border-b-2 transition-all duration-150 whitespace-nowrap
                ${isActive
                  ? scheme.active
                  : `border-transparent text-text-secondary ${scheme.hover}`
                }
              `}
            >
              {/* Icon — inherits text color from button */}
              {tab.icon && (
                <span className={`transition-transform duration-150 ${isActive ? 'scale-105' : ''}`}>
                  {tab.icon}
                </span>
              )}

              {/* Label */}
              <span>{tab.label}</span>

              {/* Badge Count */}
              {tab.badgeCount !== undefined && tab.badgeCount > 0 && (
                <span
                  className={`
                    inline-flex items-center justify-center min-w-[18px] h-[18px] px-1
                    rounded-full text-[10px] font-semibold tabular-nums
                    ${isActive ? scheme.badge : 'bg-white/8 text-text-tertiary'}
                  `}
                >
                  {tab.badgeCount}
                </span>
              )}

              {/* Processing Indicator */}
              {tab.isProcessing && (
                <span className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium bg-warning-light text-warning border border-warning/30">
                  <svg className="h-2.5 w-2.5 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                  </svg>
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

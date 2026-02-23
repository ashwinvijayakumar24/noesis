import type { ReactNode } from 'react'

export interface Tab {
  id: string
  label: string
  icon?: ReactNode
  badgeCount?: number
  badgeVariant?: 'neutral' | 'primary' | 'warning' | 'success'
  isProcessing?: boolean
}

export interface TabNavigationProps {
  tabs: Tab[]
  activeTab: string
  onTabChange: (tabId: string) => void
  className?: string
}

export function TabNavigation({ tabs, activeTab, onTabChange, className = '' }: TabNavigationProps) {
  const getBadgeStyles = (variant: Tab['badgeVariant'] = 'neutral') => {
    const styles = {
      neutral: 'bg-bg-hover text-text-tertiary border-border-default',
      primary: 'bg-accent-light text-accent-primary border-accent-primary/30',
      warning: 'bg-warning-light text-warning border-warning/30',
      success: 'bg-success-light text-success border-success/30',
    }
    return styles[variant]
  }

  return (
    <div className={`border-b border-border-default ${className}`}>
      <div className="flex justify-start gap-2 overflow-x-auto scrollbar-hide">
        {tabs.map((tab) => {
          const isActive = activeTab === tab.id

          return (
            <button
              key={tab.id}
              onClick={() => onTabChange(tab.id)}
              className={`
                relative flex items-center gap-2 sm:gap-3 px-4 sm:px-6 py-3 sm:py-4 min-h-[48px] text-sm sm:text-base font-sans font-semibold
                border-b-2 transition-all duration-150 whitespace-nowrap tracking-normal
                ${
                  isActive
                    ? 'border-accent-primary text-accent-primary bg-accent-light/10'
                    : 'border-transparent text-text-secondary hover:text-text-primary hover:bg-bg-hover'
                }
              `}
            >
              {/* Icon */}
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
                    inline-flex items-center justify-center min-w-[20px] h-5 px-1.5
                    rounded-full text-xs font-mono font-semibold border
                    ${getBadgeStyles(tab.badgeVariant)}
                  `}
                >
                  {tab.badgeCount}
                </span>
              )}

              {/* Processing Indicator */}
              {tab.isProcessing && (
                <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium bg-warning-light text-warning border border-warning/30">
                  <svg className="h-3 w-3 animate-spin" fill="none" viewBox="0 0 24 24">
                    <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                    <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                  </svg>
                  <span className="hidden sm:inline">Updating</span>
                </span>
              )}
            </button>
          )
        })}
      </div>
    </div>
  )
}

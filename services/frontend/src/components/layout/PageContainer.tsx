import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { ArrowLeftIcon } from '@heroicons/react/24/outline'
import AuthenticatedHeader from '../navigation/AuthenticatedHeader'
import { TabNavigation } from '../navigation/TabNavigation'

interface Breadcrumb {
  label: string
  href?: string
}

interface TabItem {
  id: string
  label: string
  icon?: ReactNode
  badgeCount?: number
  badgeVariant?: 'neutral' | 'primary' | 'warning' | 'success'
  isProcessing?: boolean
}

interface PageContainerProps {
  children: ReactNode
  breadcrumbs?: Breadcrumb[]
  onSearchOpen?: () => void

  // Back button
  backLink?: string
  backLabel?: string

  // Page header
  title?: string
  description?: string
  headerActions?: ReactNode

  // Tabs (optional)
  tabs?: TabItem[]
  activeTab?: string
  onTabChange?: (tabId: string) => void

  // Layout customization
  maxWidth?: 'sm' | 'md' | 'lg' | 'xl' | '2xl' | '3xl' | '4xl' | '5xl' | '6xl' | '7xl' | 'full'
  spacing?: 'tight' | 'normal' | 'loose'
}

export default function PageContainer({
  children,
  breadcrumbs = [],
  onSearchOpen,
  backLink,
  backLabel = 'Back',
  title,
  description,
  headerActions,
  tabs,
  activeTab,
  onTabChange,
  maxWidth = '7xl',
  spacing = 'normal',
}: PageContainerProps) {
  const maxWidthClass = `max-w-${maxWidth}`
  const spacingClass = {
    tight: 'py-4',
    normal: 'py-8',
    loose: 'py-12',
  }[spacing]

  return (
    <div className="min-h-screen bg-bg-void">
      {/* Header */}
      <AuthenticatedHeader breadcrumbs={breadcrumbs} onSearchOpen={onSearchOpen} />

      {/* Main Content */}
      <main className={`${maxWidthClass} mx-auto px-4 sm:px-6 lg:px-8 ${spacingClass}`}>
        {/* Back Button */}
        {backLink && (
          <Link
            to={backLink}
            className="inline-flex items-center gap-2 text-text-secondary hover:text-accent-primary mb-6 transition-colors duration-150 group"
          >
            <ArrowLeftIcon className="h-5 w-5 transition-transform duration-150 group-hover:-translate-x-1" />
            <span className="font-medium tracking-normal">{backLabel}</span>
          </Link>
        )}

        {/* Page Header */}
        {title && (
          <div className="mb-6 sm:mb-8">
            <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4 mb-4">
              <div className="flex-1">
                <h1 className="text-3xl sm:text-4xl lg:text-5xl font-sans font-semibold text-text-primary mb-2 leading-heading-1 tracking-tight">
                  {title}
                </h1>
                {description && (
                  <p className="text-text-secondary text-base sm:text-lg leading-body-large tracking-normal max-w-3xl">
                    {description}
                  </p>
                )}
              </div>
              {headerActions && (
                <div className="flex items-center gap-3 flex-shrink-0">
                  {headerActions}
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab Navigation */}
        {tabs && activeTab && onTabChange && (
          <TabNavigation
            tabs={tabs}
            activeTab={activeTab}
            onTabChange={onTabChange}
            className="mb-8"
          />
        )}

        {/* Content */}
        <div className="space-y-8">
          {children}
        </div>
      </main>
    </div>
  )
}

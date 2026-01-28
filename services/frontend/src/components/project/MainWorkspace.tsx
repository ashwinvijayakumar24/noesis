import { useState, useEffect, Suspense, lazy } from 'react'
import { MapIcon, BeakerIcon, ChartBarIcon } from '@heroicons/react/24/outline'
import CompassGrid from './CompassGrid'

// Lazy load heavy components
const ResearchPlanningView = lazy(() => import('./ResearchPlanningView'))
const MethodologyAnalysisView = lazy(() => import('./MethodologyAnalysisView'))

type WorkspaceTab = 'compass' | 'research' | 'methodology'

interface MainWorkspaceProps {
  // Compass props
  insights: any | null
  projectId: string
  // Research Planning props
  // (will be added later)
  // Methodology props
  // (will be added later)
}

// Loading component for lazy-loaded tabs
function TabLoader() {
  return (
    <div className="flex items-center justify-center py-12">
      <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-solid border-accent-primary border-r-transparent"></div>
    </div>
  )
}

export default function MainWorkspace({ insights, projectId }: MainWorkspaceProps) {
  // Load last active tab from localStorage, default to 'compass'
  const [activeTab, setActiveTab] = useState<WorkspaceTab>(() => {
    const saved = localStorage.getItem('noesis_last_workspace_tab')
    return (saved as WorkspaceTab) || 'compass'
  })

  // Persist active tab to localStorage
  useEffect(() => {
    localStorage.setItem('noesis_last_workspace_tab', activeTab)
  }, [activeTab])

  return (
    <div className="h-full flex flex-col bg-bg-base">
      {/* Tab Navigation */}
      <div className="flex-shrink-0 border-b border-border-base bg-surface">
        <div className="flex gap-1 px-6">
          <button
            onClick={() => setActiveTab('compass')}
            className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'compass'
                ? 'border-accent-primary text-text-primary'
                : 'border-transparent text-text-tertiary hover:text-text-secondary'
            }`}
          >
            <div className="flex items-center gap-2">
              <MapIcon className={`h-5 w-5 ${activeTab === 'compass' ? 'text-amber-400' : ''}`} />
              <span>Literature Review Compass</span>
            </div>
          </button>

          <button
            onClick={() => setActiveTab('research')}
            className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'research'
                ? 'border-accent-primary text-text-primary'
                : 'border-transparent text-text-tertiary hover:text-text-secondary'
            }`}
          >
            <div className="flex items-center gap-2">
              <BeakerIcon className={`h-5 w-5 ${activeTab === 'research' ? 'text-purple-400' : ''}`} />
              <span>Research Planning</span>
            </div>
          </button>

          <button
            onClick={() => setActiveTab('methodology')}
            className={`px-6 py-4 text-sm font-medium border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'methodology'
                ? 'border-accent-primary text-text-primary'
                : 'border-transparent text-text-tertiary hover:text-text-secondary'
            }`}
          >
            <div className="flex items-center gap-2">
              <ChartBarIcon className={`h-5 w-5 ${activeTab === 'methodology' ? 'text-emerald-400' : ''}`} />
              <span>Methodology & Analysis</span>
            </div>
          </button>
        </div>
      </div>

      {/* Tab Content */}
      <div className="flex-1 overflow-y-auto p-6">
        {activeTab === 'compass' && (
          <CompassGrid insights={insights} projectId={projectId} />
        )}

        {activeTab === 'research' && (
          <Suspense fallback={<TabLoader />}>
            <ResearchPlanningView insights={insights} projectId={projectId} />
          </Suspense>
        )}

        {activeTab === 'methodology' && (
          <Suspense fallback={<TabLoader />}>
            <MethodologyAnalysisView insights={insights} projectId={projectId} />
          </Suspense>
        )}
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { MagnifyingGlassIcon, XMarkIcon, FunnelIcon } from '@heroicons/react/24/outline'
import { Badge } from '../ui/Badge'

export interface FilterState {
  severityFilter: 'all' | 'critical' | 'major' | 'minor' | 'suggestion'
  priorityFilter: 'all' | 'high' | 'medium' | 'low'
  claimTypeFilter: 'all' | string
  citationStatusFilter: 'all' | 'missing' | 'has_citations' | 'original'
  searchQuery: string
}

interface AnalysisFiltersProps {
  filters: FilterState
  onFiltersChange: (filters: FilterState) => void
  claimTypes: string[]
  activeTab?: string
}

export default function AnalysisFilters({
  filters,
  onFiltersChange,
  claimTypes,
  activeTab
}: AnalysisFiltersProps) {
  const [searchInput, setSearchInput] = useState(filters.searchQuery)

  // Debounce search query
  useEffect(() => {
    const timer = setTimeout(() => {
      if (searchInput !== filters.searchQuery) {
        onFiltersChange({ ...filters, searchQuery: searchInput })
      }
    }, 300)

    return () => clearTimeout(timer)
  }, [searchInput])

  const handleFilterChange = (key: keyof FilterState, value: string) => {
    onFiltersChange({ ...filters, [key]: value })
  }

  const clearFilters = () => {
    setSearchInput('')
    onFiltersChange({
      severityFilter: 'all',
      priorityFilter: 'all',
      claimTypeFilter: 'all',
      citationStatusFilter: 'all',
      searchQuery: ''
    })
  }

  const getActiveFilterCount = () => {
    let count = 0
    if (filters.severityFilter !== 'all') count++
    if (filters.priorityFilter !== 'all') count++
    if (filters.claimTypeFilter !== 'all') count++
    if (filters.citationStatusFilter !== 'all') count++
    if (filters.searchQuery) count++
    return count
  }

  const activeCount = getActiveFilterCount()

  return (
    <div className="border-b border-border-default bg-surface p-4 space-y-3">
      {/* Search Bar */}
      <div className="relative">
        <MagnifyingGlassIcon className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-text-muted" />
        <input
          type="text"
          value={searchInput}
          onChange={(e) => setSearchInput(e.target.value)}
          placeholder="Search feedback, claims, gaps..."
          className="w-full pl-10 pr-4 py-2 bg-bg-base border border-border-default rounded-lg text-sm text-text-primary placeholder-text-muted focus:outline-none focus:ring-2 focus:ring-accent-primary focus:border-transparent"
        />
        {searchInput && (
          <button
            onClick={() => setSearchInput('')}
            className="absolute right-3 top-1/2 -translate-y-1/2 text-text-muted hover:text-text-primary"
          >
            <XMarkIcon className="h-4 w-4" />
          </button>
        )}
      </div>

      {/* Filters Row */}
      <div className="flex items-center gap-3 flex-wrap">
        <div className="flex items-center gap-2">
          <FunnelIcon className="h-4 w-4 text-text-muted" />
          <span className="text-xs font-medium text-text-tertiary">Filters:</span>
        </div>

        {/* Severity Filter (for Feedback tab) */}
        {(activeTab === 'feedback' || activeTab === undefined) && (
          <select
            value={filters.severityFilter}
            onChange={(e) => handleFilterChange('severityFilter', e.target.value)}
            className="px-3 py-1.5 text-xs bg-bg-base border border-border-default rounded-md text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-primary font-mono"
          >
            <option value="all">All Severities</option>
            <option value="critical">Critical</option>
            <option value="major">Major</option>
            <option value="minor">Minor</option>
            <option value="suggestion">Suggestion</option>
          </select>
        )}

        {/* Priority Filter (for Gaps tab) */}
        {(activeTab === 'gaps' || activeTab === undefined) && (
          <select
            value={filters.priorityFilter}
            onChange={(e) => handleFilterChange('priorityFilter', e.target.value)}
            className="px-3 py-1.5 text-xs bg-bg-base border border-border-default rounded-md text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-primary font-mono"
          >
            <option value="all">All Priorities</option>
            <option value="high">High Priority</option>
            <option value="medium">Medium Priority</option>
            <option value="low">Low Priority</option>
          </select>
        )}

        {/* Claim Type Filter (for Claims tab) */}
        {(activeTab === 'claims' || activeTab === undefined) && claimTypes.length > 0 && (
          <select
            value={filters.claimTypeFilter}
            onChange={(e) => handleFilterChange('claimTypeFilter', e.target.value)}
            className="px-3 py-1.5 text-xs bg-bg-base border border-border-default rounded-md text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-primary font-mono"
          >
            <option value="all">All Claim Types</option>
            {claimTypes.map(type => (
              <option key={type} value={type}>{type}</option>
            ))}
          </select>
        )}

        {/* Citation Status Filter (for Claims tab) */}
        {(activeTab === 'claims' || activeTab === undefined) && (
          <select
            value={filters.citationStatusFilter}
            onChange={(e) => handleFilterChange('citationStatusFilter', e.target.value)}
            className="px-3 py-1.5 text-xs bg-bg-base border border-border-default rounded-md text-text-secondary focus:outline-none focus:ring-2 focus:ring-accent-primary font-mono"
          >
            <option value="all">All Citation Status</option>
            <option value="missing">Missing Citations</option>
            <option value="has_citations">Has Citations</option>
            <option value="original">Original Contribution</option>
          </select>
        )}

        {/* Active Filter Count & Clear Button */}
        {activeCount > 0 && (
          <>
            <Badge variant="info" className="ml-auto">
              {activeCount} {activeCount === 1 ? 'filter' : 'filters'} active
            </Badge>
            <button
              onClick={clearFilters}
              className="flex items-center gap-1 px-3 py-1.5 text-xs text-text-secondary hover:text-text-primary bg-surface-hover rounded-md transition-colors font-mono"
            >
              <XMarkIcon className="h-3 w-3" />
              Clear All
            </button>
          </>
        )}
      </div>
    </div>
  )
}

import {
  DocumentTextIcon,
  RocketLaunchIcon,
  BookOpenIcon,
  BeakerIcon,
  ChartBarIcon,
  ChatBubbleLeftRightIcon,
  CheckCircleIcon,
  BookmarkIcon
} from '@heroicons/react/24/outline'

interface SectionCount {
  section_type: string
  new_count: number
  saved_count: number
  dismissed_count: number
  total_count: number
}

interface SectionNavigationProps {
  sections: SectionCount[]
  activeSection: string
  onSectionChange: (section: string) => void
}

// Section configuration with icons and display names (neon-brutalist colors)
const SECTION_CONFIG = {
  abstract: {
    icon: DocumentTextIcon,
    label: 'Abstract',
    color: 'text-info'
  },
  introduction: {
    icon: RocketLaunchIcon,
    label: 'Introduction',
    color: 'text-accent-purple'
  },
  literature_review: {
    icon: BookOpenIcon,
    label: 'Literature Review',
    color: 'text-success'
  },
  methodology: {
    icon: BeakerIcon,
    label: 'Methodology',
    color: 'text-warning'
  },
  results: {
    icon: ChartBarIcon,
    label: 'Results',
    color: 'text-accent-teal'
  },
  discussion: {
    icon: ChatBubbleLeftRightIcon,
    label: 'Discussion',
    color: 'text-accent-purple'
  },
  conclusion: {
    icon: CheckCircleIcon,
    label: 'Conclusion',
    color: 'text-success'
  },
  references: {
    icon: BookmarkIcon,
    label: 'References',
    color: 'text-text-muted'
  }
}

export default function SectionNavigation({
  sections,
  activeSection,
  onSectionChange
}: SectionNavigationProps) {
  return (
    <div className="bg-bg-surface rounded-2xl border border-border-base p-4">
      <h3 className="text-lg font-display font-semibold text-text-primary mb-4 px-2">
        Navigate by Section
      </h3>

      <nav className="space-y-2">
        {Object.entries(SECTION_CONFIG).map(([sectionType, config]) => {
          const sectionData = sections.find(s => s.section_type === sectionType)
          const newCount = sectionData?.new_count || 0
          const isActive = activeSection === sectionType
          const Icon = config.icon

          // Only show sections that have feedback
          if (!sectionData || sectionData.total_count === 0) {
            return null
          }

          return (
            <button
              key={sectionType}
              onClick={() => onSectionChange(sectionType)}
              className={`w-full flex items-center justify-between px-3 py-3 rounded-lg transition-all duration-200 text-left ${
                isActive
                  ? 'bg-neon-pink/10 border-l-4 border-l-neon-pink text-neon-pink shadow-sm'
                  : 'hover:bg-bg-elevated border-l-4 border-l-transparent hover:border-l-neon-pink/30'
              }`}
            >
              <div className="flex items-center gap-3 flex-1 min-w-0">
                {/* Icon with active indicator */}
                <div className={`flex-shrink-0 transition-colors duration-200 ${isActive ? 'text-neon-pink' : config.color}`}>
                  <Icon className="w-5 h-5" strokeWidth={isActive ? 2.5 : 2} />
                </div>

                {/* Section label */}
                <span className={`text-sm font-medium truncate transition-colors duration-200 ${
                  isActive ? 'text-text-primary' : 'text-text-secondary'
                }`}>
                  {config.label}
                </span>
              </div>

              {/* Badge showing NEW items count */}
              {newCount > 0 && (
                <span className={`flex-shrink-0 ml-2 px-2 py-0.5 rounded-full text-xs font-mono font-semibold transition-all duration-200 ${
                  isActive
                    ? 'bg-neon-pink text-white'
                    : 'bg-neon-pink/10 text-neon-pink border border-neon-pink/30'
                }`}>
                  {newCount}
                </span>
              )}
            </button>
          )
        })}
      </nav>

      {/* Summary footer */}
      <div className="mt-4 pt-4 border-t border-border-base">
        <div className="flex items-center justify-between text-sm px-2 mb-2">
          <span className="text-text-muted font-mono">Total Sections</span>
          <span className="font-display font-bold text-text-primary">
            {sections.filter(s => s.total_count > 0).length}
          </span>
        </div>
        <div className="flex items-center justify-between text-sm px-2">
          <span className="text-text-muted font-mono">New Items</span>
          <span className="font-display font-bold text-neon-pink">
            {sections.reduce((sum, s) => sum + s.new_count, 0)}
          </span>
        </div>
      </div>
    </div>
  )
}

import { useState, useEffect } from 'react'
import { MapIcon } from '@heroicons/react/24/outline'
import { useAuthStore } from '../../stores/authStore'
import { api } from '../../lib/api'
import toast from 'react-hot-toast'
import CoverageGapsDiscoveryView from './CoverageGapsDiscoveryView'

interface CompassGridProps {
  insights: any | null
  projectId: string
}

// Card Component for each Compass feature
function CompassCard({
  icon,
  title,
  description,
  stats,
  color,
  onClick
}: {
  icon: string
  title: string
  description: string
  stats: string[]
  color: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="p-6 bg-surface rounded-lg border border-border-base hover:border-accent-primary hover:shadow-lg transition-all duration-200 text-left group"
    >
      {/* Icon & Title */}
      <div className="flex items-center gap-3 mb-3">
        <div className={`text-3xl ${color}`}>{icon}</div>
        <h3 className="text-lg font-serif font-semibold text-text-primary group-hover:text-accent-primary transition-colors">
          {title}
        </h3>
      </div>

      {/* Description */}
      <p className="text-sm text-text-tertiary mb-4">{description}</p>

      {/* Stats */}
      <div className="space-y-1.5">
        {stats.map((stat, index) => (
          <div key={index} className="flex items-start gap-2">
            <span className="text-accent-primary mt-0.5">•</span>
            <span className="text-sm text-text-secondary">{stat}</span>
          </div>
        ))}
      </div>

      {/* View Button */}
      <div className="mt-4 pt-4 border-t border-border-subtle">
        <span className="text-sm font-medium text-accent-primary group-hover:underline">
          View Details →
        </span>
      </div>
    </button>
  )
}

export default function CompassGrid({ insights, projectId }: CompassGridProps) {
  const { session } = useAuthStore()
  const [guidance, setGuidance] = useState<any | null>(null)
  const [loading, setLoading] = useState(false)
  const [showCoverageModal, setShowCoverageModal] = useState(false)

  useEffect(() => {
    if (!guidance && insights) {
      loadGuidance()
    }
  }, [insights])

  const loadGuidance = async () => {
    if (!session?.access_token) return

    setLoading(true)
    try {
      const data = await api.compass.getGuidance(session.access_token, projectId)
      setGuidance(data)
    } catch (error: any) {
      console.error('Failed to load guidance:', error)
      toast.error(error.message || 'Failed to load compass guidance')
    } finally {
      setLoading(false)
    }
  }

  // No insights analyzed yet
  if (!insights) {
    return (
      <div className="bg-surface/50 rounded-lg border border-border-base p-12 text-center">
        <div className="max-w-md mx-auto">
          <div className="p-3 bg-accent-primary/10 rounded-lg inline-block mb-4">
            <MapIcon className="h-12 w-12 text-accent-primary" />
          </div>
          <h3 className="text-xl font-serif font-semibold text-text-primary mb-2">
            Insights Analysis Required
          </h3>
          <p className="text-text-tertiary mb-4">
            Please analyze project insights first before using the Literature Review Compass.
          </p>
          <p className="text-sm text-text-muted">
            Click <strong>"Analyze Insights"</strong> in the sidebar
          </p>
        </div>
      </div>
    )
  }

  // Loading state
  if (loading) {
    return (
      <div className="bg-surface rounded-lg border border-border-base p-12 text-center">
        <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-solid border-accent-primary border-r-transparent mb-4"></div>
        <p className="text-text-secondary">Analyzing your literature...</p>
      </div>
    )
  }

  // Calculate stats from guidance and insights
  const structureRecsCount = guidance?.structure_recommendations?.length || 3
  const topStructureScore = guidance?.structure_recommendations?.[0]?.score || 0.8
  const themesCount = insights?.common_themes?.length || 0
  const synthesisQuestionsCount = guidance?.synthesis_questions?.length || 0
  const gapsCount = insights?.research_gaps?.length || 0
  const papersToDiscoverCount = insights?.paper_recommendations?.length || 0

  return (
    <div>
      {/* Header */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <div className="p-2 bg-accent-primary/10 rounded-lg">
            <MapIcon className="h-6 w-6 text-accent-primary" />
          </div>
          <div>
            <h2 className="text-2xl font-serif font-semibold text-text-primary">
              Literature Review Compass
            </h2>
            <p className="text-sm text-text-tertiary">
              Your expert guide for structuring and writing your literature review
            </p>
          </div>
        </div>
      </div>

      {/* Description */}
      <div className="bg-surface/50 rounded-lg border border-border-base p-6 mb-6">
        <h3 className="text-lg font-serif font-semibold text-text-primary mb-2">
          How the Compass Works
        </h3>
        <p className="text-sm text-text-tertiary mb-3">
          The Literature Review Compass analyzes your literature to provide structural guidance and critical
          thinking questions. Unlike AI writing tools, it doesn't write for you—it helps you become a better writer.
        </p>
      </div>

      {/* 2×2 Grid of Cards */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Structure Advisor Card */}
        <CompassCard
          icon="📊"
          title="Structure Advisor"
          description="Scored organizational approaches with detailed outlines"
          stats={[
            `${structureRecsCount} organizational approaches analyzed`,
            `Top recommendation: ${(topStructureScore * 100).toFixed(0)}% match`,
            'Chronological, Thematic, or Methodological structures'
          ]}
          color="text-blue-400"
          onClick={() => {
            // TODO: Open modal or expand view
            toast('Structure Advisor - Coming soon in full view', { icon: '📊' })
          }}
        />

        {/* Thematic Clusters Card */}
        <CompassCard
          icon="🎯"
          title="Thematic Clustering"
          description="How your papers group by common themes"
          stats={[
            `${themesCount} major themes identified`,
            'Papers automatically grouped by topic',
            'Discover patterns across your literature'
          ]}
          color="text-purple-400"
          onClick={() => {
            // TODO: Open modal or expand view
            toast('Thematic Clustering - Coming soon in full view', { icon: '🎯' })
          }}
        />

        {/* Synthesis Questions Card */}
        <CompassCard
          icon="💭"
          title="Synthesis Questions"
          description="Critical thinking prompts to guide your writing"
          stats={[
            `${synthesisQuestionsCount} questions generated`,
            'Questions across 4 categories',
            'Based on conflicts, gaps, and patterns'
          ]}
          color="text-green-400"
          onClick={() => {
            // TODO: Open modal or expand view
            toast('Synthesis Questions - Coming soon in full view', { icon: '💭' })
          }}
        />

        {/* Coverage, Gaps & Discovery Card */}
        <CompassCard
          icon="🔍"
          title="Coverage, Gaps & Discovery"
          description="What's covered, what's missing, and papers to explore"
          stats={[
            `${gapsCount} research gaps identified`,
            `${papersToDiscoverCount} papers recommended to explore`,
            'Strengthen your literature coverage'
          ]}
          color="text-orange-400"
          onClick={() => setShowCoverageModal(true)}
        />
      </div>

      {/* Coverage, Gaps & Discovery Modal */}
      {showCoverageModal && (
        <CoverageGapsDiscoveryView
          insights={insights}
          projectId={projectId}
          onClose={() => setShowCoverageModal(false)}
        />
      )}
    </div>
  )
}

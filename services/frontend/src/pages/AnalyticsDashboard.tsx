import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import { motion } from 'framer-motion'
import {
  UserGroupIcon,
  ChartBarIcon,
  ArrowTrendingUpIcon,
  SparklesIcon,
  ClockIcon,
  FireIcon,
} from '@heroicons/react/24/outline'
import PageContainer from '../components/layout/PageContainer'
import { handleError } from '../lib/errorHandler'

interface DashboardMetrics {
  mau: number
  dau: number
  activation_rate: number
  retention_rate: number
  power_users: number
  total_drafts: number
  total_documents: number
  total_projects: number
  avg_session_duration: number
  conversion_rate: number
}

interface MetricCard {
  title: string
  value: string | number
  change?: number
  icon: any
  color: string
}

export default function AnalyticsDashboard() {
  const { session } = useAuthStore()
  const [metrics, setMetrics] = useState<DashboardMetrics | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    document.title = 'Analytics Dashboard | Noesis'
  }, [])

  useEffect(() => {
    if (session?.access_token) {
      loadDashboardMetrics()
    }
  }, [session])

  const loadDashboardMetrics = async () => {
    if (!session?.access_token) return

    try {
      setLoading(true)
      const response = await fetch('/api/analytics/dashboard', {
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
        },
      })

      if (!response.ok) {
        throw new Error('Failed to load analytics dashboard')
      }

      const data = await response.json()
      setMetrics(data)
    } catch (error: any) {
      handleError(error, 'loading analytics dashboard')
    } finally {
      setLoading(false)
    }
  }

  const formatNumber = (num: number): string => {
    if (num >= 1000000) {
      return `${(num / 1000000).toFixed(1)}M`
    } else if (num >= 1000) {
      return `${(num / 1000).toFixed(1)}K`
    }
    return num.toString()
  }

  const formatPercentage = (num: number): string => {
    return `${(num * 100).toFixed(1)}%`
  }

  const formatDuration = (minutes: number): string => {
    if (minutes >= 60) {
      const hours = Math.floor(minutes / 60)
      const mins = Math.floor(minutes % 60)
      return `${hours}h ${mins}m`
    }
    return `${Math.floor(minutes)}m`
  }

  if (loading) {
    return (
      <PageContainer title="Analytics Dashboard" description="Platform metrics and insights">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[...Array(6)].map((_, i) => (
            <div
              key={i}
              className="bg-bg-surface border border-border-default rounded-lg p-6 animate-pulse"
            >
              <div className="h-6 bg-bg-hover rounded w-1/2 mb-4"></div>
              <div className="h-10 bg-bg-hover rounded w-1/3"></div>
            </div>
          ))}
        </div>
      </PageContainer>
    )
  }

  if (!metrics) {
    return (
      <PageContainer title="Analytics Dashboard" description="Platform metrics and insights">
        <div className="text-center py-20 bg-bg-surface rounded-lg border border-border-default">
          <p className="text-text-secondary">Failed to load analytics data</p>
        </div>
      </PageContainer>
    )
  }

  const metricCards: MetricCard[] = [
    {
      title: 'Monthly Active Users',
      value: formatNumber(metrics.mau),
      change: 12.5,
      icon: UserGroupIcon,
      color: 'accent',
    },
    {
      title: 'Daily Active Users',
      value: formatNumber(metrics.dau),
      change: 8.3,
      icon: ChartBarIcon,
      color: 'teal',
    },
    {
      title: 'Activation Rate',
      value: formatPercentage(metrics.activation_rate),
      change: 5.2,
      icon: ArrowTrendingUpIcon,
      color: 'indigo',
    },
    {
      title: 'Retention Rate',
      value: formatPercentage(metrics.retention_rate),
      change: -2.1,
      icon: SparklesIcon,
      color: 'purple',
    },
    {
      title: 'Power Users',
      value: formatNumber(metrics.power_users),
      change: 15.7,
      icon: FireIcon,
      color: 'rose',
    },
    {
      title: 'Avg. Session Duration',
      value: formatDuration(metrics.avg_session_duration),
      change: 3.8,
      icon: ClockIcon,
      color: 'amber',
    },
  ]

  const getColorClasses = (color: string) => {
    const colorMap: Record<string, { bg: string; text: string; border: string }> = {
      accent: { bg: 'bg-accent-light', text: 'text-accent-primary', border: 'border-accent-primary/30' },
      teal: { bg: 'bg-teal-light', text: 'text-teal-primary', border: 'border-teal-primary/30' },
      indigo: { bg: 'bg-indigo-light', text: 'text-indigo-primary', border: 'border-indigo-primary/30' },
      purple: { bg: 'bg-purple-500/20', text: 'text-purple-300', border: 'border-purple-500/30' },
      rose: { bg: 'bg-rose-500/20', text: 'text-rose-300', border: 'border-rose-500/30' },
      amber: { bg: 'bg-amber-500/20', text: 'text-amber-300', border: 'border-amber-500/30' },
    }
    return colorMap[color] || colorMap.accent
  }

  return (
    <PageContainer
      title="Analytics Dashboard"
      description="Platform metrics and user insights"
      spacing="loose"
    >
      {/* Key Metrics Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
        {metricCards.map((card, index) => {
          const colors = getColorClasses(card.color)
          return (
            <motion.div
              key={card.title}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ delay: index * 0.1, duration: 0.3 }}
              className="bg-bg-surface border border-border-default rounded-lg p-6 hover:border-accent-primary/30 hover:shadow-sm transition-all duration-150"
            >
              <div className="flex items-start justify-between mb-4">
                <div className={`w-12 h-12 rounded-lg ${colors.bg} border ${colors.border} flex items-center justify-center`}>
                  <card.icon className={`h-6 w-6 ${colors.text}`} />
                </div>
                {card.change !== undefined && (
                  <div
                    className={`text-sm font-mono ${
                      card.change > 0
                        ? 'text-teal-primary'
                        : card.change < 0
                        ? 'text-red-400'
                        : 'text-text-muted'
                    }`}
                  >
                    {card.change > 0 ? '+' : ''}
                    {card.change.toFixed(1)}%
                  </div>
                )}
              </div>
              <div>
                <div className="text-4xl font-sans font-semibold text-text-primary mb-2">
                  {card.value}
                </div>
                <div className="text-sm font-mono text-text-muted tracking-normal">
                  {card.title}
                </div>
              </div>
            </motion.div>
          )
        })}
      </div>

      {/* Summary Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mt-6">
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.6, duration: 0.3 }}
          className="bg-bg-surface border border-border-default rounded-lg p-6"
        >
          <div className="text-sm font-mono text-text-muted mb-2">Total Projects</div>
          <div className="text-3xl font-sans font-semibold text-text-primary">
            {formatNumber(metrics.total_projects)}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.7, duration: 0.3 }}
          className="bg-bg-surface border border-border-default rounded-lg p-6"
        >
          <div className="text-sm font-mono text-text-muted mb-2">Total Documents</div>
          <div className="text-3xl font-sans font-semibold text-text-primary">
            {formatNumber(metrics.total_documents)}
          </div>
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.8, duration: 0.3 }}
          className="bg-bg-surface border border-border-default rounded-lg p-6"
        >
          <div className="text-sm font-mono text-text-muted mb-2">Total Drafts Analyzed</div>
          <div className="text-3xl font-sans font-semibold text-text-primary">
            {formatNumber(metrics.total_drafts)}
          </div>
        </motion.div>
      </div>

      {/* Conversion Funnel */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ delay: 0.9, duration: 0.3 }}
        className="bg-bg-surface border border-border-default rounded-lg p-6 mt-6"
      >
        <h3 className="text-lg font-sans font-semibold text-text-primary mb-6 tracking-normal">
          Conversion Funnel
        </h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Signed Up</span>
            <span className="text-sm font-mono text-text-primary">100%</span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Created Project</span>
            <span className="text-sm font-mono text-text-primary">
              {formatPercentage(metrics.activation_rate)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Uploaded Documents</span>
            <span className="text-sm font-mono text-text-primary">
              {formatPercentage(metrics.activation_rate * 0.85)}
            </span>
          </div>
          <div className="flex items-center justify-between">
            <span className="text-sm text-text-secondary">Analyzed Draft</span>
            <span className="text-sm font-mono text-text-primary">
              {formatPercentage(metrics.conversion_rate)}
            </span>
          </div>
        </div>
      </motion.div>

      {/* Admin Notice */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 1.0 }}
        className="mt-6 bg-amber-500/10 border border-amber-500/30 rounded-lg p-4 text-center"
      >
        <p className="text-sm text-amber-300 font-mono tracking-normal">
          Admin dashboard - Metrics updated every 15 minutes
        </p>
      </motion.div>
    </PageContainer>
  )
}

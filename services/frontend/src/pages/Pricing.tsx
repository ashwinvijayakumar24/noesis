import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { NoesisLogo } from '../components/ui/NoesisLogo'
import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import {
  CheckBadgeIcon,
  XMarkIcon,
  SparklesIcon,
  UserGroupIcon,
  AcademicCapIcon,
} from '@heroicons/react/24/outline'
import { Button } from '../components/ui/Button'
import toast from 'react-hot-toast'

interface PricingTier {
  name: string
  price: number
  interval: string
  description: string
  features: string[]
  limitations: string[]
  cta: string
  highlighted?: boolean
  badge?: string
  icon: any
}

export default function Pricing() {
  const navigate = useNavigate()
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    document.title = 'Pricing | Noesis'
  }, [])

  const handleSubscribe = async (tierName: string) => {
    if (!session?.access_token) {
      navigate('/login')
      return
    }

    try {
      setLoading(true)
      const response = await fetch('/api/subscriptions/checkout', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          plan: tierName.toLowerCase(),
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to create checkout session')
      }

      const data = await response.json()

      // Redirect to checkout URL (Stripe or similar)
      if (data.checkout_url) {
        window.location.href = data.checkout_url
      } else {
        toast.success('Subscription activated!')
        navigate('/projects')
      }
    } catch (error) {
      console.error('Subscription error:', error)
      toast.error('Failed to start checkout. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const pricingTiers: PricingTier[] = [
    {
      name: 'Free',
      price: 0,
      interval: 'month',
      description: 'Perfect for exploring Noesis and small research projects',
      features: [
        '1 draft analysis per month',
        '5 document uploads per month',
        'Unlimited chat queries',
        'Citation gap detection',
        'Reviewer-style feedback',
        'BibTeX export',
        'All core features',
      ],
      limitations: [
        'Limited draft analyses',
        'Limited document uploads',
      ],
      cta: 'Get Started Free',
      icon: AcademicCapIcon,
    },
    {
      name: 'Pro',
      price: 12,
      interval: 'month',
      description: 'For active researchers with ongoing projects',
      features: [
        'Unlimited draft analyses',
        'Unlimited document uploads',
        'Priority processing',
        'Larger draft size limits (50+ pages)',
        'Advanced citation suggestions',
        'PDF export with branding',
        'Email support',
        'Everything in Free',
      ],
      limitations: [],
      cta: 'Subscribe to Pro',
      highlighted: true,
      badge: 'Most Popular',
      icon: SparklesIcon,
    },
    {
      name: 'Team',
      price: 20,
      interval: 'user/month',
      description: 'For research labs and collaborative teams (minimum 3 users)',
      features: [
        'Starting at $60/month for 3 users',
        'Add or remove seats anytime',
        'Shared project workspaces',
        'Team collaboration features',
        'Real-time activity tracking',
        'Dedicated support',
        'Admin dashboard',
        'Priority feature requests',
        'Everything in Pro',
      ],
      limitations: [],
      cta: 'Subscribe to Team',
      icon: UserGroupIcon,
    },
  ]

  return (
    <div className="min-h-screen bg-bg-void text-text-primary">
      {/* Navigation */}
      <motion.nav
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="fixed top-0 left-0 right-0 z-50 bg-bg-surface/95 backdrop-blur-md border-b border-border-default"
      >
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <div className="flex justify-between items-center h-14">
            <div className="cursor-pointer" onClick={() => navigate('/')}>
              <NoesisLogo size="sm" />
            </div>
            <div className="flex items-center gap-4">
              {session ? (
                <Button onClick={() => navigate('/projects')} variant="primary" size="sm">
                  Go to Projects
                </Button>
              ) : (
                <>
                  <button
                    onClick={() => navigate('/login')}
                    className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors duration-150"
                  >
                    Sign In
                  </button>
                  <Button onClick={() => navigate('/signup')} variant="primary" size="sm">
                    Get Started
                  </Button>
                </>
              )}
            </div>
          </div>
        </div>
      </motion.nav>

      {/* Hero Section */}
      <section className="pt-32 pb-16 px-6 sm:px-8">
        <div className="max-w-5xl mx-auto text-center">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
          >
            <h1 className="text-5xl sm:text-6xl lg:text-7xl font-sans font-semibold leading-display tracking-tightest mb-6">
              Transparent, <span className="text-accent-primary">Research-Friendly</span> Pricing
            </h1>
            <p className="text-xl sm:text-2xl text-text-secondary leading-body-large tracking-normal max-w-3xl mx-auto">
              Choose the plan that fits your research workflow. All plans include core features.
            </p>
          </motion.div>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-32 px-6 sm:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-3 gap-8">
            {pricingTiers.map((tier, index) => (
              <motion.div
                key={tier.name}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className={`relative bg-bg-surface rounded-lg p-8 ${
                  tier.highlighted
                    ? 'border-2 border-accent-primary shadow-lg'
                    : 'border border-border-default'
                }`}
              >
                {/* Badge */}
                {tier.badge && (
                  <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                    <span className="px-4 py-1 bg-accent-primary text-white text-sm font-semibold rounded-full">
                      {tier.badge}
                    </span>
                  </div>
                )}

                <div className="space-y-6 mt-2">
                  {/* Icon & Title */}
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-12 h-12 rounded-lg flex items-center justify-center ${
                        tier.highlighted
                          ? 'bg-accent-light border border-accent-primary/30'
                          : 'bg-bg-hover border border-border-default'
                      }`}
                    >
                      <tier.icon
                        className={`h-6 w-6 ${
                          tier.highlighted ? 'text-accent-primary' : 'text-text-tertiary'
                        }`}
                      />
                    </div>
                    <h3 className="text-2xl font-sans font-semibold text-text-primary tracking-normal">
                      {tier.name}
                    </h3>
                  </div>

                  {/* Price */}
                  <div>
                    <div className="flex items-baseline gap-2">
                      <span className="text-5xl font-semibold text-text-primary">
                        ${tier.price}
                      </span>
                      <span className="text-text-tertiary">/{tier.interval}</span>
                    </div>
                    <p className="text-sm text-text-tertiary mt-2 tracking-normal">
                      {tier.description}
                    </p>
                  </div>

                  {/* Features */}
                  <ul className="space-y-3">
                    {tier.features.map((feature, idx) => (
                      <li key={idx} className="flex items-start gap-3 text-sm">
                        <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                        <span className="text-text-secondary tracking-normal">{feature}</span>
                      </li>
                    ))}
                    {tier.limitations.map((limitation, idx) => (
                      <li key={idx} className="flex items-start gap-3 text-sm">
                        <XMarkIcon className="h-5 w-5 text-text-muted shrink-0 mt-0.5" />
                        <span className="text-text-muted tracking-normal">{limitation}</span>
                      </li>
                    ))}
                  </ul>

                  {/* CTA Button */}
                  <Button
                    onClick={() => handleSubscribe(tier.name)}
                    variant={tier.highlighted ? 'primary' : 'secondary'}
                    size="lg"
                    className="w-full"
                    disabled={loading}
                  >
                    {loading ? 'Processing...' : tier.cta}
                  </Button>

                  {tier.name === 'Free' && (
                    <p className="text-xs text-text-muted text-center font-mono tracking-normal">
                      No credit card required
                    </p>
                  )}
                </div>
              </motion.div>
            ))}
          </div>

          {/* FAQ Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4 }}
            className="mt-16 bg-bg-surface border border-border-default rounded-lg p-8"
          >
            <h3 className="text-2xl font-sans font-semibold text-text-primary mb-6 tracking-normal">
              Frequently Asked Questions
            </h3>
            <div className="space-y-6">
              <div>
                <h4 className="font-sans font-semibold text-text-primary mb-2 tracking-normal">
                  Can I switch plans later?
                </h4>
                <p className="text-sm text-text-secondary leading-relaxed tracking-normal">
                  Yes! You can upgrade or downgrade your plan at any time. Changes take effect
                  immediately, and we'll prorate your billing.
                </p>
              </div>
              <div>
                <h4 className="font-sans font-semibold text-text-primary mb-2 tracking-normal">
                  What payment methods do you accept?
                </h4>
                <p className="text-sm text-text-secondary leading-relaxed tracking-normal">
                  We accept all major credit cards (Visa, MasterCard, American Express) and
                  institutional purchase orders for Team plans.
                </p>
              </div>
              <div>
                <h4 className="font-sans font-semibold text-text-primary mb-2 tracking-normal">
                  Is there an academic discount?
                </h4>
                <p className="text-sm text-text-secondary leading-relaxed tracking-normal">
                  Yes! Students and faculty can contact us at{' '}
                  <a
                    href="mailto:academic@noesis.is"
                    className="text-accent-primary hover:text-accent-hover transition-colors"
                  >
                    academic@noesis.is
                  </a>{' '}
                  for special pricing.
                </p>
              </div>
              <div>
                <h4 className="font-sans font-semibold text-text-primary mb-2 tracking-normal">
                  What happens if I exceed my free tier limits?
                </h4>
                <p className="text-sm text-text-secondary leading-relaxed tracking-normal">
                  You'll receive a notification when approaching your limits. You can upgrade to
                  Pro anytime to continue using Noesis without interruption.
                </p>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 sm:px-8 border-t border-border-default bg-bg-void">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div>
              <NoesisLogo size="md" />
            </div>
            <div className="text-text-muted text-sm font-mono">
              © 2026 Noesis. All rights reserved.
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

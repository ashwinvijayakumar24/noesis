import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import { NoesisLogo } from '../components/ui/NoesisLogo'
import { useEffect, useState } from 'react'
import { useAuthStore } from '../stores/authStore'
import {
  CheckBadgeIcon,
  SparklesIcon,
  UserGroupIcon,
  AcademicCapIcon,
  BuildingOffice2Icon,
} from '@heroicons/react/24/outline'
import { Button } from '../components/ui/Button'
import toast from 'react-hot-toast'

export default function Pricing() {
  const navigate = useNavigate()
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    document.title = 'Pricing | Noesis'
  }, [])

  const handleSubscribe = async (tierName: string) => {
    if (tierName === 'Enterprise') {
      window.location.href = 'mailto:team@noesis.is?subject=Enterprise%20Plan%20Inquiry'
      return
    }

    if (!session?.access_token) {
      navigate('/login')
      return
    }

    if (tierName === 'Free') {
      navigate('/signup')
      return
    }

    try {
      setLoading(true)
      const origin = window.location.origin
      const response = await fetch('/api/subscriptions/checkout', {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${session.access_token}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          plan_tier: tierName.toLowerCase(),
          success_url: `${origin}/projects?subscribed=true`,
          cancel_url: `${origin}/pricing`,
        }),
      })

      if (!response.ok) {
        throw new Error('Failed to create checkout session')
      }

      const data = await response.json()

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

  const tiers = [
    {
      name: 'Free',
      price: '$0',
      interval: '/month',
      description: 'For researchers working on their first paper',
      icon: AcademicCapIcon,
      highlighted: false,
      badge: null,
      cta: 'Get Started Free',
      subtext: 'No credit card required',
      features: [
        '2 draft analyses per month',
        '30 PDF uploads per month total',
        '30 BibTeX references per month total',
        '5 Discover searches per day',
        '5 Literature Map refreshes per day',
        'Citation gap detection',
        'Reviewer-style feedback with source grounding',
        'BibTeX export',
        'All core features',
      ],
    },
    {
      name: 'Pro',
      price: '$12',
      interval: '/month',
      description: 'For active researchers with ongoing projects',
      icon: SparklesIcon,
      highlighted: true,
      badge: 'Most Popular',
      cta: 'Subscribe to Pro',
      subtext: null,
      features: [
        '20 draft analyses per month',
        '100 PDF uploads per month total',
        '100 BibTeX references per month total',
        '50 Discover searches per day',
        'Unlimited Literature Map refreshes',
        'Priority processing',
        'Larger draft size limits (50+ pages)',
        'Advanced citation suggestions',
        'PDF export with branding',
        'Email support',
        'Everything in Free',
      ],
    },
    {
      name: 'Team',
      price: '$20',
      interval: '/user/month',
      description: 'For research groups (2–3 researchers)',
      icon: UserGroupIcon,
      highlighted: false,
      badge: null,
      cta: 'Subscribe to Team',
      subtext: '$40–$60/mo for a full group',
      features: [
        '2–3 users billed per seat',
        'Effectively unlimited usage across PDFs, BibTeX, draft analyses, Discover, and Literature Map refreshes',
        'All Pro features for every member',
        'Shared project workspaces',
        'Team collaboration features',
        'Shared literature libraries',
        'Dedicated support',
        'Priority feature requests',
      ],
    },
    {
      name: 'Enterprise',
      price: 'Custom',
      interval: '',
      description: 'For departments and large labs (4+ users)',
      icon: BuildingOffice2Icon,
      highlighted: false,
      badge: null,
      cta: 'Contact Us',
      subtext: null,
      features: [
        '4+ users, custom seat count',
        'Everything in Team',
        'Custom integrations',
        'Admin dashboard & SSO',
        'Dedicated customer success manager',
        'Institution purchase orders accepted',
        'Custom onboarding',
      ],
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
              Start free with clear per-user quotas. Upgrade when you need higher limits or multi-user access.
            </p>
          </motion.div>
        </div>
      </section>

      {/* Pricing Cards */}
      <section className="pb-32 px-6 sm:px-8">
        <div className="max-w-7xl mx-auto">
          <div className="grid md:grid-cols-2 xl:grid-cols-4 gap-6">
            {tiers.map((tier, index) => (
              <motion.div
                key={tier.name}
                id={`plan-${tier.name.toLowerCase()}`}
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className={`relative bg-bg-surface rounded-xl p-8 flex flex-col ${
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

                <div className="flex flex-col gap-6 flex-1 mt-2">
                  {/* Icon & Title */}
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-12 h-12 rounded-lg flex items-center justify-center shrink-0 ${
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
                    <div className="flex items-baseline gap-1">
                      <span className="text-4xl font-semibold text-text-primary">
                        {tier.price}
                      </span>
                      {tier.interval && (
                        <span className="text-text-tertiary text-sm">{tier.interval}</span>
                      )}
                    </div>
                    <p className="text-sm text-text-tertiary mt-2 tracking-normal">
                      {tier.description}
                    </p>
                  </div>

                  {/* Features */}
                  <ul className="space-y-3 flex-1">
                    {tier.features.map((feature, idx) => (
                      <li key={idx} className="flex items-start gap-3 text-sm">
                        <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                        <span className="text-text-secondary tracking-normal">{feature}</span>
                      </li>
                    ))}
                  </ul>

                  {/* CTA */}
                  <div className="space-y-2">
                    <Button
                      onClick={() => handleSubscribe(tier.name)}
                      variant={tier.highlighted ? 'primary' : 'secondary'}
                      size="lg"
                      className="w-full"
                      disabled={loading && tier.name !== 'Free' && tier.name !== 'Enterprise'}
                    >
                      {loading && tier.name !== 'Free' && tier.name !== 'Enterprise'
                        ? 'Processing...'
                        : tier.cta}
                    </Button>
                    {tier.subtext && (
                      <p className="text-xs text-text-muted text-center font-mono tracking-normal">
                        {tier.subtext}
                      </p>
                    )}
                  </div>
                </div>
              </motion.div>
            ))}
          </div>

          {/* FAQ Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.5 }}
            className="mt-16 bg-bg-surface border border-border-default rounded-xl p-8"
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
                  What counts as a "draft analysis"?
                </h4>
                <p className="text-sm text-text-secondary leading-relaxed tracking-normal">
                  Each time you submit a draft for AI-powered reviewer feedback, claim extraction,
                  and gap detection, that counts as one analysis. Re-running an existing draft's
                  analysis also counts. PDF uploads, BibTeX imports, Discover searches, and
                  Literature Map refreshes each have their own separate quotas.
                </p>
              </div>
              <div>
                <h4 className="font-sans font-semibold text-text-primary mb-2 tracking-normal">
                  What payment methods do you accept?
                </h4>
                <p className="text-sm text-text-secondary leading-relaxed tracking-normal">
                  We accept all major credit cards (Visa, MasterCard, American Express) and
                  institutional purchase orders for Enterprise plans.
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
                  Pro or Team anytime to continue without interruption. Free includes 30 PDFs,
                  30 BibTeX references, 2 draft analyses, 5 Discover searches per day, and
                  5 Literature Map refreshes per day so you can evaluate a real project before
                  committing.
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

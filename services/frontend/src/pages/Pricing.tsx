/**
 * Pricing.tsx  (replacement for services/frontend/src/pages/Pricing.tsx)
 *
 * Changes from original:
 *   - `disabled` removed from all Buttons (CTAs now active)
 *   - handleSubscribe uses api.subscriptions.createCheckout instead of raw fetch
 *   - Anon users redirected to / (login gate) for paid tiers
 *   - Returns ?subscribed=true to /billing (not /projects) so BillingPage
 *     can show the success toast
 *   - Team CTA shows "Join Waitlist" until team checkout is GA
 *   - Enterprise CTA mailto link unchanged
 */

import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { motion } from 'framer-motion'
import toast from 'react-hot-toast'
import {
  AcademicCapIcon,
  BeakerIcon,
  BuildingOffice2Icon,
  CheckBadgeIcon,
  SparklesIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import PublicLayout from '../components/layout/PublicLayout'
import { Button } from '../components/ui/Button'
import { useAuthStore } from '../stores/authStore'
import { api } from '../lib/api'

export default function Pricing() {
  const navigate = useNavigate()
  const { session } = useAuthStore()
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    document.title = 'Pricing | Noesis'
  }, [])

  const handleSubscribe = async (tierName: string) => {
    if (tierName === 'Enterprise') {
      window.location.href =
        'mailto:avijayakumar41@gatech.edu?subject=Enterprise%20Plan%20Inquiry'
      return
    }

    if (tierName === 'Free') {
      navigate('/')
      return
    }

    // Team plan is not yet GA -- direct to waitlist email.
    if (tierName === 'Team') {
      window.location.href =
        'mailto:avijayakumar41@gatech.edu?subject=Team%20Plan%20Waitlist'
      return
    }

    if (!session?.access_token) {
      navigate('/')
      return
    }

    try {
      setLoading(true)
      const origin = window.location.origin
      const result = (await api.subscriptions.createCheckout(session.access_token, {
        plan_tier: tierName.toLowerCase(),
        success_url: `${origin}/billing?subscribed=true&plan=${tierName.toLowerCase()}`,
        cancel_url: `${origin}/pricing`,
      })) as { checkout_url: string }

      if (result.checkout_url) {
        window.location.href = result.checkout_url
      } else {
        toast.error('Failed to start checkout. Please try again.')
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
      description: 'For evaluating Noesis with one focused manuscript project.',
      icon: AcademicCapIcon,
      highlighted: false,
      cta: 'Get Started Free',
      features: [
        '1 active project',
        '3 draft analyses per month',
        '30 literature uploads per month',
        'Complete manuscript review from start to finish',
      ],
    },
    {
      name: 'Pro',
      price: '$12',
      interval: '/month',
      description: 'For active researchers revising multiple manuscripts.',
      icon: SparklesIcon,
      highlighted: true,
      cta: 'Subscribe to Pro',
      features: [
        '3 active projects',
        '10 draft analyses per month',
        '100 literature uploads per month total',
        'Priority processing',
        'Larger draft size limits',
        'Exportable analysis reports',
      ],
    },
    {
      name: 'Team',
      price: '$20',
      interval: '/user/month',
      description: 'For small research groups that need higher operational caps.',
      icon: UserGroupIcon,
      highlighted: false,
      cta: 'Join Waitlist',
      features: [
        'Everything in Pro',
        'Up to 10 users billed per seat',
        'Effectively unlimited usage',
        'Shared project workspaces',
        'Team collaboration features',
        'Shared literature libraries',
        'Dedicated support',
      ],
    },
    {
      name: 'Enterprise',
      price: 'Custom',
      interval: '',
      description: 'For departments and institutions with procurement requirements.',
      icon: BuildingOffice2Icon,
      highlighted: false,
      cta: 'Contact Us',
      features: ['Custom seat count', 'SSO and audit logs', 'SLA + dedicated support'],
    },
  ]

  return (
    <PublicLayout>
      <main>
        <section className="border-b border-border-default px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.75fr_1.25fr] lg:items-end">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
            >
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-border-default bg-bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary">
                <BeakerIcon className="h-4 w-4 text-accent-primary" />
                Current beta pricing
              </div>
              <h1 className="text-4xl font-heading font-semibold leading-[1.08] text-text-primary sm:text-5xl lg:text-6xl">
                Clear quotas for draft review.
              </h1>
            </motion.div>
            <motion.p
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35, delay: 0.06 }}
              className="max-w-3xl text-base leading-7 text-text-secondary sm:text-lg"
            >
              Start free with enough usage to review a real manuscript. Upgrade when you need
              more draft analyses, larger literature context, or higher project volume.
            </motion.p>
          </div>
        </section>

        <section className="px-4 py-16 sm:px-6 lg:px-8">
          <div className="mx-auto grid max-w-7xl gap-4 md:grid-cols-2 xl:grid-cols-4">
            {tiers.map((tier, index) => (
              <motion.div
                key={tier.name}
                id={`plan-${tier.name.toLowerCase()}`}
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: index * 0.05, duration: 0.25 }}
                className={`flex min-h-full flex-col rounded-xl border bg-bg-surface p-5 ${
                  tier.highlighted ? 'border-accent-primary/70' : 'border-border-default'
                }`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-border-default bg-bg-elevated">
                    <tier.icon
                      className={`h-5 w-5 ${
                        tier.highlighted ? 'text-accent-primary' : 'text-text-tertiary'
                      }`}
                    />
                  </div>
                  {tier.highlighted && (
                    <span className="rounded-md border border-accent-primary/30 bg-accent-light/40 px-2 py-1 text-xs font-semibold text-accent-primary">
                      Active researchers
                    </span>
                  )}
                </div>

                <div className="mt-5">
                  <h2 className="text-xl font-semibold text-text-primary">{tier.name}</h2>
                  <p className="mt-2 min-h-[48px] text-sm leading-6 text-text-secondary">
                    {tier.description}
                  </p>
                </div>

                <div className="mt-6 flex items-baseline gap-1">
                  <span className="text-4xl font-semibold text-text-primary">{tier.price}</span>
                  {tier.interval && (
                    <span className="text-sm text-text-tertiary">{tier.interval}</span>
                  )}
                </div>

                <ul className="mt-6 flex-1 space-y-3">
                  {tier.features.map((feature) => (
                    <li
                      key={feature}
                      className="flex items-start gap-2 text-sm leading-6 text-text-secondary"
                    >
                      <CheckBadgeIcon className="mt-0.5 h-4 w-4 shrink-0 text-accent-primary" />
                      <span>{feature}</span>
                    </li>
                  ))}
                </ul>

                <div className="mt-7">
                  <Button
                    onClick={() => handleSubscribe(tier.name)}
                    variant={tier.highlighted ? 'primary' : 'secondary'}
                    size="md"
                    className="w-full"
                    disabled={loading && tier.name === 'Pro'}
                  >
                    {loading && tier.name === 'Pro' ? 'Processing...' : tier.cta}
                  </Button>
                </div>
              </motion.div>
            ))}
          </div>
        </section>

        <section className="border-t border-border-default bg-bg-surface/30 px-4 py-16 sm:px-6 lg:px-8">
          <div className="mx-auto grid max-w-7xl gap-8 lg:grid-cols-[0.8fr_1.2fr]">
            <div>
              <p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-accent-primary">
                Billing notes
              </p>
              <h2 className="text-3xl font-semibold text-text-primary">
                What counts against quota?
              </h2>
              <p className="mt-4 text-sm leading-6 text-text-secondary">
                Quotas are monthly and per user. Draft analyses, PDF uploads, and BibTeX
                references are tracked separately so one large import does not hide draft review
                usage.
              </p>
            </div>

            <div className="space-y-3">
              {[
                {
                  question: 'What counts as a draft analysis?',
                  answer:
                    'Each submitted manuscript review counts as one draft analysis, including reruns on an existing version.',
                },
                {
                  question: 'Can I switch plans later?',
                  answer:
                    'Sure! You can upgrade or downgrade your plan at any time through the billing portal.',
                },
                {
                  question: 'Do you offer academic or institutional pricing?',
                  answer:
                    'Not at the moment, but we are working on it! Reach out to avijayakumar41@gatech.edu if you are interested.',
                },
              ].map((item) => (
                <div
                  key={item.question}
                  className="rounded-lg border border-border-default bg-bg-surface p-5"
                >
                  <h3 className="text-sm font-semibold text-text-primary">{item.question}</h3>
                  <p className="mt-2 text-sm leading-6 text-text-secondary">{item.answer}</p>
                </div>
              ))}
            </div>
          </div>
        </section>
      </main>
    </PublicLayout>
  )
}

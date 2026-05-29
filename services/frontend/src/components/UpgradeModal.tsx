import { Fragment } from 'react'
import { Dialog, Transition } from '@headlessui/react'
import { XMarkIcon, SparklesIcon, CheckBadgeIcon, RocketLaunchIcon } from '@heroicons/react/24/outline'
import { useNavigate } from 'react-router-dom'
import { useUpgradeModalStore } from '../stores/upgradeModalStore'

const QUOTA_LABELS: Record<string, string> = {
  drafts: 'monthly draft analysis',
  documents: 'monthly PDF or BibTeX import',
  chat_messages: 'monthly chat message',
  paper_discovery: 'paper recommendation search',
}

const PRO_HIGHLIGHTS = [
  '20 draft analyses per month',
  '100 PDF uploads per month total',
  '100 BibTeX references per month total',
  'Priority processing',
]

const TEAM_HIGHLIGHTS = [
  'Everything in Pro',
  '2-3 users billed at $20/user/month',
  'Effectively unlimited usage across the team',
  'Shared project workspaces',
  'Shared literature libraries',
  'Dedicated support',
]

export default function UpgradeModal() {
  const { isOpen, quotaType, limitMessage, close } = useUpgradeModalStore()
  const navigate = useNavigate()

  const label = quotaType ? QUOTA_LABELS[quotaType] : 'monthly'

  const handleUpgrade = (plan: 'pro' | 'team') => {
    close()
    navigate('/pricing')
    // Scroll to the plan after navigation (best effort)
    setTimeout(() => {
      const el = document.getElementById(`plan-${plan}`)
      if (el) el.scrollIntoView({ behavior: 'smooth' })
    }, 300)
  }

  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className="relative z-50" onClose={close}>
        <Transition.Child
          as={Fragment}
          enter="ease-out duration-200"
          enterFrom="opacity-0"
          enterTo="opacity-100"
          leave="ease-in duration-150"
          leaveFrom="opacity-100"
          leaveTo="opacity-0"
        >
          <div className="fixed inset-0 bg-black/70 backdrop-blur-sm" />
        </Transition.Child>

        <div className="fixed inset-0 overflow-y-auto">
          <div className="flex min-h-full items-center justify-center p-4">
            <Transition.Child
              as={Fragment}
              enter="ease-out duration-200"
              enterFrom="opacity-0 scale-95"
              enterTo="opacity-100 scale-100"
              leave="ease-in duration-150"
              leaveFrom="opacity-100 scale-100"
              leaveTo="opacity-0 scale-95"
            >
              <Dialog.Panel className="w-full max-w-lg transform rounded-xl bg-bg-surface border border-border-default shadow-2xl transition-all">
                {/* Header */}
                <div className="flex items-start justify-between px-6 pt-6 pb-4">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <RocketLaunchIcon className="h-5 w-5 text-accent-primary" />
                      <Dialog.Title className="text-lg font-semibold text-text-primary">
                        You've reached your {label} limit
                      </Dialog.Title>
                    </div>
                    <p className="text-sm text-text-secondary">
                      {limitMessage || 'Upgrade to Pro for higher quotas or Team for 2-3 researchers with effectively unlimited usage.'}
                    </p>
                  </div>
                  <button onClick={close} className="p-1 text-text-tertiary hover:text-text-primary rounded transition-colors ml-4 shrink-0">
                    <XMarkIcon className="h-5 w-5" />
                  </button>
                </div>

                {/* Plan cards */}
                <div className="px-6 pb-6 grid grid-cols-2 gap-4">
                  {/* Pro */}
                  <div className="border-2 border-accent-primary rounded-xl p-4 bg-accent-light/20 flex flex-col">
                    <div className="flex items-center gap-2 mb-3">
                      <SparklesIcon className="h-5 w-5 text-accent-primary" />
                      <span className="font-semibold text-text-primary">Pro</span>
                      <span className="ml-auto text-xs bg-accent-primary text-white px-2 py-0.5 rounded-full font-semibold">Popular</span>
                    </div>
                    <p className="text-2xl font-bold text-text-primary mb-1">$12<span className="text-sm font-normal text-text-tertiary">/mo</span></p>
                    <ul className="space-y-1.5 mt-3 flex-1">
                      {PRO_HIGHLIGHTS.map((f) => (
                        <li key={f} className="flex items-start gap-2 text-xs text-text-secondary">
                          <CheckBadgeIcon className="h-4 w-4 text-accent-primary shrink-0 mt-0.5" />
                          {f}
                        </li>
                      ))}
                    </ul>
                    <button
                      onClick={() => handleUpgrade('pro')}
                      className="mt-4 w-full py-2.5 bg-accent-primary text-white text-sm font-semibold rounded-lg hover:bg-accent-hover transition-colors"
                    >
                      Upgrade to Pro
                    </button>
                  </div>

                  {/* Team */}
                  <div className="border border-border-default rounded-xl p-4 bg-bg-hover flex flex-col">
                    <div className="flex items-center gap-2 mb-3">
                      <SparklesIcon className="h-5 w-5 text-text-tertiary" />
                      <span className="font-semibold text-text-primary">Team</span>
                    </div>
                    <p className="text-2xl font-bold text-text-primary mb-1">$20<span className="text-sm font-normal text-text-tertiary">/user/mo</span></p>
                    <p className="text-xs text-text-muted mb-1">For 2-3 users</p>
                    <ul className="space-y-1.5 mt-3 flex-1">
                      {TEAM_HIGHLIGHTS.map((f) => (
                        <li key={f} className="flex items-start gap-2 text-xs text-text-secondary">
                          <CheckBadgeIcon className="h-4 w-4 text-text-tertiary shrink-0 mt-0.5" />
                          {f}
                        </li>
                      ))}
                    </ul>
                    <button
                      onClick={() => handleUpgrade('team')}
                      className="mt-4 w-full py-2.5 border border-border-default text-text-secondary text-sm font-semibold rounded-lg hover:border-accent-primary/40 hover:text-text-primary transition-colors"
                    >
                      Upgrade to Team
                    </button>
                  </div>
                </div>

                {/* Footer */}
                <div className="border-t border-border-default px-6 py-4 flex items-center justify-between">
                  <p className="text-xs text-text-muted">No credit card required during beta.</p>
                  <button onClick={close} className="text-xs text-text-muted hover:text-text-secondary transition-colors">
                    Continue with free tier →
                  </button>
                </div>
              </Dialog.Panel>
            </Transition.Child>
          </div>
        </div>
      </Dialog>
    </Transition>
  )
}

import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { ArrowRightIcon, EnvelopeIcon, CalendarDaysIcon } from '@heroicons/react/24/outline'
import PublicLayout from '../components/layout/PublicLayout'
import { CONTACT_EMAIL, BOOKING_URL } from '../config/site'

export default function Contact() {
  useEffect(() => {
    document.title = 'Contact Sales | Noesis'
  }, [])

  const mailto = `mailto:${CONTACT_EMAIL}?subject=${encodeURIComponent('Noesis — Pre-submission review for our lab')}`

  return (
    <PublicLayout>
      <section className="px-4 py-20 sm:px-6 lg:px-8">
        <div className="mx-auto max-w-3xl text-center">
          <p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-accent-primary">
            Now onboarding research teams
          </p>
          <h1 className="text-4xl font-semibold leading-tight text-text-primary sm:text-5xl">
            Bring pre-submission review to your lab.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-base leading-7 text-text-secondary sm:text-lg">
            Noesis runs reviewer-style analysis on a manuscript against its own literature before
            it leaves your desk. We're rolling out to research groups and departments one at a time —
            reach out to set up access for your team.
          </p>

          <div className="mt-9 flex flex-col justify-center gap-3 sm:flex-row">
            {BOOKING_URL && (
              <a
                href={BOOKING_URL}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center justify-center gap-2 rounded-md border border-accent-primary/60 bg-accent-primary px-5 py-3 text-sm font-semibold text-white transition-all duration-150 hover:border-accent-hover hover:bg-accent-hover"
              >
                <CalendarDaysIcon className="h-4 w-4" />
                Book a demo
              </a>
            )}
            <a
              href={mailto}
              className={`inline-flex items-center justify-center gap-2 rounded-md px-5 py-3 text-sm font-semibold transition-all duration-150 ${
                BOOKING_URL
                  ? 'border border-border-default bg-bg-surface text-text-primary hover:border-border-strong hover:bg-bg-elevated'
                  : 'border border-accent-primary/60 bg-accent-primary text-white hover:border-accent-hover hover:bg-accent-hover'
              }`}
            >
              <EnvelopeIcon className="h-4 w-4" />
              Contact sales
            </a>
          </div>

          <p className="mt-5 text-sm text-text-tertiary">
            Or email us directly at{' '}
            <a href={mailto} className="font-medium text-accent-primary hover:text-accent-hover">
              {CONTACT_EMAIL}
            </a>
          </p>

          <div className="mt-12 border-t border-border-default pt-8">
            <Link
              to="/demo"
              className="inline-flex items-center gap-2 text-sm font-semibold text-accent-primary transition-colors duration-150 hover:text-accent-hover"
            >
              See a sample analysis
              <ArrowRightIcon className="h-4 w-4" />
            </Link>
          </div>
        </div>
      </section>
    </PublicLayout>
  )
}

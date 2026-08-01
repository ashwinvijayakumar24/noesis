import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowRightIcon,
  BeakerIcon,
  CheckBadgeIcon,
  ClipboardDocumentCheckIcon,
  DocumentTextIcon,
  LockClosedIcon,
  PencilSquareIcon,
  ShieldCheckIcon,
} from '@heroicons/react/24/outline'
import PublicLayout from '../components/layout/PublicLayout'
import DraftAnalysisShowcase from '../components/draft-analysis/DraftAnalysisShowcase'
import { FREEZE_MODE } from '../config/site'

// During freeze mode the backend is offline, so the primary CTA points at the
// Contact page (B2B) instead of self-serve signup.
const primaryCtaTo = FREEZE_MODE ? '/contact' : '/signup'
const primaryCtaLabelHero = FREEZE_MODE ? 'Book a Demo' : 'Start Free'
const primaryCtaLabelFooter = FREEZE_MODE ? 'Contact Sales' : 'Get Started Free'
// Pricing is hidden in B2B freeze mode — secondary CTA points at the live demo instead.
const secondaryCtaTo = FREEZE_MODE ? '/demo' : '/pricing'
const secondaryCtaLabel = FREEZE_MODE ? 'See the Demo' : 'View Pricing'

const checks = [
  {
    title: 'Unsupported claims',
    description: 'Flags claims that need citation support, stronger evidence, or clearer scope before another reviewer sees the draft.',
    icon: ClipboardDocumentCheckIcon,
  },
  {
    title: 'Citation fit',
    description: 'Compares manuscript claims with your project literature and targeted external scholarly context so citation gaps and weak source matches are easier to triage.',
    icon: DocumentTextIcon,
  },
  {
    title: 'Reviewer panel',
    description: 'Separates editorial checks from reviewer-style critique across contribution, methodology, clarity, and literature coverage.',
    icon: BeakerIcon,
  },
  {
    title: 'Revision queue',
    description: 'Turns critique into durable tasks with priority, section context, and document anchors where the source file allows it.',
    icon: PencilSquareIcon,
  },
]

const workflow = [
  {
    step: '01',
    title: 'Create a manuscript project',
    description: 'Keep the draft, paper type, citation style, and relevant literature in one focused workspace.',
  },
  {
    step: '02',
    title: 'Add the literature you are using',
    description: 'Upload PDFs or import BibTeX references so the review has the same context your argument depends on.',
  },
  {
    step: '03',
    title: 'Run pre-submission review',
    description: 'Noesis runs editing checks, reviewer-style analysis, claim support checks, targeted external-source lookup, and a meta-review synthesis.',
  },
  {
    step: '04',
    title: 'Revise from the queue',
    description: 'Work through prioritized issues, save or dismiss feedback, then upload the next version when the draft changes.',
  },
]

const trustItems = [
  'Noesis critiques drafts; it does not write the paper for you.',
  'Uploaded drafts stay scoped to your authenticated project workspace.',
  'Drafts are processed through backend API workflows, not consumer chat sessions.',
  'Manuscripts and project literature are not sold or used to train Noesis models.',
]

const faqItems = [
  {
    question: 'What is Noesis?',
    answer: 'Noesis is a pre-submission review workspace for academic drafts. It reviews a manuscript against its project literature and returns reviewer-style feedback, citation checks, coverage gaps, and revision tasks.',
  },
  {
    question: 'How is this different from a writing assistant?',
    answer: 'Noesis is designed for critique, not authorship. The product identifies weak claims, missing citations, reviewer-facing issues, and structural problems so the author can revise their own work.',
  },
  {
    question: 'What should I upload first?',
    answer: 'Start with the papers and references that support the manuscript, then upload the draft you want reviewed. The strongest results come from a focused project library tied to one paper.',
  },
  {
    question: 'Does Noesis only use papers I upload?',
    answer: 'No. Your project literature is the primary context, but Noesis can also use targeted external scholarly lookup to help identify missing support, related work, or reviewer-facing gaps. External services receive focused search queries or citation context, not your full draft file.',
  },
  {
    question: 'Does Noesis need my full draft?',
    answer: 'Draft review requires manuscript text so the system can locate claims, sections, and revision targets. The privacy policy explains storage, providers, retention, and deletion in detail.',
  },
]

function SectionHeader({
  eyebrow,
  title,
  description,
}: {
  eyebrow: string
  title: string
  description: string
}) {
  return (
    <div className="max-w-2xl">
      <p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-accent-primary">{eyebrow}</p>
      <h2 className="text-3xl font-heading font-semibold leading-tight text-text-primary sm:text-4xl">
        {title}
      </h2>
      <p className="mt-4 text-base leading-7 text-text-secondary">{description}</p>
    </div>
  )
}

function FAQ() {
  const [openIndex, setOpenIndex] = useState(0)

  return (
    <section className="border-t border-border-default bg-bg-surface/30 px-4 py-20 sm:px-6 lg:px-8">
      <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.75fr_1.25fr]">
        <SectionHeader
          eyebrow="Questions"
          title="The short version before you upload a draft."
          description="Noesis is narrow on purpose: one manuscript, the relevant literature, and a reviewer-style queue you can act on."
        />

        <div className="space-y-2">
          {faqItems.map((item, index) => (
            <div key={item.question} className="overflow-hidden rounded-lg border border-border-default bg-bg-surface">
              <button
                onClick={() => setOpenIndex(openIndex === index ? -1 : index)}
                className="flex w-full items-center justify-between gap-4 px-5 py-4 text-left transition-colors duration-150 hover:bg-bg-elevated/70"
                aria-expanded={openIndex === index}
              >
                <span className="text-sm font-semibold text-text-primary">{item.question}</span>
                <span className={`grid h-5 w-5 shrink-0 place-items-center rounded border border-border-default text-text-tertiary transition-transform duration-150 ${openIndex === index ? 'rotate-45' : ''}`}>
                  +
                </span>
              </button>
              <AnimatePresence initial={false}>
                {openIndex === index && (
                  <motion.div
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.18 }}
                    className="overflow-hidden"
                  >
                    <p className="border-t border-border-default px-5 py-4 text-sm leading-6 text-text-secondary">
                      {item.answer}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

export default function Landing() {
  useEffect(() => {
    document.title = 'Noesis | Pre-Submission Review for Research Drafts'
  }, [])

  return (
    <PublicLayout>
      <main>
        <section className="relative overflow-hidden border-b border-border-default px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <div className="absolute inset-0 pointer-events-none bg-[radial-gradient(circle_at_20%_0%,rgba(229,72,77,0.10),transparent_34%),radial-gradient(circle_at_80%_12%,rgba(13,148,136,0.08),transparent_30%)]" />
          <div className="relative mx-auto grid max-w-7xl items-center gap-10 lg:grid-cols-[minmax(0,0.82fr)_minmax(0,1.18fr)]">
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.35 }}
              className="max-w-3xl"
            >
              <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-border-default bg-bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary">
                <span className="h-1.5 w-1.5 rounded-full bg-accent-primary" />
                Draft-aware review before submission
              </div>

              <h1 className="text-4xl font-heading font-semibold leading-[1.06] text-text-primary sm:text-5xl lg:text-6xl">
                Pre-submission review for research drafts.
              </h1>
              <p className="mt-6 max-w-2xl text-base leading-7 text-text-secondary sm:text-lg">
                Upload the literature behind a manuscript, then run reviewer-style analysis that checks your draft against your sources and targeted external scholarly context before the draft leaves your desk.
              </p>

              <div className="mt-8 flex flex-col gap-3 sm:flex-row">
                <Link
                  to={primaryCtaTo}
                  className="inline-flex items-center justify-center gap-2 rounded-md border border-accent-primary/60 bg-accent-primary px-5 py-3 text-sm font-semibold text-white transition-all duration-150 hover:border-accent-hover hover:bg-accent-hover"
                >
                  {primaryCtaLabelHero}
                </Link>
                <Link
                  to={secondaryCtaTo}
                  className="inline-flex items-center justify-center rounded-md border border-border-default bg-bg-surface px-5 py-3 text-sm font-semibold text-text-primary transition-all duration-150 hover:border-border-strong hover:bg-bg-elevated"
                >
                  {secondaryCtaLabel}
                </Link>
              </div>

              <div className="mt-8 grid gap-2 text-xs text-text-tertiary sm:grid-cols-3">
                {['No credit card required', 'Private project workspace', 'Author-controlled revisions'].map((item) => (
                  <div key={item} className="flex items-center gap-2">
                    <CheckBadgeIcon className="h-4 w-4 text-accent-primary" />
                    <span>{item}</span>
                  </div>
                ))}
              </div>
            </motion.div>

            <motion.div
              initial={{ opacity: 0, x: 18 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.38, delay: 0.08 }}
              className="min-w-0"
            >
              <DraftAnalysisShowcase variant="preview" showDocumentPane={false} />
            </motion.div>
          </div>
        </section>

        <section className="px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[0.72fr_1.28fr]">
            <SectionHeader
              eyebrow="What it checks"
              title="A focused review pass for the problems reviewers actually flag."
              description="The homepage now describes the core product only: draft review grounded in your manuscript context and project literature."
            />

            <div className="grid gap-3 sm:grid-cols-2">
              {checks.map((item, index) => (
                <motion.div
                  key={item.title}
                  initial={{ opacity: 0, y: 10 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.2 }}
                  transition={{ duration: 0.25, delay: index * 0.04 }}
                  className="rounded-lg border border-border-default bg-bg-surface p-5 transition-colors duration-150 hover:border-border-strong"
                >
                  <div className="mb-5 flex h-10 w-10 items-center justify-center rounded-lg border border-border-default bg-bg-elevated">
                    <item.icon className="h-5 w-5 text-accent-primary" strokeWidth={1.6} />
                  </div>
                  <h3 className="text-lg font-semibold text-text-primary">{item.title}</h3>
                  <p className="mt-2 text-sm leading-6 text-text-secondary">{item.description}</p>
                </motion.div>
              ))}
            </div>
          </div>
        </section>

        <section className="border-y border-border-default bg-bg-surface/30 px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-7xl">
            <SectionHeader
              eyebrow="Workflow"
              title="From literature context to a revision queue."
              description="Noesis works best when the draft review is tied to one manuscript and the sources that manuscript depends on."
            />

            <div className="mt-10 overflow-hidden rounded-xl border border-border-default bg-bg-surface">
              {workflow.map((item) => (
                <div
                  key={item.step}
                  className="grid gap-4 border-b border-border-default px-5 py-5 last:border-b-0 md:grid-cols-[80px_minmax(0,0.45fr)_minmax(0,1fr)] md:items-start"
                >
                  <span className="font-mono text-sm font-semibold text-accent-primary">{item.step}</span>
                  <h3 className="text-base font-semibold text-text-primary">{item.title}</h3>
                  <p className="text-sm leading-6 text-text-secondary">{item.description}</p>
                </div>
              ))}
            </div>
          </div>
        </section>

        <section className="px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto grid max-w-7xl gap-10 lg:grid-cols-[1fr_0.95fr] lg:items-start">
            <div className="rounded-xl border border-border-default bg-bg-surface p-6 sm:p-8">
              <div className="mb-5 flex items-center gap-3">
                <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-border-default bg-bg-elevated">
                  <ShieldCheckIcon className="h-5 w-5 text-accent-primary" />
                </div>
                <div>
                  <p className="text-xs font-bold uppercase tracking-[0.14em] text-text-muted">Trust posture</p>
                  <h2 className="mt-1 text-2xl font-semibold text-text-primary">Private drafts, clear limits.</h2>
                </div>
              </div>
              <div className="space-y-3">
                {trustItems.map((item) => (
                  <div key={item} className="flex gap-3 rounded-lg border border-border-default bg-bg-elevated/60 px-4 py-3">
                    <LockClosedIcon className="mt-0.5 h-4 w-4 shrink-0 text-accent-primary" />
                    <p className="text-sm leading-6 text-text-secondary">{item}</p>
                  </div>
                ))}
              </div>
            </div>

            {FREEZE_MODE ? (
              <div className="space-y-5">
                <SectionHeader
                  eyebrow="For research teams"
                  title="Rolling out to labs and departments."
                  description="We're onboarding research groups one at a time and tailoring access to how your team drafts and submits. Reach out to set up your group."
                />
                <div className="rounded-lg border border-border-default bg-bg-surface p-5">
                  <p className="text-sm leading-6 text-text-secondary">
                    Group onboarding, shared literature workspaces, and pre-submission review across your team's manuscripts.
                  </p>
                  <Link
                    to="/contact"
                    className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-accent-primary transition-colors duration-150 hover:text-accent-hover"
                  >
                    Contact sales
                    <ArrowRightIcon className="h-4 w-4" />
                  </Link>
                </div>
              </div>
            ) : (
              <div className="space-y-5">
                <SectionHeader
                  eyebrow="Pricing"
                  title="Start with a real manuscript before paying."
                  description="Free includes enough quota to evaluate one focused project. Pro raises monthly draft, PDF, and BibTeX limits for active researchers."
                />
                <div className="rounded-lg border border-border-default bg-bg-surface p-5">
                  <div className="grid gap-3 text-sm text-text-secondary sm:grid-cols-2">
                    <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
                      <p className="font-semibold text-text-primary">Free</p>
                      <p className="mt-2 leading-6">2 draft analyses per month, 30 PDF uploads, and 30 BibTeX references.</p>
                    </div>
                    <div className="rounded-lg border border-border-default bg-bg-elevated p-4">
                      <p className="font-semibold text-text-primary">Pro</p>
                      <p className="mt-2 leading-6">20 draft analyses per month, 100 PDF uploads, and 100 BibTeX references.</p>
                    </div>
                  </div>
                  <Link
                    to="/pricing"
                    className="mt-5 inline-flex items-center gap-2 text-sm font-semibold text-accent-primary transition-colors duration-150 hover:text-accent-hover"
                  >
                    Compare plans
                    <ArrowRightIcon className="h-4 w-4" />
                  </Link>
                </div>
              </div>
            )}
          </div>
        </section>

        <FAQ />

        <section className="px-4 py-20 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-4xl rounded-xl border border-border-default bg-bg-surface p-8 text-center sm:p-10">
            <p className="mb-3 text-xs font-bold uppercase tracking-[0.14em] text-accent-primary">Pre-submission pass</p>
            <h2 className="text-3xl font-semibold leading-tight text-text-primary sm:text-4xl">
              Put a reviewer-style queue between your draft and submission.
            </h2>
            <p className="mx-auto mt-4 max-w-2xl text-sm leading-6 text-text-secondary sm:text-base">
              Noesis is built for researchers who want sharper claims, better citation coverage, and fewer avoidable reviewer objections.
            </p>
            <div className="mt-8 flex flex-col justify-center gap-3 sm:flex-row">
              <Link
                to={primaryCtaTo}
                className="inline-flex items-center justify-center rounded-md border border-accent-primary/60 bg-accent-primary px-5 py-3 text-sm font-semibold text-white transition-all duration-150 hover:border-accent-hover hover:bg-accent-hover"
              >
                {primaryCtaLabelFooter}
              </Link>
              <Link
                to="/privacy"
                className="inline-flex items-center justify-center rounded-md border border-border-default bg-bg-elevated px-5 py-3 text-sm font-semibold text-text-primary transition-colors duration-150 hover:border-border-strong"
              >
                Read Privacy Policy
              </Link>
            </div>
          </div>
        </section>
      </main>
    </PublicLayout>
  )
}

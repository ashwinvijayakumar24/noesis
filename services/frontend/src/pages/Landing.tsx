import { motion } from 'framer-motion'
import {
  LightBulbIcon,
  BeakerIcon,
  ArrowRightIcon,
  ClipboardDocumentCheckIcon,
  ShieldCheckIcon,
  UserIcon,
  AcademicCapIcon,
  CheckBadgeIcon,
  BookOpenIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'
import { Button } from '../components/ui/Button'
import { NoesisLogo } from '../components/ui/NoesisLogo'
import DraftAnalysisShowcase from '../components/draft-analysis/DraftAnalysisShowcase'

const FAQ_ITEMS = [
  {
    question: 'What is Noesis?',
    answer: 'Noesis is a draft-aware research workspace. You build a literature library, generate a Literature Map, discover missing papers, and analyze your draft with literature-grounded feedback before submission.',
  },
  {
    question: 'How is Noesis different from ChatGPT or other AI writing tools?',
    answer: 'Noesis does not write or rewrite your paper. It reviews the draft against your project literature, surfaces unsupported claims, missing citations, and coverage gaps, and keeps the feedback tied to real sources instead of generic chat output.',
  },
  {
    question: 'Does Noesis write my paper for me?',
    answer: 'No. Noesis critiques your existing draft so you can strengthen your own argument, citations, and literature coverage. Your thinking stays central to the paper.',
  },
  {
    question: 'Is Noesis free to use?',
    answer: 'Yes. The free tier includes 2 draft analyses per month, 30 PDF uploads, 30 BibTeX references, 5 Discover searches per day, and 5 Literature Map refreshes per day. Pro is $12/month for higher per-user quotas.',
  },
  {
    question: 'What file types are supported?',
    answer: 'Noesis supports PDF, DOCX, and TXT for draft uploads, and BibTeX (.bib) files for importing your reference library from Zotero, Mendeley, or Endnote.',
  },
]

function FAQ() {
  return (
    <section className="py-24 px-6 sm:px-8 bg-bg-surface" aria-label="Frequently asked questions about the Noesis research feedback workflow">
      <div className="max-w-3xl mx-auto">
        <motion.div
          initial={{ opacity: 0, y: 12 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: false }}
          transition={{ duration: 0.3 }}
          className="text-center mb-12"
        >
          <h2 className="text-4xl sm:text-5xl font-heading font-semibold tracking-tight text-text-primary mb-4">
            Common Questions
          </h2>
          <p className="text-lg text-text-secondary tracking-normal">
            Everything you need to know about Noesis
          </p>
        </motion.div>

        <div className="space-y-3">
          {FAQ_ITEMS.map((item, index) => (
            <motion.div
              key={index}
              initial={{ opacity: 0, y: 8 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: false }}
              transition={{ delay: index * 0.06, duration: 0.3 }}
              className="bg-bg-void border border-border-default rounded-xl overflow-hidden"
            >
              <div className="w-full flex items-center justify-between px-6 py-5 text-left">
                <span className="text-base font-semibold text-text-primary pr-4">{item.question}</span>
                <span className="shrink-0 rounded-md border border-accent-primary/30 px-2 py-1 text-xs font-mono text-accent-primary">
                  Available
                </span>
              </div>
              <p className="px-6 pb-5 text-text-secondary leading-relaxed text-sm">
                {item.answer}
              </p>
            </motion.div>
          ))}
        </div>
      </div>
    </section>
  )
}

interface Testimonial {
  id: string
  name: string
  role: string
  institution: string
  quote: string
  approved: boolean
}

export default function Landing() {
  const [testimonials, setTestimonials] = useState<Testimonial[]>([])

  useEffect(() => {
    document.title = 'Noesis | AI Pre-Submission Peer Review'
    loadTestimonials()
  }, [])

  const loadTestimonials = async () => {
    // TODO: Implement testimonials API endpoint
    // For now, skip loading testimonials
    setTestimonials([])
  }

  const fadeIn = {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.5, ease: 'easeOut' }
  }

  const disabledButtonClass = 'opacity-60 cursor-not-allowed hover:shadow-none hover:-translate-y-0'

  const features = [
    {
      icon: ClipboardDocumentCheckIcon,
      title: 'Two-Pass Draft Analysis',
      description: 'Run a structured editing review first, then a deeper reviewer-style analysis for unsupported claims, weak arguments, citation gaps, and coverage problems.'
    },
    {
      icon: BookOpenIcon,
      title: 'Build the Literature Workspace',
      description: 'Upload PDFs, import BibTeX, and save discovered papers into one project library. Your draft is analyzed against the literature you are actually working with.'
    },
    {
      icon: BeakerIcon,
      title: 'Literature Map and Discovery',
      description: 'Generate a Literature Map to surface themes, gaps, and conflicts, then use Discover to find missing papers from trusted academic sources and add them to the project.'
    },
    {
      icon: LightBulbIcon,
      title: 'Grounded and Private',
      description: 'Noesis keeps the workflow project-based, shows source-grounded support where available, and treats your draft as a private workspace artifact rather than public training data.'
    }
  ]

  const useCases = [
    {
      role: 'PIs & Postdocs',
      description: 'Run lab drafts through a consistent pre-submission review flow. Catch unsupported claims, missing literature, and weak evidence before the manuscript leaves the group.',
      impact: 'Protect submission timelines'
    },
    {
      role: 'PhD Students',
      description: 'Get structured feedback before sending a draft to your advisor. See where the argument is weak, where citations are missing, and which papers may still need to be added.',
      impact: 'Confident revisions'
    },
    {
      role: 'Grant Writers',
      description: 'Strengthen proposals and research narratives with better literature coverage, clearer support for claims, and a cleaner revision workflow.',
      impact: 'Stronger grant applications'
    }
  ]

  return (
    <div className="min-h-screen bg-bg-void text-text-primary">
      {/* Navigation - Compact Dark Header */}
      <motion.nav
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="fixed top-0 left-0 right-0 z-50 bg-bg-surface/95 backdrop-blur-md border-b border-border-default"
      >
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center">
              <NoesisLogo size="md" />
            </div>
            <div className="flex items-center gap-4">
              <button
                type="button"
                disabled
                className="px-4 py-2 text-sm font-medium text-text-muted cursor-not-allowed opacity-70"
              >
                Sign In Paused
              </button>
              <Button
                disabled
                variant="primary"
                size="sm"
                className={disabledButtonClass}
              >
                Beta Coming Soon
              </Button>
            </div>
          </div>
        </div>
      </motion.nav>

      {/* Hero Section - Two Column Layout */}
      <section className="relative pt-28 pb-12 sm:pt-36 sm:pb-14 px-6 sm:px-8 overflow-hidden bg-gradient-to-br from-bg-void via-bg-surface to-bg-void">
        <div className="max-w-7xl mx-auto">
          <div className="grid items-center gap-10 lg:grid-cols-[minmax(0,0.88fr)_minmax(0,1.12fr)] xl:gap-14">

            <motion.div
              className="relative z-10 space-y-8 text-center lg:text-left"
              initial="initial"
              animate="animate"
              variants={{ animate: { transition: { staggerChildren: 0.15 } } }}
            >
              <motion.h1
                variants={fadeIn}
                className="text-4xl sm:text-5xl xl:text-6xl font-heading font-semibold leading-display tracking-tightest"
              >
                AI Research Feedback{' '}
                <span className="text-accent-primary">Before Submission</span>
              </motion.h1>

              <motion.div
                variants={fadeIn}
                className="mx-auto inline-flex items-center rounded-lg border border-accent-primary bg-accent-primary px-4 py-2 text-sm font-semibold text-white shadow-sm lg:mx-0"
              >
                Beta access is paused while Noesis is being reworked. A new version is coming soon.
              </motion.div>

              <motion.p
                variants={fadeIn}
                className="mx-auto max-w-3xl text-lg leading-body-large tracking-normal text-text-secondary sm:text-xl lg:mx-0 lg:max-w-2xl"
              >
                Build a project library, generate a Literature Map, discover missing papers, and run two-pass draft analysis grounded in the literature behind your manuscript.
              </motion.p>

              <motion.div
                variants={fadeIn}
                className="flex flex-col items-center justify-center gap-4 sm:flex-row lg:justify-start"
              >
                <Button
                  disabled
                  variant="primary"
                  size="lg"
                  className={`flex items-center gap-2 group ${disabledButtonClass}`}
                >
                  Beta Coming Soon
                  <ArrowRightIcon className="h-5 w-5" />
                </Button>
              </motion.div>

              <motion.div
                variants={fadeIn}
                className="flex flex-wrap items-center justify-center gap-6 text-sm text-text-muted font-mono lg:justify-start"
              >
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-accent-primary" />
                  <span>Beta paused</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-accent-primary" />
                  <span>New version coming soon</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-accent-primary" />
                  <span>Private workspace</span>
                </div>
              </motion.div>
            </motion.div>

          <motion.div
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.5, delay: 0.2 }}
            className="relative z-10"
          >
            <DraftAnalysisShowcase variant="preview" showDocumentPane={false} />
          </motion.div>
          </div>
        </div>
      </section>

      {/* Features Section - Professional Dark Cards */}
      <section id="features" className="py-16 px-6 sm:px-8 bg-bg-void">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false }}
            transition={{ duration: 0.3 }}
            className="mb-16 text-center"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-heading font-semibold leading-heading-1 tracking-tighter text-text-primary mb-6">
              Literature-grounded{' '}
              <span className="text-accent-primary relative inline-block">
                Draft Review
                <motion.span
                  className="absolute -bottom-1 left-0 right-0 h-0.5 bg-accent-primary/60 rounded-full"
                  initial={{ scaleX: 0, originX: 0 }}
                  whileInView={{ scaleX: 1 }}
                  viewport={{ once: false }}
                  transition={{ delay: 0.4, duration: 0.7, ease: 'easeOut' }}
                />
              </span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary max-w-3xl mx-auto leading-body-large tracking-normal">
              Built to critique a manuscript against its literature, not to write the paper for you
            </p>
          </motion.div>

          {/* Feature Cards - Rose Accent Hover */}
          <div className="grid md:grid-cols-2 gap-6 lg:gap-8">
            {features.map((feature, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 32, scale: 0.96 }}
                whileInView={{ opacity: 1, y: 0, scale: 1 }}
                viewport={{ once: false, amount: 0.15 }}
                transition={{ delay: index * 0.08, duration: 0.35, ease: [0.25, 0.46, 0.45, 0.94] }}
                className="group bg-bg-surface border border-border-default rounded-lg p-8 hover:border-accent-primary/30 hover:-translate-y-0.5 transition-all duration-150 shadow-xs hover:shadow-sm"
              >
                <div className="space-y-6">
                  {/* Icon with Rose Accent on Hover */}
                  <div className="w-14 h-14 rounded-lg bg-bg-subtle border border-border-default flex items-center justify-center group-hover:border-accent-primary/50 group-hover:bg-accent-light transition-all duration-150">
                    <feature.icon
                      className="w-7 h-7 text-text-tertiary group-hover:text-accent-primary transition-colors duration-150"
                      strokeWidth={1.5}
                    />
                  </div>

                  {/* Content */}
                  <div className="space-y-3">
                    <h3 className="text-2xl sm:text-3xl font-sans font-semibold text-text-primary leading-heading-3 tracking-normal">
                      {feature.title}
                    </h3>
                    <p className="text-text-secondary leading-body tracking-normal">
                      {feature.description}
                    </p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust & Academic Integrity Section - Dark Theme with Rose Accent */}
      <section className="relative py-16 overflow-hidden">
        <div className="max-w-6xl mx-auto px-6 sm:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.3 }}
            viewport={{ once: false }}
            className="bg-bg-surface border border-accent-primary/20 rounded-lg p-8 sm:p-12"
          >
            <h3 className="text-3xl sm:text-4xl font-heading font-semibold text-text-primary mb-8 text-center tracking-tight">
              Built on <span className="text-accent-primary">Trust & Academic Integrity</span>
            </h3>

            <div className="grid sm:grid-cols-2 gap-8">
              <div className="flex items-start gap-4">
                <div className="shrink-0 mt-1 w-12 h-12 rounded-lg bg-accent-light flex items-center justify-center border border-accent-primary/30">
                  <ShieldCheckIcon className="h-6 w-6 text-accent-primary" />
                </div>
                <div>
                  <h4 className="font-sans font-semibold text-text-primary mb-2 text-lg tracking-normal">Your Data, Your Research</h4>
                  <p className="text-sm text-text-secondary leading-body-small tracking-normal">
                    Your drafts and documents are never used to train AI models. Your research remains private and secure.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="shrink-0 mt-1 w-12 h-12 rounded-lg bg-accent-light flex items-center justify-center border border-accent-primary/30">
                  <UserIcon className="h-6 w-6 text-accent-primary" />
                </div>
                <div>
                  <h4 className="font-sans font-semibold text-text-primary mb-2 text-lg tracking-normal">You Own Your Work</h4>
                  <p className="text-sm text-text-secondary leading-body-small tracking-normal">
                    Noesis critiques and suggests. You decide what changes belong in the manuscript.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="shrink-0 mt-1 w-12 h-12 rounded-lg bg-accent-light flex items-center justify-center border border-accent-primary/30">
                  <AcademicCapIcon className="h-6 w-6 text-accent-primary" />
                </div>
                <div>
                  <h4 className="font-sans font-semibold text-text-primary mb-2 text-lg tracking-normal">Research Integrity</h4>
                  <p className="text-sm text-text-secondary leading-body-small tracking-normal">
                    We do not auto-write. We help you identify weaknesses, missing citations, and literature gaps before submission.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="shrink-0 mt-1 w-12 h-12 rounded-lg bg-accent-light flex items-center justify-center border border-accent-primary/30">
                  <CheckBadgeIcon className="h-6 w-6 text-accent-primary" />
                </div>
                <div>
                  <h4 className="font-sans font-semibold text-text-primary mb-2 text-lg tracking-normal">Real Citations Only</h4>
                  <p className="text-sm text-text-secondary leading-body-small tracking-normal">
                    Citation suggestions come from your uploaded literature and linked discovery sources, not invented references.
                  </p>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Use Cases */}
      <section className="py-32 px-6 sm:px-8">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false }}
            transition={{ duration: 0.5 }}
            className="mb-16 text-center"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-heading font-semibold leading-[1.2] tracking-tight text-text-primary mb-6">
              Built for <span className="text-accent-primary">Serious Researchers</span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary tracking-normal">
              Designed for PhD students, postdocs, faculty, and research teams
            </p>
          </motion.div>

          <div className="space-y-6">
            {useCases.map((useCase, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: false }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className="group bg-bg-surface border border-border-default rounded-lg p-8 hover:border-accent-primary/30 hover:-translate-y-0.5 transition-all duration-150"
              >
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
                  <div className="flex-1 space-y-3">
                    <h3 className="text-2xl sm:text-3xl font-sans font-semibold text-text-primary tracking-normal">
                      {useCase.role}
                    </h3>
                    <p className="text-lg text-text-secondary leading-relaxed tracking-normal">
                      {useCase.description}
                    </p>
                  </div>
                  <div className="md:text-right shrink-0">
                    <div className="inline-flex items-center gap-2 px-4 py-2 bg-bg-elevated border border-border-default rounded-lg">
                      <div className="h-2 w-2 rounded-full bg-accent-primary"></div>
                      <div className="text-sm font-sans font-medium text-text-primary">
                        {useCase.impact}
                      </div>
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Trusted by Researchers Section — removed pending verified user list */}

      {/* Testimonials Section */}
      {testimonials.length > 0 && (
        <section className="py-24 px-6 sm:px-8 bg-bg-surface">
          <div className="max-w-6xl mx-auto">
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: false }}
              transition={{ duration: 0.5 }}
              className="text-center mb-16"
            >
              <h2 className="text-4xl sm:text-5xl font-sans font-semibold text-text-primary mb-4 tracking-tight">
                What Researchers Are Saying
              </h2>
              <p className="text-xl text-text-secondary tracking-normal">
                Real feedback from academics using Noesis
              </p>
            </motion.div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
              {testimonials.map((testimonial, index) => (
                <motion.div
                  key={testimonial.id}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: false }}
                  transition={{ delay: index * 0.1, duration: 0.5 }}
                  className="bg-bg-void border border-border-default rounded-lg p-8"
                >
                  <div className="mb-6">
                    <p className="text-base text-text-secondary leading-relaxed tracking-normal italic">
                      "{testimonial.quote}"
                    </p>
                  </div>
                  <div className="border-t border-border-default pt-4">
                    <div className="font-sans font-semibold text-text-primary text-sm tracking-normal">
                      {testimonial.name}
                    </div>
                    <div className="text-xs text-text-tertiary font-mono mt-1">
                      {testimonial.role}
                    </div>
                    <div className="text-xs text-text-muted font-mono mt-1">
                      {testimonial.institution}
                    </div>
                  </div>
                </motion.div>
              ))}
            </div>
          </div>
        </section>
      )}

      {/* How It Works - Clean, Professional */}
      <section className="py-32 px-6 sm:px-8 bg-bg-void">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false }}
            className="mb-20 text-center"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-heading font-semibold leading-[1.2] tracking-tight text-text-primary mb-6">
              A clear workflow from literature to draft
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary tracking-normal">
              Get started in four steps
            </p>
          </motion.div>

          <div className="space-y-24">
            {[
              {
                number: '01',
                title: 'Build your literature library',
                description: 'Upload PDFs, import BibTeX, and organize the papers that matter for the draft you are writing.',
                color: 'rose'
              },
              {
                number: '02',
                title: 'Generate a Literature Map',
                description: 'Synthesize the field inside the project to see evidence clusters, research gaps, conflicts, and where your current library is still thin.',
                color: 'teal'
              },
              {
                number: '03',
                title: 'Discover missing papers',
                description: 'Use project-aware recommendations to find papers that strengthen weak sections or fill literature gaps before submission.',
                color: 'indigo'
              },
              {
                number: '04',
                title: 'Run two-pass draft analysis',
                description: 'Start with editing and citation checks, then move into deeper reviewer-style feedback on claims, evidence, coverage, and argument quality.',
                color: 'rose'
              }
            ].map((step, index) => (
              <div
                key={index}
                className={`flex flex-col md:flex-row gap-12 items-center ${
                  index % 2 === 1 ? 'md:flex-row-reverse' : ''
                }`}
              >
                {/* Number Badge - spring pop-in */}
                <motion.div
                  initial={{ opacity: 0, scale: 0.4 }}
                  whileInView={{ opacity: 1, scale: 1 }}
                  viewport={{ once: false, amount: 0.5 }}
                  transition={{
                    delay: index * 0.1,
                    duration: 0.5,
                    type: 'spring',
                    stiffness: 180,
                    damping: 14
                  }}
                  className="shrink-0 w-32 h-32 flex items-center justify-center"
                >
                <span className={`text-6xl font-heading font-bold ${
                    step.color === 'rose' ? 'text-accent-primary' :
                    step.color === 'teal' ? 'text-teal-primary' :
                    'text-indigo-primary'
                  }`}>
                    {step.number}
                  </span>
                </motion.div>

                {/* Content Card - slide in from alternating side */}
                <motion.div
                  initial={{ opacity: 0, x: index % 2 === 0 ? 48 : -48 }}
                  whileInView={{ opacity: 1, x: 0 }}
                  viewport={{ once: false, amount: 0.3 }}
                  transition={{ delay: index * 0.1 + 0.1, duration: 0.4, ease: 'easeOut' }}
                className="flex-1"
              >
                <div className="bg-bg-void border border-border-default rounded-lg p-8 space-y-4">
                    <h3 className="text-3xl sm:text-4xl font-heading font-semibold text-text-primary tracking-normal">
                      {step.title}
                    </h3>
                    <p className="text-lg text-text-secondary leading-relaxed tracking-normal">
                      {step.description}
                    </p>
                  </div>
                </motion.div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section - Professional Dark */}
      <section className="relative py-32 bg-bg-void overflow-visible">
        <div className="max-w-7xl mx-auto px-6 sm:px-8 overflow-visible">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            viewport={{ once: false }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-heading font-semibold leading-[1.2] tracking-tight text-text-primary mb-6">
              <span className="text-accent-primary">Transparent</span>, Research-Friendly Pricing
            </h2>
            <p className="text-lg sm:text-xl text-text-secondary max-w-3xl mx-auto tracking-normal">
              Choose the plan that fits your research needs. Start free with clear per-user quotas, then upgrade when you need more volume or team access.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-4 gap-8 max-w-7xl mx-auto pt-8 overflow-visible">
            {/* Free Plan */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1, duration: 0.5 }}
              viewport={{ once: false }}
              className="bg-bg-surface border-2 border-accent-primary rounded-lg p-8 shadow-md flex flex-col"
            >
              <div className="flex flex-col flex-1">
                <div className="mb-6">
                  <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
                    Free
                  </h3>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-text-primary">$0</span>
                    <span className="text-text-tertiary">/month</span>
                  </div>
                  <p className="text-sm text-text-tertiary mt-2">
                    For researchers working on their first paper
                  </p>
                </div>

                <ul className="space-y-3 mb-6 flex-1">
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">2 draft analyses per month</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">30 PDF uploads per month total</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">30 BibTeX references per month total</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">5 Discover searches per day</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">5 Literature Map refreshes per day</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Citation gap detection & BibTeX export</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">All core features</span>
                  </li>
                </ul>

                <div className="mt-auto space-y-4">
                  <button
                    disabled
                    className="w-full py-3 px-4 bg-surface border-2 border-accent-primary text-text-primary font-semibold rounded-lg cursor-not-allowed text-center"
                  >
                    Beta Coming Soon
                  </button>

                </div>
              </div>
            </motion.div>

            {/* Pro Plan */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2, duration: 0.5 }}
              viewport={{ once: false }}
              className="bg-bg-surface border border-border-default rounded-lg p-8 relative hover:border-accent-primary transition-all duration-200 flex flex-col"
            >
              <div className="flex flex-col flex-1">
                <div className="mb-6">
                  <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
                    Pro
                  </h3>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-text-primary">$12</span>
                    <span className="text-text-tertiary">/month</span>
                  </div>
                  <p className="text-sm text-text-tertiary mt-2">
                    For active researchers with higher per-user quotas
                  </p>
                </div>

                <ul className="space-y-3 mb-6 flex-1">
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">20 draft analyses per month</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">100 PDF uploads per month total</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">100 BibTeX references per month total</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">50 Discover searches per day</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Unlimited Literature Map refreshes</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Priority processing</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Larger draft size limits (50+ pages)</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Advanced citation suggestions</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Email support</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Everything in Free</span>
                  </li>
                </ul>

                <div className="mt-auto space-y-4">
                  <button
                    disabled
                    className="block w-full py-3 px-4 bg-accent-primary text-white font-semibold rounded-lg text-center opacity-50 cursor-not-allowed"
                  >
                    Beta Coming Soon
                  </button>
                </div>
              </div>
            </motion.div>

            {/* Team Plan */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.5 }}
              viewport={{ once: false }}
              className="bg-bg-surface border border-border-default rounded-lg p-8 relative hover:border-accent-primary transition-all duration-200 flex flex-col"
            >
              <div className="flex flex-col flex-1">
                <div className="mb-6">
                  <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
                    Team
                  </h3>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-text-primary">$20</span>
                    <span className="text-text-tertiary">/user/month</span>
                  </div>
                  <p className="text-sm text-text-tertiary mt-2">
                    For research groups with 2-3 users
                  </p>
                </div>

                <ul className="space-y-3 mb-6 flex-1">
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Everything in Pro</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">2-3 users billed per seat</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Effectively unlimited usage</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Shared project workspaces</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Team collaboration features</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Shared literature libraries</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Priority support</span>
                  </li>
                </ul>

                <div className="mt-auto space-y-4">
                  <button
                    disabled
                    className="block w-full py-3 px-4 bg-accent-primary text-white font-semibold rounded-lg text-center opacity-50 cursor-not-allowed"
                  >
                    Beta Coming Soon
                  </button>
                </div>
              </div>
            </motion.div>

            {/* Enterprise Plan */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.4, duration: 0.5 }}
              viewport={{ once: false }}
              className="bg-bg-surface border border-border-default rounded-lg p-8 relative hover:border-accent-primary transition-all duration-200 flex flex-col"
            >
              <div className="flex flex-col flex-1">
                <div className="mb-6">
                  <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
                    Enterprise
                  </h3>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-text-primary">Custom</span>
                  </div>
                  <p className="text-sm text-text-tertiary mt-2">
                    For large institutions and universities
                  </p>
                </div>

                <ul className="space-y-3 mb-6 flex-1">
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Everything in Team</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">SSO integration (SAML, OAuth)</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Custom deployment options</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Dedicated account manager</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Custom SLA & uptime guarantees</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Volume pricing discounts</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Advanced compliance support</span>
                  </li>
                </ul>

                <div className="mt-auto space-y-4">
                  <button
                    disabled
                    className="block w-full py-3 px-4 border-2 border-accent-primary text-accent-primary font-semibold rounded-lg text-center opacity-50 cursor-not-allowed"
                  >
                    Beta Coming Soon
                  </button>
                </div>
              </div>
            </motion.div>
          </div>

        </div>
      </section>

      {/* FAQ Section */}
      <FAQ />

      {/* CTA Section - Professional Dark */}
      <section className="py-32 px-6 sm:px-8 relative overflow-hidden bg-bg-void">
        <div className="max-w-4xl mx-auto relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: false }}
            className="text-center space-y-8 bg-bg-surface border border-accent-primary/20 rounded-xl p-12 sm:p-16"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-sans font-semibold leading-[1.1] tracking-tight text-text-primary">
              Ready to strengthen <br className="hidden sm:block" />
              <span className="text-accent-primary">your research?</span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary max-w-2xl mx-auto tracking-normal">
              Beta access is paused while the product is being reworked. The research workflow details remain available here.
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <Button
                disabled
                variant="primary"
                size="lg"
                className={disabledButtonClass}
              >
                Beta Coming Soon
              </Button>
              <button
                type="button"
                disabled
                className="px-8 py-4 border border-border-default text-text-muted font-semibold rounded-md opacity-60 cursor-not-allowed text-lg"
              >
                Sign In Paused
              </button>
            </div>

            {/* Trust Indicators - Rose Accent */}
            <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-8 pt-8 text-sm text-text-muted font-mono">
              <div className="flex items-center gap-2">
                <CheckBadgeIcon className="h-4 w-4 text-accent-primary" />
                <span>Beta paused</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckBadgeIcon className="h-4 w-4 text-accent-primary" />
                <span>New version coming soon</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckBadgeIcon className="h-4 w-4 text-accent-primary" />
                <span>Privacy-first</span>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer - Professional Dark */}
      <footer className="py-12 px-6 sm:px-8 border-t border-border-default bg-bg-void">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div className="flex items-center">
              <NoesisLogo size="md" />
            </div>
            <div className="text-text-muted text-sm font-mono">
              © 2026 Noesis. All rights reserved.
            </div>
            <div className="flex items-center gap-6 text-text-muted text-sm">
              <span className="cursor-not-allowed opacity-70">Privacy</span>
              <span className="cursor-not-allowed opacity-70">Terms</span>
              <a href="mailto:privacy@noesis.app" className="hover:text-accent-primary transition-colors duration-150">Contact</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

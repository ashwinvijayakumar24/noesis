import { motion, AnimatePresence } from 'framer-motion'
import { useNavigate, Link } from 'react-router-dom'
import {
  DocumentTextIcon as _DocumentTextIcon,
  ChatBubbleLeftRightIcon as _ChatBubbleLeftRightIcon,
  LightBulbIcon,
  BeakerIcon,
  ArrowRightIcon,
  ClipboardDocumentCheckIcon,
  ShieldCheckIcon,
  UserIcon,
  AcademicCapIcon,
  CheckBadgeIcon,
  DocumentArrowDownIcon as _DocumentArrowDownIcon,
  BookOpenIcon,
  ExclamationCircleIcon,
  ExclamationTriangleIcon,
} from '@heroicons/react/24/outline'
import { useEffect, useState } from 'react'
import { Button } from '../components/ui/Button'
import { NoesisLogo } from '../components/ui/NoesisLogo'

const TABS = [
  { id: 'analysis', label: 'Draft Analysis' },
  { id: 'feedback', label: 'Reviewer Feedback' },
  { id: 'gaps', label: 'Coverage Gaps' },
] as const

type TabId = typeof TABS[number]['id']

function AnalysisTab() {
  return (
    <div className="space-y-3">
      <div className="bg-bg-elevated border-l-4 border-l-accent-primary border border-border-default rounded-lg p-4">
        <div className="flex items-center gap-2 mb-3">
          <ExclamationCircleIcon className="h-4 w-4 text-accent-primary shrink-0" />
          <h3 className="text-sm font-semibold text-text-primary">Top Action Items</h3>
        </div>
        <ol className="space-y-2">
          {[
            'Add primary citations for CRISPR efficiency claims in §2.3',
            'Address off-target effect coverage gap in Methods section',
            'Strengthen Discussion with Cas9 variant comparison data',
          ].map((action, i) => (
            <li key={i} className="flex items-start gap-2.5">
              <span className="flex-shrink-0 w-5 h-5 rounded-full bg-accent-primary text-white text-xs font-semibold flex items-center justify-center mt-0.5">
                {i + 1}
              </span>
              <span className="text-sm text-text-secondary leading-snug">{action}</span>
            </li>
          ))}
        </ol>
      </div>

      <div className="bg-bg-surface rounded-lg border border-warning p-4">
        <div className="flex items-center gap-4 mb-4">
          <ExclamationTriangleIcon className="h-8 w-8 text-warning shrink-0" />
          <div>
            <div className="flex items-baseline gap-2">
              <span className="text-5xl font-sans font-extrabold text-warning tracking-tighter">74</span>
              <span className="text-sm font-semibold text-text-secondary">/ 100 · Needs Work</span>
            </div>
            <p className="text-xs font-mono text-text-muted mt-0.5">CRISPR-Cas9 Off-Target Effects — v2</p>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-2">
          {[
            { label: 'Claims', value: '12', note: '4 need citation', color: 'text-warning' },
            { label: 'Gaps', value: '5', note: '2 critical', color: 'text-error' },
            { label: 'Feedback', value: '8', note: '3 critical', color: 'text-error' },
          ].map(m => (
            <div key={m.label} className="bg-bg-elevated rounded-lg p-3 border border-border-default">
              <p className="text-xs text-text-muted font-mono uppercase tracking-wide mb-1">{m.label}</p>
              <p className="text-2xl font-sans font-bold text-text-primary">{m.value}</p>
              <p className={`text-xs font-medium ${m.color}`}>{m.note}</p>
            </div>
          ))}
        </div>
      </div>
    </div>
  )
}

function FeedbackTab() {
  return (
    <div className="space-y-3">
      <div className="flex gap-2 flex-wrap">
        {['Introduction', 'Methods ⚠', 'Results', 'Discussion'].map((s, i) => (
          <button key={s} className={`px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all duration-150 ${
            i === 1
              ? 'bg-bg-elevated text-text-primary border-border-subtle'
              : 'bg-bg-surface text-text-secondary border-border-default'
          }`}>
            {s}
          </button>
        ))}
      </div>

      <div className="flex space-x-1 border-b border-border-default">
        <button className="px-4 py-2 text-sm font-semibold border-b-2 border-accent-primary text-text-primary">
          New
          <span className="ml-1.5 px-2 py-0.5 rounded-full text-xs bg-accent-primary text-white font-semibold">7</span>
        </button>
        <button className="px-4 py-2 text-sm font-semibold border-b-2 border-transparent text-text-secondary">
          Saved
          <span className="ml-1.5 px-2 py-0.5 rounded-full text-xs bg-bg-elevated text-text-muted border border-border-default">2</span>
        </button>
        <button className="px-4 py-2 text-sm font-semibold border-b-2 border-transparent text-text-secondary">
          Dismissed
        </button>
      </div>

      <div className="bg-bg-surface rounded-lg border border-border-default border-l-4 border-l-accent-primary p-4 transition-all duration-150">
        <div className="flex items-start justify-between mb-3">
          <div className="flex items-center gap-2">
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-mono font-semibold uppercase bg-accent-primary text-white">
              Unsupported Claim
            </span>
            <span className="px-2.5 py-1 rounded-md text-xs font-mono font-semibold uppercase bg-error text-white">
              HIGH
            </span>
          </div>
        </div>
        <p className="text-sm text-text-primary leading-relaxed mb-3">
          The reported CRISPR efficiency of &gt;85% in vivo lacks primary data support in this manuscript.
        </p>
        <div className="flex gap-2 mb-3">
          <span className="text-xs font-mono text-text-secondary bg-bg-elevated px-2 py-1 rounded-md border border-border-default">§ Methods · 2.3</span>
          <span className="text-xs font-mono text-text-secondary bg-bg-elevated px-2 py-1 rounded-md border border-border-default">High confidence</span>
        </div>
        <div className="border-t border-border-default pt-3 flex items-center gap-2">
          <p className="text-xs text-text-muted">Suggested:</p>
          <span className="text-xs font-mono text-accent-primary">Zhang et al. (2023) · 94% match</span>
        </div>
      </div>
    </div>
  )
}

function GapsTab() {
  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-sm font-semibold text-text-secondary">Coverage Analysis</h3>
        <span className="text-xs font-mono text-white bg-error px-2 py-0.5 rounded-md font-semibold">3 Critical Gaps</span>
      </div>
      {[
        { type: 'Missing Methodology', priority: 'CRITICAL', color: 'error',
          title: 'Off-target effect measurement protocols not cited',
          suggestion: 'Anzalone et al. (2020), Kleinstiver et al. (2019)' },
        { type: 'Theoretical Gap', priority: 'HIGH', color: 'warning',
          title: 'Cas9 variant comparison literature absent from §3',
          suggestion: 'Spencer & Zhang (2022)' },
        { type: 'Statistical Support', priority: 'HIGH', color: 'warning',
          title: 'In vivo efficiency claims lack comparative studies',
          suggestion: 'Liu et al. (2021)' },
      ].map((gap, i) => (
        <div key={i} className={`bg-bg-surface rounded-lg border-l-2 ${
          gap.color === 'error' ? 'border-l-error' : 'border-l-warning'
        } border border-border-default p-3`}>
          <div className="flex items-center gap-2 mb-1.5">
            <span className={`text-xs font-mono font-semibold px-2 py-0.5 rounded-md text-white ${
              gap.color === 'error' ? 'bg-error' : 'bg-warning'}`}>{gap.priority}</span>
            <span className="text-xs text-text-muted">{gap.type}</span>
          </div>
          <p className="text-sm text-text-primary mb-2">{gap.title}</p>
          <p className="text-xs text-text-muted">Suggested: <span className="text-accent-primary font-mono">{gap.suggestion}</span></p>
        </div>
      ))}
    </div>
  )
}

function ProductShowcase() {
  const [activeTab, setActiveTab] = useState<TabId>('analysis')
  return (
    <div className="bg-bg-surface border border-border-default rounded-xl overflow-hidden shadow-2xl">
      <div className="flex items-center gap-3 px-4 py-3 bg-bg-elevated border-b border-border-default">
        <div className="flex gap-1.5 shrink-0">
          <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
          <div className="w-2.5 h-2.5 rounded-full bg-yellow-500" />
          <div className="w-2.5 h-2.5 rounded-full bg-green-500" />
        </div>
        <div className="flex gap-1 ml-2">
          {TABS.map(tab => (
            <button
              key={tab.id}
              onClick={() => setActiveTab(tab.id)}
              className={`px-3 py-1.5 rounded-md text-xs font-semibold transition-all duration-150 ${
                activeTab === tab.id
                  ? 'bg-bg-surface text-text-primary border border-border-default'
                  : 'text-text-muted hover:text-text-secondary'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>
      <div className="p-5 min-h-[380px] relative overflow-hidden">
        <AnimatePresence mode="wait">
          <motion.div
            key={activeTab}
            initial={{ opacity: 0, x: 8 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -8 }}
            transition={{ duration: 0.15 }}
          >
            {activeTab === 'analysis' && <AnalysisTab />}
            {activeTab === 'feedback' && <FeedbackTab />}
            {activeTab === 'gaps' && <GapsTab />}
          </motion.div>
        </AnimatePresence>
        <div className="absolute bottom-0 left-0 right-0 h-14 bg-gradient-to-t from-bg-void/70 to-transparent pointer-events-none" />
      </div>
    </div>
  )
}

const FAQ_ITEMS = [
  {
    question: 'What is Noesis?',
    answer: 'Noesis is an AI pre-submission peer review tool. Upload your research draft and Noesis finds unsupported claims, citation gaps, and methodology blind spots — grounded in your literature and 200M+ papers.',
  },
  {
    question: 'How is Noesis different from ChatGPT or other AI writing tools?',
    answer: 'Noesis does not write or rewrite your paper. It acts like an expert academic reviewer: identifying what a hostile reviewer would flag before you submit. Every piece of feedback is grounded in your uploaded literature — no hallucinated references.',
  },
  {
    question: 'Does Noesis write my paper for me?',
    answer: 'No. Noesis critiques your existing draft — finding weaknesses, unsupported claims, and citation gaps — so you can strengthen your own arguments. Your thinking, your paper.',
  },
  {
    question: 'Is Noesis free to use?',
    answer: 'Yes. The free tier includes 5 draft analyses per month, 30 PDF uploads, and access to 200M+ papers. Pro plan is $12/month for heavier use.',
  },
  {
    question: 'What file types are supported?',
    answer: 'Noesis supports PDF, DOCX, and TXT for draft uploads, and BibTeX (.bib) files for importing your reference library from Zotero, Mendeley, or Endnote.',
  },
]

function FAQ() {
  const [openIndex, setOpenIndex] = useState<number | null>(null)

  return (
    <section className="py-24 px-6 sm:px-8 bg-bg-surface" aria-label="Frequently asked questions about Noesis pre-submission peer review">
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
              <button
                onClick={() => setOpenIndex(openIndex === index ? null : index)}
                className="w-full flex items-center justify-between px-6 py-5 text-left hover:bg-bg-surface/50 transition-colors duration-150"
                aria-expanded={openIndex === index}
              >
                <span className="text-base font-semibold text-text-primary pr-4">{item.question}</span>
                <span className={`shrink-0 w-5 h-5 flex items-center justify-center text-accent-primary transition-transform duration-150 ${openIndex === index ? 'rotate-45' : ''}`}>
                  <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true">
                    <path d="M8 2v12M2 8h12" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                  </svg>
                </span>
              </button>
              <AnimatePresence initial={false}>
                {openIndex === index && (
                  <motion.div
                    key="content"
                    initial={{ height: 0, opacity: 0 }}
                    animate={{ height: 'auto', opacity: 1 }}
                    exit={{ height: 0, opacity: 0 }}
                    transition={{ duration: 0.2, ease: 'easeInOut' }}
                    className="overflow-hidden"
                  >
                    <p className="px-6 pb-5 text-text-secondary leading-relaxed text-sm">
                      {item.answer}
                    </p>
                  </motion.div>
                )}
              </AnimatePresence>
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
  const navigate = useNavigate()
  const [testimonials, setTestimonials] = useState<Testimonial[]>([])

  useEffect(() => {
    document.title = 'Noesis - Know What Reviewer 2 Will Say Before You Submit'
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

  const features = [
    {
      icon: ClipboardDocumentCheckIcon,
      title: 'Expert Reviewer Feedback',
      description: 'Upload your draft and get expert academic reviewer-style critique: unsupported claims, missing citations, coverage gaps, and argument weaknesses — with source passages shown.'
    },
    {
      icon: BookOpenIcon,
      title: 'Import Your Library Instantly',
      description: 'Export from Zotero, Mendeley, or Endnote as a .bib file and import in seconds. No rebuilding your library from scratch — your references are ready immediately.'
    },
    {
      icon: BeakerIcon,
      title: 'Discover 200M+ Papers',
      description: 'Not just your uploads. Noesis searches PubMed, arXiv, and Semantic Scholar to surface papers relevant to your coverage gaps — then adds them to your project automatically.'
    },
    {
      icon: LightBulbIcon,
      title: 'Grounded in Your Literature',
      description: 'Every piece of feedback shows the exact passage from your uploaded literature that informed it. Not a black box — see the AI\'s reasoning and evaluate it yourself.'
    }
  ]

  const useCases = [
    {
      role: 'PIs & Postdocs',
      description: 'Run every lab draft through Noesis before submission. Catch unsupported claims and coverage gaps before Reviewer 2 does. One caught comment = weeks saved.',
      impact: 'Protect submission timelines'
    },
    {
      role: 'PhD Students',
      description: 'Get expert reviewer-style feedback before your advisor sees your draft. Know the weaknesses before the high-stakes conversation.',
      impact: 'Confident revisions'
    },
    {
      role: 'Grant Writers',
      description: 'Strengthen NIH and NSF proposals with comprehensive literature coverage analysis. Identify gaps reviewers will flag before the study section sees your application.',
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
                onClick={() => navigate('/login')}
                className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors duration-150"
              >
                Sign In
              </button>
              <Button
                onClick={() => navigate('/signup')}
                variant="primary"
                size="sm"
              >
                Get Started
              </Button>
            </div>
          </div>
        </div>
      </motion.nav>

      {/* Hero Section - Two Column Layout */}
      <section className="relative pt-28 pb-16 sm:pt-36 sm:pb-20 px-6 sm:px-8 overflow-hidden bg-gradient-to-br from-bg-void via-bg-surface to-bg-void">
        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-2 gap-12 xl:gap-16 items-center">

            {/* Left Column — Text + CTA */}
            <motion.div
              className="space-y-8 relative z-10 text-center lg:text-left"
              initial="initial"
              animate="animate"
              variants={{ animate: { transition: { staggerChildren: 0.15 } } }}
            >
              <motion.h1
                variants={fadeIn}
                className="text-4xl sm:text-5xl xl:text-6xl font-heading font-semibold leading-display tracking-tightest"
              >
                Know What{' '}
                <span className="text-accent-primary">Reviewer 2</span>{' '}
                Will Say Before You Submit
              </motion.h1>

              <motion.p
                variants={fadeIn}
                className="text-lg sm:text-xl text-text-secondary leading-body-large tracking-normal max-w-xl mx-auto lg:mx-0"
              >
                Upload your draft. Noesis finds unsupported claims, citation gaps, and blind spots — grounded in your literature and 200M+ papers. Not AI writing. Expert AI review.
              </motion.p>

              <motion.div
                variants={fadeIn}
                className="flex flex-col sm:flex-row items-center lg:items-start justify-center lg:justify-start gap-4"
              >
                <Button
                  onClick={() => navigate('/signup')}
                  variant="primary"
                  size="lg"
                  className="flex items-center gap-2 group"
                >
                  Get Started Free
                  <ArrowRightIcon className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
                </Button>
              </motion.div>

              <motion.div
                variants={fadeIn}
                className="flex flex-wrap items-center justify-center lg:justify-start gap-6 text-sm text-text-muted font-mono"
              >
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-accent-primary" />
                  <span>No credit card</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-accent-primary" />
                  <span>Free tier</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-accent-primary" />
                  <span>Privacy-first</span>
                </div>
              </motion.div>
            </motion.div>

            {/* Right Column — Product Showcase */}
            <motion.div
              initial={{ opacity: 0, x: 24 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.6, delay: 0.3 }}
              className="relative z-10"
            >
              <ProductShowcase />
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
              Pre-Submission{' '}
              <span className="text-accent-primary relative inline-block">
                Peer Review
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
              Expert AI feedback grounded in your literature — not a writing assistant
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
                    Noesis critiques and suggests—you decide. Your thinking, your arguments, your paper.
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
                    We don't auto-write. We help you identify weaknesses, gaps, and missing citations before peer review.
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
                    Citation suggestions come from your uploaded literature—no hallucinated references.
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
              Trusted by undergrads, PhDs, postdocs, and faculty
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
              Simple. Powerful. <span className="text-accent-primary">Fast.</span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary tracking-normal">
              Get started in three steps
            </p>
          </motion.div>

          <div className="space-y-24">
            {[
              {
                number: '01',
                title: 'Upload Your Papers',
                description: 'Add PDF research papers to your project. Noesis automatically extracts text, metadata, and citations from each document.',
                color: 'rose'
              },
              {
                number: '02',
                title: 'AI Analyzes Everything',
                description: 'Advanced AI extracts methodology, findings, claims, and citations from each paper. No hallucinated references, only real analysis.',
                color: 'teal'
              },
              {
                number: '03',
                title: 'Get Critique & Guidance',
                description: 'Upload your draft to get reviewer-style feedback, citation suggestions, and structural guidance—before peer review.',
                color: 'indigo'
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
              Choose the plan that fits your research needs. Start free, upgrade anytime.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-4 gap-8 max-w-7xl mx-auto pt-8 overflow-visible">
            {/* Free Beta Plan - Current */}
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
                    <span className="text-text-secondary">5 draft analyses per month</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">30 PDF uploads per month</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">100 BibTeX imports per month</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">10 paper discovery searches per day</span>
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
                    Active Plan
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
                    For active researchers with heavier usage needs
                  </p>
                </div>

                <ul className="space-y-3 mb-6 flex-1">
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Unlimited draft analyses</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Unlimited document uploads</span>
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
                    Get Started
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
                    For research groups (minimum 3 users)
                  </p>
                </div>

                <ul className="space-y-3 mb-6 flex-1">
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Everything in Pro</span>
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
                    <span className="text-text-secondary">Add or remove seats anytime</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Priority support</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Usage analytics dashboard</span>
                  </li>
                </ul>

                <div className="mt-auto space-y-4">
                  <button
                    disabled
                    className="block w-full py-3 px-4 bg-accent-primary text-white font-semibold rounded-lg text-center opacity-50 cursor-not-allowed"
                  >
                    Get Started
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
                    Contact Sales
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
              Join researchers who are submitting stronger papers with confidence
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <Button
                onClick={() => navigate('/signup')}
                variant="primary"
                size="lg"
              >
                Get Started Free
              </Button>
              <button
                onClick={() => navigate('/login')}
                className="px-8 py-4 border border-border-default text-text-secondary font-semibold rounded-md hover:border-accent-primary/30 hover:text-text-primary transition-all duration-150 text-lg"
              >
                Sign In
              </button>
            </div>

            {/* Trust Indicators - Rose Accent */}
            <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-8 pt-8 text-sm text-text-muted font-mono">
              <div className="flex items-center gap-2">
                <CheckBadgeIcon className="h-4 w-4 text-accent-primary" />
                <span>No credit card required</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckBadgeIcon className="h-4 w-4 text-accent-primary" />
                <span>Free tier available</span>
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
              <Link to="/privacy" className="hover:text-accent-primary transition-colors duration-150">Privacy</Link>
              <a href="#" className="hover:text-accent-primary transition-colors duration-150">Terms</a>
              <a href="mailto:privacy@noesis.app" className="hover:text-accent-primary transition-colors duration-150">Contact</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

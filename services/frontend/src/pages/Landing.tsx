import { motion } from 'framer-motion'
import { useNavigate, Link } from 'react-router-dom'
import {
  DocumentTextIcon as _DocumentTextIcon,
  ChatBubbleLeftRightIcon,
  LightBulbIcon,
  BeakerIcon,
  ArrowRightIcon,
  ClipboardDocumentCheckIcon,
  ShieldCheckIcon,
  UserIcon,
  AcademicCapIcon,
  CheckBadgeIcon,
  SparklesIcon,
} from '@heroicons/react/24/outline'
import { useEffect } from 'react'
import { Button } from '../components/ui/Button'

export default function Landing() {
  const navigate = useNavigate()

  useEffect(() => {
    document.title = 'Noesis - AI-Powered Research Intelligence Platform'
  }, [])

  const fadeIn = {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.5, ease: 'easeOut' }
  }

  const features = [
    {
      icon: LightBulbIcon,
      title: 'AI-Powered Analysis',
      description: 'Advanced AI analyzes research papers for methodology, findings, claims, and citations—building your research knowledge base.'
    },
    {
      icon: ClipboardDocumentCheckIcon,
      title: 'Draft Critique & Feedback',
      description: 'Upload your draft and get reviewer-style feedback: unsupported claims, missing citations, coverage gaps, and structural suggestions.'
    },
    {
      icon: ChatBubbleLeftRightIcon,
      title: 'Conversational Research Assistant',
      description: 'Ask questions in natural language and receive answers grounded in your literature, never hallucinating citations.'
    },
    {
      icon: BeakerIcon,
      title: 'Citation Gap Detection',
      description: 'Identify unsupported claims in your draft and get AI-suggested papers from your literature to strengthen arguments.'
    }
  ]

  const useCases = [
    {
      role: 'PhD Students',
      description: 'Get reviewer-style feedback on dissertation drafts before your advisor sees them. Surface weak claims and citation gaps early.',
      impact: 'Pre-review confidence'
    },
    {
      role: 'Academic Researchers',
      description: 'Strengthen grant proposals and papers before submission. Identify coverage gaps and improve argument defensibility.',
      impact: 'Stronger submissions'
    },
    {
      role: 'Systematic Review Authors',
      description: 'Manage large literature collections, identify synthesis gaps, and ensure comprehensive coverage before publication.',
      impact: 'Complete coverage'
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
          <div className="flex justify-between items-center h-14">
            <div className="flex items-center gap-3">
              <img
                src="/noesis.png"
                alt="Noesis"
                className="h-6"
              />
              <span className="text-sm font-sans font-semibold text-text-primary">
                Noesis
              </span>
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

      {/* Hero Section - Professional Dark Gradient */}
      <section className="relative pt-32 pb-24 sm:pt-40 sm:pb-32 px-6 sm:px-8 overflow-hidden bg-gradient-to-br from-bg-void via-bg-surface to-bg-void">
        <div className="max-w-5xl mx-auto">
          {/* Centered Content */}
          <motion.div
            className="text-center space-y-8 relative z-10"
            initial="initial"
            animate="animate"
            variants={{
              animate: { transition: { staggerChildren: 0.15 } }
            }}
          >
            {/* Main Headline - Centered */}
            <motion.h1
              variants={fadeIn}
              className="text-5xl sm:text-6xl lg:text-7xl font-sans font-semibold leading-display tracking-tightest mx-auto"
            >
              Strengthen Your Research{' '}
              <span className="text-accent-primary">Before Peer Review</span>
            </motion.h1>

            {/* Subheadline - Centered */}
            <motion.p
              variants={fadeIn}
              className="text-xl sm:text-2xl text-text-secondary leading-body-large tracking-normal max-w-3xl mx-auto"
            >
              AI research assistant that critiques your drafts, surfaces citation gaps, and identifies weak claims—like a reviewer, before submission.
            </motion.p>

            {/* CTA Buttons - Centered */}
            <motion.div
              variants={fadeIn}
              className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4"
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
              <button
                onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
                className="px-8 py-4 text-text-secondary font-semibold hover:text-text-primary transition-colors text-lg"
              >
                Watch Demo
              </button>
            </motion.div>

            {/* Trust Badges - Centered */}
            <motion.div
              variants={fadeIn}
              className="flex flex-wrap items-center justify-center gap-6 pt-4 text-sm text-text-muted font-mono"
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

          {/* Demo Card - Below Content, Centered */}
          <motion.div
            className="mt-16 max-w-2xl mx-auto"
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8, delay: 0.4 }}
          >
            {/* Demo Card - Professional, Static */}
            <div className="bg-bg-surface border border-border-default rounded-lg p-8 shadow-lg">
              {/* Mock Analysis Content */}
              <div className="space-y-6">
                <div className="flex items-center gap-3 mb-6">
                  <SparklesIcon className="h-6 w-6 text-accent-primary" />
                  <span className="text-lg font-sans font-semibold text-text-primary">
                    Draft Analysis
                  </span>
                </div>

                {/* Stat Cards - Dark Theme */}
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-accent-light border border-accent-primary/30 rounded-md p-5">
                    <div className="text-3xl font-sans font-bold text-accent-primary mb-1">12</div>
                    <div className="text-xs font-mono text-text-muted">Claims Analyzed</div>
                  </div>
                  <div className="bg-indigo-light border border-indigo-primary/30 rounded-md p-5">
                    <div className="text-3xl font-sans font-bold text-indigo-primary mb-1">5</div>
                    <div className="text-xs font-mono text-text-muted">Citations Found</div>
                  </div>
                </div>

                {/* Progress Bar - Rose Gradient */}
                <div className="space-y-2 mt-6">
                  <div className="flex items-center justify-between text-xs font-mono text-text-muted">
                    <span>Coverage Score</span>
                    <span>87%</span>
                  </div>
                  <div className="h-2.5 bg-bg-hover rounded-full overflow-hidden">
                    <motion.div
                      className="h-full bg-gradient-to-r from-accent-primary to-rose-primary"
                      initial={{ width: 0 }}
                      animate={{ width: '87%' }}
                      transition={{ duration: 1.5, delay: 0.6 }}
                    />
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Features Section - Professional Dark Cards */}
      <section id="features" className="py-16 px-6 sm:px-8 bg-bg-void">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.3 }}
            className="mb-16 text-center"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-sans font-semibold leading-heading-1 tracking-tighter text-text-primary mb-6">
              Research Intelligence, <br className="hidden sm:block" />
              <span className="text-accent-primary">Not Auto-Writing</span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary max-w-3xl mx-auto leading-body-large tracking-normal">
              Powered by advanced AI, semantic search, and intelligent analytics
            </p>
          </motion.div>

          {/* Feature Cards - Rose Accent Hover */}
          <div className="grid md:grid-cols-2 gap-6 lg:gap-8">
            {features.map((feature, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.1, duration: 0.3 }}
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
            viewport={{ once: true }}
            className="bg-bg-surface border border-accent-primary/20 rounded-lg p-8 sm:p-12"
          >
            <h3 className="text-3xl sm:text-4xl font-sans font-semibold text-text-primary mb-8 text-center tracking-tight">
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
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="mb-16 text-center"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-sans font-semibold leading-[1.2] tracking-tight text-text-primary mb-6">
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
                viewport={{ once: true }}
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
                    <div className="px-4 py-2 bg-accent-light border border-accent-primary/30 rounded-md">
                      <div className="text-xs font-mono text-text-muted mb-1">Impact</div>
                      <div className="text-base font-sans font-semibold text-accent-primary">
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

      {/* How It Works - Clean, Professional */}
      <section className="py-32 px-6 sm:px-8 bg-bg-surface">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-20 text-center"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-sans font-semibold leading-[1.2] tracking-tight text-text-primary mb-6">
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
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.2, duration: 0.3 }}
                className={`flex flex-col md:flex-row gap-12 items-center ${
                  index % 2 === 1 ? 'md:flex-row-reverse' : ''
                }`}
              >
                {/* Number Badge - NO Spring Animation */}
                <div className="shrink-0">
                  <div
                    className={`w-32 h-32 rounded-xl ${
                      step.color === 'rose' ? 'bg-accent-light border-accent-primary/30' :
                      step.color === 'teal' ? 'bg-teal-light border-teal-primary/30' :
                      'bg-indigo-light border-indigo-primary/30'
                    } border flex items-center justify-center`}
                  >
                    <span className={`text-5xl font-sans font-bold ${
                      step.color === 'rose' ? 'text-accent-primary' :
                      step.color === 'teal' ? 'text-teal-primary' :
                      'text-indigo-primary'
                    }`}>
                      {step.number}
                    </span>
                  </div>
                </div>

                {/* Content Card */}
                <div className="flex-1">
                  <div className="bg-bg-void border border-border-default rounded-lg p-8 space-y-4">
                    <h3 className="text-3xl sm:text-4xl font-sans font-semibold text-text-primary tracking-normal">
                      {step.title}
                    </h3>
                    <p className="text-lg text-text-secondary leading-relaxed tracking-normal">
                      {step.description}
                    </p>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section - Professional Dark */}
      <section className="relative py-32 overflow-hidden bg-bg-void">
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-sans font-semibold leading-[1.2] tracking-tight text-text-primary mb-6">
              <span className="text-accent-primary">Transparent</span>, Research-Friendly Pricing
            </h2>
            <p className="text-lg sm:text-xl text-text-secondary max-w-3xl mx-auto tracking-normal">
              All users are currently on the <span className="font-semibold text-accent-primary">Free Beta Plan</span>.
              Usage limits ensure fair access during beta testing. Future paid plans will support heavier usage.
            </p>
          </motion.div>

          <div className="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
            {/* Free Beta Plan - Current */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.1, duration: 0.5 }}
              viewport={{ once: true }}
              className="bg-bg-surface border-2 border-accent-primary rounded-lg p-8 relative shadow-md"
            >
              <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                <span className="px-4 py-1 bg-teal-primary text-white text-sm font-semibold rounded-full">
                  Current Plan
                </span>
              </div>

              <div className="space-y-6 mt-4">
                <div>
                  <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
                    Free (Beta)
                  </h3>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-text-primary">$0</span>
                    <span className="text-text-tertiary">/month</span>
                  </div>
                  <p className="text-sm text-text-tertiary mt-2">
                    Perfect for trying Noesis and small research projects
                  </p>
                </div>

                <ul className="space-y-3">
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">10 draft analyses per month</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">50 document uploads per month</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Unlimited chat queries</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Citation gap detection</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Reviewer-style feedback</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">BibTeX export</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">All core features</span>
                  </li>
                </ul>

                <button
                  disabled
                  className="w-full py-3 px-4 bg-surface border-2 border-accent-primary text-text-primary font-semibold rounded-lg cursor-not-allowed"
                >
                  Active Plan
                </button>

                <p className="text-xs text-text-muted text-center font-mono">
                  Currently available to all users during beta
                </p>
              </div>
            </motion.div>

            {/* Student/Researcher Plan - Coming Soon */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.2, duration: 0.5 }}
              viewport={{ once: true }}
              className="bg-bg-surface border border-border-default rounded-lg p-8 relative"
            >
              <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                <span className="px-4 py-1 bg-amber-primary text-white text-sm font-semibold rounded-full">
                  Coming Soon
                </span>
              </div>

              <div className="space-y-6 mt-4">
                <div>
                  <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
                    Student / Researcher
                  </h3>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-text-primary">$15</span>
                    <span className="text-text-tertiary">/month</span>
                  </div>
                  <p className="text-sm text-text-tertiary mt-2">
                    For active researchers with heavier usage needs
                  </p>
                </div>

                <ul className="space-y-3">
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

                <button
                  disabled
                  className="w-full py-3 px-4 border border-border-base text-text-muted font-semibold rounded-lg cursor-not-allowed opacity-50"
                >
                  Notify Me
                </button>

                <p className="text-xs text-text-muted text-center font-mono">
                  Planned for Spring 2026
                </p>
              </div>
            </motion.div>

            {/* Lab/Team Plan - Future */}
            <motion.div
              initial={{ opacity: 0, y: 20 }}
              whileInView={{ opacity: 1, y: 0 }}
              transition={{ delay: 0.3, duration: 0.5 }}
              viewport={{ once: true }}
              className="bg-bg-surface border border-border-default rounded-lg p-8 relative"
            >
              <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                <span className="px-4 py-1 bg-bg-hover text-text-primary text-sm font-semibold rounded-full border border-border-default">
                  Future
                </span>
              </div>

              <div className="space-y-6 mt-4">
                <div>
                  <h3 className="text-2xl font-sans font-semibold text-text-primary mb-2 tracking-normal">
                    Lab / Team
                  </h3>
                  <div className="flex items-baseline gap-2">
                    <span className="text-4xl font-bold text-text-primary">Custom</span>
                  </div>
                  <p className="text-sm text-text-tertiary mt-2">
                    For research groups and institutions
                  </p>
                </div>

                <ul className="space-y-3">
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
                    <span className="text-text-secondary">Dedicated support</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Custom usage limits</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">SSO integration (optional)</span>
                  </li>
                  <li className="flex items-start gap-3 text-sm">
                    <CheckBadgeIcon className="h-5 w-5 text-accent-primary shrink-0 mt-0.5" />
                    <span className="text-text-secondary">Everything in Student plan</span>
                  </li>
                </ul>

                <button
                  disabled
                  className="w-full py-3 px-4 border border-border-base text-text-muted font-semibold rounded-lg cursor-not-allowed opacity-50"
                >
                  Contact Sales
                </button>

                <p className="text-xs text-text-muted text-center font-mono">
                  Roadmap for late 2026
                </p>
              </div>
            </motion.div>
          </div>

          {/* Beta Notice */}
          <motion.div
            initial={{ opacity: 0 }}
            whileInView={{ opacity: 1 }}
            transition={{ delay: 0.3 }}
            viewport={{ once: true }}
            className="mt-12 max-w-3xl mx-auto bg-bg-surface border border-border-default rounded-lg p-6 text-center"
          >
            <p className="text-sm text-text-tertiary tracking-normal">
              <span className="font-semibold text-text-secondary">Beta Period:</span> All features are free while we collect feedback and refine the platform.
              Limits exist to prevent abuse and ensure quality service for all researchers.
              <a href="mailto:support@noesis.ai" className="text-accent-primary hover:text-accent-hover transition-colors duration-150 ml-1">
                Contact us
              </a> if you need higher limits for a research project.
            </p>
          </motion.div>
        </div>
      </section>

      {/* CTA Section - Professional Dark */}
      <section className="py-32 px-6 sm:px-8 relative overflow-hidden bg-bg-void">
        <div className="max-w-4xl mx-auto relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
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
            <div className="flex items-center gap-3">
              <img
                src="/noesis.png"
                alt="Noesis"
                className="h-8"
              />
              <span className="text-lg font-sans font-semibold text-text-primary">
                Noesis
              </span>
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

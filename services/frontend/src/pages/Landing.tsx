import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  DocumentTextIcon,
  ChatBubbleLeftRightIcon,
  LightBulbIcon,
  BeakerIcon,
  ArrowRightIcon,
  ClipboardDocumentCheckIcon,
  ShieldCheckIcon,
  UserIcon,
  AcademicCapIcon,
  CheckBadgeIcon,
} from '@heroicons/react/24/outline'
import { useEffect } from 'react'

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
    <div className="min-h-screen bg-bg-base text-text-primary">
      {/* Navigation */}
      <motion.nav
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="fixed top-0 left-0 right-0 z-50 bg-bg-base/80 backdrop-blur-sm border-b border-border-base"
      >
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <img src="/noesis.png" alt="Noesis" className="h-8" />
              <span className="text-lg font-serif font-semibold text-text-primary">
                Noesis
              </span>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/login')}
                className="px-4 py-2 text-sm font-medium text-text-tertiary hover:text-text-primary transition-colors"
              >
                Sign In
              </button>
              <button
                onClick={() => navigate('/signup')}
                className="px-6 py-2 text-sm font-semibold bg-accent-primary text-white rounded-lg hover:bg-accent-hover transition-colors"
              >
                Get Started
              </button>
            </div>
          </div>
        </div>
      </motion.nav>

      {/* Hero Section */}
      <section className="relative pt-32 pb-20 sm:pt-40 sm:pb-32 px-6 sm:px-8">
        <div className="max-w-4xl mx-auto">
          <motion.div
            className="space-y-8"
            initial="initial"
            animate="animate"
            variants={{
              animate: { transition: { staggerChildren: 0.1 } }
            }}
          >
            {/* Main Headline */}
            <motion.h1
              variants={fadeIn}
              className="text-5xl sm:text-6xl lg:text-7xl font-serif font-bold leading-[1.1] tracking-tight"
            >
              Strengthen Your Research{' '}
              <span className="text-accent-primary">Before Peer Review</span>
            </motion.h1>

            {/* Subheadline */}
            <motion.p
              variants={fadeIn}
              className="text-xl sm:text-2xl text-text-tertiary leading-relaxed max-w-3xl"
            >
              AI research assistant that critiques your drafts, surfaces citation gaps, and identifies weak claims—like a reviewer, before submission.
            </motion.p>

            {/* CTA Buttons */}
            <motion.div
              variants={fadeIn}
              className="flex flex-col sm:flex-row items-start sm:items-center gap-4 pt-4"
            >
              <button
                onClick={() => navigate('/signup')}
                className="group px-8 py-4 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors flex items-center gap-2"
              >
                Get Started Free
                <ArrowRightIcon className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
              </button>
              <button
                onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
                className="px-8 py-4 text-text-secondary font-medium hover:text-text-primary transition-colors"
              >
                Learn More
              </button>
            </motion.div>

            {/* Stats */}
            <motion.div
              variants={fadeIn}
              className="grid grid-cols-3 gap-8 pt-12 border-t border-border-base"
            >
              <div>
                <div className="text-3xl sm:text-4xl font-serif font-bold text-text-primary mb-1">
                  AI-Powered
                </div>
                <div className="text-sm text-text-muted font-mono">Analysis</div>
              </div>
              <div>
                <div className="text-3xl sm:text-4xl font-serif font-bold text-text-primary mb-1">
                  Citation
                </div>
                <div className="text-sm text-text-muted font-mono">Gap Detection</div>
              </div>
              <div>
                <div className="text-3xl sm:text-4xl font-serif font-bold text-text-primary mb-1">
                  Pre-Review
                </div>
                <div className="text-sm text-text-muted font-mono">Feedback</div>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-32 px-6 sm:px-8 bg-surface/30">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="mb-16"
          >
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-text-primary mb-4">
              Research Intelligence, Not Auto-Writing
            </h2>
            <p className="text-xl text-text-tertiary">
              Powered by advanced AI, semantic search, and intelligent analytics
            </p>
          </motion.div>

          <div className="grid md:grid-cols-2 gap-12 lg:gap-16">
            {features.map((feature, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className="space-y-4"
              >
                {/* Icon */}
                <div className="w-12 h-12 text-text-tertiary">
                  <feature.icon className="w-full h-full" strokeWidth={1.5} />
                </div>

                {/* Content */}
                <h3 className="text-2xl font-serif font-semibold text-text-primary">
                  {feature.title}
                </h3>
                <p className="text-text-tertiary leading-relaxed">
                  {feature.description}
                </p>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust & Academic Integrity Section */}
      <section className="relative py-20 overflow-hidden">
        <div className="max-w-5xl mx-auto px-6 sm:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            viewport={{ once: true }}
            className="bg-surface border border-border-base rounded-lg p-8 sm:p-12"
          >
            <h3 className="text-2xl sm:text-3xl font-serif font-semibold text-text-primary mb-6 text-center">
              Built on Trust & Academic Integrity
            </h3>

            <div className="grid sm:grid-cols-2 gap-6">
              <div className="flex items-start gap-4">
                <div className="shrink-0 mt-1">
                  <ShieldCheckIcon className="h-6 w-6 text-accent-primary" />
                </div>
                <div>
                  <h4 className="font-semibold text-text-primary mb-2">Your Data, Your Research</h4>
                  <p className="text-sm text-text-tertiary">
                    Your drafts and documents are never used to train AI models. Your research remains private and secure.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="shrink-0 mt-1">
                  <UserIcon className="h-6 w-6 text-accent-primary" />
                </div>
                <div>
                  <h4 className="font-semibold text-text-primary mb-2">You Own Your Work</h4>
                  <p className="text-sm text-text-tertiary">
                    Noesis critiques and suggests—you decide. Your thinking, your arguments, your paper.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="shrink-0 mt-1">
                  <AcademicCapIcon className="h-6 w-6 text-accent-primary" />
                </div>
                <div>
                  <h4 className="font-semibold text-text-primary mb-2">Research Integrity</h4>
                  <p className="text-sm text-text-tertiary">
                    We don't auto-write. We help you identify weaknesses, gaps, and missing citations before peer review.
                  </p>
                </div>
              </div>

              <div className="flex items-start gap-4">
                <div className="shrink-0 mt-1">
                  <CheckBadgeIcon className="h-6 w-6 text-accent-primary" />
                </div>
                <div>
                  <h4 className="font-semibold text-text-primary mb-2">Real Citations Only</h4>
                  <p className="text-sm text-text-tertiary">
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
            className="mb-16"
          >
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-text-primary mb-4">
              Built for Serious Researchers
            </h2>
            <p className="text-xl text-text-tertiary">
              Trusted by undergrads, PhDs, postdocs, and faculty
            </p>
          </motion.div>

          <div className="space-y-12">
            {useCases.map((useCase, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 12 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className="p-8 border border-border-base rounded-lg hover:border-border-subtle transition-colors"
              >
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
                  <div className="flex-1 space-y-3">
                    <h3 className="text-2xl font-serif font-semibold text-text-primary">
                      {useCase.role}
                    </h3>
                    <p className="text-text-tertiary leading-relaxed">
                      {useCase.description}
                    </p>
                  </div>
                  <div className="md:text-right">
                    <div className="text-sm font-mono text-text-muted mb-1">Impact</div>
                    <div className="text-lg font-medium text-text-secondary">
                      {useCase.impact}
                    </div>
                  </div>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* How It Works */}
      <section className="py-32 px-6 sm:px-8 bg-surface/30">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-16"
          >
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-text-primary mb-4">
              Simple. Powerful. Fast.
            </h2>
            <p className="text-xl text-text-tertiary">
              Get started in three steps
            </p>
          </motion.div>

          <div className="space-y-16">
            {[
              {
                number: '01',
                title: 'Upload Your Papers',
                description: 'Add PDF research papers to your project. Noesis automatically extracts text, metadata, and citations from each document.'
              },
              {
                number: '02',
                title: 'AI Analyzes Everything',
                description: 'Advanced AI extracts methodology, findings, claims, and citations from each paper. No hallucinated references, only real analysis.'
              },
              {
                number: '03',
                title: 'Get Critique & Guidance',
                description: 'Upload your draft to get reviewer-style feedback, citation suggestions, and structural guidance—before peer review.'
              }
            ].map((step, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, x: -12 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.15, duration: 0.5 }}
                className="flex flex-col md:flex-row gap-8 items-start"
              >
                {/* Number */}
                <div className="shrink-0">
                  <div className="text-6xl font-serif font-bold text-surface-active">
                    {step.number}
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1 pt-2 space-y-3">
                  <h3 className="text-2xl font-serif font-semibold text-text-primary">
                    {step.title}
                  </h3>
                  <p className="text-text-tertiary leading-relaxed max-w-2xl">
                    {step.description}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="relative py-32 overflow-hidden">
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-text-primary mb-6">
              Transparent, Research-Friendly Pricing
            </h2>
            <p className="text-lg sm:text-xl text-text-secondary max-w-3xl mx-auto">
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
              className="bg-surface border-2 border-accent-primary rounded-lg p-8 relative"
            >
              <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                <span className="px-4 py-1 bg-green-600 text-white text-sm font-semibold rounded-full">
                  Current Plan
                </span>
              </div>

              <div className="space-y-6 mt-4">
                <div>
                  <h3 className="text-2xl font-serif font-semibold text-text-primary mb-2">
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
              className="bg-surface border border-border-base rounded-lg p-8 relative"
            >
              <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                <span className="px-4 py-1 bg-amber-600 text-white text-sm font-semibold rounded-full">
                  Coming Soon
                </span>
              </div>

              <div className="space-y-6 mt-4">
                <div>
                  <h3 className="text-2xl font-serif font-semibold text-text-primary mb-2">
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
              className="bg-surface border border-border-base rounded-lg p-8 relative"
            >
              <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                <span className="px-4 py-1 bg-slate-600 text-white text-sm font-semibold rounded-full">
                  Future
                </span>
              </div>

              <div className="space-y-6 mt-4">
                <div>
                  <h3 className="text-2xl font-serif font-semibold text-text-primary mb-2">
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
            className="mt-12 max-w-3xl mx-auto bg-surface border border-border-base rounded-lg p-6 text-center"
          >
            <p className="text-sm text-text-tertiary">
              <span className="font-semibold text-text-secondary">Beta Period:</span> All features are free while we collect feedback and refine the platform.
              Limits exist to prevent abuse and ensure quality service for all researchers.
              <a href="mailto:support@noesis.ai" className="text-accent-primary hover:text-accent-hover transition-colors ml-1">
                Contact us
              </a> if you need higher limits for a research project.
            </p>
          </motion.div>
        </div>
      </section>

      {/* CTA Section */}
      <section className="py-32 px-6 sm:px-8">
        <div className="max-w-4xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center space-y-8"
          >
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-text-primary">
              Ready to strengthen your research?
            </h2>
            <p className="text-xl text-text-tertiary max-w-2xl mx-auto">
              Join researchers who are submitting stronger papers with confidence
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <button
                onClick={() => navigate('/signup')}
                className="px-8 py-4 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
              >
                Get Started Free
              </button>
              <button
                onClick={() => navigate('/login')}
                className="px-8 py-4 border border-border-base text-text-secondary font-medium rounded-lg hover:border-border-subtle hover:text-text-primary transition-colors"
              >
                Sign In
              </button>
            </div>

            {/* Trust Indicators */}
            <div className="flex flex-wrap items-center justify-center gap-8 pt-8 text-sm text-text-muted font-mono">
              <div>✓ No credit card required</div>
              <div>✓ Free tier available</div>
              <div>✓ Cancel anytime</div>
              <div>✓ Your drafts are never used for AI training</div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 sm:px-8 border-t border-border-base">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div className="flex items-center gap-3">
              <img src="/noesis.png" alt="Noesis" className="h-8" />
              <span className="text-lg font-serif font-semibold text-text-primary">
                Noesis
              </span>
            </div>
            <div className="text-text-muted text-sm font-mono">
              © 2026 Noesis. All rights reserved.
            </div>
            <div className="flex items-center gap-6 text-text-muted text-sm">
              <a href="#" className="hover:text-text-secondary transition-colors">Privacy</a>
              <a href="#" className="hover:text-text-secondary transition-colors">Terms</a>
              <a href="#" className="hover:text-text-secondary transition-colors">Contact</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

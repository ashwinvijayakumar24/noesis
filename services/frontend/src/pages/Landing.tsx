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
import { MagneticButton } from '../components/ui/MagneticButton'

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
      {/* Navigation */}
      <motion.nav
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="fixed top-0 left-0 right-0 z-50 bg-bg-void/80 backdrop-blur-xl border-b border-border-base"
      >
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3 group cursor-pointer">
              <img
                src="/noesis.png"
                alt="Noesis"
                className="h-8 transition-all duration-300 group-hover:drop-shadow-[0_0_8px_rgba(255,31,76,0.6)]"
              />
              <span className="text-lg font-display font-semibold text-text-primary">
                Noesis
              </span>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/login')}
                className="px-4 py-2 text-sm font-medium text-text-secondary hover:text-text-primary transition-colors"
              >
                Sign In
              </button>
              <MagneticButton
                onClick={() => navigate('/signup')}
                variant="primary"
                size="sm"
              >
                Get Started
              </MagneticButton>
            </div>
          </div>
        </div>
      </motion.nav>

      {/* Hero Section - Asymmetric Layout */}
      <section className="relative pt-32 pb-20 sm:pt-40 sm:pb-32 px-6 sm:px-8 overflow-hidden">
        {/* Pink Glow Background Blob */}
        <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-neon-pink/20 rounded-full blur-[120px] opacity-30 pointer-events-none" />

        <div className="max-w-7xl mx-auto">
          <div className="grid lg:grid-cols-5 gap-12 lg:gap-16 items-center">
            {/* Left Column (60%) - Content */}
            <motion.div
              className="lg:col-span-3 space-y-8 relative z-10"
              initial="initial"
              animate="animate"
              variants={{
                animate: { transition: { staggerChildren: 0.15 } }
              }}
            >
              {/* Main Headline */}
              <motion.h1
                variants={fadeIn}
                className="text-5xl sm:text-6xl lg:text-7xl font-display font-extrabold leading-[1.1] tracking-tighter"
              >
                Strengthen Your Research{' '}
                <span className="gradient-text">Before Peer Review</span>
              </motion.h1>

              {/* Subheadline */}
              <motion.p
                variants={fadeIn}
                className="text-xl sm:text-2xl text-text-secondary leading-relaxed max-w-2xl"
              >
                AI research assistant that critiques your drafts, surfaces citation gaps, and identifies weak claims—like a reviewer, before submission.
              </motion.p>

              {/* CTA Buttons */}
              <motion.div
                variants={fadeIn}
                className="flex flex-col sm:flex-row items-start sm:items-center gap-4 pt-4"
              >
                <MagneticButton
                  onClick={() => navigate('/signup')}
                  variant="primary"
                  size="lg"
                  className="flex items-center gap-2 group"
                >
                  Get Started Free
                  <ArrowRightIcon className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
                </MagneticButton>
                <button
                  onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
                  className="px-8 py-4 text-text-secondary font-semibold hover:text-text-primary transition-colors text-lg"
                >
                  Watch Demo
                </button>
              </motion.div>

              {/* Trust Badges */}
              <motion.div
                variants={fadeIn}
                className="flex flex-wrap items-center gap-6 pt-4 text-sm text-text-muted font-mono"
              >
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-neon-pink" />
                  <span>No credit card</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-neon-pink" />
                  <span>Free tier</span>
                </div>
                <div className="flex items-center gap-2">
                  <CheckBadgeIcon className="h-5 w-5 text-neon-pink" />
                  <span>Privacy-first</span>
                </div>
              </motion.div>
            </motion.div>

            {/* Right Column (40%) - Animated Demo Mockup */}
            <motion.div
              className="lg:col-span-2 relative"
              initial={{ opacity: 0, x: 20 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ duration: 0.8, delay: 0.3 }}
            >
              {/* Floating Demo Card */}
              <motion.div
                className="relative bg-gradient-to-br from-bg-surface to-bg-elevated border border-border-base rounded-2xl p-8 shadow-2xl"
                animate={{
                  y: [0, -20, 0],
                  rotate: [-2, 2, -2]
                }}
                transition={{
                  duration: 6,
                  ease: "easeInOut",
                  repeat: Infinity
                }}
              >
                {/* Accent Glow */}
                <div className="absolute inset-0 bg-gradient-to-br from-neon-pink/10 to-transparent rounded-2xl pointer-events-none" />

                {/* Mock Analysis Content */}
                <div className="space-y-6 relative z-10">
                  <div className="flex items-center gap-3">
                    <SparklesIcon className="h-6 w-6 text-neon-pink" />
                    <span className="text-lg font-display font-semibold text-text-primary">
                      Draft Analysis
                    </span>
                  </div>

                  {/* Stat Cards */}
                  <div className="grid grid-cols-2 gap-4">
                    <motion.div
                      className="bg-bg-void/50 border border-border-base rounded-lg p-4"
                      animate={{ opacity: [0.7, 1, 0.7] }}
                      transition={{ duration: 2, repeat: Infinity }}
                    >
                      <div className="text-2xl font-display font-bold text-neon-pink mb-1">12</div>
                      <div className="text-xs font-mono text-text-muted">Claims Analyzed</div>
                    </motion.div>
                    <motion.div
                      className="bg-bg-void/50 border border-border-base rounded-lg p-4"
                      animate={{ opacity: [0.7, 1, 0.7] }}
                      transition={{ duration: 2, delay: 0.3, repeat: Infinity }}
                    >
                      <div className="text-2xl font-display font-bold text-accent-teal mb-1">5</div>
                      <div className="text-xs font-mono text-text-muted">Citations Found</div>
                    </motion.div>
                  </div>

                  {/* Progress Bar */}
                  <div className="space-y-2">
                    <div className="flex items-center justify-between text-xs font-mono text-text-muted">
                      <span>Coverage Score</span>
                      <span>87%</span>
                    </div>
                    <div className="h-2 bg-bg-void rounded-full overflow-hidden">
                      <motion.div
                        className="h-full bg-gradient-to-r from-neon-pink to-accent-teal"
                        initial={{ width: 0 }}
                        animate={{ width: '87%' }}
                        transition={{ duration: 1.5, delay: 0.5 }}
                      />
                    </div>
                  </div>
                </div>

                {/* Floating Accent Badge */}
                <motion.div
                  className="absolute -top-4 -right-4 bg-neon-pink text-white px-4 py-2 rounded-full text-xs font-semibold shadow-neon-glow"
                  animate={{ y: [-5, 5, -5] }}
                  transition={{ duration: 3, repeat: Infinity }}
                >
                  ✓ Ready to Review
                </motion.div>
              </motion.div>

              {/* Floating Accent Card (Bottom Left) */}
              <motion.div
                className="absolute -bottom-8 -left-8 bg-bg-elevated border border-border-base rounded-xl p-4 shadow-xl hidden lg:block"
                animate={{
                  y: [0, -10, 0],
                  x: [-5, 5, -5]
                }}
                transition={{
                  duration: 5,
                  ease: "easeInOut",
                  repeat: Infinity,
                  delay: 1
                }}
              >
                <div className="flex items-center gap-3">
                  <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse" />
                  <span className="text-sm font-mono text-text-secondary">Live Analysis</span>
                </div>
              </motion.div>
            </motion.div>
          </div>
        </div>
      </section>

      {/* Features Section - Bento Grid */}
      <section id="features" className="py-32 px-6 sm:px-8 bg-bg-surface/30">
        <div className="max-w-7xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="mb-16 text-center"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-display font-bold leading-[1.2] tracking-tight text-text-primary mb-6">
              Research Intelligence, <br className="hidden sm:block" />
              <span className="gradient-text">Not Auto-Writing</span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary max-w-3xl mx-auto">
              Powered by advanced AI, semantic search, and intelligent analytics
            </p>
          </motion.div>

          {/* Bento Grid - Asymmetric Cards */}
          <div className="grid md:grid-cols-2 gap-6 lg:gap-8">
            {features.map((feature, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, y: 20 }}
                whileInView={{ opacity: 1, y: 0 }}
                viewport={{ once: true }}
                transition={{ delay: index * 0.1, duration: 0.5 }}
                className="group relative bg-bg-surface border border-border-base rounded-2xl p-8 hover:border-neon-pink/30 hover:-translate-y-2 transition-all duration-300"
                style={{
                  boxShadow: '0 4px 24px rgba(0, 0, 0, 0.1)'
                }}
              >
                {/* Gradient Overlay on Hover */}
                <div className="absolute inset-0 bg-gradient-to-br from-neon-pink/5 to-transparent rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none" />

                <div className="relative z-10 space-y-6">
                  {/* Icon with Pink Glow on Hover */}
                  <div className="w-14 h-14 rounded-xl bg-bg-void/50 border border-border-base flex items-center justify-center group-hover:border-neon-pink/50 transition-all duration-300">
                    <feature.icon
                      className="w-7 h-7 text-text-tertiary group-hover:text-neon-pink transition-colors"
                      strokeWidth={1.5}
                    />
                  </div>

                  {/* Content */}
                  <div className="space-y-3">
                    <h3 className="text-2xl sm:text-3xl font-display font-semibold text-text-primary leading-tight">
                      {feature.title}
                    </h3>
                    <p className="text-text-secondary leading-relaxed">
                      {feature.description}
                    </p>
                  </div>
                </div>

                {/* Subtle Border Glow Effect */}
                <div className="absolute inset-0 rounded-2xl opacity-0 group-hover:opacity-100 transition-opacity duration-300 pointer-events-none"
                  style={{
                    boxShadow: '0 0 0 1px rgba(255, 31, 76, 0.1), 0 8px 32px rgba(255, 31, 76, 0.1)'
                  }}
                />
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Trust & Academic Integrity Section */}
      <section className="relative py-32 overflow-hidden">
        <div className="max-w-6xl mx-auto px-6 sm:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            viewport={{ once: true }}
            className="bg-bg-surface border-2 border-neon-pink/20 rounded-3xl p-8 sm:p-12 relative overflow-hidden"
          >
            {/* Background Accent */}
            <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-neon-pink/5 to-transparent pointer-events-none" />

            <div className="relative z-10">
              <h3 className="text-3xl sm:text-4xl font-display font-bold text-text-primary mb-8 text-center">
                Built on <span className="gradient-text">Trust & Academic Integrity</span>
              </h3>

              <div className="grid sm:grid-cols-2 gap-8">
                <div className="flex items-start gap-4">
                  <div className="shrink-0 mt-1 w-12 h-12 rounded-xl bg-neon-pink/10 flex items-center justify-center border border-neon-pink/30">
                    <ShieldCheckIcon className="h-6 w-6 text-neon-pink" />
                  </div>
                  <div>
                    <h4 className="font-display font-semibold text-text-primary mb-2 text-lg">Your Data, Your Research</h4>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      Your drafts and documents are never used to train AI models. Your research remains private and secure.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="shrink-0 mt-1 w-12 h-12 rounded-xl bg-neon-pink/10 flex items-center justify-center border border-neon-pink/30">
                    <UserIcon className="h-6 w-6 text-neon-pink" />
                  </div>
                  <div>
                    <h4 className="font-display font-semibold text-text-primary mb-2 text-lg">You Own Your Work</h4>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      Noesis critiques and suggests—you decide. Your thinking, your arguments, your paper.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="shrink-0 mt-1 w-12 h-12 rounded-xl bg-neon-pink/10 flex items-center justify-center border border-neon-pink/30">
                    <AcademicCapIcon className="h-6 w-6 text-neon-pink" />
                  </div>
                  <div>
                    <h4 className="font-display font-semibold text-text-primary mb-2 text-lg">Research Integrity</h4>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      We don't auto-write. We help you identify weaknesses, gaps, and missing citations before peer review.
                    </p>
                  </div>
                </div>

                <div className="flex items-start gap-4">
                  <div className="shrink-0 mt-1 w-12 h-12 rounded-xl bg-neon-pink/10 flex items-center justify-center border border-neon-pink/30">
                    <CheckBadgeIcon className="h-6 w-6 text-neon-pink" />
                  </div>
                  <div>
                    <h4 className="font-display font-semibold text-text-primary mb-2 text-lg">Real Citations Only</h4>
                    <p className="text-sm text-text-secondary leading-relaxed">
                      Citation suggestions come from your uploaded literature—no hallucinated references.
                    </p>
                  </div>
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
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-display font-bold leading-[1.2] tracking-tight text-text-primary mb-6">
              Built for <span className="gradient-text">Serious Researchers</span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary">
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
                className="group bg-bg-surface border border-border-base rounded-2xl p-8 hover:border-neon-pink/30 hover:-translate-y-1 transition-all duration-300"
              >
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
                  <div className="flex-1 space-y-3">
                    <h3 className="text-2xl sm:text-3xl font-display font-semibold text-text-primary">
                      {useCase.role}
                    </h3>
                    <p className="text-lg text-text-secondary leading-relaxed">
                      {useCase.description}
                    </p>
                  </div>
                  <div className="md:text-right shrink-0">
                    <div className="px-4 py-2 bg-neon-pink/10 border border-neon-pink/30 rounded-lg">
                      <div className="text-xs font-mono text-text-muted mb-1">Impact</div>
                      <div className="text-base font-display font-semibold text-neon-pink">
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

      {/* How It Works - Diagonal Flow */}
      <section className="py-32 px-6 sm:px-8 bg-bg-surface/30">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-20 text-center"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-display font-bold leading-[1.2] tracking-tight text-text-primary mb-6">
              Simple. Powerful. <span className="gradient-text">Fast.</span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary">
              Get started in three steps
            </p>
          </motion.div>

          <div className="space-y-24">
            {[
              {
                number: '01',
                title: 'Upload Your Papers',
                description: 'Add PDF research papers to your project. Noesis automatically extracts text, metadata, and citations from each document.',
                color: 'neon-pink'
              },
              {
                number: '02',
                title: 'AI Analyzes Everything',
                description: 'Advanced AI extracts methodology, findings, claims, and citations from each paper. No hallucinated references, only real analysis.',
                color: 'accent-teal'
              },
              {
                number: '03',
                title: 'Get Critique & Guidance',
                description: 'Upload your draft to get reviewer-style feedback, citation suggestions, and structural guidance—before peer review.',
                color: 'accent-purple'
              }
            ].map((step, index) => (
              <motion.div
                key={index}
                initial={{ opacity: 0, x: index % 2 === 0 ? -40 : 40 }}
                whileInView={{ opacity: 1, x: 0 }}
                viewport={{ once: true, margin: "-100px" }}
                transition={{ delay: index * 0.2, duration: 0.6 }}
                className={`flex flex-col md:flex-row gap-12 items-center ${
                  index % 2 === 1 ? 'md:flex-row-reverse' : ''
                }`}
              >
                {/* Number Badge */}
                <div className="shrink-0">
                  <motion.div
                    className={`w-32 h-32 rounded-2xl bg-gradient-to-br ${
                      step.color === 'neon-pink' ? 'from-neon-pink/20 to-neon-pink/5' :
                      step.color === 'accent-teal' ? 'from-accent-teal/20 to-accent-teal/5' :
                      'from-accent-purple/20 to-accent-purple/5'
                    } border ${
                      step.color === 'neon-pink' ? 'border-neon-pink/30' :
                      step.color === 'accent-teal' ? 'border-accent-teal/30' :
                      'border-accent-purple/30'
                    } flex items-center justify-center`}
                    whileHover={{ scale: 1.05, rotate: 5 }}
                    transition={{ type: "spring", stiffness: 300 }}
                  >
                    <span className={`text-5xl font-display font-bold ${
                      step.color === 'neon-pink' ? 'text-neon-pink' :
                      step.color === 'accent-teal' ? 'text-accent-teal' :
                      'text-accent-purple'
                    }`}>
                      {step.number}
                    </span>
                  </motion.div>
                </div>

                {/* Content Card */}
                <div className="flex-1">
                  <div className="bg-bg-surface border border-border-base rounded-2xl p-8 space-y-4">
                    <h3 className="text-3xl sm:text-4xl font-display font-semibold text-text-primary">
                      {step.title}
                    </h3>
                    <p className="text-lg text-text-secondary leading-relaxed">
                      {step.description}
                    </p>
                  </div>
                </div>

                {/* Connecting Arrow (Desktop Only) */}
                {index < 2 && (
                  <div className="hidden lg:block absolute left-1/2 transform -translate-x-1/2"
                    style={{ top: `${(index + 1) * 24}rem` }}
                  >
                    <motion.div
                      initial={{ opacity: 0, scale: 0.8 }}
                      whileInView={{ opacity: 1, scale: 1 }}
                      viewport={{ once: true }}
                      transition={{ delay: (index + 1) * 0.2 + 0.3 }}
                      className="text-neon-pink/30"
                    >
                      <svg width="24" height="48" viewBox="0 0 24 48" fill="none">
                        <path d="M12 0L12 44M12 44L6 38M12 44L18 38" stroke="currentColor" strokeWidth="2" strokeLinecap="round" />
                      </svg>
                    </motion.div>
                  </div>
                )}
              </motion.div>
            ))}
          </div>
        </div>
      </section>

      {/* Pricing Section */}
      <section className="relative py-32 overflow-hidden bg-bg-surface/30">
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            viewport={{ once: true }}
            className="text-center mb-16"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-display font-bold leading-[1.2] tracking-tight text-text-primary mb-6">
              <span className="gradient-text">Transparent</span>, Research-Friendly Pricing
            </h2>
            <p className="text-lg sm:text-xl text-text-secondary max-w-3xl mx-auto">
              All users are currently on the <span className="font-semibold text-neon-pink">Free Beta Plan</span>.
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
              className="bg-bg-surface border-2 border-neon-pink rounded-2xl p-8 relative shadow-neon-glow"
            >
              <div className="absolute -top-4 left-1/2 -translate-x-1/2">
                <span className="px-4 py-1 bg-green-600 text-white text-sm font-semibold rounded-full">
                  Current Plan
                </span>
              </div>

              <div className="space-y-6 mt-4">
                <div>
                  <h3 className="text-2xl font-display font-semibold text-text-primary mb-2">
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
      <section className="py-32 px-6 sm:px-8 relative overflow-hidden">
        {/* Pink Glow Background */}
        <div className="absolute inset-0 bg-gradient-to-b from-transparent via-neon-pink/5 to-transparent pointer-events-none" />

        <div className="max-w-4xl mx-auto relative z-10">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="text-center space-y-8 bg-gradient-to-br from-bg-surface/50 to-bg-elevated/50 border border-neon-pink/20 rounded-3xl p-12 sm:p-16 backdrop-blur-sm"
          >
            <h2 className="text-4xl sm:text-5xl lg:text-6xl font-display font-bold leading-[1.1] tracking-tight text-text-primary">
              Ready to strengthen <br className="hidden sm:block" />
              <span className="gradient-text">your research?</span>
            </h2>
            <p className="text-xl sm:text-2xl text-text-secondary max-w-2xl mx-auto">
              Join researchers who are submitting stronger papers with confidence
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <MagneticButton
                onClick={() => navigate('/signup')}
                variant="primary"
                size="lg"
              >
                Get Started Free
              </MagneticButton>
              <button
                onClick={() => navigate('/login')}
                className="px-8 py-4 border-2 border-border-base text-text-secondary font-semibold rounded-lg hover:border-neon-pink/30 hover:text-text-primary transition-all duration-300 text-lg"
              >
                Sign In
              </button>
            </div>

            {/* Trust Indicators */}
            <div className="flex flex-wrap items-center justify-center gap-6 sm:gap-8 pt-8 text-sm text-text-muted font-mono">
              <div className="flex items-center gap-2">
                <CheckBadgeIcon className="h-4 w-4 text-neon-pink" />
                <span>No credit card required</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckBadgeIcon className="h-4 w-4 text-neon-pink" />
                <span>Free tier available</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckBadgeIcon className="h-4 w-4 text-neon-pink" />
                <span>Privacy-first</span>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 sm:px-8 border-t border-border-base bg-bg-void">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div className="flex items-center gap-3 group">
              <img
                src="/noesis.png"
                alt="Noesis"
                className="h-8 transition-all duration-300 group-hover:drop-shadow-[0_0_8px_rgba(255,31,76,0.6)]"
              />
              <span className="text-lg font-display font-semibold text-text-primary">
                Noesis
              </span>
            </div>
            <div className="text-text-muted text-sm font-mono">
              © 2026 Noesis. All rights reserved.
            </div>
            <div className="flex items-center gap-6 text-text-muted text-sm">
              <Link to="/privacy" className="hover:text-neon-pink transition-colors">Privacy</Link>
              <a href="#" className="hover:text-neon-pink transition-colors">Terms</a>
              <a href="mailto:privacy@noesis.app" className="hover:text-neon-pink transition-colors">Contact</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

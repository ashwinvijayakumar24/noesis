import { motion } from 'framer-motion'
import { useNavigate } from 'react-router-dom'
import {
  DocumentTextIcon,
  ChatBubbleLeftRightIcon,
  LightBulbIcon,
  BeakerIcon,
  ArrowRightIcon,
  AcademicCapIcon,
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
      description: 'Automatically extract methodology, findings, and citations from research papers using GPT-4. Transform weeks of reading into structured insights in minutes.'
    },
    {
      icon: DocumentTextIcon,
      title: 'Literature Review Generation',
      description: 'Generate publication-ready literature reviews with proper academic citations. Choose from IEEE, APA, or custom formats for seamless integration into your work.'
    },
    {
      icon: ChatBubbleLeftRightIcon,
      title: 'Conversational Research Assistant',
      description: 'Ask questions in natural language and receive answers grounded in your paper collection, complete with citations and page references.'
    },
    {
      icon: BeakerIcon,
      title: 'Research Gap Identification',
      description: 'Synthesize insights across papers to identify unexplored research areas, methodological gaps, and novel opportunities in your field.'
    }
  ]

  const useCases = [
    {
      role: 'PhD Students',
      description: 'Complete comprehensive literature reviews in days instead of weeks. Focus on research, not reading.',
      impact: 'Save 4-6 weeks per chapter'
    },
    {
      role: 'Academic Researchers',
      description: 'Generate literature sections for grant proposals and papers with proper citations and academic rigor.',
      impact: 'Save 2-3 weeks per proposal'
    },
    {
      role: 'Systematic Review Authors',
      description: 'Analyze and synthesize 100-300 papers with automated thematic analysis and citation tracking.',
      impact: 'Save 3-6 months per review'
    }
  ]

  return (
    <div className="min-h-screen bg-neutral-950 text-neutral-50">
      {/* Navigation */}
      <motion.nav
        initial={{ y: -20, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        className="fixed top-0 left-0 right-0 z-50 bg-neutral-950/80 backdrop-blur-sm border-b border-neutral-800"
      >
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <div className="flex justify-between items-center h-16">
            <div className="flex items-center gap-3">
              <img src="/noesis.png" alt="Noesis" className="h-8" />
              <span className="text-lg font-serif font-semibold text-neutral-50">
                Noesis
              </span>
            </div>
            <div className="flex items-center gap-4">
              <button
                onClick={() => navigate('/login')}
                className="px-4 py-2 text-sm font-medium text-neutral-400 hover:text-neutral-50 transition-colors"
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
              Transform Your Literature Review in{' '}
              <span className="text-accent-primary">Hours</span>, Not Weeks
            </motion.h1>

            {/* Subheadline */}
            <motion.p
              variants={fadeIn}
              className="text-xl sm:text-2xl text-neutral-400 leading-relaxed max-w-3xl"
            >
              AI-powered research intelligence for PhD students and academics. Auto-generate literature reviews, identify research gaps, and accelerate your research.
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
                Start Free Trial
                <ArrowRightIcon className="h-5 w-5 group-hover:translate-x-1 transition-transform" />
              </button>
              <button
                onClick={() => document.getElementById('features')?.scrollIntoView({ behavior: 'smooth' })}
                className="px-8 py-4 text-neutral-300 font-medium hover:text-neutral-50 transition-colors"
              >
                Learn More
              </button>
            </motion.div>

            {/* Stats */}
            <motion.div
              variants={fadeIn}
              className="grid grid-cols-3 gap-8 pt-12 border-t border-neutral-800"
            >
              <div>
                <div className="text-3xl sm:text-4xl font-serif font-bold text-neutral-50 mb-1">
                  80%
                </div>
                <div className="text-sm text-neutral-500 font-mono">Time saved</div>
              </div>
              <div>
                <div className="text-3xl sm:text-4xl font-serif font-bold text-neutral-50 mb-1">
                  100+
                </div>
                <div className="text-sm text-neutral-500 font-mono">Papers analyzed</div>
              </div>
              <div>
                <div className="text-3xl sm:text-4xl font-serif font-bold text-neutral-50 mb-1">
                  4-6wk
                </div>
                <div className="text-sm text-neutral-500 font-mono">Reduced to 1wk</div>
              </div>
            </motion.div>
          </motion.div>
        </div>
      </section>

      {/* Features Section */}
      <section id="features" className="py-32 px-6 sm:px-8 bg-neutral-900/30">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ duration: 0.5 }}
            className="mb-16"
          >
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-neutral-50 mb-4">
              Everything you need for breakthrough research
            </h2>
            <p className="text-xl text-neutral-400">
              Powered by GPT-4, semantic search, and advanced analytics
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
                <div className="w-12 h-12 text-neutral-400">
                  <feature.icon className="w-full h-full" strokeWidth={1.5} />
                </div>

                {/* Content */}
                <h3 className="text-2xl font-serif font-semibold text-neutral-50">
                  {feature.title}
                </h3>
                <p className="text-neutral-400 leading-relaxed">
                  {feature.description}
                </p>
              </motion.div>
            ))}
          </div>
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
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-neutral-50 mb-4">
              Built for researchers
            </h2>
            <p className="text-xl text-neutral-400">
              Trusted by PhD students, academics, and research teams
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
                className="p-8 border border-neutral-800 rounded-lg hover:border-neutral-700 transition-colors"
              >
                <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-6">
                  <div className="flex-1 space-y-3">
                    <h3 className="text-2xl font-serif font-semibold text-neutral-50">
                      {useCase.role}
                    </h3>
                    <p className="text-neutral-400 leading-relaxed">
                      {useCase.description}
                    </p>
                  </div>
                  <div className="md:text-right">
                    <div className="text-sm font-mono text-neutral-500 mb-1">Impact</div>
                    <div className="text-lg font-medium text-neutral-300">
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
      <section className="py-32 px-6 sm:px-8 bg-neutral-900/30">
        <div className="max-w-6xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            className="mb-16"
          >
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-neutral-50 mb-4">
              Simple. Powerful. Fast.
            </h2>
            <p className="text-xl text-neutral-400">
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
                description: 'GPT-4 analyzes each paper to extract methodology, findings, and key insights. The system identifies themes and research gaps across your entire collection.'
              },
              {
                number: '03',
                title: 'Generate Insights',
                description: 'Create publication-ready literature reviews, get research question recommendations, and explore your papers through conversational AI.'
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
                <div className="flex-shrink-0">
                  <div className="text-6xl font-serif font-bold text-neutral-800">
                    {step.number}
                  </div>
                </div>

                {/* Content */}
                <div className="flex-1 pt-2 space-y-3">
                  <h3 className="text-2xl font-serif font-semibold text-neutral-50">
                    {step.title}
                  </h3>
                  <p className="text-neutral-400 leading-relaxed max-w-2xl">
                    {step.description}
                  </p>
                </div>
              </motion.div>
            ))}
          </div>
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
            <h2 className="text-4xl sm:text-5xl font-serif font-semibold text-neutral-50">
              Ready to transform your research?
            </h2>
            <p className="text-xl text-neutral-400 max-w-2xl mx-auto">
              Join researchers worldwide who are saving weeks on literature reviews
            </p>
            <div className="flex flex-col sm:flex-row items-center justify-center gap-4 pt-4">
              <button
                onClick={() => navigate('/signup')}
                className="px-8 py-4 bg-accent-primary text-white font-semibold rounded-lg hover:bg-accent-hover transition-colors"
              >
                Start Free Trial
              </button>
              <button
                onClick={() => navigate('/login')}
                className="px-8 py-4 border border-neutral-700 text-neutral-300 font-medium rounded-lg hover:border-neutral-600 hover:text-neutral-50 transition-colors"
              >
                Sign In
              </button>
            </div>

            {/* Trust Indicators */}
            <div className="flex flex-wrap items-center justify-center gap-8 pt-8 text-sm text-neutral-500 font-mono">
              <div>✓ No credit card required</div>
              <div>✓ Free tier available</div>
              <div>✓ Cancel anytime</div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Footer */}
      <footer className="py-12 px-6 sm:px-8 border-t border-neutral-800">
        <div className="max-w-7xl mx-auto">
          <div className="flex flex-col md:flex-row justify-between items-center gap-6">
            <div className="flex items-center gap-3">
              <img src="/noesis.png" alt="Noesis" className="h-8" />
              <span className="text-lg font-serif font-semibold text-neutral-50">
                Noesis
              </span>
            </div>
            <div className="text-neutral-500 text-sm font-mono">
              © 2026 Noesis. All rights reserved.
            </div>
            <div className="flex items-center gap-6 text-neutral-500 text-sm">
              <a href="#" className="hover:text-neutral-300 transition-colors">Privacy</a>
              <a href="#" className="hover:text-neutral-300 transition-colors">Terms</a>
              <a href="#" className="hover:text-neutral-300 transition-colors">Contact</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

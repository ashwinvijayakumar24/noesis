import { useEffect } from 'react'
import { Link } from 'react-router-dom'
import { motion } from 'framer-motion'
import {
  ShieldCheckIcon,
  LockClosedIcon,
  ServerIcon,
  CloudIcon,
  DocumentTextIcon,
  UserGroupIcon,
  ClockIcon,
  GlobeAltIcon,
} from '@heroicons/react/24/outline'

export default function PrivacyPolicy() {
  useEffect(() => {
    document.title = 'Privacy Policy - Noesis'
    window.scrollTo(0, 0)
  }, [])

  const fadeIn = {
    initial: { opacity: 0, y: 12 },
    animate: { opacity: 1, y: 0 },
    transition: { duration: 0.5 }
  }

  const sections = [
    {
      icon: DocumentTextIcon,
      title: 'Information We Collect',
      id: 'information-collected',
      content: (
        <>
          <p className="text-text-secondary mb-4">
            We collect information necessary to provide our research intelligence services:
          </p>
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-text-primary mb-2">Account Information</h4>
              <ul className="list-disc pl-6 space-y-2 text-text-secondary">
                <li>Email address (for authentication and communication)</li>
                <li>Name (optional, for personalization)</li>
                <li>Account creation date and last login</li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-text-primary mb-2">Research Content</h4>
              <ul className="list-disc pl-6 space-y-2 text-text-secondary">
                <li>Research drafts (PDF, DOCX, TXT files)</li>
                <li>Literature documents (PDF files)</li>
                <li>Project titles and descriptions</li>
                <li>Chat messages and queries</li>
                <li>Annotations and notes</li>
              </ul>
            </div>
            <div>
              <h4 className="font-semibold text-text-primary mb-2">Usage Analytics</h4>
              <ul className="list-disc pl-6 space-y-2 text-text-secondary">
                <li>Feature usage patterns (documents uploaded, analyses run)</li>
                <li>Session duration and activity timestamps</li>
                <li>Error logs (with sensitive content redacted)</li>
              </ul>
            </div>
          </div>
        </>
      )
    },
    {
      icon: ShieldCheckIcon,
      title: 'How We Use Your Information',
      id: 'how-we-use',
      content: (
        <>
          <p className="text-text-secondary mb-4">
            Your data is used exclusively to provide and improve our research intelligence services:
          </p>
          <div className="space-y-3">
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-accent-primary"></div>
              <div>
                <p className="font-semibold text-text-primary">Provide AI Analysis Services</p>
                <p className="text-sm text-text-secondary">Process your drafts and documents to generate insights, identify claims, suggest citations, and provide reviewer-style feedback.</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-accent-primary"></div>
              <div>
                <p className="font-semibold text-text-primary">Improve Platform Features</p>
                <p className="text-sm text-text-secondary">Analyze aggregated usage patterns to enhance accuracy, speed, and user experience (no individual research content is used).</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-accent-primary"></div>
              <div>
                <p className="font-semibold text-text-primary">Send Service Notifications</p>
                <p className="text-sm text-text-secondary">Notify you about analysis completion, quota limits, and critical system updates.</p>
              </div>
            </div>
            <div className="flex items-start gap-3">
              <div className="flex-shrink-0 w-2 h-2 mt-2 rounded-full bg-accent-primary"></div>
              <div>
                <p className="font-semibold text-text-primary">Ensure Security & Compliance</p>
                <p className="text-sm text-text-secondary">Monitor for abuse, maintain system integrity, and comply with legal obligations.</p>
              </div>
            </div>
          </div>
          <div className="mt-6 p-4 bg-red-900/10 border border-red-500/20 rounded-lg">
            <p className="text-sm font-semibold text-red-400 mb-2">What We DO NOT Do:</p>
            <ul className="text-sm text-red-300 space-y-1 list-disc pl-5">
              <li>We do not send marketing emails without explicit consent</li>
              <li>We do not share your research with other users</li>
              <li>We do not sell your data to third parties</li>
              <li>We do not use your content for AI model training</li>
            </ul>
          </div>
        </>
      )
    },
    {
      icon: CloudIcon,
      title: 'Third-Party Services',
      id: 'third-party',
      content: (
        <>
          <p className="text-text-secondary mb-4">
            Noesis uses the following trusted third-party services to deliver our platform:
          </p>
          <div className="space-y-4">
            <div className="p-4 bg-surface border border-border-base rounded-lg">
              <div className="flex items-start gap-3 mb-2">
                <ServerIcon className="h-5 w-5 text-accent-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-text-primary">OpenAI (AI Processing)</h4>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Purpose:</strong> Powers AI analysis (GPT-4o) and embeddings (text-embedding-3-small)
                  </p>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Data Handling:</strong> Zero data retention enabled. Your research content is processed but never stored by OpenAI for training or other purposes.
                  </p>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Privacy Policy:</strong>{' '}
                    <a
                      href="https://openai.com/policies/privacy-policy"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent-primary hover:text-accent-hover underline"
                    >
                      OpenAI Privacy Policy
                    </a>
                  </p>
                </div>
              </div>
            </div>

            <div className="p-4 bg-surface border border-border-base rounded-lg">
              <div className="flex items-start gap-3 mb-2">
                <LockClosedIcon className="h-5 w-5 text-accent-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-text-primary">Supabase (Database, Auth, Storage)</h4>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Purpose:</strong> PostgreSQL database, user authentication, and file storage
                  </p>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Data Handling:</strong> All data encrypted at rest and in transit. Row-Level Security ensures user isolation.
                  </p>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Privacy Policy:</strong>{' '}
                    <a
                      href="https://supabase.com/privacy"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent-primary hover:text-accent-hover underline"
                    >
                      Supabase Privacy Policy
                    </a>
                  </p>
                </div>
              </div>
            </div>

            <div className="p-4 bg-surface border border-border-base rounded-lg">
              <div className="flex items-start gap-3 mb-2">
                <GlobeAltIcon className="h-5 w-5 text-accent-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-text-primary">Vercel (Hosting)</h4>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Purpose:</strong> Frontend application hosting and delivery
                  </p>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Data Handling:</strong> No access to user research content. Only serves static frontend assets.
                  </p>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Privacy Policy:</strong>{' '}
                    <a
                      href="https://vercel.com/legal/privacy-policy"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent-primary hover:text-accent-hover underline"
                    >
                      Vercel Privacy Policy
                    </a>
                  </p>
                </div>
              </div>
            </div>

            <div className="p-4 bg-surface border border-border-base rounded-lg">
              <div className="flex items-start gap-3 mb-2">
                <ServerIcon className="h-5 w-5 text-accent-primary flex-shrink-0 mt-0.5" />
                <div>
                  <h4 className="font-semibold text-text-primary">Sentry (Error Tracking)</h4>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Purpose:</strong> Application error monitoring and debugging
                  </p>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Data Handling:</strong> PII scrubbing enabled. Research content is automatically redacted from error logs.
                  </p>
                  <p className="text-sm text-text-muted mt-1">
                    <strong>Privacy Policy:</strong>{' '}
                    <a
                      href="https://sentry.io/privacy/"
                      target="_blank"
                      rel="noopener noreferrer"
                      className="text-accent-primary hover:text-accent-hover underline"
                    >
                      Sentry Privacy Policy
                    </a>
                  </p>
                </div>
              </div>
            </div>
          </div>
        </>
      )
    },
    {
      icon: ClockIcon,
      title: 'Data Retention',
      id: 'data-retention',
      content: (
        <>
          <p className="text-text-secondary mb-4">
            We retain your data only as long as necessary to provide our services:
          </p>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Active Account Data</h4>
                <p className="text-sm text-text-secondary">
                  Retained until you delete your account or specific projects/documents
                </p>
              </div>
              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Deleted Content</h4>
                <p className="text-sm text-text-secondary">
                  Permanently removed within 30 days (including backups)
                </p>
              </div>
              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Usage Analytics</h4>
                <p className="text-sm text-text-secondary">
                  Aggregated analytics retained indefinitely (no personal identifiers)
                </p>
              </div>
              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Legal Compliance</h4>
                <p className="text-sm text-text-secondary">
                  Minimal data retained if required by law (audit logs, billing records)
                </p>
              </div>
            </div>
            <div className="mt-4 p-4 bg-green-900/10 border border-green-500/20 rounded-lg">
              <p className="text-sm font-semibold text-green-400 mb-2">Your Control:</p>
              <p className="text-sm text-green-300">
                You can delete individual documents, projects, or your entire account at any time from your dashboard. Deletion is permanent and cannot be undone.
              </p>
            </div>
          </div>
        </>
      )
    },
    {
      icon: LockClosedIcon,
      title: 'Data Security',
      id: 'data-security',
      content: (
        <>
          <p className="text-text-secondary mb-4">
            We implement industry-standard security measures to protect your research:
          </p>
          <div className="space-y-4">
            <div>
              <h4 className="font-semibold text-text-primary mb-3">Technical Security Measures</h4>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                <div className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 mt-2 rounded-full bg-accent-primary flex-shrink-0"></div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Encryption</p>
                    <p className="text-xs text-text-muted">All data encrypted at rest (AES-256) and in transit (TLS 1.3)</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 mt-2 rounded-full bg-accent-primary flex-shrink-0"></div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Row-Level Security</p>
                    <p className="text-xs text-text-muted">Database isolation ensures you can only access your own data</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 mt-2 rounded-full bg-accent-primary flex-shrink-0"></div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Authentication</p>
                    <p className="text-xs text-text-muted">JWT-based authentication with secure password hashing (bcrypt)</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 mt-2 rounded-full bg-accent-primary flex-shrink-0"></div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Security Headers</p>
                    <p className="text-xs text-text-muted">CSP, HSTS, X-Frame-Options protect against common attacks</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 mt-2 rounded-full bg-accent-primary flex-shrink-0"></div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Rate Limiting</p>
                    <p className="text-xs text-text-muted">Prevents abuse and protects against cost explosion attacks</p>
                  </div>
                </div>
                <div className="flex items-start gap-2">
                  <div className="w-1.5 h-1.5 mt-2 rounded-full bg-accent-primary flex-shrink-0"></div>
                  <div>
                    <p className="text-sm font-medium text-text-primary">Regular Audits</p>
                    <p className="text-xs text-text-muted">Continuous monitoring for security vulnerabilities</p>
                  </div>
                </div>
              </div>
            </div>
            <div>
              <h4 className="font-semibold text-text-primary mb-3">AI Processing Security</h4>
              <ul className="space-y-2 text-sm text-text-secondary">
                <li className="flex items-start gap-2">
                  <span className="text-accent-primary">•</span>
                  <span><strong>Zero Data Retention:</strong> OpenAI does not store your research content for training or other purposes</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-accent-primary">•</span>
                  <span><strong>No Cross-User Contamination:</strong> Your data never appears in other users' results</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-accent-primary">•</span>
                  <span><strong>In-Memory Processing:</strong> No temporary files stored on disk during analysis</span>
                </li>
              </ul>
            </div>
          </div>
        </>
      )
    },
    {
      icon: UserGroupIcon,
      title: 'Your Privacy Rights (GDPR/CCPA)',
      id: 'user-rights',
      content: (
        <>
          <p className="text-text-secondary mb-4">
            You have comprehensive control over your data:
          </p>
          <div className="space-y-4">
            <div className="grid grid-cols-1 gap-4">
              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Right to Access</h4>
                <p className="text-sm text-text-secondary mb-2">
                  View and download all data associated with your account.
                </p>
                <p className="text-xs text-text-muted font-mono">
                  Available in: Dashboard → Settings → Export Data
                </p>
              </div>

              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Right to Deletion</h4>
                <p className="text-sm text-text-secondary mb-2">
                  Permanently delete your account and all associated data.
                </p>
                <p className="text-xs text-text-muted font-mono">
                  Available in: Dashboard → Settings → Delete Account
                </p>
              </div>

              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Right to Portability</h4>
                <p className="text-sm text-text-secondary mb-2">
                  Export your data in machine-readable formats (JSON, BibTeX, PDF).
                </p>
                <p className="text-xs text-text-muted font-mono">
                  Available in: Project pages → Export options
                </p>
              </div>

              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Right to Opt-Out</h4>
                <p className="text-sm text-text-secondary mb-2">
                  Disable optional analytics and email notifications.
                </p>
                <p className="text-xs text-text-muted font-mono">
                  Available in: Dashboard → Settings → Privacy Preferences
                </p>
              </div>

              <div className="p-4 bg-surface border border-border-base rounded-lg">
                <h4 className="font-semibold text-text-primary mb-2">Right to Rectification</h4>
                <p className="text-sm text-text-secondary mb-2">
                  Correct inaccurate personal information at any time.
                </p>
                <p className="text-xs text-text-muted font-mono">
                  Available in: Dashboard → Settings → Account Information
                </p>
              </div>
            </div>

            <div className="p-4 bg-blue-900/10 border border-blue-500/20 rounded-lg">
              <p className="text-sm font-semibold text-blue-400 mb-2">Need Help?</p>
              <p className="text-sm text-blue-300">
                To exercise any of these rights or if you have questions, contact us at{' '}
                <a href="mailto:privacy@noesis.app" className="underline hover:text-blue-200">
                  privacy@noesis.app
                </a>
              </p>
              <p className="text-xs text-blue-400 mt-2">We respond to all requests within 30 days.</p>
            </div>
          </div>
        </>
      )
    },
  ]

  return (
    <div className="min-h-screen bg-bg-base text-text-primary">
      {/* Navigation */}
      <nav className="fixed top-0 left-0 right-0 z-50 bg-bg-base/80 backdrop-blur-sm border-b border-border-base">
        <div className="max-w-7xl mx-auto px-6 sm:px-8">
          <div className="flex justify-between items-center h-16">
            <Link to="/" className="flex items-center gap-3">
              <img src="/noesis.png" alt="Noesis" className="h-8" />
              <span className="text-lg font-serif font-semibold text-text-primary">
                Noesis
              </span>
            </Link>
            <Link
              to="/"
              className="px-4 py-2 text-sm font-medium text-text-tertiary hover:text-text-primary transition-colors"
            >
              Back to Home
            </Link>
          </div>
        </div>
      </nav>

      {/* Header */}
      <section className="pt-32 pb-16 px-6 sm:px-8">
        <div className="max-w-4xl mx-auto">
          <motion.div {...fadeIn}>
            <div className="flex items-center gap-3 mb-6">
              <ShieldCheckIcon className="h-12 w-12 text-accent-primary" />
              <h1 className="text-4xl md:text-5xl font-serif font-bold text-text-primary">
                Privacy Policy
              </h1>
            </div>
            <p className="text-lg text-text-secondary mb-4">
              Your research is private and secure. This policy explains how we collect, use, and protect your data.
            </p>
            <p className="text-sm text-text-muted font-mono">
              Last Updated: February 14, 2026
            </p>
          </motion.div>
        </div>
      </section>

      {/* Quick Summary */}
      <section className="pb-12 px-6 sm:px-8">
        <div className="max-w-4xl mx-auto">
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.1 }}
          >
            <div className="p-6 bg-accent-primary/5 border border-accent-primary/20 rounded-xl">
              <h2 className="text-xl font-semibold text-text-primary mb-4">Privacy Commitment (TL;DR)</h2>
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 text-sm">
                <div className="flex items-start gap-3">
                  <ShieldCheckIcon className="h-5 w-5 text-accent-primary flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-text-primary">Your Data is Private</p>
                    <p className="text-text-muted">Never shared with other users or sold to third parties</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <LockClosedIcon className="h-5 w-5 text-accent-primary flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-text-primary">Zero Data Retention</p>
                    <p className="text-text-muted">OpenAI doesn't store your research for training</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <ServerIcon className="h-5 w-5 text-accent-primary flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-text-primary">Complete User Isolation</p>
                    <p className="text-text-muted">Row-Level Security ensures account-level separation</p>
                  </div>
                </div>
                <div className="flex items-start gap-3">
                  <UserGroupIcon className="h-5 w-5 text-accent-primary flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-semibold text-text-primary">You Have Control</p>
                    <p className="text-text-muted">Access, export, or delete your data anytime</p>
                  </div>
                </div>
              </div>
            </div>
          </motion.div>
        </div>
      </section>

      {/* Main Content Sections */}
      <section className="pb-20 px-6 sm:px-8">
        <div className="max-w-4xl mx-auto space-y-12">
          {sections.map((section, index) => (
            <motion.div
              key={section.id}
              id={section.id}
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              transition={{ duration: 0.6, delay: 0.1 * (index + 2) }}
              className="scroll-mt-24"
            >
              <div className="flex items-center gap-3 mb-6">
                <section.icon className="h-8 w-8 text-accent-primary" />
                <h2 className="text-2xl font-serif font-semibold text-text-primary">
                  {section.title}
                </h2>
              </div>
              <div className="pl-11">
                {section.content}
              </div>
            </motion.div>
          ))}

          {/* Contact Section */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.8 }}
            className="pt-8 border-t border-border-base"
          >
            <h2 className="text-2xl font-serif font-semibold text-text-primary mb-6">
              Contact Us
            </h2>
            <div className="space-y-4 text-text-secondary">
              <p>
                If you have questions about this Privacy Policy or our data practices, please contact us:
              </p>
              <div className="p-4 bg-surface border border-border-base rounded-lg space-y-2">
                <p className="text-sm">
                  <strong className="text-text-primary">Email:</strong>{' '}
                  <a href="mailto:privacy@noesis.app" className="text-accent-primary hover:text-accent-hover underline">
                    privacy@noesis.app
                  </a>
                </p>
                <p className="text-sm">
                  <strong className="text-text-primary">Response Time:</strong> Within 48 hours for privacy concerns
                </p>
                <p className="text-sm">
                  <strong className="text-text-primary">GDPR/CCPA Requests:</strong> Processed within 30 days
                </p>
              </div>
            </div>
          </motion.div>

          {/* Updates */}
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.6, delay: 0.9 }}
            className="pt-8 border-t border-border-base"
          >
            <h2 className="text-2xl font-serif font-semibold text-text-primary mb-6">
              Policy Updates
            </h2>
            <p className="text-text-secondary mb-4">
              We may update this Privacy Policy periodically to reflect changes in our practices or legal requirements.
            </p>
            <div className="p-4 bg-surface border border-border-base rounded-lg">
              <ul className="space-y-2 text-sm text-text-secondary">
                <li className="flex items-start gap-2">
                  <span className="text-accent-primary">•</span>
                  <span><strong>Material Changes:</strong> We'll notify you via email at least 30 days before changes take effect</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-accent-primary">•</span>
                  <span><strong>Minor Updates:</strong> Posted on this page with an updated "Last Updated" date</span>
                </li>
                <li className="flex items-start gap-2">
                  <span className="text-accent-primary">•</span>
                  <span><strong>Your Options:</strong> Continued use constitutes acceptance; you may delete your account if you disagree</span>
                </li>
              </ul>
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
              <Link to="/privacy" className="hover:text-text-secondary transition-colors">Privacy</Link>
              <a href="#" className="hover:text-text-secondary transition-colors">Terms</a>
              <a href="mailto:privacy@noesis.app" className="hover:text-text-secondary transition-colors">Contact</a>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}

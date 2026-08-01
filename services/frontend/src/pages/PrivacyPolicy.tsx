import { useEffect, type ReactNode } from 'react'
import {
  ClockIcon,
  CloudIcon,
  DocumentTextIcon,
  GlobeAltIcon,
  LockClosedIcon,
  ServerIcon,
  ShieldCheckIcon,
  UserGroupIcon,
} from '@heroicons/react/24/outline'
import PublicLayout from '../components/layout/PublicLayout'

const Section = ({
  icon: Icon,
  title,
  children,
}: {
  icon: typeof ShieldCheckIcon
  title: string
  children: ReactNode
}) => (
  <section className="rounded-lg border border-border-default bg-bg-surface p-5 sm:p-6">
    <div className="mb-4 flex items-center gap-3">
      <div className="flex h-9 w-9 items-center justify-center rounded-lg border border-border-default bg-bg-elevated">
        <Icon className="h-4 w-4 text-accent-primary" />
      </div>
      <h2 className="text-lg font-semibold text-text-primary">{title}</h2>
    </div>
    <div className="space-y-4 text-sm leading-6 text-text-secondary">{children}</div>
  </section>
)

const BulletList = ({ children }: { children: ReactNode }) => (
  <ul className="space-y-2 pl-4">{children}</ul>
)

const Bullet = ({ children }: { children: ReactNode }) => (
  <li className="list-disc pl-1">{children}</li>
)

const Strong = ({ children }: { children: ReactNode }) => (
  <span className="font-semibold text-text-primary">{children}</span>
)

export default function PrivacyPolicy() {
  useEffect(() => {
    window.scrollTo(0, 0)
    document.title = 'Privacy Policy | Noesis'
  }, [])

  return (
    <PublicLayout>
      <main>
        <section className="border-b border-border-default px-4 py-16 sm:px-6 sm:py-20 lg:px-8">
          <div className="mx-auto max-w-4xl">
            <div className="mb-5 inline-flex items-center gap-2 rounded-full border border-border-default bg-bg-surface px-3 py-1.5 text-xs font-semibold text-text-secondary">
              <ShieldCheckIcon className="h-4 w-4 text-accent-primary" />
              Privacy Policy
            </div>
            <h1 className="text-4xl font-heading font-semibold leading-tight text-text-primary sm:text-5xl">
              How Noesis handles research drafts and data.
            </h1>
            <p className="mt-5 max-w-3xl text-base leading-7 text-text-secondary sm:text-lg">
              Noesis is built for unpublished academic work. This policy explains what we collect,
              how draft analysis works, who processes data, and what is retained.
            </p>
            <p className="mt-4 font-mono text-xs text-text-muted">Last updated: May 27, 2026</p>
          </div>
        </section>

        <section className="px-4 py-12 sm:px-6 lg:px-8">
          <div className="mx-auto max-w-4xl space-y-5">
            <div className="rounded-xl border border-border-default bg-bg-surface p-5 shadow-xs sm:p-6">
              <div className="mb-4 flex items-center justify-between gap-4 border-b border-border-default pb-4">
                <h2 className="text-lg font-semibold text-text-primary">Plain-English Summary</h2>
                <span className="hidden rounded-md border border-border-default bg-bg-elevated px-2.5 py-1 font-mono text-[11px] text-text-tertiary sm:inline-flex">
                  Data handling
                </span>
              </div>
              <BulletList>
                <Bullet>
                  <Strong>Your drafts are private to your account.</Strong> Draft files are stored in
                  private Supabase Storage buckets, not public buckets.
                </Bullet>
                <Bullet>
                  <Strong>Noesis uses provider APIs, not consumer chat products.</Strong> Draft analysis
                  is processed through the OpenAI API and backend services.
                </Bullet>
                <Bullet>
                  <Strong>We do not train Noesis models on your drafts.</Strong> We also do not sell
                  manuscripts, projects, literature collections, or generated feedback.
                </Bullet>
                <Bullet>
                  <Strong>Drafts remain available until you delete them.</Strong> This lets you reopen
                  the PDF, revisit feedback, export reports, and compare revisions.
                </Bullet>
                <Bullet>
                  <Strong>External literature services do not receive full draft files.</Strong> They
                  receive only the search terms, identifiers, claims, or short queries needed to find
                  relevant papers.
                </Bullet>
              </BulletList>
            </div>

            <Section icon={DocumentTextIcon} title="Information We Collect">
              <p>We collect the information needed to run Noesis and analyze your research work.</p>
              <BulletList>
                <Bullet>
                  <Strong>Account information:</Strong> email address, authentication identifiers,
                  login metadata, and optional OAuth profile information if you sign in with Google.
                </Bullet>
                <Bullet>
                  <Strong>Research content:</Strong> projects, project descriptions, uploaded PDFs,
                  BibTeX references, draft manuscripts, extracted text, citation metadata, generated
                  feedback, reviewer-style tasks, anchors, and exports you request.
                </Bullet>
                <Bullet>
                  <Strong>Usage and diagnostic data:</Strong> quota usage, feature events, processing
                  status, performance data, and error reports. We scrub logs to avoid storing raw
                  manuscript text in diagnostics.
                </Bullet>
                <Bullet>
                  <Strong>Billing data:</Strong> if you purchase a paid plan, payment and subscription
                  metadata is handled by Stripe. We do not store full card numbers.
                </Bullet>
              </BulletList>
            </Section>

            <Section icon={ServerIcon} title="How We Use Your Data">
              <p>We use your data to provide the product and protect the service.</p>
              <BulletList>
                <Bullet>Authenticate users and keep projects scoped to the correct account.</Bullet>
                <Bullet>Store literature libraries, drafts, generated analyses, and exports.</Bullet>
                <Bullet>
                  Analyze manuscripts for claims, citation gaps, coverage gaps, reviewer-style
                  critique, readiness scoring, and revision tasks.
                </Bullet>
                <Bullet>Search external scholarly sources for relevant citations and paper metadata.</Bullet>
                <Bullet>Enforce quotas, prevent abuse, debug failures, and maintain security.</Bullet>
              </BulletList>
              <p>
                We do not use your unpublished drafts to train Noesis models, and we do not sell your
                research content.
              </p>
            </Section>

            <Section icon={CloudIcon} title="Draft Analysis Data Flow">
              <p>When you upload a draft, the current architecture works like this:</p>
              <BulletList>
                <Bullet>
                  The draft file is uploaded to a private Supabase Storage bucket and associated with
                  your authenticated user and project.
                </Bullet>
                <Bullet>
                  The backend retrieves the file, extracts text and page-level context, and sends the
                  necessary text, claims, or chunks to the OpenAI API for analysis and embeddings.
                </Bullet>
                <Bullet>
                  Background workers process analysis jobs. Queue and progress records are minimized
                  and are intended to carry job state rather than full manuscript files.
                </Bullet>
                <Bullet>
                  Noesis stores the generated analysis, revision tasks, citation checks, short anchors,
                  and metadata needed to show the results again without requiring a full rerun.
                </Bullet>
                <Bullet>
                  The uploaded draft remains stored so you can reopen it, view page anchors, export
                  results, and compare future revisions. Deleting the draft removes the stored file and
                  associated analysis data.
                </Bullet>
              </BulletList>
            </Section>

            <Section icon={GlobeAltIcon} title="Third-Party Processors">
              <p>Noesis depends on a small number of infrastructure and AI providers.</p>
              <BulletList>
                <Bullet>
                  <Strong>Supabase:</Strong> authentication, PostgreSQL database, and private file
                  storage for drafts and literature uploads.
                </Bullet>
                <Bullet>
                  <Strong>OpenAI API:</Strong> draft analysis, structured feedback generation, and
                  embeddings. Noesis uses API calls from the backend, not consumer ChatGPT sessions.
                </Bullet>
                <Bullet>
                  <Strong>PubMed, Semantic Scholar, OpenAlex, and arXiv:</Strong> literature search and
                  metadata lookup. We send targeted search queries, paper identifiers, extracted claims,
                  or citation context rather than full draft PDFs.
                </Bullet>
                <Bullet><Strong>Vercel and AWS:</Strong> frontend and backend hosting infrastructure.</Bullet>
                <Bullet><Strong>Sentry:</Strong> error monitoring with sensitive-content scrubbing.</Bullet>
                <Bullet><Strong>Stripe:</Strong> payments and subscription management for paid plans.</Bullet>
              </BulletList>
            </Section>

            <Section icon={ClockIcon} title="Retention and Deletion">
              <p>
                Drafts are not automatically deleted immediately after processing because Noesis uses
                them to support PDF viewing, page anchors, exports, reruns, and revision comparison.
              </p>
              <BulletList>
                <Bullet>
                  <Strong>Drafts:</Strong> retained while the draft exists in your project. When you
                  delete a draft, Noesis deletes the stored draft file and associated analysis records.
                </Bullet>
                <Bullet>
                  <Strong>Projects and literature:</Strong> retained until you delete the relevant
                  project, document, or account.
                </Bullet>
                <Bullet>
                  <Strong>Generated analysis:</Strong> retained so you can return to prior feedback and
                  compare revisions, unless the draft or project is deleted.
                </Bullet>
                <Bullet>
                  <Strong>Operational records:</Strong> quota, billing, security, and diagnostic
                  records may be retained as needed to operate the service, resolve disputes, prevent
                  abuse, and meet legal obligations.
                </Bullet>
              </BulletList>
              <p>
                If a deletion request fails or you want account-level deletion, contact us and we will
                help remove the relevant data.
              </p>
            </Section>

            <Section icon={LockClosedIcon} title="Security">
              <p>We use practical security controls appropriate for a production academic SaaS.</p>
              <BulletList>
                <Bullet>Private storage buckets for uploaded drafts and documents.</Bullet>
                <Bullet>Authenticated API access and user-scoped authorization checks.</Bullet>
                <Bullet>Encrypted connections through HTTPS/TLS for hosted product traffic.</Bullet>
                <Bullet>Provider-managed encryption at rest for database and storage services.</Bullet>
                <Bullet>Log scrubbing to reduce the risk of manuscript text appearing in logs.</Bullet>
                <Bullet>Secrets managed through environment configuration rather than frontend code.</Bullet>
              </BulletList>
              <p>
                Noesis has not completed SOC 2 Type II certification. We are prioritizing correct
                architecture, data minimization, and transparent claims before pursuing formal
                compliance programs.
              </p>
            </Section>

            <Section icon={UserGroupIcon} title="Your Choices">
              <BulletList>
                <Bullet>You can delete drafts and projects you no longer want stored.</Bullet>
                <Bullet>You can export available project and analysis outputs from supported screens.</Bullet>
                <Bullet>You can contact us to request account deletion or ask what data is associated with your account.</Bullet>
                <Bullet>You can choose not to upload unpublished work if you are not comfortable with the processing flow above.</Bullet>
              </BulletList>
            </Section>

            <Section icon={ShieldCheckIcon} title="Contact and Updates">
              <p>
                For privacy questions, deletion requests, or security concerns, contact{' '}
                <a className="text-accent-primary transition-colors hover:text-accent-hover" href="mailto:ashwin@noesis.is">
                  ashwin@noesis.is
                </a>
                .
              </p>
              <p>
                We may update this policy as the product changes. When we make material changes, we
                will update the date above and, when appropriate, notify users in the product.
              </p>
            </Section>
          </div>
        </section>
      </main>
    </PublicLayout>
  )
}

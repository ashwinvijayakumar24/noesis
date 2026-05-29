import { describe, expect, it } from 'vitest'
import { readFile } from 'node:fs/promises'

async function readSourceFile(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), 'utf8')
}

describe('pricing and quota copy', () => {
  it('updates the dedicated pricing page to current per-user quotas', async () => {
    const source = await readSourceFile('./pages/Pricing.tsx')

    expect(source).toContain('3 active projects')
    expect(source).toContain('2 draft analyses per month')
    expect(source).toContain('30 PDF uploads per month total')
    expect(source).toContain('30 BibTeX references per month total')
    expect(source).toContain('10 active projects')
    expect(source).toContain('20 draft analyses per month')
    expect(source).toContain('100 PDF uploads per month total')
    expect(source).toContain('100 BibTeX references per month total')
    expect(source).toContain('2-3 users billed per seat')
    expect(source).toContain('Effectively unlimited usage across PDFs, BibTeX, and draft analyses')
    expect(source).toContain('avijayakumar41@gatech.edu')
    expect(source).not.toContain('Discover searches')
    expect(source).not.toContain('Literature Map refreshes')
    expect(source).not.toContain('Team collaboration features')
    expect(source).not.toContain('Shared project workspaces')
    expect(source).not.toContain('5 draft analyses per month')
    expect(source).not.toContain('100 BibTeX imports per month')
    expect(source).not.toContain('10 paper discovery searches per day')
    expect(source).not.toContain('Lab member invite link')
  })

  it('keeps the landing page focused on draft review instead of duplicated pricing tables', async () => {
    const source = await readSourceFile('./pages/Landing.tsx')

    expect(source).toContain('Pre-submission review for research drafts')
    expect(source).toContain('Unsupported claims')
    expect(source).toContain('Reviewer panel')
    expect(source).toContain('Revision queue')
    expect(source).toContain('targeted external scholarly context')
    expect(source).toContain('targeted external-source lookup')
    expect(source).toContain('External services receive focused search queries or citation context, not your full draft file.')
    expect(source).toContain('2 draft analyses per month')
    expect(source).toContain('20 draft analyses per month')
    expect(source).not.toContain('Enterprise Plan')
    expect(source).not.toContain('Contact Sales')
    expect(source).not.toContain('Discover searches')
    expect(source).not.toContain('Literature Map refreshes')
    expect(source).not.toContain('Team collaboration features')
    expect(source).not.toContain('Shared project workspaces')
    expect(source).not.toContain('minimum 3 users')
    expect(source).not.toContain('Unlimited draft analyses')
    expect(source).not.toContain('Unlimited document uploads')
    expect(source).not.toContain('10 paper discovery searches per day')
  })

  it('standardizes public-page links and contact domains', async () => {
    const landing = await readSourceFile('./pages/Landing.tsx')
    const privacy = await readSourceFile('./pages/PrivacyPolicy.tsx')
    const publicLayout = await readSourceFile('./components/layout/PublicLayout.tsx')

    expect(publicLayout).toContain('mailto:avijayakumar41@gatech.edu')
    expect(privacy).toContain('mailto:avijayakumar41@gatech.edu')
    expect(landing).not.toContain('Terms')
    expect(publicLayout).not.toContain('Terms')
    expect(landing).not.toContain('href="#"')
    expect(publicLayout).not.toContain('href="#"')
    expect(landing + privacy + publicLayout).not.toContain('noesis.app')
    expect(landing + privacy + publicLayout).not.toContain('noesis.dev')
  })

  it('updates upgrade and email capture modals to current plans and quotas', async () => {
    const upgradeModal = await readSourceFile('./components/UpgradeModal.tsx')
    const emailCaptureModal = await readSourceFile('./components/EmailCaptureModal.tsx')

    expect(upgradeModal).toContain('monthly PDF or BibTeX import')
    expect(upgradeModal).toContain('20 draft analyses per month')
    expect(upgradeModal).toContain('100 PDF uploads per month total')
    expect(upgradeModal).toContain('100 BibTeX references per month total')
    expect(upgradeModal).toContain('Team')
    expect(upgradeModal).not.toContain('Discover searches')
    expect(upgradeModal).not.toContain('Literature Map refreshes')
    expect(upgradeModal).not.toContain('Lab')
    expect(upgradeModal).not.toContain('$49')

    expect(emailCaptureModal).toContain('2 draft analyses per month on Free')
    expect(emailCaptureModal).toContain('30 PDF uploads and 30 BibTeX references per month')
    expect(emailCaptureModal).toContain('Literature-grounded draft review')
    expect(emailCaptureModal).not.toContain('Unlimited draft analyses (free tier)')
  })
})

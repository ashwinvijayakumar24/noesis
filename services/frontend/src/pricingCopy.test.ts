import { describe, expect, it } from 'vitest'
import { readFile } from 'node:fs/promises'

async function readSourceFile(relativePath: string) {
  return readFile(new URL(relativePath, import.meta.url), 'utf8')
}

describe('pricing and quota copy', () => {
  it('updates the dedicated pricing page to current per-user quotas', async () => {
    const source = await readSourceFile('./pages/Pricing.tsx')

    expect(source).toContain('2 draft analyses per month')
    expect(source).toContain('30 PDF uploads per month total')
    expect(source).toContain('30 BibTeX references per month total')
    expect(source).toContain('5 Discover searches per day')
    expect(source).toContain('5 Literature Map refreshes per day')
    expect(source).toContain('20 draft analyses per month')
    expect(source).toContain('100 PDF uploads per month total')
    expect(source).toContain('100 BibTeX references per month total')
    expect(source).toContain('50 Discover searches per day')
    expect(source).toContain('Unlimited Literature Map refreshes')
    expect(source).toContain('2–3 users billed per seat')
    expect(source).not.toContain('5 draft analyses per month')
    expect(source).not.toContain('100 BibTeX imports per month')
    expect(source).not.toContain('10 paper discovery searches per day')
    expect(source).not.toContain('Lab member invite link')
  })

  it('updates landing page pricing copy and FAQ language', async () => {
    const source = await readSourceFile('./pages/Landing.tsx')

    expect(source).toContain('2 draft analyses per month')
    expect(source).toContain('30 BibTeX references per month total')
    expect(source).toContain('5 Discover searches per day')
    expect(source).toContain('5 Literature Map refreshes per day')
    expect(source).toContain('100 PDF uploads per month total')
    expect(source).toContain('Unlimited Literature Map refreshes')
    expect(source).toContain('2-3 users billed per seat')
    expect(source).not.toContain('minimum 3 users')
    expect(source).not.toContain('Unlimited draft analyses')
    expect(source).not.toContain('Unlimited document uploads')
    expect(source).not.toContain('10 paper discovery searches per day')
  })

  it('updates upgrade and email capture modals to current plans and quotas', async () => {
    const upgradeModal = await readSourceFile('./components/UpgradeModal.tsx')
    const emailCaptureModal = await readSourceFile('./components/EmailCaptureModal.tsx')

    expect(upgradeModal).toContain('monthly PDF or BibTeX import')
    expect(upgradeModal).toContain('daily Discover search')
    expect(upgradeModal).toContain('20 draft analyses per month')
    expect(upgradeModal).toContain('100 PDF uploads per month total')
    expect(upgradeModal).toContain('100 BibTeX references per month total')
    expect(upgradeModal).toContain('50 Discover searches per day')
    expect(upgradeModal).toContain('Unlimited Literature Map refreshes')
    expect(upgradeModal).toContain('Team')
    expect(upgradeModal).not.toContain('Lab')
    expect(upgradeModal).not.toContain('$49')

    expect(emailCaptureModal).toContain('2 draft analyses per month on Free')
    expect(emailCaptureModal).toContain('30 PDF uploads and 30 BibTeX references per month')
    expect(emailCaptureModal).toContain('5 Discover searches and 5 Literature Map refreshes per day')
    expect(emailCaptureModal).not.toContain('Unlimited draft analyses (free tier)')
  })
})

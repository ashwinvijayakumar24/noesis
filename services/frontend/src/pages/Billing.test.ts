import { beforeAll, describe, expect, it } from 'vitest'

const storage = {
  getItem: () => null,
  setItem: () => undefined,
  removeItem: () => undefined,
  clear: () => undefined,
}

beforeAll(() => {
  Object.defineProperty(globalThis, 'sessionStorage', { value: storage, configurable: true })
  Object.defineProperty(globalThis, 'localStorage', { value: storage, configurable: true })
})

describe('Billing helpers', () => {
  describe('usagePct', () => {
    it('returns the usage percentage rounded to the nearest integer', async () => {
      const { usagePct } = await import('./Billing')
      expect(usagePct(5, 10)).toBe(50)
      expect(usagePct(1, 3)).toBe(33)
    })

    it('caps at 100 when used exceeds limit', async () => {
      const { usagePct } = await import('./Billing')
      expect(usagePct(15, 10)).toBe(100)
    })

    it('returns 0 for unlimited limits (>= 9999)', async () => {
      const { usagePct } = await import('./Billing')
      expect(usagePct(500, 9999)).toBe(0)
      expect(usagePct(0, 10000)).toBe(0)
    })

    it('returns 0 when limit is zero or negative', async () => {
      const { usagePct } = await import('./Billing')
      expect(usagePct(5, 0)).toBe(0)
    })
  })

  describe('planLabel', () => {
    it('maps known tiers to display labels', async () => {
      const { planLabel } = await import('./Billing')
      expect(planLabel('free')).toBe('Free')
      expect(planLabel('pro')).toBe('Pro')
      expect(planLabel('team')).toBe('Research Group')
    })

    it('capitalises unknown tiers', async () => {
      const { planLabel } = await import('./Billing')
      expect(planLabel('enterprise')).toBe('Enterprise')
    })
  })
})

describe('api.subscriptions contract', () => {
  it('exposes all required methods with correct names', async () => {
    const { api } = await import('../lib/api')
    expect(typeof api.subscriptions.getPlans).toBe('function')
    expect(typeof api.subscriptions.createCheckout).toBe('function')
    expect(typeof api.subscriptions.cancel).toBe('function')
    expect(typeof api.subscriptions.getUsage).toBe('function')
    expect(typeof api.subscriptions.getPortalSession).toBe('function')
  })

  it('does not expose the old method names', async () => {
    const { api } = await import('../lib/api')
    const subs = api.subscriptions as Record<string, unknown>
    expect(subs['checkout']).toBeUndefined()
    expect(subs['usage']).toBeUndefined()
    expect(subs['portalSession']).toBeUndefined()
  })
})

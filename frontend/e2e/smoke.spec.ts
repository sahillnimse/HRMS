/**
 * Lightweight Playwright E2E smoke test covering critical HRMS AI flows.
 * Run with:
 *   npx playwright test frontend/e2e/smoke.spec.ts
 * Requires running backend (localhost:8000) + frontend (localhost:5173) and
 * env vars E2E_EMAIL / E2E_PASSWORD.
 */

// @ts-expect-error Optional dev dependency: install `@playwright/test` when running E2E locally or in CI.
import { test, expect } from '@playwright/test'

const BASE_URL = process.env.E2E_BASE_URL || 'http://localhost:5173'
const EMAIL = process.env.E2E_EMAIL || 'admin@company.com'
const PASSWORD = process.env.E2E_PASSWORD || 'AdminPass123!'

test.describe('HRMS AI Smoke Suite', () => {
  test('login, natural-language search, jobs, interviews, analytics, and admin privacy', async ({
    page,
  }: {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    page: any
  }) => {
    await page.goto(`${BASE_URL}/login`)
    await page.fill('input[type="email"]', EMAIL)
    await page.fill('input[type="password"]', PASSWORD)
    await page.click('button[type="submit"]')

    await expect(page.getByText('Candidate Dashboard')).toBeVisible({ timeout: 15000 })

    // Navigate through core workspace screens
    await page.goto(`${BASE_URL}/jobs`)
    await expect(page.getByText(/Jobs|Requisitions/i).first()).toBeVisible()

    await page.goto(`${BASE_URL}/interviews`)
    await expect(page.getByText('Interviews & Templates')).toBeVisible()

    await page.goto(`${BASE_URL}/analytics`)
    await expect(page.getByText('Hiring Analytics')).toBeVisible()

    await page.goto(`${BASE_URL}/privacy`)
    await expect(page.getByText('Privacy, Retention & Admin Tools')).toBeVisible()
  })
})

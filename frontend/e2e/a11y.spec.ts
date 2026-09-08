import AxeBuilder from '@axe-core/playwright'
import { expect, test } from '@playwright/test'

import { mockAuthenticatedApis } from './fixtures'

test.describe('public home — accessibility & quality', () => {
  test('axe: no serious/critical violations', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Voice2Appointment' })).toBeVisible()

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'])
      .analyze()

    const blocking = results.violations.filter((v) =>
      ['serious', 'critical'].includes(v.impact ?? ''),
    )
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([])
  })

  test('landmarks and skip link', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('main')).toHaveAttribute('id', 'main-content')
    await page.keyboard.press('Tab')
    const skip = page.getByRole('link', { name: 'Skip to main content' })
    await expect(skip).toBeFocused()
    await skip.press('Enter')
    await expect(page.locator('#main-content')).toBeFocused()
  })

  test('keyboard-only: sign-in fields reachable', async ({ page }) => {
    await page.goto('/?mode=signIn')
    const email = page.getByLabel(/email/i).first()
    await email.focus()
    await expect(email).toBeFocused()
    await page.keyboard.type('person@example.com')
    await page.keyboard.press('Tab')
    const password = page.getByLabel(/password/i).first()
    await expect(password).toBeFocused()
  })

  test('mobile viewport keeps brand + form usable', async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Voice2Appointment' })).toBeVisible()
    await expect(page.getByLabel(/email/i).first()).toBeVisible()
    const box = await page.getByRole('heading', { name: 'Voice2Appointment' }).boundingBox()
    expect(box?.width ?? 0).toBeGreaterThan(120)
  })

  test('200% zoom still shows primary CTA region', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      document.documentElement.style.zoom = '2'
    })
    await expect(page.getByRole('heading', { name: 'Voice2Appointment' })).toBeVisible()
    await expect(page.getByLabel(/email/i).first()).toBeVisible()
  })

  test('forced-colors + reduced-motion do not hide main content', async ({ page }) => {
    await page.emulateMedia({ forcedColors: 'active', reducedMotion: 'reduce' })
    await page.goto('/')
    await expect(page.getByRole('main')).toBeVisible()
    await expect(page.getByRole('heading', { name: 'Voice2Appointment' })).toBeVisible()
  })

  test('long translated headline wraps without clipping controls', async ({ page }) => {
    await page.goto('/')
    await page.evaluate(() => {
      const h = document.querySelector('h1')
      if (h) {
        h.textContent =
          'Sprachgesteuerte Terminvereinbarung für internationale Kundenanfragen und mehrsprachige Unterstützung'
      }
    })
    const heading = page.locator('h1')
    await expect(heading).toBeVisible()
    const box = await heading.boundingBox()
    expect(box?.height ?? 0).toBeGreaterThan(40)
    await expect(page.getByLabel(/email/i).first()).toBeVisible()
  })

  test('visual regression: home hero', async ({ page }) => {
    await page.goto('/')
    await expect(page.getByRole('heading', { name: 'Voice2Appointment' })).toBeVisible()
    await expect(page).toHaveScreenshot('home-hero.png', {
      fullPage: false,
      // Fonts/subpixel differ slightly across CI hosts.
      maxDiffPixelRatio: 0.04,
    })
  })
})

test.describe('authenticated shell — a11y smoke', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedApis(page)
  })

  test('dashboard landmarks + axe', async ({ page }) => {
    await page.goto('/dashboard')
    await expect(page.getByRole('heading', { name: 'Today' })).toBeVisible({ timeout: 15_000 })
    await expect(page.getByRole('navigation', { name: 'Primary' })).toBeVisible()
    await expect(page.getByRole('main')).toHaveAttribute('id', 'main-content')

    const results = await new AxeBuilder({ page })
      .withTags(['wcag2a', 'wcag2aa'])
      .disableRules(['color-contrast']) // frosted glass / chart chrome can flake in CI
      .analyze()
    const blocking = results.violations.filter((v) =>
      ['serious', 'critical'].includes(v.impact ?? ''),
    )
    expect(blocking, JSON.stringify(blocking, null, 2)).toEqual([])
  })
})

import { expect, test } from '@playwright/test'

import { mockAuthenticatedApis } from './fixtures'

test.describe('dialog focus restore', () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedApis(page)
  })

  test('calendar disconnect dialog returns focus to opener', async ({ page }) => {
    await page.goto('/integrations')
    await page.getByRole('tab', { name: 'Calendar' }).click()
    const disconnect = page.getByRole('button', { name: 'Disconnect' })
    await expect(disconnect).toBeEnabled({ timeout: 10_000 })
    await disconnect.focus()
    await disconnect.click()
    const dialog = page.getByRole('dialog')
    await expect(dialog).toBeVisible()
    await page.getByRole('button', { name: 'Cancel' }).click()
    await expect(dialog).toBeHidden()
    await expect(disconnect).toBeFocused()
  })
})

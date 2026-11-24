import { test, expect } from '@playwright/test'

// Runs against the mock backend: login → library → experiment → draw a box → autosave.
test('login, draw a box and autosave', async ({ page }, info) => {
  const fa = info.project.name === 'fa'
  await page.goto('/login')
  if (!fa) await page.evaluate(() => localStorage.setItem('lang', 'en'))
  await page.reload()
  await page.fill('#u', 'admin'); await page.fill('#p', 'admin')
  await page.locator('form button').click()
  await expect(page).toHaveURL(/\/images$/)
  await expect(page.locator('html')).toHaveAttribute('dir', fa ? 'rtl' : 'ltr')
  await page.locator('a[href="/experiments"]').click()
  await page.locator('a[href^="/annotate/"]').first().click()
  await expect(page.locator('canvas').first()).toBeVisible()
  await page.keyboard.press('b')
  const box = await page.locator('canvas').first().boundingBox()
  await page.mouse.move(box.x + 200, box.y + 120); await page.mouse.down()
  await page.mouse.move(box.x + 400, box.y + 220, { steps: 6 }); await page.mouse.up()
  await expect(page.locator('[role=status]').first()).toHaveText(fa ? 'ذخیره‌شده' : 'Saved', { timeout: 6000 })
})

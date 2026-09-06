import assert from 'node:assert/strict';
import { chromium } from 'playwright';
const browser = await chromium.launch({headless: true, executablePath: process.env.BROWSER_EXECUTABLE || undefined});
try {
  const page = await browser.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.goto(process.env.FRONTEND_URL || 'http://127.0.0.1:5173');
  await page.locator('.ready').nth(1).waitFor();
  assert.equal(await page.locator('.ready').count(), 2);
  assert.equal(await page.locator('.cards article').nth(2).locator('strong').innerText(), '0001');
  await page.route('**/api/health/ready', route => route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({status:'unavailable'})}));
  await page.getByRole('button', {name:'Refresh status'}).click();
  await page.locator('.unavailable').waitFor();
  assert.equal(await page.locator('.cards article').nth(2).locator('strong').innerText(), '—');
  await page.unroute('**/api/health/ready');
  await page.getByRole('button', {name:'Refresh status'}).click();
  await page.locator('.ready').nth(1).waitFor();
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true);
  assert.deepEqual(errors, []);
  if (process.env.SMOKE_SCREENSHOT) {
    await page.setViewportSize({width:1280,height:900});
    await page.screenshot({path:process.env.SMOKE_SCREENSHOT,fullPage:true});
  }
  console.log('Frontend smoke passed: live API + migrated database, failure/recovery, mobile layout, no runtime errors.');
} finally { await browser.close(); }

const { chromium } = require('playwright');
const path = require('path');

(async () => {
  const browser = await chromium.launch({
    headless: true,
    args: ['--use-fake-ui-for-media-stream', '--use-fake-device-for-media-stream']
  });
  const context = await browser.newContext({
    permissions: ['microphone'],
    viewport: { width: 1280, height: 800 }
  });
  const page = await context.newPage();

  console.log('Navigating to http://localhost:5000');
  await page.goto('http://localhost:5000', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#vh-fab-trigger', { state: 'visible', timeout: 5000 });

  const isOpen = await page.locator('#vh-main-panel.is-open').count() > 0;
  if (!isOpen) {
    await page.locator('#vh-fab-trigger').click();
    await page.waitForSelector('#vh-main-panel.is-open', { timeout: 5000 });
  }
  await page.waitForSelector('#vh-messages-stream .vh-bubble.bot', { timeout: 6000 });

  const outPath = 'C:/Users/Aryan Tripathi/.gemini/antigravity-ide/brain/2a118500-9344-4621-bd3c-0ab9c00ac84a/voicehire_e2e_landing.png';
  await page.screenshot({ path: outPath });
  console.log('Screenshot saved to:', outPath);

  // Navigate to login page to verify assistant state
  await page.goto('http://localhost:5000/login?role=worker', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('#vh-fab-trigger', { timeout: 5000 });
  const isLoginOpen = await page.locator('#vh-main-panel.is-open').count() > 0;
  if (!isLoginOpen) {
    await page.locator('#vh-fab-trigger').click();
    await page.waitForSelector('#vh-main-panel.is-open', { timeout: 3000 });
  }
  await page.waitForTimeout(1000);

  const outLoginPath = 'C:/Users/Aryan Tripathi/.gemini/antigravity-ide/brain/2a118500-9344-4621-bd3c-0ab9c00ac84a/voicehire_e2e_login.png';
  await page.screenshot({ path: outLoginPath });
  console.log('Screenshot saved to:', outLoginPath);

  await browser.close();
})();

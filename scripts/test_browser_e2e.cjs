/* Real browser regression. Install playwright-core separately; no production dependency.
   PLAYWRIGHT_MODULE=/path/to/playwright-core CHROMIUM_EXECUTABLE=/path/to/chrome
   COMETFORGE_URL=http://127.0.0.1:5183 FIXTURE_DIR=/tmp/fixtures node scripts/test_browser_e2e.cjs */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright-core');
const output = process.env.SCREENSHOT_DIR || '/tmp/cometforge-ui-screenshots';
fs.mkdirSync(output, {recursive:true});
const fixtures = process.env.FIXTURE_DIR;
assert.ok(fixtures, 'Set FIXTURE_DIR to a folder with sample.pdf and landscape.png');
(async () => {
 const browser = await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE,headless:true});
 try {
  const context = await browser.newContext({viewport:{width:1380,height:900},deviceScaleFactor:1,reducedMotion:'reduce'});
  await context.addInitScript(() => localStorage.setItem('cometforge:tour-seen','true'));
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.COMETFORGE_URL || 'http://127.0.0.1:5183/');
  await page.waitForFunction(()=>Boolean(window.CometForgeLayout));
  async function shot(name) {
   await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
   await page.screenshot({path:path.join(output,name),animations:'disabled'});
  }
  await page.locator('#fileInput').setInputFiles([path.join(fixtures,'sample.pdf'),path.join(fixtures,'landscape.png')]);
  await page.waitForFunction(()=>window.CometForge.getSnapshot().files.length === 2);
  await page.locator('.rotateSource').first().click();
  assert.ok((await page.evaluate(()=>window.CometForge.getSnapshot().options.source_rotations)).includes(90));
  await page.locator('#flowNext').click();
  assert.equal(await page.locator('#layoutStep').isVisible(), true);
  async function footerInViewport() {
   const box=await page.locator('.flowBottom').boundingBox();
   assert.ok(box && box.y>=0 && box.y+box.height<=page.viewportSize().height+1,'Primary actions must stay visible');
  }
  async function choose(id, value) {
   const text = await page.locator(`#${id} option[value="${value}"]`).textContent();
   await page.locator(`#${id}Trigger`).click();
   await page.locator(`#${id}Menu`).getByRole('option',{name:text,exact:true}).click();
  }
  await choose('pageSize','a4'); await choose('pageOrientation','portrait');
  await choose('pageMargin','custom'); await page.locator('#marginMm').fill('12.5');
  await page.locator('#marginMm').dispatchEvent('change');
  await page.locator('#rotateAllRight').click();
  await page.locator('.pageRotationDetails summary').click();
  await page.locator('#rotatePages').fill('2'); await page.locator('#rotatePagesRight').click();
  const options = await page.evaluate(()=>window.CometForge.getSnapshot().options);
  assert.equal(options.page_size,'a4'); assert.equal(options.rotation,90);
  assert.equal(options.margin_mm,12.5); assert.equal(options.page_rotations['2'],90);
  await page.locator('#flowBody').evaluate(el=>el.scrollTop=0);
  await footerInViewport();
  await shot('layout-desktop.png');
  for (const theme of ['prism','comet','light']) {
   await choose('appTheme',theme);
   await shot(`layout-${theme}.png`);
   assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),theme);
  }
  await choose('appTheme','prism');
  await page.setViewportSize({width:800,height:600});
  await footerInViewport();
  await shot('layout-compact.png');
  const overflow = await page.evaluate(()=>document.documentElement.scrollWidth > innerWidth + 1);
  assert.equal(overflow,false,'Horizontal page overflow at 800px');
  await page.locator('#flowNext').click();
  await choose('compressMode','off'); await page.locator('#outName').fill('Browser QA');
  await page.locator('#splitEnabled').check(); await page.locator('#splitCount').fill('2');
  await page.locator('#splitCount').dispatchEvent('change');
  await page.locator('#flowNext').click();
  assert.equal(await page.locator('#reviewStep').isVisible(),true);
  await page.locator('#forgeBtn').click();
  await page.waitForFunction(()=>!document.getElementById('resultsView').classList.contains('hidden'),null,{timeout:60000});
  await page.waitForFunction(()=>document.getElementById('wipeAfter').naturalWidth > 0,null,{timeout:60000});
  assert.equal(await page.locator('.outputFile').count(),2);
  await shot('results-compact.png');
  await page.setViewportSize({width:1380,height:900});
  await shot('results-desktop.png');
  assert.equal(await page.locator('#wipeBefore').evaluate(el=>el.naturalWidth),await page.locator('#wipeAfter').evaluate(el=>el.naturalWidth));
  await page.locator('#wipeHandle').focus(); await page.keyboard.press('ArrowRight');
  assert.notEqual(await page.locator('#wipeHandle').getAttribute('aria-valuenow'),'50');
  const downloadPromise = page.waitForEvent('download');
  await page.locator('#downloadAllBtn').click();
  const download = await downloadPromise;
  assert.match(download.suggestedFilename(),/\.zip$/);
  await download.saveAs(path.join(output,'browser-qa.zip'));
  await page.locator('#closeResultsBtn').click();
  await page.setViewportSize({width:1380,height:900});
  await page.locator('[data-step="2"]').click();
  await choose('appTheme','light');
  await page.reload();
  assert.equal(await page.evaluate(()=>document.documentElement.dataset.theme),'light');
  assert.deepEqual(errors,[],'JavaScript errors');
  console.log('PASS: browser import, four-step flow, rotations, paper/custom margin, compact layout, split export, rendered comparison, keyboard divider, ZIP download and theme persistence');
  await context.close();
 } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});

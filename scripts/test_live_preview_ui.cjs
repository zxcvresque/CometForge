/* Real-browser live-layout regression; use the same driver variables as test_browser_e2e.cjs. */
const assert=require('node:assert/strict');
const path=require('node:path');
const fs=require('node:fs');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright-core');
const fixtures=process.env.FIXTURE_DIR;
assert.ok(fixtures,'Set FIXTURE_DIR to sample.pdf and landscape.png');
const output=process.env.SCREENSHOT_DIR||'/tmp/cometforge-live-ui';fs.mkdirSync(output,{recursive:true});
(async()=>{const browser=await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE,headless:true});try{
 const context=await browser.newContext({viewport:{width:1380,height:900},reducedMotion:'reduce'});
 await context.addInitScript(()=>{localStorage.setItem('cometforge:tour-seen','true');localStorage.setItem('cometforge:theme','prism');localStorage.removeItem('cometforge:sidebar-collapsed');});
 const page=await context.newPage(),errors=[];page.on('pageerror',error=>errors.push(error.message));
 await page.goto(process.env.COMETFORGE_URL||'http://127.0.0.1:5187/');
 await page.locator('#fileInput').setInputFiles([path.join(fixtures,'sample.pdf'),path.join(fixtures,'landscape.png')]);
 await page.waitForFunction(()=>window.CometForge.getSnapshot().files.length===2);
 await page.locator('#sidebarToggle').click();
 for(const button of await page.locator('#flowSteps button').all()){assert.equal(await button.isVisible(),true);assert.ok(await button.getAttribute('title'));assert.ok(await button.getAttribute('aria-label'));}
 await page.locator('[data-step="2"]').click();assert.equal(await page.locator('#layoutStep').isVisible(),true);
 await page.screenshot({path:path.join(output,'collapsed-navigation.png'),animations:'disabled'});
 await page.locator('#sidebarToggle').click();
 await page.locator('#pageSizeTrigger').click();
 assert.equal(await page.locator('#pageSizeMenu [role=option]:visible').count(),4,'Only Original, A4, Letter and More should show');
 assert.equal(await page.locator('#pageSizeMenu').getByRole('option',{name:/A0/}).isVisible(),false);
 await page.locator('#pageSizeMenu .popupMore').click();await page.locator('#pageSizeMenu').getByRole('option',{name:'A3 · 297 × 420 mm',exact:true}).click();
 assert.equal(await page.locator('#pageSize').inputValue(),'a3');
 async function choose(id,value){const text=await page.locator(`#${id} option[value="${value}"]`).textContent();await page.locator(`#${id}Trigger`).click();let option=page.locator(`#${id}Menu`).getByRole('option',{name:text,exact:true});if(!await option.isVisible()){await page.locator(`#${id}Menu .popupMore`).click();}await option.click();}
 await choose('pageSize','original');
 await page.locator('.sourceThumbButton').first().click();
 await page.locator('#sourcePreviewDialog').waitFor({state:'visible'});
 const image=page.locator('#sourcePreviewImage');
 async function shot(name){await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));await page.screenshot({path:path.join(output,name),animations:'disabled'});}
 async function ready(previous){await page.waitForFunction(previous=>{const image=document.getElementById('sourcePreviewImage');return image&&!image.hidden&&image.complete&&image.naturalWidth>0&&(!previous||image.src!==previous)&&document.getElementById('sourcePreviewStage').getAttribute('aria-busy')==='false';},previous,{timeout:45000});}
 await ready();
 const initial=await image.getAttribute('src');
 await page.locator('#sourcePreviewRotateRight').click();await ready(initial);
 assert.equal((await page.evaluate(()=>window.CometForgeLayout.getOptions())).page_rotations['1'],90);
 let old=await image.getAttribute('src');await choose('sourcePreviewSize','a4');await ready(old);
 old=await image.getAttribute('src');await choose('sourcePreviewOrientation','portrait');await ready(old);
 const portrait=await image.evaluate(image=>[image.naturalWidth,image.naturalHeight]);assert.ok(portrait[0]<portrait[1]);
 old=await image.getAttribute('src');await choose('sourcePreviewMargin','custom');await ready(old);
 old=await image.getAttribute('src');await page.locator('#sourcePreviewMarginMm').fill('17.5');await page.locator('#sourcePreviewMarginMm').dispatchEvent('input');await ready(old);
 assert.equal(await page.locator('#marginMm').inputValue(),'17.5');
 old=await image.getAttribute('src');await choose('sourcePreviewOrientation','landscape');await ready(old);
 const landscape=await image.evaluate(image=>[image.naturalWidth,image.naturalHeight]);assert.ok(landscape[0]>landscape[1]);
 old=await image.getAttribute('src');await choose('sourcePreviewFit','cover');await ready(old);
 assert.equal(await page.locator('#pageFit').inputValue(),'cover');
 await shot('live-layout-desktop.png');
 await page.setViewportSize({width:800,height:600});await shot('live-layout-compact.png');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth+1),false);
 // A burst of changes must settle on the last value, with no stale raster replacement.
 await page.locator('#sourcePreviewMarginMm').fill('8');await page.locator('#sourcePreviewMarginMm').dispatchEvent('input');
 await page.locator('#sourcePreviewMarginMm').fill('12');await page.locator('#sourcePreviewMarginMm').dispatchEvent('input');
 old=await image.getAttribute('src');await page.locator('#sourcePreviewMarginMm').fill('15');await page.locator('#sourcePreviewMarginMm').dispatchEvent('input');await ready(old);
 assert.equal(await page.locator('#marginMm').inputValue(),'15');
 await page.keyboard.press('Escape');assert.equal(await page.locator('#sourcePreviewDialog').isVisible(),false);
 await page.setViewportSize({width:1380,height:900});
 await page.locator('.sourceThumbButton').nth(1).click();await ready();assert.match(await page.locator('#sourcePreviewPage').textContent(),/1.*3/);
 old=await image.getAttribute('src');await page.locator('#sourcePreviewNext').click();await ready(old);assert.match(await page.locator('#sourcePreviewPage').textContent(),/2.*3/);
 old=await image.getAttribute('src');await page.locator('#sourcePreviewRotateLeft').click();await ready(old);
 await page.locator('#sourcePreviewDone').click();assert.equal(await page.locator('#sourcePreviewDialog').isVisible(),false);
 assert.deepEqual(errors,[]);console.log('PASS: collapsed navigation, common/More sizes, thumbnail popup, live paper/orientation/fit/custom margins, per-page rotation, rapid updates, PDF page navigation and dialog close');
 await context.close();
}finally{await browser.close();}})().catch(error=>{console.error(error);process.exitCode=1;});

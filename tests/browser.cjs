// Run with Playwright available to Node. No npm install is required by the app.
const { chromium } = require('playwright');
const { spawn } = require('node:child_process');
const assert = require('node:assert/strict');
const server = spawn(process.env.DRAMA_TEST_PYTHON || 'python', ['server.py'], {env:{...process.env, DRAMA_PORT:'18765'},stdio:'ignore'});
(async()=>{
 let browser;
 try{
  browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
  const page=await browser.newPage(),errors=[];
  page.on('pageerror',e=>errors.push(e.message));
  for(let n=0;n<50;n++){
   try{await page.goto('http://127.0.0.1:18765');break}catch(e){if(n===49)throw e;await new Promise(r=>setTimeout(r,100))}
  }
  await page.waitForFunction(()=>!document.getElementById('engineStatus').textContent.includes('확인 중'));
  assert.match(await page.locator('#engineStatus').innerText(),/Wan2.2/);
  assert.equal(await page.locator('#tabs button').count(),6);
  for(const country of ['kr','jp','us','uk','fr','it']){
   await page.selectOption('#country',country);
   assert.match(await page.locator('#cast-summary').innerText(),/183cm/);
   assert.equal(await page.locator('.actor').count(),2);
  }
  await page.selectOption('#country','kr');
  await page.click('#generate');
  assert.equal(await page.locator('.scene').count(),3);
  await page.selectOption('#engine','wan22');
  assert.equal(await page.locator('#wanFields').isVisible(),true);
  await page.selectOption('#mode','i2v');
  assert.equal(await page.locator('#imageField').isVisible(),true);
  await page.click('#renderVideo');
  assert.match(await page.locator('#renderStatus').innerText(),/이미지/);
  await page.selectOption('#mode','t2v');
  await page.click('#renderVideo');
  await page.waitForFunction(()=>document.getElementById('renderStatus').textContent.startsWith('오류:'));
  assert.match(await page.locator('#renderStatus').innerText(),/CUDA|체크포인트|소스/);
  await page.selectOption('#engine','storyboard');
  await page.selectOption('#duration','3');
  await page.click('#renderVideo');
  await page.waitForFunction(()=>document.getElementById('renderStatus').textContent.includes('생성 완료'),{timeout:60000});
  assert.equal(await page.locator('#videoLink a').count(),1);
  await page.waitForFunction(()=>document.getElementById('videoPreview').readyState>=1);
  assert.ok(await page.locator('#videoPreview').evaluate(v=>v.duration)>=9);
  assert.deepEqual(errors,[]);
  console.log('PASS: six countries, fixed height, script, AI input/error, real storyboard video playback; no JS errors');
 }finally{if(browser)await browser.close();server.kill()}
})().catch(e=>{console.error(e);process.exitCode=1});

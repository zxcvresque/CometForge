/* Comparison controller unit checks; no browser or visual computer testing. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const script = fs.readFileSync(path.join(__dirname,'../static/comparison.js'),'utf8');
class Element {
  constructor() {
    this.style={};this.attrs={};this.events={};const classes=new Set();
    this.classList={add:v=>classes.add(v),remove:v=>classes.delete(v),contains:v=>classes.has(v)};
  }
  addEventListener(name,fn){this.events[name]=fn;}
  setAttribute(name,value){this.attrs[name]=value;}
  getAttribute(name){return name==='src'?this.src:this.attrs[name];}
  removeAttribute(name){delete this.attrs[name];if(name==='src')delete this.src;}
  focus(){}
  getBoundingClientRect(){return{left:100,width:400};}
  setPointerCapture(id){this.capture=id;}
  hasPointerCapture(id){return this.capture===id;}
  releasePointerCapture(){this.capture=null;}
}
function fixture() {
  const nodes=new Map(),id=name=>{if(!nodes.has(name))nodes.set(name,new Element());return nodes.get(name);};
  id('compareResolution').value='hd';
  let urlCount=0, timer;const requested=[],revoked=[],images=[];
  const state={fallback:0};
  const context={document:{getElementById:id},window:{devicePixelRatio:2,CometForge:{fmtMB:n=>String(n)}},AbortController,
    fetch:(url,options)=>new Promise(resolve=>requested.push({url,options,resolve})),
    URL:{createObjectURL:()=>`blob:${++urlCount}`,revokeObjectURL:url=>revoked.push(url)},
    Image:class{constructor(){this.naturalWidth=1200;this.naturalHeight=1600;images.push(this);}decode(){return Promise.resolve();}},
    setTimeout:fn=>{timer=fn;return 1;},clearTimeout:()=>{timer=null;},
  };
  vm.runInNewContext(script,context);
  const file={renderBase:'/render/0',pageCount:3,beforeBytes:100,bytes:50};
  const resolve=(requests=requested.splice(0),dpi=288)=>requests.forEach(({resolve,url})=>resolve({ok:true,headers:{get:name=>name==='X-Render-DPI'?String(dpi):name==='X-Render-Limited'?String(dpi<Number(new URL(url,'http://local').searchParams.get('dpi'))):null},blob:async()=>url}));
  return{id,requested,revoked,images,state,context,file,resolve,api:context.window.CometForgeComparison,
    show:()=>context.window.CometForgeComparison.show(file,()=>state.fallback++),runTimer:()=>{const fn=timer;timer=null;fn?.();}};
}
async function flush(){for(let i=0;i<4;i++)await new Promise(resolve=>setImmediate(resolve));}

test('HD loads paired pages and drag/keyboard/zoom keep clipping aligned',async()=>{
  const f=fixture();f.show();assert.equal(f.requested.length,2);
  assert.ok(f.requested[0].url.endsWith('variant=before&dpi=288'));
  assert.ok(f.requested[1].url.endsWith('variant=after&dpi=288'));
  f.resolve();await flush();assert.match(f.id('compareStatus').textContent,/HD · 288 DPI/);
  const event={pointerId:1,clientX:400,preventDefault(){}};
  f.id('wipeHandle').events.pointerdown(event);assert.equal(f.id('wipeHandle').style.left,'75%');
  event.clientX=1000;f.id('wipeHandle').events.pointermove(event);assert.equal(f.id('wipeHandle').style.left,'100%');
  f.id('wipeHandle').events.keydown({key:'Home',preventDefault(){}});assert.equal(f.id('wipeHandle').attrs['aria-valuenow'],'0');
  f.id('wipeHandle').events.keydown({key:'ArrowRight',shiftKey:true,preventDefault(){}});assert.equal(f.id('wipeAfter').style.clipPath,'inset(0 0 0 10%)');
  f.id('compareZoomIn').events.click();f.runTimer();assert.equal(f.id('wipeCanvas').style.width,'125%');
  assert.ok(f.requested.every(r=>r.url.endsWith('dpi=360')));f.resolve(undefined,360);await flush();
  assert.equal(f.id('wipeAfter').style.clipPath,'inset(0 0 0 10%)');
  f.id('compareResolution').value='standard';f.id('compareResolution').events.change();
  assert.ok(f.requested.every(r=>r.url.endsWith('dpi=144')));f.resolve(undefined,144);await flush();
  assert.match(f.id('compareStatus').textContent,/Standard · 144 DPI/);
});

test('rapid page changes discard old images and abort stale requests',async()=>{
  const f=fixture();f.show();f.resolve();await flush();
  f.id('compareNext').events.click();const stale=f.requested.splice(0);
  f.id('compareNext').events.click();assert.equal(stale[0].options.signal.aborted,true);
  f.resolve();await flush();const latest=f.id('wipeBefore').src;
  f.resolve(stale);await flush();assert.equal(f.id('wipeBefore').src,latest);
  assert.equal(f.id('comparePage').textContent,'Page 3 of 3');
  assert.equal(f.id('compareNext').disabled,true);
  f.api.clear();assert.equal(f.id('wipeBefore').src,undefined);assert.ok(f.revoked.length>0);
});

test('dimension mismatch refuses false alignment and uses PDF fallback',async()=>{
  const f=fixture();f.show();f.resolve();
  // Override decoder dimensions before asynchronous page decoding resumes.
  f.context.Image=class{constructor(){this.naturalWidth=f.images.length?800:1200;this.naturalHeight=1600;f.images.push(this);}decode(){return Promise.resolve();}};
  await flush();assert.equal(f.state.fallback,1);assert.match(f.id('compareStatus').textContent,/geometry differs/);
  assert.equal(f.id('wipeBefore').src,undefined);assert.equal(f.revoked.length,2);
});

test('large-page limited DPI is reported honestly',async()=>{
  const f=fixture();f.show();f.resolve(undefined,220.123456);await flush();
  assert.match(f.id('compareStatus').textContent,/220.1 DPI · large-page safety limit/);
});

test('older backend never pretends standard previews are HD',async()=>{
  const f=fixture();f.show();f.requested.splice(0).forEach(r=>r.resolve({ok:true,headers:{get:()=>null}}));
  await flush();assert.equal(f.state.fallback,1);assert.match(f.id('compareStatus').textContent,/Restart this instance/);
});

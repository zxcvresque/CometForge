/* DOM-contract/unit checks only: no browser, screenshots or computer control. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.resolve(__dirname, '..');
const source = name => fs.readFileSync(path.join(root, 'static', name), 'utf8');

class Element {
  constructor() {
    this.attrs = {}; this.style = {setProperty(){}}; this.children = []; this.listeners = {};
    const classes = new Set();
    this.classList = {add: v => classes.add(v), contains: v => classes.has(v), toggle(v, enabled) { if (enabled) classes.add(v); else classes.delete(v); }};
  }
  setAttribute(k,v) { this.attrs[k] = v; }
  removeAttribute(k) { delete this.attrs[k]; }
  addEventListener(k,v) { this.listeners[k] = v; }
  append(...items) { this.children.push(...items); }
  prepend(item) { this.children.unshift(item); }
  replaceChildren(...items) { this.children = items; }
  focus() { this.focused = true; }
  remove() { this.removed = true; }
  querySelector() { return this.heading ||= new Element(); }
  querySelectorAll() { return this.buttons; }
  click() { if (!this.disabled) this.listeners.click?.(); }
}
function fixture() {
  const elements = new Map();
  const id = name => { if (!elements.has(name)) elements.set(name, new Element()); return elements.get(name); };
  id('flowSteps').buttons = [1,2,3].map(step => Object.assign(new Element(), {dataset:{step:String(step)}}));
  id('targetMb').value = '20';
  const events = {};
  const document = {getElementById:id, createElement:()=>new Element(), dispatchEvent(){}, body:new Element(), addEventListener(){}, removeEventListener(){}, hidden:false};
  const window = {addEventListener:(name,fn)=> { events[name] = fn; },removeEventListener(){}};
  const context = vm.createContext({window, document, CustomEvent:class { constructor(type, init) { this.type=type; this.detail=init?.detail; } }});
  return {id,events,window,document,context};
}

test('HTML IDs, scripts and required guided-flow hooks exist', () => {
  const html = source('index.html');
  const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
  assert.equal(new Set(ids).size, ids.length, 'duplicate IDs');
  for (const script of ['guided-flow.js','celebration.js']) {
    assert.ok(html.includes(`/static/${script}`));
    for (const match of source(script).matchAll(/\bid\('([^']+)'\)/g)) assert.ok(ids.includes(match[1]), match[1]);
  }
  assert.ok(!html.includes('↗'));
  assert.ok(html.includes('quietDocument'));
  for (const match of html.matchAll(/(?:src|href)="\/static\/([^"?]+)/g)) assert.ok(fs.existsSync(path.join(root,'static',match[1])), match[1]);
});

test('guided steps, summaries and busy controls preserve options', () => {
  const f = fixture();
  const state = {files:[],options:{output_name:'Example.pdf',split_enabled:false,target_mb:20,compress_mode:'targetfit',linearize:false}};
  f.window.CometForge = {getSnapshot:()=>state,fmtMB:n=>`${(n/1e6).toFixed(2)} MB`};
  vm.runInContext(source('guided-flow.js'), f.context);
  assert.equal(f.id('sourceStep').hidden, false);
  assert.equal(f.id('flowNext').disabled, true);
  state.files = [{size:20e6}]; f.events['cometforge:change']();
  assert.equal(f.id('flowNext').disabled, false);
  f.id('flowNext').click(); assert.equal(f.id('exportStep').hidden, false);
  state.options.split_enabled = true; state.options.split_count = 5;
  f.id('splitEnabled').checked = true;
  f.events['cometforge:change']();
  f.id('flowNext').click(); assert.equal(f.id('reviewStep').hidden, false);
  assert.equal(f.id('forgeBtn').classList.contains('hidden'), false);
  assert.match(f.id('flowSummary').textContent, /5 PDFs/);
  assert.ok(f.id('flowReview').children.some(el=>el.textContent==='Example.pdf'));
  f.events['cometforge:busy']({detail:true});
  assert.equal(f.id('flowBack').disabled, true);
  assert.equal(f.id('outName').disabled, true);
  assert.equal(f.id('forgeBtn').textContent, 'Forging…');
  f.events['cometforge:busy']({detail:false});
  assert.equal(f.id('outName').disabled, false);
  assert.equal(f.id('splitCount').disabled, false);
  f.id('flowBack').click(); assert.equal(f.id('exportStep').hidden, false);
  assert.equal(state.options.output_name, 'Example.pdf');
  state.options.compress_mode = 'lossless'; f.events['cometforge:change']();
  assert.equal(f.id('targetMb').disabled, true);
  state.files = []; f.events['cometforge:change']();
  assert.equal(f.id('forgeBtn').disabled, true);
});

test('completion fires only after ready output, not error or oversized result', () => {
  const client = source('app.js');
  assert.ok(client.includes('await loadOutputView(jobId, status, options);'));
  assert.ok(client.includes('if (status.target_met !== false) window.dispatchEvent(new CustomEvent("cometforge:complete"'));
  assert.ok(client.indexOf('stage === "error"') < client.indexOf('cometforge:complete'));
  assert.ok(source('size-preview.js').includes("api.pollJob(result.job_id, state.options)"));
});

test('reduced-motion celebration is static, deduplicated and cleaned up', () => {
  const f = fixture(); let timeout; let frameCount = 0;
  f.window.matchMedia = () => ({matches:true,addEventListener(){},removeEventListener(){}});
  Object.assign(f.context, {setTimeout:fn=> { timeout=fn; return 1; },clearTimeout(){},cancelAnimationFrame(){},requestAnimationFrame(){frameCount++;}});
  vm.runInContext(source('celebration.js'), f.context);
  f.events['cometforge:complete']({detail:{jobId:'a',count:5}});
  assert.equal(frameCount,0);
  assert.equal(f.document.body.children.length,1);
  assert.match(f.document.body.children[0].children[0].textContent,/5 PDFs ready/);
  f.events['cometforge:complete']({detail:{jobId:'a',count:5}});
  assert.equal(f.document.body.children.length,1);
  timeout(); assert.equal(f.document.body.children[0].removed,true);
  f.document.hidden=true;
  f.events['cometforge:complete']({detail:{jobId:'b',count:1}});
  assert.equal(f.document.body.children.length,1);
});

test('animated comet uses bounded canvas resolution and ends after one flyby', () => {
  const f = fixture(); let draw; let time = 0; let frames = 0;
  const ctx = new Proxy({}, {get:(_,key)=>key==='createRadialGradient'?()=>({addColorStop(){}}):()=>{},set:()=>true});
  f.document.createElement = tag => {
    const element = new Element();
    if (tag === 'canvas') element.getContext = () => ctx;
    return element;
  };
  Object.assign(f.window, {innerWidth:1200,innerHeight:800,devicePixelRatio:3,matchMedia:()=>({matches:false,addEventListener(){},removeEventListener(){}})});
  Object.assign(f.context, {performance:{now:()=>time},setTimeout(){},clearTimeout(){},cancelAnimationFrame(){},requestAnimationFrame:fn=>{draw=fn;return ++frames;}});
  vm.runInContext(source('celebration.js'), f.context);
  f.events['cometforge:complete']({detail:{jobId:'animated',count:1}});
  const layer = f.document.body.children[0], canvas = layer.children[0];
  assert.equal(canvas.width,2400);
  assert.equal(canvas.height,1600);
  draw(1000); assert.equal(layer.removed,undefined);
  draw(2450); assert.equal(layer.removed,true);
  assert.equal(frames,2);
});

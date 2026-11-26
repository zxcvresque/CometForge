/* Interruptible motion contracts; actual captures are reviewed separately. */
const {test} = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname,'../static/motion.js'),'utf8');

class Element {
  constructor(id='',hidden=false) {
    this.id=id;this.hidden=hidden;this.style={};this.attrs={};this.children=[];this.animations=[];
    const classes=new Set();
    this.classList={contains:value=>classes.has(value),add:value=>classes.add(value),remove:value=>classes.delete(value)};
  }
  animate(frames,options) {
    let resolve,reject;
    const active={frames,options,cancelled:false,finished:new Promise((yes,no)=>{resolve=yes;reject=no;}),
      finish(){resolve();},cancel(){this.cancelled=true;reject(new Error('cancelled'));}};
    this.animations.push(active);return active;
  }
  cloneNode(){const copy=new Element(this.id);copy.children=this.children.map(child=>Object.assign(new Element(),child));return copy;}
  querySelectorAll(){return this.children;}
  removeAttribute(name){delete this.attrs[name];if(name==='id')this.id='';}
  setAttribute(name,value){this.attrs[name]=value;}
  toggleAttribute(name,yes){if(yes)this.attrs[name]='';else delete this.attrs[name];}
  getBoundingClientRect(){return{left:20,top:30,width:220,height:160};}
  remove(){this.removed=true;}
}
function fixture(reduced=false) {
  const nodes=new Map(['sourceStep','layoutStep','exportStep','reviewStep','queueView','resultsView','customMarginField','splitOptions'].map((id,index)=>[id,new Element(id,![0,4].includes(index))]));
  const events={},mediaEvents={},windowEvents={},observations=[];
  const document={hidden:false,readyState:'complete',documentElement:new Element(),body:{append(node){this.last=node;}},
    getElementById:id=>nodes.get(id),addEventListener:(name,fn)=>{events[name]=fn;},removeEventListener:name=>{delete events[name];}};
  const media={matches:reduced,addEventListener:(name,fn)=>{mediaEvents[name]=fn;},removeEventListener:name=>{delete mediaEvents[name];}};
  let observer;
  const context={document,window:{matchMedia:()=>media,getComputedStyle:()=>({opacity:'.74'}),
    addEventListener:(name,fn)=>{windowEvents[name]=fn;}},MutationObserver:class {
      constructor(callback){observer=this;this.callback=callback;}
      observe(element,options){observations.push({element,options});}
      disconnect(){this.disconnected=true;}
    }};
  vm.runInNewContext(source,context);
  return{nodes,document,events,media,mediaEvents,windowEvents,observations,observer,api:context.window.CometForgeMotion,
    mutate(...elements){observer.callback(elements.map(target=>({target})));}};
}
async function flush(){await Promise.resolve();await Promise.resolve();}

test('default content stays visible and startup does not animate the page',()=>{
  const f=fixture();
  assert.equal(f.nodes.get('sourceStep').hidden,false);
  assert.equal(f.observations.length,8);
  assert.ok([...f.nodes.values()].every(element=>element.animations.length===0));
  const css=fs.readFileSync(path.join(__dirname,'../static/motion.css'),'utf8');
  assert.ok(!/opacity\s*:\s*0|visibility\s*:\s*hidden|display\s*:\s*none/.test(css));
  assert.ok(!/transition\s*:\s*all/.test(css));
});

test('step direction follows navigation and interruption cancels stale work',async()=>{
  const f=fixture(),source=f.nodes.get('sourceStep'),layout=f.nodes.get('layoutStep');
  source.hidden=true;layout.hidden=false;f.mutate(source,layout);
  const forward=layout.animations[0];
  assert.equal(forward.options.duration,180);
  assert.equal(forward.frames[0].transform,'translateX(8px)');
  layout.hidden=true;source.hidden=false;f.mutate(layout,source);
  assert.equal(forward.cancelled,true);
  assert.equal(source.animations[0].frames[0].transform,'translateX(-8px)');
  f.api.reveal(source);assert.equal(source.animations[0].cancelled,true);
  source.animations.at(-1).finish();await flush();
});

test('reduced motion removes spatial and mask movement but keeps feedback',()=>{
  const f=fixture(true),element=new Element();
  f.api.reveal(element);
  assert.equal(element.animations[0].options.duration,90);
  assert.ok(element.animations[0].frames.every(frame=>!('transform' in frame)));
  f.api.openPopup(element);
  assert.ok(element.animations.at(-1).frames.every(frame=>!('clipPath' in frame)&&!('transform'in frame)));
  f.api.closePopup(element);
  const exit=f.document.body.last;
  assert.equal(exit.animations[0].options.duration,70);
  assert.equal(exit.attrs['aria-hidden'],'true');assert.equal(exit.inert,true);
});

test('popup exits never hold focus and reopening removes the old visual proxy',async()=>{
  const f=fixture(),menu=new Element('paperMenu');
  menu.children=[new Element('option')];
  f.api.openPopup(menu);f.api.closePopup(menu);
  const exit=f.document.body.last;
  assert.equal(menu.animations[0].cancelled,true);
  assert.equal(exit.id,'');assert.equal(exit.children[0].id,'');
  assert.equal(exit.children[0].tabIndex,-1);
  assert.equal(exit.animations[0].frames[0].opacity,.74);
  f.api.openPopup(menu);
  assert.equal(exit.removed,true);assert.equal(exit.animations[0].cancelled,true);
  await flush();
  f.api.closePopup(menu);const final=f.document.body.last;
  final.animations[0].finish();await flush();assert.equal(final.removed,true);
});

test('preference changes, hidden windows and page exit cancel all animation',async()=>{
  const f=fixture(),element=new Element();
  f.api.reveal(element);f.media.matches=true;f.mediaEvents.change();
  assert.equal(element.animations[0].cancelled,true);
  f.api.reveal(element);f.document.hidden=true;f.events.visibilitychange();
  assert.equal(element.animations[1].cancelled,true);
  assert.ok('data-motion-paused'in f.document.documentElement.attrs);
  f.api.reveal(element);assert.equal(element.animations.length,2);
  f.document.hidden=false;f.events.visibilitychange();
  f.api.reveal(element);f.windowEvents.pagehide();
  assert.equal(element.animations[2].cancelled,true);assert.equal(f.observer.disconnected,true);
  f.api.reveal(element);assert.equal(element.animations.length,3);
  await flush();
});

test('details only acknowledge opening without animating layout dimensions',()=>{
  const f=fixture(),details=new Element();details.tagName='DETAILS';details.open=true;
  const summary=new Element(),content=new Element();summary.tagName='SUMMARY';content.tagName='DIV';details.children=[summary,content];
  f.events.toggle({target:details});assert.equal(summary.animations.length,0);assert.equal(content.animations.length,1);
  assert.ok(content.animations[0].frames.every(frame=>Object.keys(frame).every(key=>key==='opacity')));
});

test('popup exit proxies stay inside a modal dialog top layer',()=>{
  const f=fixture(),menu=new Element('modalPaperMenu');
  const dialog={append(node){this.last=node;}};
  menu.closest=selector=>selector==='dialog'?dialog:null;
  f.api.closePopup(menu);
  assert.ok(dialog.last);assert.equal(f.document.body.last,undefined);
  assert.equal(dialog.last.inert,true);assert.equal(dialog.last.attrs['aria-hidden'],'true');
});

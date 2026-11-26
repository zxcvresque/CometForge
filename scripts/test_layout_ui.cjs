/* Meaningful range/rotation regressions; actual native GUI is tested separately. */
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const path=require('node:path');
const root=path.resolve(__dirname,'..');
function setup(){
  const defaults={pageSize:'original',pageOrientation:'auto',pageFit:'contain',pageMargin:'none',marginMm:'10',pageRotation:'0'};
  const elements=new Map();
  const events={};
  const id=name=>{
    if(!elements.has(name))elements.set(name,{value:defaults[name]||'',style:{},attrs:{},listeners:{},addEventListener(event,fn){this.listeners[event]=fn;},dispatchEvent(event){this.listeners[event.type]?.(event);},setAttribute(key,value){this.attrs[key]=value;},removeAttribute(key){delete this.attrs[key];}});
    return elements.get(name);
  };
  const window={addEventListener:(event,fn)=>events[event]=fn,dispatchEvent(){}};
  vm.runInNewContext(fs.readFileSync(path.join(root,'static/layout.js'),'utf8'),{window,document:{getElementById:id},Event:class{constructor(type){this.type=type;}}});
  return {id,window,events,api:window.CometForgeLayout};
}
test('page rotation ranges reject invalid input without partial edits',()=>{
  const f=setup();
  assert.deepEqual([...f.api.parsePages('1, 3–5, 4')],[1,3,4,5]);
  for(const input of ['', '0', '5-3', '2.5', '1, nope', '1-10001'])assert.throws(()=>f.api.parsePages(input));
  f.id('rotatePages').value='1, nope';f.id('rotatePagesRight').listeners.click();
  assert.equal(Object.keys(f.api.getOptions().page_rotations).length,0);
  assert.equal(f.id('rotatePages').attrs['aria-invalid'],'true');
});
test('global and page rotations compose, wrap and reset independently',()=>{
  const f=setup();
  f.id('rotateAllLeft').listeners.click();
  assert.equal(f.api.getOptions().rotation,270);
  f.id('rotatePages').value='1,3-4';f.id('rotatePagesRight').listeners.click();
  assert.equal(JSON.stringify(f.api.getOptions().page_rotations),'{"1":90,"3":90,"4":90}');
  f.id('rotatePagesLeft').listeners.click();
  assert.equal(Object.keys(f.api.getOptions().page_rotations).length,0);
  f.id('rotatePagesRight').listeners.click();f.api.resetPageRotations();
  assert.equal(f.api.getOptions().rotation,270);
  assert.equal(Object.keys(f.api.getOptions().page_rotations).length,0);
});
test('layout options retain custom margins and white page guide across busy state',()=>{
  const f=setup();
  f.id('pageSize').value='letter';f.id('pageOrientation').value='landscape';f.id('pageFit').value='cover';f.id('pageMargin').value='custom';f.id('marginMm').value='12.5';
  f.id('pageMargin').listeners.change();
  assert.equal(f.api.getOptions().margin_mm,12.5);
  assert.equal(f.id('customMarginField').hidden,false);
  assert.match(f.id('layoutFitHelp').textContent,/crops/);
  f.events['cometforge:busy']({detail:true});
  assert.equal(f.id('resetPageRotations').disabled,true);
  assert.equal(f.api.getOptions().page_size,'letter');
});

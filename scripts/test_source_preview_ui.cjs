/* Exercise common/expanded page-size menus and modal popup portals. */
const {test}=require('node:test');const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const app=fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8');
const popup=app.slice(app.indexOf('function setupPopupSelect(select) {'),app.indexOf('\nfunction setupSidebar()'));
class Node {
 constructor(tag='div'){this.tagName=tag.toUpperCase();this.children=[];this.attrs={};this.style={};this.listeners={};this.hidden=false;this.dataset={};this._classes=new Set();this.classList={contains:x=>this._classes.has(x)||this.className?.split(' ').includes(x),add:x=>this._classes.add(x),remove:x=>{this._classes.delete(x);this.className=(this.className||'').split(' ').filter(y=>y!==x).join(' ')},toggle:(x,on)=>on?this._classes.add(x):this._classes.delete(x)};}
 setAttribute(k,v){this.attrs[k]=v;}getAttribute(k){return this.attrs[k];}append(...children){children.forEach(child=>{child.parent=this;this.children.push(child)});}prepend(child){child.parent=this;this.children.unshift(child);}addEventListener(k,fn){(this.listeners[k]||=[]).push(fn);}dispatchEvent(e){for(const fn of this.listeners[e.type]||[])fn(e);}click(){this.dispatchEvent({type:'click'});}before(node){this.wrapper=node;}closest(){return this.dialog||null;}contains(node){return node===this||this.children.some(child=>child.contains?.(node));}focus(){fixture.document.activeElement=this;}getBoundingClientRect(){return{left:30,right:230,top:100,bottom:134,width:200,height:Math.min(400,this.children.filter(c=>!c.hidden).length*34+10)}}querySelectorAll(){return this.children.filter(c=>c.attrs.role==='option');}
}
let fixture;
function setup(modal=false){
 const body=new Node(),dialog=new Node('dialog');
 const document={body,activeElement:null,getElementById:()=>null,querySelector:()=>null,createElement:tag=>new Node(tag),listeners:{},addEventListener(k,fn){(this.listeners[k]||=[]).push(fn)},dispatchEvent(e){for(const fn of this.listeners[e.type]||[])fn(e)}};
 const window={innerWidth:1000,innerHeight:760,CometForgeMotion:{openPopup(){},closePopup(){}},addEventListener(){}};
 const select=new Node('select');select.id='pageSize';select.dataset.commonValues='original,a4,letter';select.dialog=modal?dialog:null;
 select.options=[{value:'original',text:'Original'},{value:'a0',text:'A0'},{value:'a4',text:'A4'},{value:'letter',text:'US Letter'},{value:'legal',text:'US Legal'}];select._value='original';
 Object.defineProperties(select,{value:{get(){return this._value},set(v){this._value=v}},selectedIndex:{get(){return this.options.findIndex(x=>x.value===this._value)}},selectedOptions:{get(){return[this.options[this.selectedIndex]]}}});
 fixture={document,window,select,body,dialog};
 const context=vm.createContext({document,window,Event:class{constructor(type){this.type=type}},CustomEvent:class{constructor(type,init){this.type=type;this.detail=init?.detail}}});
 vm.runInContext(popup+';setupPopupSelect(testSelect);',vm.createContext({...context,testSelect:select}));
 fixture.wrapper=select.wrapper;fixture.trigger=select.wrapper.children[0];fixture.menu=(modal?dialog:body).children[0];return fixture;
}
const visible=f=>f.menu.children.filter(node=>!node.hidden);
test('page-size menu starts with Original/A4/Letter; extra sizes stay behind More',()=>{
 const f=setup();f.trigger.click();
 assert.deepEqual(visible(f).slice(0,3).map(x=>x.children[1].textContent),['Original','A4','US Letter']);
 assert.equal(visible(f).length,4);
 visible(f).at(-1).click();
 assert.equal(visible(f).length,3); // Back, A0, Legal
 assert.equal(visible(f)[1].children[1].textContent,'A0');
 visible(f).at(-1).click();assert.equal(f.select.value,'legal');assert.equal(f.menu.classList.contains('hidden'),true);
 f.trigger.click();assert.equal(visible(f).length,4); // Reopening is concise, even for an extra selection.
});
test('expanded size navigation has keyboard access and popup remains in modal top layer',()=>{
 const f=setup(true);assert.equal(f.body.children.length,0);assert.equal(f.menu.parent,f.dialog);
 f.trigger.click();visible(f).at(-1).click();
 const first=visible(f)[0];first.focus();let prevented=false;
 f.menu.dispatchEvent({type:'keydown',key:'End',preventDefault(){prevented=true}});
 assert.equal(prevented,true);assert.equal(f.document.activeElement,visible(f).at(-1));
 f.menu.dispatchEvent({type:'keydown',key:'Escape',preventDefault(){},stopPropagation(){}});
 assert.equal(f.menu.classList.contains('hidden'),true);assert.equal(f.document.activeElement,f.trigger);
});

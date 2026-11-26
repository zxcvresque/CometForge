const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
function run({saved,dark=true,broken=false}={}){
 const listeners={}, changes={};
 const select={value:'',dispatchEvent(){},addEventListener(name,fn){listeners[name]=fn;}};
 const document={documentElement:{dataset:{}},getElementById:()=>select,addEventListener:(name,fn)=>changes[name]=fn,readyState:'loading'};
 const media={matches:dark,addEventListener:(name,fn)=>changes.media=fn};
 const localStorage={getItem(){if(broken)throw new Error('blocked');return saved;},setItem(key,value){this.saved=value;}};
 const window={matchMedia:()=>media};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'../static/themes.js'),'utf8'),{window,document,localStorage,Event:class{}});
 return {document,select,listeners,changes,media,localStorage};
}
test('theme restores before CSS and survives unavailable storage',()=>{
 assert.equal(run({saved:'light'}).document.documentElement.dataset.theme,'light');
 assert.equal(run({saved:'comet'}).document.documentElement.dataset.theme,'comet');
 assert.equal(run({saved:'bad'}).document.documentElement.dataset.theme,'prism');
 assert.equal(run({broken:true}).document.documentElement.dataset.theme,'prism');
});
test('system preference follows OS changes and manual choice persists',()=>{
 const f=run({saved:'system',dark:false});
 assert.equal(f.document.documentElement.dataset.theme,'light');
 f.changes.DOMContentLoaded();
 f.media.matches=true;f.changes.media();
 assert.equal(f.document.documentElement.dataset.theme,'prism');
 f.select.value='comet';f.listeners.change();
 assert.equal(f.localStorage.saved,'comet');
 f.media.matches=false;f.changes.media();
 assert.equal(f.document.documentElement.dataset.theme,'comet');
});

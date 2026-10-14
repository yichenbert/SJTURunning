import test from 'node:test';
import assert from 'node:assert/strict';
import vm from 'node:vm';
import {readFileSync} from 'node:fs';
const source=readFileSync(new URL('../static/theme.js',import.meta.url),'utf8');
function setup(saved=null, dark=false, blocked=false) {
  const events={}, media={matches:dark,addEventListener:(name,fn)=>events.media=fn};
  const root={dataset:{},style:{}},meta={},select={value:'',addEventListener:(name,fn)=>events.select=fn};
  const storage=new Map(saved===null?[]:[['sjtu-run-web:theme',saved]]);
  vm.runInNewContext(source, {
    window:{matchMedia:()=>media,addEventListener:(name,fn)=>events[name]=fn},
    localStorage:{getItem:key=>{if(blocked)throw Error();return storage.get(key);},setItem:(key,value)=>{if(blocked)throw Error();storage.set(key,value);}},
    document:{documentElement:root,querySelector:()=>({setAttribute:(key,value)=>meta[key]=value}),getElementById:()=>select,addEventListener:(name,fn)=>events[name]=fn}
  });
  return {root,media,meta,select,events,storage};
}
test('system theme applies before DOM ready and follows live system changes',()=>{
  const s=setup(null,true);
  assert.equal(s.root.dataset.theme,'dark');
  s.events.DOMContentLoaded();assert.equal(s.select.value,'system');
  s.media.matches=false;s.events.media();assert.equal(s.root.dataset.theme,'light');
  assert.equal(s.meta.content,'#ffffff');assert.equal(s.root.style.colorScheme,'light');
});
test('manual selection persists and overrides system until system mode is restored',()=>{
  const s=setup('light',true);s.events.DOMContentLoaded();
  assert.equal(s.root.dataset.theme,'light');
  s.events.select({target:{value:'dark'}});assert.equal(s.storage.get('sjtu-run-web:theme'),'dark');
  s.media.matches=false;s.events.media();assert.equal(s.root.dataset.theme,'dark');
  s.events.select({target:{value:'system'}});assert.equal(s.root.dataset.theme,'light');
});
test('invalid or blocked storage safely falls back to system and allows manual changes',()=>{
  for(const s of [setup('invalid',true),setup(null,true,true)]){
    assert.equal(s.root.dataset.theme,'dark');s.events.DOMContentLoaded();
    s.events.select({target:{value:'light'}});assert.equal(s.root.dataset.theme,'light');
  }
});
test('theme follows changes and resets from other tabs',()=>{
  const s=setup('light',true);s.events.DOMContentLoaded();
  s.events.storage({key:'sjtu-run-web:theme',newValue:'dark'});assert.equal(s.select.value,'dark');
  s.events.storage({key:null,newValue:null});assert.equal(s.select.value,'system');assert.equal(s.root.dataset.theme,'dark');
});

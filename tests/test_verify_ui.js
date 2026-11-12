'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const escape = value => String(value).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const decode = value => value.replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&#39;/g,"'").replace(/&amp;/g,'&');
class Element {
  constructor(tag='div',attrs={}) {this.tag=tag;this.attrs=attrs;this.id=attrs.id||'';this.dataset={};this.children=[];this.listeners={};this.disabled='disabled' in attrs;for(const [k,v] of Object.entries(attrs))if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,c)=>c.toUpperCase())]=v;}
  get isConnected(){return this.root||!!this.parentNode?.isConnected;}
  append(n){this.children.push(n);n.parentNode=this;}
  set innerHTML(s){this.children=[];this.markup=s;const stack=[this];for(const token of s.match(/<[^>]+>|[^<]+/g)||[]){if(/^<\//.test(token)){if(stack.length>1)stack.pop();continue;}const m=token.match(/^<([\w-]+)([\s\S]*?)>$/);if(!m){const n=new Element('#text');n.text=decode(token);stack.at(-1).append(n);continue;}const attrs={};for(const a of m[2].matchAll(/([\w-]+)(?:="([^"]*)")?/g))attrs[a[1]]=decode(a[2]||'');const n=new Element(m[1],attrs);stack.at(-1).append(n);if(!['input','br','hr'].includes(n.tag))stack.push(n);}}
  get textContent(){return (this.text||'')+this.children.map(n=>n.textContent).join('');}
  matches(s){if(s[0]==='#')return this.id===s.slice(1);const a=s.match(/^(\w+)?\[([\w-]+)(?:="([^"]*)")?\]$/);return a?(!a[1]||this.tag===a[1])&&a[2] in this.attrs&&(a[3]===undefined||a[3]===this.attrs[a[2]]):this.tag===s;}
  querySelectorAll(s){return this.children.flatMap(n=>[...(s.split(',').some(q=>n.matches(q.trim()))?[n]:[]),...n.querySelectorAll(s)]);}
  querySelector(s){return this.querySelectorAll(s)[0]||null;}
  closest(s){return this.matches(s)?this:this.parentNode?.closest(s)||null;}
  addEventListener(t,f){(this.listeners[t]||= []).push(f);}
  hasAttribute(n){return n in this.attrs;}
}
const tick=()=>new Promise(r=>setImmediate(r));
const copy=x=>JSON.parse(JSON.stringify(x));
const docId='a'.repeat(32), doc2='b'.repeat(32);
function fixture(){
 const main=new Element('main');main.root=true;const views=new Map(),calls=[],overrides=new Map();
 const records={one:{workspace_id:'one',version:7,claims:[{id:'c1',note_id:'n1',note_version:1,claim_anchor:'A <claim>',status:'attached',document_id:docId,page:2,excerpt:'<script>bad</script>',stale:false},{id:'c2',note_id:'n1',note_version:1,claim_anchor:'Other',status:'checked',document_id:docId,page:2,excerpt:'quote',stale:false},{id:'c3',note_id:'n1',note_version:1,claim_anchor:'Needs',status:'needs_source',document_id:null,page:null,excerpt:'',stale:false}]},two:{workspace_id:'two',version:1,claims:[]}};
 const report=id=>({workspace_id:id,totals:{missing_metadata_sources:1,failed_checks:0},notes:id==='one'?[{id:'n1',check_status:'checked',missing_metadata:[{document_id:docId,name:'<Source>',fields:['year']}],mechanical_issues:[],unresolved_references:[]}]:[]});
 const c={window:null,state:{workspace:'one',view:'verify',intent:1,stopped:false,note:'n1',data:{documents:[{id:docId,workspace_id:'one',kind:'pdf',name:'<Source>',metadata:{title:'<Source>'}},{id:doc2,workspace_id:'one',kind:'pdf',name:'Second',metadata:{}}],notes:[{id:'n1',workspace_id:'one',title:'Draft <one>',version:1,body:`A <claim> Other Needs [[source:${docId}:2]] [[source:${doc2}:3]]`},{id:'n2',workspace_id:'one',title:'Other draft',version:1,body:''}]}},escapeHTML:escape,headline:(a,b)=>'<h1>'+escape(a)+'</h1><p>'+escape(b)+'</p>',notify(){},openDocument:async(...args)=>{c.opened=args;},selectNote:async id=>{c.selected=id;},setView:async id=>{c.state.view=id;},
  documents:()=>c.state.data.documents.filter(x=>x.workspace_id===c.state.workspace),notes:()=>c.state.data.notes.filter(x=>x.workspace_id===c.state.workspace),
  draftCitationEntries:(body,docs,w)=>[...body.matchAll(/\[\[(source|reference):([a-f0-9]{32})(?::(\d+))?\]\]/g)].map(m=>({marker:m[0],mode:m[1],doc:docs.find(d=>d.id===m[2]&&d.workspace_id===w),page:m[3]?Number(m[3]):null,count:1,valid:true})),
  request:async(route,data)=>{calls.push({route,data:data?copy(data):null});if(overrides.has(route))return overrides.get(route)(data);if(route.startsWith('/reading?'))return copy(records[decodeURIComponent(route.split('=')[1])]);if(route.startsWith('/project-review?'))return report(decodeURIComponent(route.split('=')[1]));if(route==='/reading/claim'){const r=records[data.workspace_id];r.claims.find(x=>x.id===data.id).status=data.status;r.version++;return copy(r);}throw Error(route);},
  render:()=>views.get(c.state.view)?.render(main),KoshViews:{register:v=>views.set(v.id,v)}};c.window=c;vm.createContext(c);vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/verify.js'),'utf8'),c);
 const fire=async(type,target)=>{assert.ok(target);for(let n=target;n;n=n.parentNode)for(const f of n.listeners[type]||[])f({target});await tick();};
 return {c,main,views,calls,records,overrides,render:()=>views.get('verify').render(main),click:s=>fire('click',main.querySelector(s)),fire};
}
(async()=>{const f=fixture();assert.ok(f.views.has('verify'));assert.equal(typeof f.c.KoshVerify.counts,'function');f.render();await tick();assert.match(f.main.textContent,/Drafts/);assert.ok(f.main.querySelector('#verify-draft'));assert.equal(f.main.querySelectorAll('[data-verify-claim]').length,2);assert.equal(f.main.querySelector('script'),null);assert.ok(f.main.textContent.includes('<script>bad</script>'));assert.ok(f.main.textContent.includes('Second'));assert.ok(f.calls.every(x=>x.data===null));await f.click('[data-verify-save="c1"]');assert.deepEqual(f.calls.find(x=>x.route==='/reading/claim').data,{workspace_id:'one',expected_version:7,id:'c1',status:'checked'});
 const controls=fixture();controls.render();await tick();assert.match(controls.main.textContent,/Drafts: 2.*Citations in drafts: 2.*Needs source: 1.*Attached: 1.*Checked: 1/);assert.ok(controls.main.querySelector('[data-metadata]'));await controls.click('[data-verify-open-claim="c1"]');assert.deepEqual(controls.c.opened,[docId,2,'<script>bad</script>']);await controls.click('[data-verify-filter="all"]');assert.equal(controls.main.querySelectorAll('[data-verify-claim]').length,3);await controls.click('[data-verify-save="c2"]');assert.equal(controls.calls.at(-1).data.status,'attached');const picker=controls.main.querySelector('#verify-draft');picker.value='n2';await controls.fire('change',picker);assert.match(controls.main.textContent,/This draft has no citations/);assert.equal(controls.main.querySelectorAll('[data-verify-claim]').length,0);await controls.click('[data-verify-draft-open]');assert.equal(controls.c.selected,'n2');
 const conflict=fixture();conflict.render();await tick();conflict.overrides.set('/reading/claim',async()=>{throw Object.assign(new Error('conflict'),{status:409});});conflict.records.one.version=12;await conflict.click('[data-verify-save="c1"]');await tick();assert.equal(conflict.c.state.view,'verify');assert.match(conflict.main.textContent,/press.*again/i);conflict.overrides.delete('/reading/claim');await conflict.click('[data-verify-save="c1"]');assert.equal(conflict.calls.filter(x=>x.route==='/reading/claim').at(-1).data.expected_version,12);
 const stale=fixture();let resolve;stale.overrides.set('/reading?workspace_id=one',()=>new Promise(r=>{resolve=r;}));stale.render();stale.c.state.workspace='two';stale.c.state.intent++;stale.render();await tick();resolve(stale.records.one);await tick();assert.equal(stale.c.KoshVerify.counts('one'),null);assert.doesNotMatch(stale.main.textContent,/Draft <one>/);
 const order=fixture();let old;order.overrides.set('/reading?workspace_id=one',()=>new Promise(r=>{old=r;}));order.render();order.overrides.delete('/reading?workspace_id=one');await order.c.KoshVerify.load('one',true);const older=copy(order.records.one);older.claims=[];old(older);await tick();assert.equal(order.c.KoshVerify.counts('one').attached,1);
 const empty=fixture();empty.c.state.workspace=null;empty.render();assert.match(empty.main.textContent,/workspace/i);assert.equal(empty.calls.length,0);
 // V2: saved sentence previews replace visible marker syntax without changing source navigation.
 const marker=`[[source:${docId}:2]]`,otherMarker=`[[reference:${doc2}]]`;
 for(const [body,expected] of [
  [`Earlier sentence. The lantern result ${marker} agrees with ${otherMarker} the second source. Next sentence.`, 'The lantern result agrees with the second source.'],
  [`Earlier sentence. The lantern result is clear. ${marker} Next sentence.`, 'The lantern result is clear.'],
  [`Earlier sentence. “The lantern result is clear.” ${marker} Next sentence.`, '“The lantern result is clear.”'],
  [`A result [[private:placeholder]] with ${marker} two markers.`, 'A result with two markers.'],
  [marker, 'Citation in Draft <one>'],
  [`Other paragraph.\n\n${marker}\n\nNext paragraph.`, 'Citation in Draft <one>'],
  ['Long '+ 'lantern '.repeat(50)+marker+'.', ('Long '+ 'lantern '.repeat(50)).slice(0,239).trimEnd()+'…']
 ]) {
  const sentence=fixture();sentence.c.state.data.notes[0].body=body;sentence.render();await tick();
  const previews=sentence.main.querySelectorAll('[class="verify-citation-sentence"]');
  assert.equal(previews[0].textContent,expected,'Citation shows its saved sentence, including post-punctuation markers');
  assert.equal(previews[0].attrs.title,marker,'Raw marker remains available as an attribute');
  assert.ok(previews[0].textContent.length<=240,'Sentence preview stays bounded');
  for(const preview of previews)assert.doesNotMatch(preview.textContent,/\[\[/,'All marker types are stripped from sentence text');
  await sentence.click('[data-verify-open-citation="0"]');
  assert.deepEqual(sentence.c.opened,[docId,2],'Readable preview keeps the original source/page action');
 }
 console.log('Verify page, claims, conflicts, workspace guards and citation sentence previews passed');})().catch(e=>{console.error(e);process.exitCode=1;});

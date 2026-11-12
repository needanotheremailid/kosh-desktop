'use strict';
// Execute the shell's real registry, dispatch and chrome with a small synthetic DOM.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ui=path.join(__dirname,'../ui');
const read=name=>fs.readFileSync(path.join(ui,name),'utf8').replace(/\r\n/g,'\n');
const app=read('app.js'),html=read('index.html');
function fn(source,name){
 const match=new RegExp('^(?:async )?function '+name+'\\(','m').exec(source);assert.ok(match,name+' is required');
 const lines=source.slice(match.index).split('\n'),out=[lines[0]];
 for(const line of lines.slice(1)){if(/^\s/.test(line)){out.push(line);continue;}if(line==='}')out.push(line);break;}
 return out.join('\n');
}
function element(id){return {id,dataset:{},hidden:false,innerHTML:'',textContent:'',attributes:{},classList:{values:new Set(),toggle(name,on){if(on)this.values.add(name);else this.values.delete(name);},contains(name){return this.values.has(name);}},setAttribute(name,value){this.attributes[name]=value;},getAttribute(name){return this.attributes[name];}};}
const navIds=['overview','discover','screen','read','evidence','synthesise','write','verify','library'];
const nav=navIds.map(id=>Object.assign(element(id),{dataset:{view:id}}));
const missing=Object.assign(element('unregistered'),{dataset:{view:'unregistered'}});nav.push(missing);
const nodes=new Map();
const node=selector=>{if(!nodes.has(selector))nodes.set(selector,element(selector));return nodes.get(selector);};
let rendered=0,evidenceRendered=0,moduleRendered=0;
const context={window:{},Map,Set,state:{data:{workspaces:[{id:'one',title:'Fixture'}],documents:[],notes:[]},workspace:'one',view:'library',intent:0,stopped:false,panel:'ask'},
 $:selector=>selector==='#view-nav [data-view="write"]'?nav.find(item=>item.dataset.view==='write'):node(selector),
 $$:selector=>selector==='#view-nav [data-view]'?nav:[],
 resetLibraryWorkspace(){},resetNotesWorkspace(){},escapeHTML:String,conflictedEditors:()=>[],workspace:()=>({id:'one',title:'Fixture'}),documents:()=>[],notes:()=>[],
 activeSplit:()=>false,readerVisible:()=>false,updateSaveState(){},flushEdits:async()=>true,render(){rendered++;},
 renderLibrary(){},renderReader(){},renderWriter(){},renderDiscovery(){},renderEvidence(){evidenceRendered++;},empty:()=>'',notify(){},setTimeout(){},
};
vm.createContext(context);
const registryStart=app.indexOf('const builtInViews='),registryEnd=app.indexOf('const folderState=',registryStart);
assert.ok(registryStart>=0&&registryEnd>registryStart,'The public view registry must be defined before module scripts run');
vm.runInContext(app.slice(registryStart,registryEnd)+'\n'+['viewAvailable','updateChrome','renderMain','setView'].filter(name=>!app.slice(registryStart,registryEnd).includes('function '+name+'(')).map(name=>fn(app,name)).join('\n'),context);
const registry=context.window.KoshViews;
assert.equal(typeof registry.register,'function');assert.equal(typeof registry.has,'function');assert.equal(typeof registry.get,'function');
assert.equal(registry.has('unregistered'),false);
context.updateChrome();assert.equal(missing.hidden,true,'A sidebar entry without a renderer is hidden');
registry.register({id:'fixture',title:'Fixture view',render(main){moduleRendered++;main.innerHTML='Module output';}});
assert.equal(registry.has('fixture'),true);assert.equal(registry.get('fixture').title,'Fixture view');
context.state.view='fixture';context.renderMain();assert.equal(moduleRendered,1,'renderMain executes the registered renderer');
assert.equal(node('#main-view').innerHTML,'Module output');assert.equal(evidenceRendered,0,'A registered view cannot fall through to Extract');
registry.register({id:'fixture',title:'Replacement view',render(main){main.innerHTML='Replacement output';}});
context.renderMain();assert.equal(node('#main-view').innerHTML,'Replacement output','A later page can replace a temporary dialog bridge');
context.updateChrome();assert.equal(node('#view-title').textContent,'Replacement view','Chrome uses the replacement title');
assert.throws(()=>registry.register({id:'library',title:'Wrong owner',render(){}}),/Built-in view/,'Modules cannot replace built-in pages');
for(const id of ['overview','screen','verify'])registry.register({id,title:id,render(){}});
if(!registry.has('synthesise'))registry.register({id:'synthesise',title:'Synthesise',render(){}});
for(const id of navIds){
 context.state.view=id;context.updateChrome();
 assert.deepEqual(nav.filter(item=>item.classList.contains('active')).map(item=>item.dataset.view),[id],'Exactly the current sidebar item is active: '+id);
 assert.deepEqual(nav.filter(item=>item.getAttribute('aria-current')==='page').map(item=>item.dataset.view),[id],'Accessible current page agrees: '+id);
 assert.equal(nav.find(item=>item.dataset.view===id).hidden,false,'Available view stays visible: '+id);
}
assert.ok(!html.includes('id="next-step"'),'The permanent next-step strip is removed');
assert.ok(!html.includes('id="add-menu"'),'Import actions live on Find');
assert.ok(!html.includes('class="more-menu'),'Secondary actions have named homes');
for(const id of navIds)assert.match(html,new RegExp('data-view="'+id+'"'),'Sidebar offers '+id);
const sidebar=html.match(/<nav id="view-nav"[^>]*>([\s\S]*?)<\/nav>/);
assert.ok(sidebar,'The research path has its own navigation landmark');
assert.deepEqual([...sidebar[1].matchAll(/data-view="([^"]+)"/g)].map(match=>match[1]),navIds,'Sidebar follows Overview, research path, then All sources');
const footer=html.match(/<div class="chrome-actions"[^>]*>([\s\S]*?)<\/div>/);
assert.ok(footer,'Sidebar footer is present');
for(const action of ['palette','settings','help'])assert.ok(footer[1].includes('data-action="'+action+'"'),'Footer offers '+action);
for(const id of ['panel-toggle','open-tools','quit-app']){
 assert.ok(footer[1].includes('id="'+id+'"'),'Footer offers '+id);
 assert.ok(app.includes("$('#"+id+"').addEventListener('click'"),'Footer control has a click handler: '+id);
}
const settings=html.match(/<dialog id="settings-dialog"[^>]*>([\s\S]*?)<\/dialog>/);
assert.ok(settings,'Settings dialog is present');
const advanced=settings[1].slice(settings[1].indexOf('<h3>Advanced</h3>'));
assert.ok(settings[1].includes('<h3>Advanced</h3>'),'Advanced tools have a named Settings section');
for(const action of ['assist-open','agent-help','folder-edits','about'])assert.ok(advanced.includes('data-action="'+action+'"'),'Advanced retains '+action);
assert.ok(advanced.includes('id="refresh-state"'),'Refresh workspace remains reachable in Advanced');
assert.ok(advanced.includes('id="menu-review-slot"'),'Review tools retain their existing Advanced mount');
assert.ok(read('project_review.js').includes("querySelector('#menu-review-slot')"),'Project review uses the retained mount');
for(const name of ['overview','screening','verify']){
 assert.ok(html.includes('src="/'+name+'.js"'),'Module script loaded: '+name);
 assert.ok(html.includes('href="/'+name+'.css"'),'Module stylesheet loaded: '+name);
 assert.ok(html.indexOf('src="/app.js"')<html.indexOf('src="/'+name+'.js"'),'Registry loads before '+name);
}
// Find renders all four source-entry routes alongside an explicit public query.
{
 const main={innerHTML:''};
 const findContext={state:{workspace:'one'},discovery:{provider:'pubmed',query:'',result:null,busy:false},
  $:()=>main,headline:title=>'<h1>'+title+'</h1>',escapeHTML:String,existingReferenceKeys:()=>new Set(),empty:()=>'',applyHints(){}};
 vm.createContext(findContext);vm.runInContext(fn(app,'findEntryPoints')+'\n'+fn(app,'renderDiscovery'),findContext);
 findContext.renderDiscovery();
 const entries=main.innerHTML.match(/<section class="find-entry-points"[^>]*>([\s\S]*?)<\/section>/);
 assert.ok(entries,'Find renders source-entry controls');
 assert.deepEqual([...entries[1].matchAll(/data-action="([^"]+)"/g)].map(match=>match[1]),['lookup-publication','paste-references','import','bibliography']);
 assert.match(main.innerHTML,/id="discovery-form"/);assert.match(main.innerHTML,/id="discovery-query"/);
 for(const provider of ['pubmed','crossref','europepmc','openalex'])assert.ok(main.innerHTML.includes('value="'+provider+'"'),'Find retains '+provider);
}
// Read landing uses real workspace filtering, escaping and the reading-state guard.
{
 const main={innerHTML:''},hostile='<img src=x onerror="attack()"> & <script>bad()</script>';
 const data={documents:[
  {id:'pdf-one',workspace_id:'one',kind:'pdf',name:'source.pdf',metadata:{title:hostile}},
  {id:'text-one',workspace_id:'one',kind:'txt',name:'Methods notes'},
  {id:'archived',workspace_id:'one',kind:'pdf',name:'Archived fixture',archived:true},
  {id:'foreign',workspace_id:'two',kind:'pdf',name:'Other project source'}
 ]};
 const saved={workspace_id:'one',sources:[{document_id:'pdf-one',status:'reading',last_page:7},{document_id:'text-one',status:'unread',last_page:1}],resume:{document_id:'text-one',page:3}};
 const readerContext={state:{workspace:'one',view:'read',doc:null,data,readSequence:0},readerRoot:()=>main,activeSplit:()=>false,
  headline:(title,subtitle)=>'<h1>'+title+'</h1><p>'+subtitle+'</p>',empty:(title,subtitle,action)=>title+subtitle+action,
  clearTimeout(){},readingHidePopover(){},Map,Set,Promise};
 vm.createContext(readerContext);
 const reading=read('reading.js'),readingEnd=reading.indexOf('function readingDraftKey(');
 assert.ok(readingEnd>0,'Reading API precedes its UI mounts');
 vm.runInContext(reading.slice(0,readingEnd)+'\n'+app.split('\n').find(line=>line.startsWith('const escapeHTML ='))+'\n'+['documents','sourceLabel','readSourceButtons','renderReader'].map(name=>fn(app,name)).join('\n'),readerContext);
 readerContext.saved=saved;vm.runInContext("readingModel.workspace='one';readingModel.data=saved;",readerContext);
 readerContext.renderReader();
 assert.match(main.innerHTML,/class="read-source-list"/);assert.match(main.innerHTML,/aria-label="Workspace sources"/);
 assert.match(main.innerHTML,/data-document="pdf-one"/);assert.match(main.innerHTML,/data-document="text-one"/);
 assert.match(main.innerHTML,/pdf · Reading/);assert.match(main.innerHTML,/txt · Unread/);
 assert.match(main.innerHTML,/Continue reading · page 7/);assert.match(main.innerHTML,/Continue reading · section 3/);
 assert.ok(main.innerHTML.includes('&lt;img src=x onerror=&quot;attack()&quot;&gt; &amp; &lt;script&gt;bad()&lt;/script&gt;'),'Hostile source title is escaped as text');
 assert.doesNotMatch(main.innerHTML,/<img|<script|data-document="archived"|data-document="foreign"/);
 readerContext.state.workspace='two';readerContext.renderReader();
 assert.match(main.innerHTML,/Other project source/);assert.match(main.innerHTML,/Reading status not loaded/);
 assert.doesNotMatch(main.innerHTML,/Continue reading|page 7|section 3|data-document="pdf-one"/,'A workspace change cannot inherit saved places from the previous workspace');
 assert.equal(vm.runInContext('KoshReading.current()',readerContext),null,'The actual reading API clears the prior workspace state');
 readerContext.state.workspace='empty';readerContext.renderReader();assert.match(main.innerHTML,/data-view="discover"/,'An empty Read page offers Find');
}
// Hand-worked fixture: four active sources (one catalogue), three imported,
// two saved drafts, three extraction rows, five prose markers and four live links.
{
 const a='a'.repeat(32),b='b'.repeat(32),c='c'.repeat(32),d='d'.repeat(32),e='e'.repeat(32),f='f'.repeat(32),unknown='0'.repeat(32);
 const data={documents:[
  {id:a,workspace_id:'one',kind:'pdf'},
  {id:b,workspace_id:'one',kind:'catalogue',metadata:{catalogue_source:'Fixture index'}},
  {id:c,workspace_id:'one',kind:'txt'},
  {id:d,workspace_id:'one',kind:'pdf',archived:true},
  {id:e,workspace_id:'one',kind:'txt'},
  {id:f,workspace_id:'two',kind:'pdf'}
 ],notes:[
  {id:'n1',workspace_id:'one',version:3,body:'Alpha [[source:'+a+':1]] again [[source:'+a+':1]] and [[reference:'+b+']]. Unresolved [[reference:'+unknown+']] foreign [[source:'+f+':1]].\n`[[reference:'+b+']]`\n```\n[[source:'+a+':2]]\n```'},
  {id:'n2',workspace_id:'one',version:1,body:'Beta'},
  {id:'n3',workspace_id:'two',version:1,body:'Foreign [[source:'+f+':1]]'}
 ],matrix:[
  {id:'m1',workspace_id:'one',document_id:a},{id:'m2',workspace_id:'one',document_id:a},
  {id:'m3',workspace_id:'one',document_id:d},{id:'m4',workspace_id:'two',document_id:f}
 ]};
 const reading={workspace_id:'one',sources:[
  {document_id:c,status:'read'},{document_id:e,status:'reading'},
  {document_id:b,status:'read'},{document_id:d,status:'read'},{document_id:f,status:'read'}
 ],claims:[
  {note_id:'n1',status:'needs_source',note_version:3,claim_anchor:'Alpha'},
  {note_id:'n2',status:'attached',note_version:1,claim_anchor:'Beta'},
  {note_id:'n1',status:'checked',note_version:3,claim_anchor:'Alpha'},
  {note_id:'n1',status:'checked',note_version:2,claim_anchor:'Alpha'},
  {note_id:'n1',status:'checked',note_version:3,claim_anchor:'Alpha',archived:true},
  {note_id:'n3',status:'checked',note_version:1,claim_anchor:'Foreign'}
 ]};
 let overviewView;
 const overviewContext={window:{KoshViews:{register:view=>{overviewView=view;},has:()=>false}},Map,Set,
  state:{workspace:'one',view:'overview',data,stopped:false},
  citationMarker(doc,mode,page,workspace){if(!doc||doc.workspace_id!==workspace)throw new Error('Unknown fixture source');return 'valid';},
  escapeHTML:String,headline:(title,subtitle)=>'<h1>'+title+'</h1><p>'+subtitle+'</p>',nextStep:()=>null,
  KoshReading:{current:()=>reading},
 };
 vm.createContext(overviewContext);
 vm.runInContext(fn(app,'draftCitationEntries')+'\n'+read('overview.js'),overviewContext);
 const counts=overviewContext.window.KoshOverview.counts;
 const plain=value=>JSON.parse(JSON.stringify(value));
 const before=JSON.stringify({data,reading});
 assert.deepEqual(plain(counts(data,'one',reading)),{
  sources:4,catalogue:1,imported:3,reading:{unread:1,reading:1,read:1},
  evidenceRows:3,evidenceSources:1,drafts:2,citations:5,citedSources:2,
  claims:{total:4,needsSource:1,attached:1,checked:1,stale:1}
 });
 assert.deepEqual(plain(counts(data,'two',reading)),{
  sources:1,catalogue:0,imported:1,reading:null,evidenceRows:1,evidenceSources:1,
  drafts:1,citations:1,citedSources:1,claims:null
 },'Another workspace never inherits the first workspace reading or claim state');
 assert.deepEqual(plain(counts(data,null,reading)),{
  sources:0,catalogue:0,imported:0,reading:null,evidenceRows:0,evidenceSources:0,
  drafts:0,citations:0,citedSources:0,claims:null
 });
 assert.equal(counts(data,'one').reading,null,'Not loaded is distinct from zero unread sources');
 assert.equal(counts(data,'one').claims,null,'Not loaded is distinct from zero claim links');
 assert.equal(JSON.stringify({data,reading}),before,'Counting does not modify saved source records');
 assert.equal(overviewView.id,'overview','The module registers its actual renderer');
 const main={innerHTML:'',querySelector:()=>null};overviewView.render(main);
 assert.match(main.innerHTML,/4 active sources/);assert.match(main.innerHTML,/3 saved evidence rows/);
 assert.match(main.innerHTML,/5 citation markers/);assert.match(main.innerHTML,/1 checked by you/);
 assert.match(main.innerHTML,/data-view="screen" disabled/,'A future page is not offered as ready');
 overviewContext.state.workspace='two';overviewView.render(main);
 assert.match(main.innerHTML,/1 active source/);assert.match(main.innerHTML,/claim links are not loaded/);
 assert.doesNotMatch(main.innerHTML,/4 active sources|5 citation markers/,'Rendered counts follow the selected workspace');
 overviewContext.state.workspace=null;overviewView.render(main);
 assert.match(main.innerHTML,/data-action="create-workspace"/);assert.doesNotMatch(main.innerHTML,/overview-path/);
 console.log('Overview counts and workspace isolation checks passed');
}
(async()=>{
 await context.setView('fixture');assert.equal(context.state.view,'fixture');assert.equal(rendered,1,'Registered views navigate through setView');
 await context.setView('unregistered');assert.equal(context.state.view,'fixture','Unknown ids cannot become the current view');assert.equal(rendered,1);
 for(const id of ['library','read','write','evidence','discover']){await context.setView(id);assert.equal(context.state.view,id,'Built-in id remains supported: '+id);}
 context.flushEdits=async()=>false;await context.setView('fixture');assert.equal(context.state.view,'discover','Failed edit flush blocks module navigation too');
 context.flushEdits=async()=>true;context.state.workspace=null;await context.setView('library');assert.equal(context.state.view,'overview','Without a workspace, navigation opens the create-workspace Overview');
 console.log('Shell registry, dispatch and sidebar checks passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

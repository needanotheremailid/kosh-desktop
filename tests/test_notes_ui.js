'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../ui/app.js'),'utf8');
const start=source.indexOf('function noteSearchText('),end=source.indexOf('function renderWriter(){',start);
assert.ok(start>=0&&end>start,'Notes navigation functions must exist');
const context={};vm.createContext(context);vm.runInContext(source.slice(start,end),context);
const notes=[
 {id:'a',workspace_id:'one',title:'Zebra',body:'A weekly reading plan.',updated_at:'2026-01-03'},
 {id:'b',workspace_id:'one',title:'Álpha',body:'Long background.\nA café reading session.\nConclusion.',updated_at:'2026-01-02'},
 {id:'c',workspace_id:'one',title:'Beta',body:'Other writing',updated_at:'2026-01-02'},
 {id:'d',workspace_id:'two',title:'Foreign',body:'weekly reading',updated_at:'2026-02-01'},
 {id:'e',workspace_id:'one',title:'',body:'',updated_at:'invalid'},
];
const original=JSON.stringify(notes),editors=new Map();
const select=(extra={})=>context.browseNotes(notes,editors,{workspace:'one',query:'',sort:'updated',...extra});
const ids=extra=>Array.from(select(extra),n=>n.id);
assert.deepEqual(ids(),['a','b','c','e']);
assert.deepEqual(ids({sort:'title'}),['b','c','e','a']);
assert.deepEqual(ids({query:'ALPHA cafe'}),['b']);
assert.deepEqual(ids({query:'weekly'}),['a'],'Other workspaces stay excluded');
assert.deepEqual(ids({query:'missing'}),[]);
assert.notEqual(context.noteSearchText('काम'),context.noteSearchText('कम'),'Keep Hindi vowel signs meaningful');
assert.notEqual(context.noteSearchText('ਕਾਮ'),context.noteSearchText('ਕਮ'),'Keep Punjabi vowel signs meaningful');
assert.equal(context.noteSearchText('INDEX'),'index');
assert.equal(context.noteSearchText('Café'),'cafe');
editors.set('a',{title:'',body:'Unsent lantern outline',dirty:true,conflict:false});
assert.deepEqual(ids({query:'zebra'}),[],'Cleared title must not fall back to saved title');
assert.deepEqual(ids({query:'lantern'}),['a'],'Unsaved body participates');
assert.equal(select({query:'lantern'})[0].title,'');
assert.equal(select({query:'lantern'})[0].dirty,true);
assert.equal(JSON.stringify(notes),original,'Search/sort must never mutate saved notes');
assert.match(context.noteExcerpt(notes[1].body,'cafe'),/A café reading session\./);
assert.ok(context.noteExcerpt('x'.repeat(600),'').length<=161);
assert.equal(context.noteExcerpt('A [[source:local-id:1]] and ![Chart](kosh-asset:figure-id)',''),'A [Source reference] and [Figure: Chart]');
assert.match(context.noteExcerpt('x'.repeat(250)+' lantern '+'y'.repeat(250),'lantern'),/lantern/,'Long paragraph excerpt must include its match');
context.noteBrowse={workspace:'one',query:'retained',sort:'title'};context.state={workspace:'one',note:'a'};
context.resetNotesWorkspace();assert.equal(context.noteBrowse.query,'retained');
context.state.workspace='two';context.resetNotesWorkspace();assert.equal(context.noteBrowse.query,'');assert.equal(context.noteBrowse.sort,'updated');
assert.equal(context.state.note,'a','Resetting navigation must not select or edit a draft');
// Exercise the real rendering helper with two independent navigation containers.
vm.runInContext(source.split('\n').find(line=>line.startsWith('const escapeHTML =')),context);
context.composingNoteInputs=new WeakSet();context.dateLabel=()=> 'Saved';context.notes=()=>notes.filter(n=>n.workspace_id===context.state.workspace);
context.state={workspace:'one',note:'a',view:'write',editors};
context.noteBrowse={workspace:'one',query:'lantern',sort:'updated'};
const makeNav=()=>({
 dataset:{notesNavigation:'writer',noteWorkspace:'one'},
 '[data-note-query]':{value:'',focus(){this.focused=true;}},
 '[data-note-sort]':{value:''},'[data-notes-count]':{textContent:'',setAttribute(){}},
 '[data-note-results]':{innerHTML:'',scrollTop:17,contains:()=>false},
 '[data-clear-notes]':{disabled:false},'[data-note-outside]':{hidden:true},
});
const navs=[makeNav(),makeNav()];context.$=(selector,nav)=>nav[selector];
let replacements=0;
Object.defineProperty(navs[0]['[data-note-results]'],'innerHTML',{get(){return 'Browser-normalized HTML';},set(value){this.rendered=value;replacements++;}});
context.$$=selector=>selector==='[data-notes-navigation]'?navs:[];context.document={activeElement:null};
context.renderNotesResults();
context.renderNotesResults();assert.equal(replacements,1,'Unchanged results must preserve the actual button nodes');
assert.equal(navs[0]['[data-notes-count]'].textContent,'1 of 4 notes & drafts');
assert.equal(navs[1]['[data-note-query]'].value,'lantern');
assert.match(navs[0]['[data-note-results]'].rendered,/Unsaved/);
assert.equal(navs[0]['[data-note-results]'].scrollTop,17);
const composing=navs[0]['[data-note-query]'];composing.value='unfinished composition';context.composingNoteInputs.add(composing);
context.renderNotesResults();assert.equal(composing.value,'unfinished composition','An autosave refresh must not erase IME composition');
context.composingNoteInputs.delete(composing);
context.noteBrowse.query='nothing';context.renderNotesResults();
assert.equal(navs[0]['[data-note-outside]'].hidden,false);assert.equal(context.state.note,'a');
context.noteBrowse.query='';editors.set('a',{title:'<img src=x onerror=alert(1)>',body:'<script>bad()</script>'});context.renderNotesResults();
assert.ok(!navs[0]['[data-note-results]'].rendered.includes('<script>'));
assert.match(navs[0]['[data-note-results]'].rendered,/&lt;img src=x/);
context.document.addEventListener=(type,fn)=>{context.keydown=fn;};
vm.runInContext(source.split('\n').find(line=>line.startsWith("document.addEventListener('keydown',")),context);
let prevented=false;context.noteBrowse.query='old';const query=navs[0]['[data-note-query]'];query.value='old';query.matches=()=>true;
context.keydown({key:'Escape',target:query,preventDefault(){prevented=true;}});
assert.equal(prevented,true);assert.equal(context.noteBrowse.query,'');assert.equal(query.value,'');
const stableInput={selectionStart:2,selectionEnd:4,focus(){this.focused=true;},setSelectionRange(start,end){this.restored=[start,end];}};
const stableNav=makeNav();stableNav.contains=e=>e===stableInput;stableNav['[data-note-results]'].scrollTop=83;
context.document.activeElement=stableInput;context.$=(selector,nav)=>nav?nav[selector]:stableNav;
const captured=context.captureNotesNavigation('writer');assert.equal(captured.scroll,83);
let reattached;const placeholder={replaceWith(node){reattached=node;}};
context.$=(selector,nav)=>nav?nav[selector]:placeholder;
context.restoreNotesNavigation(captured);assert.equal(reattached,stableNav);assert.equal(stableInput.focused,true);assert.deepEqual(stableInput.restored,[2,4]);
context.$=()=>stableInput;context.composingNoteInputs.add(stableInput);assert.equal(context.deferNotesRender('writer'),true);
context.composingNoteInputs.delete(stableInput);assert.equal(context.deferNotesRender('writer'),false);
console.log('Notes navigation: search/sort, overlays, excerpts, workspace isolation, synchronized controls, IME refresh and safe rendering passed');

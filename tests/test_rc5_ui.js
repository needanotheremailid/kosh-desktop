'use strict';
// rc.5 interaction contracts: split routing, open intent, insert-at-cursor, @ trigger, next step, palette, stopped gate, reachability, drops.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ui=path.join(__dirname,'../ui');
// A Windows checkout may have CRLF line endings; the slicing below expects LF.
const read=file=>fs.readFileSync(file,'utf8').replace(/\r\n/g,'\n');
const app=read(path.join(ui,'app.js'));
const reading=read(path.join(ui,'reading.js'));
const html=read(path.join(ui,'index.html'));
// A top-level function: its first line, indented continuation lines, and a closing "}" line.
function fn(source,name){const match=new RegExp('^(async )?function '+name+'\\(','m').exec(source);assert.ok(match,name+' is required');const lines=source.slice(match.index).split('\n'),out=[lines[0]];for(const line of lines.slice(1)){if(/^\s/.test(line)){out.push(line);continue;}if(line==='}')out.push(line);break;}return out.join('\n');}
function load(context,source,...names){vm.createContext(context);vm.runInContext(names.map(name=>fn(source,name)).join('\n'),context);return context;}

// Split routing: Source beside exists only in Write, and each pane has its own host.
{const hosts={'#source-host':'source','#writer-host':'writer','#main-view':'main'};const c=load({state:{view:'write',splitPref:true},$:s=>hosts[s]},app,'activeSplit','readerVisible','readerRoot','writerRoot');
 assert.equal(c.activeSplit(),true);assert.equal(c.readerVisible(),true);assert.equal(c.readerRoot(),'source');assert.equal(c.writerRoot(),'writer');
 c.state.view='read';assert.equal(c.activeSplit(),false,'The preference alone never splits Read');assert.equal(c.readerRoot(),'main');
 c.state.view='library';assert.equal(c.readerVisible(),false);}

// Open intent: a later open wins even when the earlier response arrives last; a page repaint is not a new intent.
{const pending=new Map();const c=load({state:{view:'read',splitPref:false,workspace:'w',intent:0,stopped:false,readSequence:0},innerWidth:1400,setPanelOpen(){},selectedPassage:null,flushEdits:async()=>true,$:()=>null,request:path=>new Promise(resolve=>pending.set(path.split('=')[1],resolve)),render(){},renderReader(){},updateChrome(){},renderPanel(){},applyHints(){},notify(){},renderMain(){}},app,'activeSplit','openDocument');
 const first=c.openDocument('A',2);
 setImmediate(async()=>{assert.ok(pending.has('A'),'A is in flight');const second=c.openDocument('B',3);await new Promise(resolve=>setImmediate(resolve));pending.get('B')({document:{id:'B',pages:5,kind:'pdf'}});await second;pending.get('A')({document:{id:'A',pages:5,kind:'pdf'}});await first;
  assert.equal(c.state.doc.id,'B','The stale open must not replace the newer one');assert.equal(c.state.page,3);
  const third=c.openDocument('C',1);c.state.page++;c.renderReader();setImmediate(async()=>{pending.get('C')({document:{id:'C',pages:2,kind:'pdf'}});await third;assert.equal(c.state.doc.id,'C','Turning pages does not cancel an open');console.log('rc.5 open-intent checks passed');});});}

// Insert at the cursor: no range keeps selected words; an explicit range replaces exactly.
{const editor={body:'Hello world',selectionStart:0,selectionEnd:5,revision:0};const c=load({state:{view:'library'},activeEditor:()=>editor,preserveDraft(){},updateSaveState(){},renderNextStep(){},saveTimer:0,clearTimeout(){},setTimeout(){},saveAll:async()=>{},renderWriter(){throw new Error('Write is not open');},$:()=>null},app,'insertWriterText');
 c.insertWriterText('X');assert.equal(editor.body,'HelloX world','Default insert lands after the selection');assert.equal(editor.selectionEnd,6);
 c.insertWriterText('Y',{start:0,end:5});assert.equal(editor.body,'YX world','An explicit range replaces');}

// Source text from Read or the pane: spacing follows the cursor, blocks start a paragraph.
{const editor={id:'n',title:'Draft',body:'Claim.',selectionEnd:6,conflict:false},store=new Map();let inserted=null,rendered=0,created=null,list=[{id:'n',title:'Draft',updated_at:'2026-01-02'}];const c=load({state:{view:'read',note:'n',intent:0,splitPref:false},notes:()=>list,editorFor:()=>editor,rememberWriterSelection(){},insertWriterText:text=>{inserted=text;},notify(){},render:()=>{rendered++;},localStorage:{setItem:(k,v)=>store.set(k,v)},createNote:(title,body,options)=>{created={title,body,options};}},app,'latestNoteId','insertSourceText');
 c.insertSourceText('[[source:a:1]]','t');assert.equal(inserted,' [[source:a:1]]');assert.equal(c.state.view,'write','Citing from Read opens Write');assert.equal(c.state.splitPref,true,'…with the source beside');assert.equal(store.get('kosh-split'),'1');assert.equal(rendered,1);
 c.insertSourceText('[[source:a:1]]\n\n> quote\n\n','t');assert.equal(inserted.slice(0,2),'\n\n','A quoted passage starts its own paragraph');
 c.state.view='library';c.state.splitPref=false;c.insertSourceText('answer','t',{fromSource:false});assert.equal(c.state.splitPref,false,'Chat answers do not open the source pane');
 editor.conflict=true;inserted=null;c.insertSourceText('x','t');assert.equal(inserted,null,'A conflicted draft is never written');
 editor.conflict=false;list=[{id:'old',title:'Old',updated_at:'2026-01-01'},{id:'n',title:'Draft',updated_at:'2026-01-02'}];c.state.note=null;inserted=null;created=null;c.insertSourceText('[[source:a:1]]','t');assert.equal(c.state.note,'n','With no draft open, citing goes to the most recently saved draft');assert.ok(inserted);assert.equal(created,null);
 list=[];c.state.note=null;c.state.view='read';const before=c.state.intent;c.insertSourceText('[[source:a:1]]','Notes on A');assert.equal(created.options.intent,before+1,'The caller allocates one intent and passes it on');assert.equal(created.options.split,true);}

// createNote: a workspace change during the flush sends nothing; one during the POST keeps the note but does not navigate.
{let release,posted=0;const kept=[];const c=load({state:{workspace:'w',intent:0,view:'library',note:null},creatingNote:false,flushEdits:()=>new Promise(resolve=>{release=resolve;}),request:async()=>{posted++;return {id:'new',title:'T'};},replaceNote:note=>kept.push(note.id),notify(){},editorFor(){},render(){},$:()=>null,localStorage:{setItem(){}}},app,'createNote');
 const first=c.createNote('T','');c.state.workspace='other';release(true);
 first.then(async()=>{assert.equal(posted,0,'A stale create never reaches the server');c.state.workspace='w';c.request=async()=>{posted++;c.state.intent++;return {id:'new',title:'T'};};c.flushEdits=async()=>true;await c.createNote('T','');assert.equal(posted,1);assert.deepEqual(kept,['new'],'The created note is kept');assert.equal(c.state.note,null,'A stale create does not navigate');console.log('rc.5 createNote intent checks passed');});}

// @ opens the picker only at the start of a word.
{const c=load({},app,'citationTriggerAt');
 assert.equal(c.citationTriggerAt('@',1),0);assert.equal(c.citationTriggerAt('see @',5),4);assert.equal(c.citationTriggerAt('me@x',3),-1,'Email addresses do not trigger');assert.equal(c.citationTriggerAt('a\n@',3),2);assert.equal(c.citationTriggerAt('abc',0),-1);}

// Next step: derived from loaded data; unknown never shows as undone; hidden per workspace.
{const store=new Map();const state={data:{workspaces:[{id:'w'}]},workspace:'w',stopped:false,view:'library',editors:new Map(),preview:false};let docs=[],notesList=[];
 const c=load({state,localStorage:{getItem:k=>store.get(k)??null},documents:()=>docs,notes:()=>notesList,activeEditor:()=>null},app,'nextStep');
 assert.equal(c.nextStep().action,'import');docs=[{id:'d'}];assert.equal(c.nextStep().action,'new-note');
 notesList=[{id:'n',body:'text'}];assert.equal(c.nextStep().view,'write');
 state.editors.set('n',{body:'see [[source:d:1]]'});assert.match(c.nextStep().text,/Export/);
 store.set('kosh-exported:w','1');assert.equal(c.nextStep(),null);
 store.delete('kosh-exported:w');store.set('kosh-tips-hidden:w','1');assert.equal(c.nextStep(),null);
 state.data={};assert.equal(c.nextStep(),null,'Without loaded data there is no suggestion');}

// Palette: every command reaches a handled action or a real view.
{const block=app.slice(app.indexOf('const paletteCommands=['),app.indexOf('];',app.indexOf('const paletteCommands=[')));
 const actions=[...block.matchAll(/action:'([a-z-]+)'/g)].map(m=>m[1]),views=[...block.matchAll(/view:'([a-z]+)'/g)].map(m=>m[1]);
 assert.ok(actions.length>10);for(const name of actions)assert.ok(app.includes("name==='"+name+"'"),'Palette action without a handler: '+name);
 for(const view of views)assert.ok(['library','read','write','evidence','discover'].includes(view),view);}

// Stopped gate: every catch/finally that writes the page directly checks state.stopped first.
{const allowed=new Set(['reviewer.js:21']);const failures=[];
 const blockEnd=(src,open)=>{let depth=0,quote=null;for(let i=open;i<src.length;i++){const ch=src[i];if(quote){if(ch==='\\'){i++;continue;}if(ch===quote)quote=null;continue;}if(ch==="'"||ch==='"'||ch==='`'){quote=ch;continue;}if(ch==='{')depth++;else if(ch==='}'){depth--;if(!depth)return i;}}return -1;};
 for(const file of fs.readdirSync(ui).filter(f=>f.endsWith('.js'))){const src=read(path.join(ui,file)),re=/\b(catch|finally)\s*(\([^)]*\))?\s*\{/g;let m;while((m=re.exec(src))){const open=m.index+m[0].length-1,body=src.slice(open+1,blockEnd(src,open)),where=file+':'+src.slice(0,m.index).split('\n').length;if(/innerHTML|textContent\s*=|insertAdjacentHTML/.test(body)&&!/^\s*if\([^)]*state\.stopped\)return/.test(body)&&!allowed.has(where))failures.push(where);}}
 assert.deepEqual(failures,[],'Unguarded DOM writes after Quit');
 for(const name of ['notify','render','renderMain','renderPanel'])assert.match(fn(app,name),/state\.stopped\)return/,name+' must be a no-op once stopped');}

// Reachability: every action the rc.4 interface offered is still offered, or under its new name.
{const rc4=['about','agent-help','apply-proposal','ask-search','assist-history','assist-open','assist-preview','assist-revise','assist-send','assist-writing','attach-catalogue','bibliography','bibliography-file','bibliography-import','bibliography-preview','cancel-ask','citation-insert','cite-library','clear-library-filters','clear-search','close-panel','copy-conflict','copy-proposal','create-workspace','draft-source','export-options','export-profile-outline','figure-import','focus-search','folder-add','folder-apply','folder-assist-open','folder-assist-preview','folder-assist-revise','folder-assist-send','folder-edits','folder-history','folder-preview','folder-revise','folder-use-draft','getting-started','help','import','insert-math','insert-reference','last-receipt','load-saved-version','lookup-publication','matrix-preserve-new','new-matrix','new-note','next-page','note-compare','note-from-page','note-history','ocr-open','ocr-run','open-ask','original-file','outline-casereport','outline-imrad','outline-protocol','outline-review','previous-page','propose-evidence','receipt-library','refresh-models','retrieval-index','retrieval-open','retrieval-search','retry-library-search','retry-preview','save-alternative','save-edits','settings','skip-guide','table-file','table-import','table-insert','table-preview','toggle-preview','writing-check'];
 const renamed={'draft-source':'toggle-split','focus-search':'palette'};const offered=fs.readdirSync(ui).filter(f=>/\.(js|html)$/.test(f)).map(f=>read(path.join(ui,f))).join('\n');
 for(const name of rc4){const now=renamed[name]||name;assert.ok(offered.includes('data-action="'+now+'"'),'No control offers '+now);assert.ok(app.includes("name==='"+now+"'")||app.includes("'"+now+"'")||now.startsWith('outline-')&&app.includes("name.startsWith('outline-')"),'No handler for '+now);}
 assert.ok(app.includes("name==='draft-source'"),'The old split action name still works');}

// Drops: only files import; dragged text keeps the browser drop into the draft.
{const c=load({},app,'fileDrag');assert.equal(c.fileDrag({dataTransfer:{types:['Files']}}),true);assert.equal(c.fileDrag({dataTransfer:{types:['text/plain']}}),false);assert.equal(c.fileDrag({}),false);}

// A rebuilt writer keeps the draft selection even when a toolbar button had focus.
{let focused=false;const body={sel:null,scrollTop:0,setSelectionRange(a,b){this.sel=[a,b];},focus(){focused=true;}};const c=load({$:s=>s==='#draft-body'?body:null},app,'restoreWriterState');
 c.restoreWriterState({focus:null,start:6,end:10,scroll:40});assert.deepEqual(body.sel,[6,10]);assert.equal(focused,false);assert.equal(body.scrollTop,40);}

// The selection bar refuses a snapshot from another page or source.
{let visible=true;const c=load({state:{workspace:'w'},readingVisibleNow:()=>visible,readingModel:{popover:{snapshot:{document:'A',page:2,workspace:'w'}}},readingRequestCurrent:(snapshot,current)=>snapshot.document===current.document&&snapshot.page===current.page,readingCurrentPage:()=>({document:'A',page:3})},reading,'readingPopoverCurrent');
 assert.equal(c.readingPopoverCurrent(),false);c.readingCurrentPage=()=>({document:'A',page:2});assert.equal(c.readingPopoverCurrent(),true);
 visible=false;assert.equal(c.readingPopoverCurrent(),false,'A hidden reader refuses the selection bar');visible=true;
 c.state.workspace='v';assert.equal(c.readingPopoverCurrent(),false,'Another workspace refuses the selection bar');c.state.workspace='w';
 c.readingModel.popover=null;assert.equal(c.readingPopoverCurrent(),false);}

// Resume ownership: a resume write queued for one view is dropped once another view owns the reading place.
{let gate=null;const c=load({readingModel:{ownerKey:'',resumeOwner:0},KoshReading:{mutate:(route,body,shouldSend)=>{gate=shouldSend;return Promise.resolve();}}},reading,'readingSyncOwner','readingWriteResume');
 c.readingSyncOwner('w:read');const owner=c.readingModel.resumeOwner;c.readingWriteResume({},owner);assert.equal(gate(),true);
 c.readingSyncOwner('w:read');assert.equal(gate(),true,'Repainting the same view keeps ownership');
 c.readingSyncOwner('w:split');assert.equal(gate(),false,'Write beside a source owns the place now');}

// Chrome: one Add menu, Search opens the palette, layout lives in Settings.
assert.ok(html.includes('id="add-menu"')&&!html.includes('id="import-button"'));assert.ok(html.includes('data-action="palette"'));assert.ok(/<dialog id="settings-dialog"[\s\S]*id="design-select"/.test(html));
console.log('rc.5 UI contract checks passed');

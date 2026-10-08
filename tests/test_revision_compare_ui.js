'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const initial={console,document:{querySelector(){return null;}},setTimeout};
vm.createContext(initial);vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/revisions.js'),'utf8'),initial);
const api=vm.runInContext('KoshRevisions',initial);
const compact=result=>Array.from(result.rows,row=>[row.kind,row.left?.number??null,row.left?.text??null,row.right?.number??null,row.right?.text??null]);
let result=api.diff('A\nB\nA\n','A\nA\nB\n');
assert.deepEqual(compact(result),[['same',1,'A\n',1,'A\n'],['delete',2,'B\n',null,null],['same',3,'A\n',2,'A\n'],['add',null,null,3,'B\n']]);
assert.equal(result.removed,1);assert.equal(result.added,1);assert.equal(result.blocks.length,2);
result=api.diff('First\nOld one\nOld two\nLast','First\nNew one\nLast');
assert.deepEqual(compact(result),[['same',1,'First\n',1,'First\n'],['change',2,'Old one\n',2,'New one\n'],['delete',3,'Old two\n',null,null],['same',4,'Last',3,'Last']]);
assert.equal(result.blocks.length,1);assert.equal(result.removed,2);assert.equal(result.added,1);
const old='🟦 Widgets\r\n[[source:abc:2]]\n<img src=x onerror=alert(1)>\nlast';
const newer='🟦 Widgets\r\n[[source:abc:3]]\n<img src=x onerror=alert(1)>\nlast\n';
result=api.diff(old,newer);
assert.equal(Array.from(result.rows,row=>row.left?.text||'').join(''),old);
assert.equal(Array.from(result.rows,row=>row.right?.text||'').join(''),newer);
assert.equal(result.blocks.length,2,'Citation locator and final newline remain distinct exact changes');
assert.equal(result.rows[2].kind,'same');
assert.equal(api.lineEnding('a\r\n'),'CRLF');assert.equal(api.lineEnding('\n'),'LF');assert.equal(api.lineEnding('last'),'No newline');
assert.deepEqual(compact(api.diff('','')),[]);assert.equal(api.diff('','\n').added,1);
assert.equal(api.diff('same\n','same\n').blocks.length,0);
result=api.diff('a\nb\nc\n','x\ny\nz\n',{maxCells:1});
assert.equal(result.coarse,true);assert.equal(result.blocks.length,1);assert.equal(result.removed,3);assert.equal(result.added,3);
assert.equal(Array.from(result.rows,row=>row.left?.text||'').join(''),'a\nb\nc\n');
const largeLeft='a\n'.repeat(20000),largeRight='b\n'.repeat(20000);const began=Date.now();result=api.diff(largeLeft,largeRight);
assert.equal(result.coarse,true);assert.equal(result.rows.length,20000);assert.equal(result.blocks.length,1);assert(Date.now()-began<3000,'Bounded fallback should not run an unbounded edit matrix');
const comparison=api.compare({title:'Old title',body:'same\n'},{title:'New title',body:'same\n'});
assert.equal(comparison.titleChanged,true);assert.equal(comparison.blocks.length,1);assert.equal(comparison.blocks[0].id,'revision-title-block');
console.log('Revision comparison: repeated-line alignment, uneven replacement, Unicode/markers/HTML, exact newlines, title changes and bounded full-text fallback passed.');

const registry=new Map(),created=[];
let context;
class Element{
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.disabled=false;this.hidden=false;this.open=false;this.value='';this.className='';this._text='';this.parentElement=null;this.attributes={};this.classList={toggle:()=>{}};created.push(this);}
 set id(value){this._id=value;registry.set(value,this);}get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];}get textContent(){return this._text+this.children.map(child=>typeof child==='string'?child:child.textContent).join('');}
 set innerHTML(value){throw new Error('Revision UI must not use raw HTML: '+value);}
 append(...children){for(const child of children){this.children.push(child);if(typeof child!=='string')child.parentElement=this;}}
 replaceChildren(...children){const remove=child=>{if(typeof child==='string')return;for(const nested of child.children)remove(nested);if(child.id&&registry.get(child.id)===child)registry.delete(child.id);child.parentElement=null;};for(const child of this.children)remove(child);this.children=[];this._text='';this.append(...children);}
 addEventListener(name,fn){this.listeners[name]=fn;}setAttribute(name,value){this.attributes[name]=value;}
 focus(){if(!this.disabled)context.document.activeElement=this;}
 showModal(){this.open=true;}close(){this.open=false;this.listeners.close?.({});}
 get isConnected(){return !!this.parentElement||this===context.document.body;}
 scrollIntoView(){this.scrolled=true;}
}
const data={1:{title:'First saved title',body:'Widgets.\nFirst sentence.\n'},2:{title:'Old saved title',body:'Widgets.\nOld sentence.\n[[source:abc:1]]\n'},3:{title:'Current <title>',body:'Widgets.\nNew sentence.\n[[source:abc:2]]\n<img src=x onerror=alert(1)>'}};
let editor={id:'n',workspace_id:'w',title:data[3].title,body:data[3].body,version:3,revision:2,dirty:false,conflict:false},flush=true,flushCalls=0,requests=[],behavior=null;
context={console,setTimeout,Uint32Array,document:{createElement:tag=>new Element(tag),querySelector:selector=>selector==='[data-action="note-compare"]'?registry.get('replacement-toolbar')||null:selector.startsWith('#')?registry.get(selector.slice(1))||null:null},state:{workspace:'w',note:'n'},activeEditor:()=>editor,flushEdits:async()=>{flushCalls++;return flush;}};
context.document.body=new Element('body');const trigger=new Element('button');context.document.body.append(trigger);context.document.activeElement=trigger;
function response(note,workspace,current,versions,withBody=false,next=null){return {note_id:note,workspace_id:workspace,current_version:current,revisions:versions.map(version=>({id:note,title:data[version].title,version,created_at:'2026-10-08T00:00:00Z',...(withBody?{body:data[version].body}:{})})),next_before:next};}
context.request=async route=>{requests.push(route);const query=new URL('http://fixture'+route).searchParams;if(behavior)return behavior(query);const id=query.get('id'),workspace=query.get('workspace_id'),current=Number(query.get('expected_version'));if(query.get('metadata_only'))return query.has('before')?response(id,workspace,current,[1],false,null):response(id,workspace,current,[3,2],false,2);return response(id,workspace,current,[Number(query.get('version'))],true);};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/revisions.js'),'utf8'),context);
const mounted=vm.runInContext('KoshRevisions',context),get=id=>registry.get(id),settle=async()=>{for(let index=0;index<8;index++)await Promise.resolve();};
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
(async()=>{
 await mounted.open();assert.equal(flushCalls,1);assert.equal(get('revision-from').value,'2');assert.equal(get('revision-to').value,'3');assert.equal(context.document.activeElement,get('revision-from'));assert.match(get('revision-right-heading').textContent,/Saved current/);assert.match(get('revision-left-heading').textContent,/Past save/);
 assert(requests.every(route=>route.includes('workspace_id=w')&&route.includes('expected_version=3')));assert.equal(requests.filter(route=>route.includes('metadata_only=1')).length,1);assert.equal(requests.filter(route=>route.includes('&version=')).length,2);
 assert.equal(created.some(element=>element.tagName==='IMG'),false);assert(created.some(element=>element.tagName==='PRE'&&element.textContent.includes('<img src=x onerror=alert(1)>')));
 assert.equal(editor.body,data[3].body);await get('revision-next-change').listeners.click();assert.match(get('revision-navigation-status').textContent,/Change 1 of 2.*saved title/);await get('revision-next-change').listeners.click();assert.match(get('revision-navigation-status').textContent,/Change 2 of 2.*body lines/);await get('revision-prev-change').listeners.click();assert.match(get('revision-navigation-status').textContent,/Change 1 of 2/);
 const beforeBodies=requests.filter(route=>route.includes('&version=')).length;await get('revision-load-earlier').listeners.click();assert.equal(get('revision-from').children.length,3);assert.equal(get('revision-from').value,'2');assert.equal(requests.filter(route=>route.includes('&version=')).length,beforeBodies,'Loading earlier labels does not fetch manuscript bodies');assert.equal(get('revision-load-earlier').hidden,true);
 get('revision-from').value='1';await get('revision-from').listeners.change();assert.match(get('revision-left-heading').textContent,/From version 1/);
 const beforeConflict=requests.length,flushBefore=flushCalls;editor.conflict=true;await mounted.open();assert.equal(requests.length,beforeConflict);assert.equal(flushCalls,flushBefore);assert.match(get('revision-status').textContent,/Resolve this draft conflict/);assert.equal(editor.conflict,true);assert.equal(editor.body,data[3].body);editor.conflict=false;flush=false;await mounted.open();assert.equal(requests.length,beforeConflict);assert.match(get('revision-status').textContent,/could not be saved/);flush=true;
 // A single saved version must load its exact body once, with no fabricated history.
 editor={...editor,title:data[1].title,body:data[1].body,version:1};behavior=query=>response('n','w',1,[1],!query.has('metadata_only'));
 const singleBefore=requests.length;await mounted.open();assert.match(get('revision-status').textContent,/Only Saved current/);assert.equal(requests.slice(singleBefore).filter(route=>route.includes('&version=')).length,1,'The same saved version is fetched once');assert.equal(get('revision-next-change').disabled,true);
 const firstBody=data[1].body;data[1].body='';editor.body='';await mounted.open();assert.equal(get('revision-pages').children[0].textContent,'No body rows','Empty saved writing must not display an invented Rows 1–0 range');data[1].body=firstBody;
 // Malformed current-body responses must produce an error and focus its message.
 editor={...editor,title:data[3].title,body:data[3].body,version:3};behavior=query=>query.has('metadata_only')?response('n','w',3,[3,2]):response('wrong-note','w',3,[Number(query.get('version'))],true);
 await mounted.open();assert.match(get('revision-status').textContent,/does not match this draft/);assert.equal(get('revision-rows').children.length,0);assert.equal(context.document.activeElement.id,'revision-status','Load errors retain focus on their explanation');
 // Superseded requests cannot render into a newer workspace comparison.
 const oldMetadata=deferred();let first=true;behavior=query=>{if(first&&query.has('metadata_only')){first=false;return oldMetadata.promise;}return response(query.get('id'),query.get('workspace_id'),3,query.has('metadata_only')?[3,2]:[Number(query.get('version'))],!query.has('metadata_only'));};
 const oldOpen=mounted.open();await settle();context.state.workspace='other';context.state.note='other-note';editor={...editor,id:'other-note',workspace_id:'other'};await mounted.open();const latest=get('revision-scope').textContent;oldMetadata.resolve(response('n','w',3,[3,2]));await oldOpen;assert.equal(get('revision-scope').textContent,latest);assert.match(get('revision-right-heading').textContent,/Saved current/);
 // Closing while metadata is loading cancels presentation, preserves text and returns focus.
 const pendingMetadata=deferred();behavior=()=>pendingMetadata.promise;get('revision-compare-dialog').close();context.document.activeElement=trigger;const closing=mounted.open();await settle();get('revision-compare-dialog').listeners.cancel({preventDefault(){throw new Error('Read-only comparison should allow Escape');}});get('revision-compare-dialog').close();pendingMetadata.resolve(response('other-note','other',3,[3,2]));await closing;assert.equal(get('revision-compare-dialog').open,false);assert.equal(context.document.activeElement,trigger);assert.equal(editor.body,data[3].body);
 // Large bodies are fully represented in bounded row pages, with visible coarse alignment.
 context.state.workspace='w';context.state.note='n';data[2].body='a\n'.repeat(2000);data[3].body='b\n'.repeat(2000);editor={...editor,id:'n',workspace_id:'w',title:data[3].title,body:data[3].body};behavior=query=>response('n','w',3,query.has('metadata_only')?[3,2]:[Number(query.get('version'))],!query.has('metadata_only'));
 await mounted.open();assert.match(get('revision-warning').textContent,/Coarse alignment/);assert.equal(get('revision-rows').children.length,200);assert.match(get('revision-page-status').textContent,/Rows 1–200 of 2000/);get('revision-pages').value='9';await get('revision-pages').listeners.change();assert.equal(get('revision-rows').children.length,200);assert.match(get('revision-page-status').textContent,/Rows 1801–2000 of 2000/);assert.equal(get('revision-next-page').disabled,true);
 editor.dirty=true;await get('revision-next-change').listeners.click();assert.match(get('revision-status').textContent,/draft or workspace changed/);assert.equal(get('revision-rows').children.length,0);assert.equal(editor.dirty,true);
 const replacement=new Element('button');replacement.id='replacement-toolbar';context.document.body.append(replacement);trigger.parentElement=null;get('revision-compare-dialog').close();assert.equal(context.document.activeElement.id,'replacement-toolbar','Close restores focus to the actual replacement note-compare toolbar control');
 console.log('Revision lifecycle: pinned paged metadata/exact bodies, source-safe DOM, saved labels, conflicts, errors, scope/close races, navigation and full-text pagination passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

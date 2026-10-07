'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const source = fs.readFileSync(require('node:path').join(__dirname,'../ui/app.js'),'utf8');
const start=source.indexOf('function libraryDocuments('), end=source.indexOf('function renderLibrary(){',start);
assert.ok(start>=0 && end>start,'Library selection helper is required');
const context={AbortController};vm.createContext(context);
vm.runInContext('function sourceLabel(d){return d.metadata?.title||d.name;}\n'+source.slice(start,end),context);
const docs=[
 {id:'c',workspace_id:'one',name:'older.pdf',kind:'pdf',created_at:'2026-01-01',metadata:{title:'Zebra',authors:'Ada North',year:'2020',doi:'10.1234/ONE'}},
 {id:'a',workspace_id:'one',name:'notes.md',kind:'md',created_at:'2026-01-03',metadata:{title:'Álpha',author_list:[{family:'Smith',given:'Jo'}],year:'unknown'}},
 {id:'b',workspace_id:'one',name:'newer.pdf',kind:'pdf',created_at:'2026-01-02',metadata:{title:'Beta',year:'2024'}},
 {id:'d',workspace_id:'one',name:'old.txt',kind:'txt',archived:1,created_at:'2026-01-04',metadata:{year:'2025'}},
 {id:'e',workspace_id:'two',name:'foreign.pdf',kind:'pdf',created_at:'2026-01-05',metadata:{title:'Beta',year:'2026'}},
 {id:'f',workspace_id:'one',name:'missing.pdf',kind:'pdf',created_at:'2026-01-01',metadata:{title:'Beta',year:''}},
];
const options={workspace:'one',archived:false,query:'',kind:'all',sort:'imported'};
const select=(extra={})=>Array.from(context.libraryDocuments(docs,{...options,...extra}),d=>d.id);
assert.deepEqual(select(),['a','b','f','c']);
assert.deepEqual(select({query:'ADA 2020'}),['c']);
assert.deepEqual(select({query:'alpha smith'}),['a']);
assert.deepEqual(select({query:'10.1234/one'}),['c']);
assert.deepEqual(select({query:'notes.md',kind:'pdf'}),[]);
assert.deepEqual(select({sort:'year'}),['b','c','a','f']);
assert.deepEqual(select({sort:'title'}),['a','f','b','c']); // missing.pdf precedes newer.pdf for equal titles.
assert.deepEqual(select({archived:true}),['d']);
assert.deepEqual(select({kind:'pdf',query:'beta'}),['b','f']);
assert.deepEqual(docs.map(d=>d.id),['c','a','b','d','e','f'],'Sorting must not mutate state');
assert.deepEqual(select({query:'<script>'}),[]);
console.log('Library selection: 11 assertions passed');
const indic=[{id:'h',workspace_id:'one',name:'a.txt',kind:'txt',metadata:{title:'काम'}},{id:'p',workspace_id:'one',name:'b.txt',kind:'txt',metadata:{title:'ਕਾਮ'}}];
assert.equal(context.libraryDocuments(indic,{...options,query:'कम'}).length,0);
assert.equal(context.libraryDocuments(indic,{...options,query:'ਕਮ'}).length,0);
assert.equal(context.libraryDocuments(indic,{...options,query:'काम'}).length,1);
context.libraryBrowse={workspace:'one',query:'',kind:'all',sequence:0};
context.state={workspace:'one',view:'library',search:'',searchResults:null,archived:false};
context.renderLibraryResults=()=>{};
const pending=[];context.request=()=>new Promise((resolve,reject)=>pending.push({resolve,reject}));
(async()=>{
 let run=context.searchLibraryPassages('first');context.clearLibrarySearch();pending.shift().resolve({results:['obsolete']});await run;assert.equal(context.state.searchResults,null);
 const first=context.searchLibraryPassages('same'),second=context.searchLibraryPassages('same');pending[1].resolve({results:['new']});await second;pending[0].resolve({results:['old']});await first;pending.length=0;assert.deepEqual(context.state.searchResults,['new']);
 run=context.searchLibraryPassages('failure');assert.equal(context.state.searchResults,null);pending.shift().reject(new Error('Unavailable'));await run;assert.equal(context.libraryBrowse.error,'Unavailable');assert.equal(context.libraryBrowse.busy,false);
 run=context.searchLibraryPassages('archived');context.state.archived=true;context.clearLibrarySearch();pending.shift().resolve({results:['old']});await run;assert.equal(context.state.searchResults,null);context.state.archived=false;
 run=context.searchLibraryPassages('workspace');context.state.workspace='two';context.resetLibraryWorkspace();context.state.workspace='one';context.resetLibraryWorkspace();pending.shift().resolve({results:['old']});await run;assert.equal(context.state.searchResults,null);
 context.libraryBrowse.query='filter';context.resetLibraryWorkspace();assert.equal(context.libraryBrowse.query,'filter');context.state.workspace='two';context.resetLibraryWorkspace();assert.equal(context.libraryBrowse.query,'');
 console.log('Passage search: clear, same-query race, errors, archive, workspace round-trip and reset passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

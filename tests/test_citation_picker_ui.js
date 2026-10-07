'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const source=fs.readFileSync(require('node:path').join(__dirname,'../ui/app.js'),'utf8');
const start=source.indexOf('function citationCandidates('),end=source.indexOf('function updateWriterMetrics(',start);
assert.ok(start>=0&&end>start,'Citation picker helpers must exist');
const context={};vm.createContext(context);
vm.runInContext(source.slice(start,end),context);
const a='a'.repeat(32),b='b'.repeat(32),c='c'.repeat(32),d='d'.repeat(32),e='e'.repeat(32);
const docs=[
 {id:a,workspace_id:'one',kind:'pdf',pages:3,name:'first.pdf',metadata:{title:'Álpha guide',authors:'Ada North',year:'2024',doi:'10.1000/alpha'}},
 {id:b,workspace_id:'one',kind:'ris',pages:1,name:'record.ris',metadata:{title:'Beta reference',catalogue_source:'Imported metadata'}},
 {id:c,workspace_id:'one',kind:'txt',pages:2,archived:1,name:'archive.txt',metadata:{title:'Archived guide'}},
 {id:d,workspace_id:'two',kind:'pdf',pages:5,name:'private.pdf',metadata:{title:'Other workspace'}},
 {id:e,workspace_id:'one',kind:'png',pages:1,name:'figure.png',metadata:{title:'Picture'}},
];
context.noteSearchText=value=>String(value??'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
context.sourceLabel=doc=>doc.metadata?.title||doc.name;
const original=JSON.stringify(docs);
assert.deepEqual(Array.from(context.citationCandidates(docs,'one','alpha north 2024',false),x=>x.id),[a]);
assert.deepEqual(Array.from(context.citationCandidates(docs,'one','',false),x=>x.id),[a,b]);
assert.equal(context.citationCandidates(docs,'one','',true).length,3);
assert.equal(JSON.stringify(docs),original);
assert.equal(context.citationMarker(docs[0],'reference','', 'one'),'[[reference:'+a+']]');
assert.equal(context.citationMarker(docs[0],'source','2','one'),'[[source:'+a+':2]]');
assert.equal(context.citationMarker(docs[2],'source','2','one'),'[[source:'+c+':2]]');
for(const page of ['0','4','1.5','-1','abc',''])assert.throws(()=>context.citationMarker(docs[0],'source',page,'one'));
assert.throws(()=>context.citationMarker(docs[1],'source','1','one'),'Catalogue metadata cannot claim a paper page');
assert.throws(()=>context.citationMarker(docs[3],'reference','','one'));
assert.throws(()=>context.citationMarker(docs[4],'reference','','one'));
const editor={id:'note',workspace_id:'one',body:'Keep these words',revision:1};
const target={note:'note',workspace:'one',body:editor.body,revision:1,end:4};
assert.equal(context.citationInsertionPoint(target,editor),4,'Insert after selection, preserving selected words');
assert.throws(()=>context.citationInsertionPoint(target,{...editor,revision:2}));
assert.throws(()=>context.citationInsertionPoint(target,{...editor,id:'different'}));
assert.throws(()=>context.citationInsertionPoint(target,{...editor,conflict:true}));
const body='[[reference:'+b+']] and [[source:'+a+':2]] then [[reference:'+b+']]\n`[[reference:'+a+']]`\n```md\n[[reference:'+a+']]\n```\n[[source:'+a+':9]]\n[[reference:'+d+']]';
const refs=context.draftCitationEntries(body,docs,'one');
assert.equal(refs.length,4);assert.equal(refs[0].count,2);assert.equal(refs[0].valid,true);assert.equal(refs[1].page,2);assert.equal(refs[2].valid,false);assert.equal(refs[3].valid,false);
const markdownStart=source.indexOf('function markdown('),markdownEnd=source.indexOf('function markEditorDirty(',markdownStart);
context.escapeHTML=text=>text.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
context.state={data:{documents:docs},workspace:'one',view:'library'};
context.pageUnit=()=> 'file page';
vm.runInContext(source.slice(markdownStart,markdownEnd),context);
assert.ok(!context.markdown('[[source:'+a+':9]]').includes('data-source-ref'),'Fallback must leave citation resolution to the validator');
assert.ok(context.markdown('`[[source:'+a+':2]]`').includes('<code>[[source:'),'Code-contained markers stay literal');
let inserted=false;const pickerError={textContent:''};
context.$=()=>pickerError;context.activeEditor=()=>editor;context.citationPicker={target,selected:a};context.insertWriterText=()=>{inserted=true;};
context.insertPickedCitation();assert.equal(inserted,false);assert.match(pickerError.textContent,/Write/);
const keyStart=source.indexOf("document.addEventListener('keydown',async event=>"),keyEnd=source.indexOf("window.addEventListener('beforeunload'",keyStart);
let shortcutHandler,navigated=false,prevented=false;
context.document={addEventListener:(_name,handler)=>{shortcutHandler=handler;}};context.setView=async()=>{navigated=true;};context.$=selector=>selector==='dialog[open]'?{}:null;
vm.runInContext(source.slice(keyStart,keyEnd),context);
shortcutHandler({ctrlKey:true,key:'k',preventDefault(){prevented=true;}}).then(()=>{assert.equal(navigated,false);assert.equal(prevented,true);console.log('Citation picker: scope, locators, target, preview and modal shortcut checks passed');}).catch(error=>{console.error(error);process.exitCode=1;});

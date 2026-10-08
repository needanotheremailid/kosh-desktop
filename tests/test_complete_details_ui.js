'use strict';
// Missing-detail completion, export warning and import guidance logic from ui/app.js, with invented records only.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../ui/app.js'),'utf8');
const slice=(from,to)=>{const start=app.indexOf(from),end=app.indexOf(to,start);assert.ok(start>=0&&end>start,'Missing '+from);return app.slice(start,end);};
const source=slice('function bibliographyMissing(','async function exportMetadataWarning(')+slice('function receiptGuidance(','\nfunction showReceipt(');
const calls=[],notices=[],storage=new Map();let statusHTML='';
const context={console,Math,String,Array,Set,Map,JSON,Number,
 CSS:{escape:value=>value},
 escapeHTML:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
 sourceLabel:doc=>doc.metadata?.title||doc.name,
 notify:(message,error)=>notices.push({message,error}),
 render(){},refresh:async()=>{},renderComplete(){},
 localStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value)},
 state:{workspace:'w',data:{documents:[]}}};
vm.createContext(context);vm.runInContext(source,context);
const completeState=vm.runInContext('completeState',context);

// The JavaScript copy matches backend.bibliography_missing.
assert.deepEqual(Array.from(context.bibliographyMissing({})),['title','authors','year','doi']);
assert.deepEqual(Array.from(context.bibliographyMissing({title:'T',author_list:[{family:'Ng',given:'A'}],year:'2020',doi:'10.1/x'})),[]);
assert.deepEqual(Array.from(context.bibliographyMissing({title:'T',authors:'A',year:'1',doi:'d',type:'journal_article',journal_abbreviation:'J'})),['volume','pages']);
assert.equal(context.completeText('author_list',[{family:'Ng',given:'A'},{literal:'Invented Group'}]),'Ng, A; Invented Group');

// Saving copies only ticked fields, keeps the expected version and bounds provenance.
const doc={id:'d1',workspace_id:'w',name:'lantern.pdf',metadata_version:3,metadata:{title:'Kept title',doi:'10.1234/lantern.42',provenance:'p'.repeat(990)}};
context.state.data.documents=[doc];
const box=(field,checked)=>({dataset:{completeField:field},checked});
const section={boxes:[box('title',false),box('author_list',true),box('year',true)]};
context.$=selector=>selector.startsWith('[data-complete-item=')?section:selector==='#export-download-status'?{insertAdjacentHTML:(where,html)=>{statusHTML+=html;}}:null;
context.$$=(selector,root)=>root.boxes;
context.request=async(route,body,options)=>{calls.push({route,body,options});return {};};
completeState.items=[{id:'d1',row:{title:'Catalogue title',author_list:[{family:'Ng',given:'A',extra:'dropped'}],year:'2020'},retrieved:'2026-10-08T12:00:00Z',error:'',saved:''}];
(async()=>{
 await context.completeSave('d1');
 assert.equal(calls.length,1);assert.equal(calls[0].route,'/metadata');assert.equal(calls[0].body.expected_metadata_version,3);assert.equal(calls[0].options?.raw,true,'Reviewed metadata bypasses the Source details form injection');
 const saved=calls[0].body.metadata;
 assert.equal(saved.title,'Kept title','Unticked existing values are never replaced');
 assert.deepEqual(JSON.parse(JSON.stringify(saved.author_list)),[{family:'Ng',given:'A'}],'Only accepted author keys are sent');
 assert.equal(saved.year,'2020');
 assert.ok(saved.provenance.length<=1000,'Provenance stays within the saved bound');
 assert.ok(saved.provenance.endsWith('author_list, year. Check against the publication.'),'The reviewed fields are recorded');
 assert.ok(saved.provenance.includes('10.1234/lantern.42'));
 assert.match(completeState.items[0].saved,/Saved 2 fields/);
 section.boxes=[box('year',false)];calls.length=0;
 await context.completeSave('d1');assert.equal(calls.length,0,'Nothing is saved without a ticked field');

 // Export warnings deduplicate sources and offer completion.
 context.warnIncompleteReferences([{document_id:'d1',name:'lantern.pdf'},{document_id:'d1',name:'lantern.pdf'},{document_id:'d2',name:'<b>other.pdf'}],'workspace export');
 assert.match(statusHTML,/2 cited sources have missing bibliography fields/);
 assert.match(statusHTML,/data-complete-ids="d1,d2"/);
 assert.ok(statusHTML.includes('&lt;b&gt;other.pdf')&&!statusHTML.includes('<b>other'),'Names are escaped');
 assert.equal(notices.at(-1).error,true);
 statusHTML='';context.warnIncompleteReferences([],'export');assert.equal(statusHTML,'','No warning without missing sources');

 // Import guidance points to Source details once per incomplete import, with first-use explanation only the first time.
 const receipts=[{status:'ready',document:{id:'p1',kind:'pdf',name:'<i>scan.pdf',metadata:{}}},{status:'ready',document:{id:'f1',kind:'png',name:'figure.png',metadata:{}}},{status:'duplicate',document:{id:'p2',kind:'pdf',name:'old.pdf',metadata:{}}}];
 const first=context.receiptGuidance(receipts);
 assert.match(first,/Kosh cites exactly what is saved/);assert.match(first,/1 imported source is missing citation fields/);
 assert.match(first,/data-receipt-details="p1"/);assert.ok(first.includes('&lt;i&gt;scan.pdf'));
 const second=context.receiptGuidance(receipts);
 assert.ok(!second.includes('Kosh cites exactly')&&second.includes('missing citation fields'),'First-use explanation appears once');
 assert.equal(context.receiptGuidance([{status:'ready',document:{id:'c',kind:'pdf',name:'c.pdf',metadata:{title:'T',authors:'A',year:'1',doi:'d'}}}]),'','Complete sources need no guidance');
 console.log('Complete details UI: parity, reviewed-field save, version and provenance bounds, export warning and import guidance passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

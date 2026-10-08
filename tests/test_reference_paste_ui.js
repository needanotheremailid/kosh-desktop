'use strict';
// Pasted reference lists, PMID completion choice and per-index pacing from ui/app.js, with invented identifiers only.
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const app=fs.readFileSync(path.join(__dirname,'../ui/app.js'),'utf8');
const line=start=>{const at=app.indexOf(start);assert.ok(at>=0,'Missing '+start);return app.slice(at,app.indexOf('\n',at));};
const slice=(from,to)=>{const start=app.indexOf(from),end=app.indexOf(to,start);assert.ok(start>=0&&end>start,'Missing '+from);return app.slice(start,end);};
const source=line('const discovery=')+'\n'+line('function publicationIdentifier(')+'\n'+slice('function bibliographyMissing(','function warnIncompleteReferences(');
const elements={'#paste-text':{value:''},'#paste-preview':{innerHTML:''},'#lookup-dialog':{close(){}}},notices=[];
const context={console,Math,String,Array,Set,Map,JSON,Number,Promise,setTimeout,performance,
 CSS:{escape:value=>value},
 escapeHTML:value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),
 $:selector=>elements[selector]||null,$$:()=>[],notify:(message,error)=>notices.push({message,error}),
 render(){},renderDiscovery(){},refresh:async()=>{},sourceLabel:doc=>doc.name,
 state:{workspace:'w',view:'library',data:{documents:[{id:'old',workspace_id:'w',name:'old.pdf',metadata:{doi:'10.5555/OLD.1'}},{id:'arch',workspace_id:'w',archived:true,name:'arch.pdf',metadata:{pmid:'777'}},{id:'other',workspace_id:'x',name:'x.pdf',metadata:{doi:'10.5555/other.9'}}]}}};
vm.createContext(context);vm.runInContext(source,context);
const get=name=>vm.runInContext(name,context),ids=text=>Array.from(context.referenceIdentifiers(text),id=>id.identifier_type+' '+id.identifier);

// Parsing finds explicit identifiers only and keeps DOI parentheses balanced.
assert.deepEqual(ids('1. Ng A. Invented trial. 2020;383(5):1-10. doi:10.5555/Lantern.2020.1.\n2. Old (doi: 10.5555/(SICI)1097-0258(1998)17:8). PMID: 9595616\n3. https://doi.org/10.5555/harbour.7)\n4. pubmed.ncbi.nlm.nih.gov/31234567/\n  27654321  \n2015\nPages 436-444, 1998\n5. again 10.5555/lantern.2020.1'),
 ['doi 10.5555/Lantern.2020.1','doi 10.5555/(SICI)1097-0258(1998)17:8','doi 10.5555/harbour.7','pmid 9595616','pmid 31234567','pmid 27654321','pmid 2015']);
assert.deepEqual(ids('Smith 2019; 12(3): 45-67. Vol 2015.'),[],'Numbers inside reference text are never PMIDs');

// Completion prefers a saved DOI, falls back to a valid PMID, and refuses malformed identifiers without sending.
assert.equal(context.completeSource({doi:'10.5555/a.1',pmid:'12'}).identifier.provider,'crossref');
assert.deepEqual(JSON.parse(JSON.stringify(context.completeSource({pmid:' 4242 '}).identifier)),{provider:'pubmed',identifier:'4242',identifier_type:'pmid'});
assert.equal(context.completeSource({pmid:'PMC12'}).identifier,null);
assert.equal(context.completeSource({doi:'12345'}).identifier,null,'A number in the DOI field is not sent to PubMed');
assert.equal(context.completeSource({}),null);
assert.ok(context.sameDoi('https://doi.org/10.5555/ABC','doi:10.5555/abc'));
assert.ok(!context.sameDoi('','')&&!context.sameDoi('10.5555/a','10.5555/b'));

(async()=>{
 // One queue per index: starts are at least a second apart, other indexes are not delayed, and a declined send is skipped.
 const starts=[];context.request=async(route,body)=>{starts.push({provider:body.provider||body.identifier_type,at:performance.now()});return {results:[]};};
 await Promise.all([context.pacedRequest('crossref','/literature/lookup',{provider:'crossref'}),context.pacedRequest('crossref','/literature/lookup',{provider:'crossref'}),context.pacedRequest('pubmed','/literature/lookup',{provider:'pubmed'})]);
 const crossref=starts.filter(s=>s.provider==='crossref');assert.ok(crossref[1].at-crossref[0].at>=1050,'Crossref requests are spaced');
 assert.ok(starts.find(s=>s.provider==='pubmed').at-crossref[0].at<500,'PubMed is not held behind Crossref');
 // An all-index search holds every index queue until it has finished.
 starts.length=0;let finishAll;context.request=async(route,body)=>{starts.push({provider:body.provider,at:performance.now()});if(body.provider==='all')await new Promise(resolve=>{finishAll=resolve;});return {results:[]};};
 const all=context.pacedRequest('all','/literature/search',{provider:'all'}),after=context.pacedRequest('pubmed','/literature/lookup',{provider:'pubmed'});
 await new Promise(resolve=>setTimeout(resolve,1300));assert.deepEqual(starts.map(s=>s.provider),['all'],'PubMed waits while the combined search runs');
 const finished=performance.now();finishAll();await Promise.all([all,after]);assert.ok(starts[1].at-finished>=1050,'PubMed starts a second after the combined search finishes');
 context.request=async(route,body)=>{starts.push({provider:body.provider,at:performance.now()});return {results:[]};};
 starts.length=0;assert.equal(await context.pacedRequest('pubmed','/literature/lookup',{provider:'pubmed'},()=>false),null);assert.equal(starts.length,0,'Stop is honoured before sending');

 // Find previews locally and skips identifiers already in the workspace, archived ones included.
 elements['#paste-text'].value='10.5555/old.1\nPMID: 777\n10.5555/other.9\nPMID: 4242\n10.5555/new.2\nPMID 5151';
 context.pasteFind();
 assert.match(elements['#paste-preview'].innerHTML,/Found 3 DOIs and 3 PMIDs\. 2 already in this workspace will not be sent\./);
 assert.match(elements['#paste-preview'].innerHTML,/data-paste-lookup>Look up 4</);
 assert.deepEqual(Array.from(get('pastePending').queue,id=>id.identifier),['10.5555/other.9','10.5555/new.2','4242','5151'],'DOIs are listed before PMIDs');

 // Lookup collects records, collapses a PMID that resolves to an already listed DOI, and lists failures.
 const sent=[];context.pacedRequest=async(provider,route,body)=>{sent.push(body.identifier);if(body.identifier==='5151')throw new Error('The index returned HTTP 404. No library records were changed.');
  const rows={'10.5555/other.9':{doi:'10.5555/other.9',title:'Other'},'4242':{doi:'10.5555/NEW.2',pmid:'4242',title:'New via PubMed'},'10.5555/new.2':{doi:'10.5555/new.2',title:'New via Crossref'}};
  return {retrieved_at:'2026-10-08T00:00:00Z',results:[{...rows[body.identifier],result_id:'r-'+body.identifier}]};};
 await context.pasteLookup();
 const discovery=get('discovery');
 assert.deepEqual(sent,['10.5555/other.9','10.5555/new.2','4242','5151']);
 assert.deepEqual(Array.from(discovery.result.results,r=>r.title),['Other','New via Crossref']);
 assert.equal(discovery.paste.duplicates,1);assert.equal(discovery.paste.failures.length,1);assert.equal(discovery.paste.done,4);
 assert.ok(discovery.paste.finished&&!discovery.busy);assert.equal(get('pastePending'),null);
 assert.match(context.pastePanel(),/Looked up 4 of 4\..*1 result was a duplicate/);assert.match(context.pastePanel(),/1 not found or failed/);assert.match(context.pastePanel(),/Add all 2 listed references/);

 // Add all saves each listed record once, counts existing ones and reports failures.
 const saves=[];context.request=async(route,body)=>{saves.push(body.result_id);if(body.result_id==='r-10.5555/new.2')return {notice:'This reference (same DOI or PMID) is already in the workspace.'};return {notice:'Saved catalogue metadata only.'};};
 await context.pasteAddAll();
 assert.deepEqual(saves,['r-10.5555/other.9','r-10.5555/new.2']);assert.match(notices.at(-1).message,/Added 1 reference; 1 already in this workspace\./);
 saves.length=0;await context.pasteAddAll();assert.equal(saves.length,0,'Added records are not saved twice');
 assert.equal(context.pastePanel().includes('data-paste-add-all'),false);

 // A listed record already in the workspace is neither counted nor sent.
 context.state.data.documents.push({id:'k',workspace_id:'w',name:'k.pdf',metadata:{doi:'https://doi.org/10.5555/known.3'}});discovery.result.results.push({doi:'10.5555/KNOWN.3',title:'Known',result_id:'r-known'});
 assert.equal(context.pastePanel().includes('data-paste-add-all'),false);saves.length=0;await context.pasteAddAll();assert.equal(saves.length,0,'Known records are not sent to save');assert.match(notices.at(-1).message,/Added 0 references; 1 already in this workspace\./);

 // Stop ends a batch before the next send.
 elements['#paste-text'].value='PMID: 1001\nPMID: 1002\nPMID: 1003';context.pasteFind();sent.length=0;
 context.pacedRequest=async(provider,route,body,shouldSend)=>{if(!shouldSend())return null;sent.push(body.identifier);discovery.paste.stop=true;return {results:[{pmid:body.identifier,title:'T'+body.identifier,result_id:'s'+body.identifier}]};};
 await context.pasteLookup();assert.deepEqual(sent,['1001']);assert.match(context.pastePanel(),/Stopped after 1 of 3 lookups/);
 console.log('Reference paste UI: explicit parsing, PMID completion choice, per-index pacing, preview, duplicates, failures, add-all and stop passed');
})().catch(error=>{console.error(error);process.exitCode=1;});

'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
function element(){let html='',text='';return {open:false,listeners:{},dataset:{},get innerHTML(){return html;},set innerHTML(value){html=value;text='';},get textContent(){return text;},set textContent(value){text=value;html='';},insertAdjacentHTML(){},addEventListener(name,fn){this.listeners[name]=fn;},showModal(){this.open=true;},close(){this.open=false;},removeAttribute(){},focus(){this.focused=true;}};}
const elements=new Map();
for(const selector of ['#project-review-dialog','#project-review-content','#project-review-status','#project-review-close','#project-review-refresh','#project-review-responses','.more-menu .menu','.more-menu','#open-project-review','#open-reviewer-responses','#draft-body'])elements.set(selector,element());
let flush=true,conflicts=[],calls=0,fetchResult,reviewerOpened=0,renders=0;
const state={workspace:'w',note:'unchanged',view:'library',data:{notes:[{id:'n',workspace_id:'w',body:'Original widgets.'}]}};
const escapeHTML=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const context={console,state,escapeHTML,document:{body:{insertAdjacentHTML(){}},querySelector:s=>elements.get(s)||null},
 flushEdits:async()=>flush,conflictedEditors:()=>conflicts,notes:()=>state.data.notes.filter(note=>note.workspace_id===state.workspace),
 request:async route=>{calls++;return typeof fetchResult==='function'?fetchResult(route):fetchResult;},render:()=>renders++,KoshReviewer:{open:async()=>reviewerOpened++}};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../ui/project_review.js'),'utf8'),context);
const api=vm.runInContext('KoshProjectReview',context),dialog=elements.get('#project-review-dialog'),content=elements.get('#project-review-content'),status=elements.get('#project-review-status');
const report=(title='Widget project',failed=false)=>({workspace_id:'w',title,checked_at:'2026-10-08T00:00:00Z',notice:'Saved drafts only; not a readiness certification.',
 totals:{drafts:1,drafts_without_reviews:1,claims:0,needs_source:0,stale_claims:0,checked_claims:0,unresolved_references:failed?null:0,missing_metadata_sources:failed?null:0,failed_checks:failed?1:0},
 notes:[{id:'n',title:'Widget draft',version:1,claims:[],needs_source:0,stale_claims:0,check_status:failed?'failed':'checked',error:failed?'Retained source changed':'',unresolved_references:failed?null:[],missing_metadata:failed?null:[],mechanical_issues:failed?null:[]}]});
const settle=async()=>{await Promise.resolve();await Promise.resolve();};
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
(async()=>{
 fetchResult=report('Unknown checks',true);await api.open();assert.equal(dialog.open,true);assert.match(content.innerHTML,/Unknown/);assert.match(content.innerHTML,/Reference counts are unknown/);assert.match(content.innerHTML,/Check failed: Retained source changed/);assert.match(content.innerHTML,/not a readiness certification/);
 assert.match(status.textContent,/Some checks failed; affected totals are unknown/);
 assert.equal(state.data.notes[0].body,'Original widgets.');
 fetchResult=()=>Promise.reject(new Error('Local read failed'));await api.open();assert.match(content.textContent,/Review unavailable: Local read failed/);assert.equal(content.innerHTML,'','A request error removes earlier totals rather than presenting old counts as current');
 flush=false;const before=calls;await api.open();assert.equal(calls,before);assert.match(content.textContent,/Some edits could not be saved/);
 flush=true;conflicts=[{id:'n'}];await api.open();assert.equal(calls,before);assert.match(content.textContent,/Resolve draft conflicts/);conflicts=[];
 state.workspace=null;await api.open();assert.equal(calls,before);assert.match(content.textContent,/Create a workspace/);
 state.workspace='w';const older=deferred();fetchResult=()=>older.promise;const oldLoad=api.open();await settle();assert.match(status.textContent,/checking saved drafts/);assert.equal(content.innerHTML,'');
 state.workspace='other';fetchResult=report('Current other workspace');await api.open();assert.match(content.innerHTML,/Current other workspace/);older.resolve(report('Discarded old workspace'));await oldLoad;assert.match(content.innerHTML,/Current other workspace/);assert.doesNotMatch(content.innerHTML,/Discarded old workspace/);
 state.workspace='w';const stale=deferred();fetchResult=()=>stale.promise;const first=api.open();await settle();fetchResult=report('Latest same workspace');await api.open();stale.resolve(report('Obsolete same workspace'));await first;assert.match(content.innerHTML,/Latest same workspace/);assert.doesNotMatch(content.innerHTML,/Obsolete same workspace/);
 const closed=deferred();fetchResult=()=>closed.promise;const closing=api.open();await settle();dialog.close();closed.resolve(report('Closed-dialog response'));await closing;assert.doesNotMatch(content.innerHTML,/Closed-dialog response/);
 fetchResult=report('Navigation');await api.open();const click=content.listeners.click,target={dataset:{reviewNote:'n'}},event={target:{closest:()=>target}};
 state.workspace='other';await click(event);assert.equal(state.note,'unchanged');assert.equal(dialog.open,true);assert.match(content.textContent,/Workspace changed/);
 state.workspace='w';await api.open();flush=false;await click(event);assert.equal(state.note,'unchanged');assert.equal(dialog.open,true);
 flush=true;await click(event);assert.equal(dialog.open,false);assert.equal(state.note,'n');assert.equal(state.view,'write');assert.equal(renders,1);assert.equal(elements.get('#draft-body').focused,true);assert.equal(state.data.notes[0].body,'Original widgets.');
 await elements.get('#project-review-responses').onclick();assert.equal(reviewerOpened,1);assert.equal(dialog.open,false);
 console.log('Project review UI: unknown/error/unsaved/conflict states, late workspace and same-workspace responses, closed dialogs and scoped draft navigation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

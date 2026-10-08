'use strict';
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../ui/installation_health.js'),'utf8'),context={console,document:{querySelector(){return null;}}};vm.createContext(context);vm.runInContext(source,context);const api=vm.runInContext('KoshInstallationHealth',context);
const component=(requirement='required')=>({requirement,status:'available',origin:'bundled',code:'AVAILABLE'});
const report={schema_version:1,app:{version:'1.0.0',build:'a'.repeat(64)},os:{family:'Windows',version:'10.0.26300'},components:{python:component(),pdf:component(),docx:component(),csl:component(),tex:component('optional'),ocr:component('optional'),local_model:{requirement:'optional',status:'not_checked',origin:'none',code:'NO_MODEL_CONTACT'}},languages:{eng:component('optional'),hin:component('optional'),pan:component('optional')}};
const contaminated=JSON.parse(JSON.stringify(report));contaminated.paths=['C:\\private-user\\secret-data'];contaminated.username='private-user';contaminated.title='Private manuscript title';contaminated.counts={patients:42};contaminated.logs='secret-session-token';contaminated.components.pdf.raw_error='private-user library failed';contaminated.components.local_model.models=['private-model-name'];
const allowed=api.safeReport(contaminated),serialized=JSON.stringify(allowed);
assert.deepEqual(Object.keys(allowed).sort(),['app','components','languages','os','schema_version']);
for(const forbidden of ['private-user','secret-data','Private manuscript','patients','secret-session-token','private-model-name'])assert(!serialized.includes(forbidden));
assert.equal(Object.keys(allowed.components.pdf).length,4);assert.equal(allowed.components.local_model.status,'not_checked');assert.match(api.remedy('local_model',allowed.components.local_model),/not contacted/i);
const poisoned=JSON.parse(JSON.stringify(report));poisoned.components.pdf.code='C:\\private-user\\broken.dll';assert.throws(()=>api.safeReport(poisoned),/validated/i);
const badApp=JSON.parse(JSON.stringify(report));badApp.app.version='1.0.0_private-user';assert.throws(()=>api.safeReport(badApp),/validated/i);
const releaseCandidate=JSON.parse(JSON.stringify(report));releaseCandidate.app.version='1.0.0-rc.1';assert.equal(api.safeReport(releaseCandidate).app.version,'1.0.0-rc.1');releaseCandidate.app.version='1.0.0-rc.1+private-user';assert.throws(()=>api.safeReport(releaseCandidate),/validated/i);
console.log('Installation health diagnostics: exact positive allowlist removes canary path/user/title/count/log/model names; unsafe values rejected.');

const registry=new Map();let downloads=[],blobPayload=null;
class Element{
 constructor(tag){this.tagName=tag.toUpperCase();this.children=[];this.listeners={};this.dataset={};this.disabled=false;this.hidden=false;this.open=false;this.value='';this.className='';this._text='';this.parentElement=null;this.attributes={};this.classList={toggle(){}};}
 set id(value){this._id=value;registry.set(value,this);}get id(){return this._id;}
 set textContent(value){this._text=String(value);this.children=[];}get textContent(){return this._text+this.children.map(child=>child.textContent).join('');}
 set innerHTML(value){throw new Error('No raw HTML in installation health dialog');}
 append(...children){for(const child of children){this.children.push(child);child.parentElement=this;}}
 replaceChildren(...children){this.children=[];this._text='';this.append(...children);}
 addEventListener(name,fn){this.listeners[name]=fn;}setAttribute(name,value){this.attributes[name]=value;}
 focus(){if(!this.disabled)ui.document.activeElement=this;}
 showModal(){this.open=true;}close(){this.open=false;this.listeners.close?.({});}
 get isConnected(){return !!this.parentElement||this===ui.document.body;}
 click(){downloads.push(this.download);}remove(){this.parentElement=null;}
}
const ui={console,document:{createElement:tag=>new Element(tag),querySelector:selector=>selector.startsWith('#')?registry.get(selector.slice(1))||null:null},URL:{createObjectURL(){return 'blob:invented';},revokeObjectURL(){}},Blob:class{constructor(parts){blobPayload=parts.join('');}},setTimeout(){}};
ui.document.body=new Element('body');const trigger=new Element('button');ui.document.body.append(trigger);ui.document.activeElement=trigger;
vm.createContext(ui);vm.runInContext(source,ui);const mounted=vm.runInContext('KoshInstallationHealth',ui),q=id=>registry.get(id);let calls=0,fail=false,behavior=null;
const request=async route=>{calls++;assert.equal(route,'/installation-health');if(behavior)return behavior();if(fail)throw new Error('C:\\private-user\\path: secret-session-token; Private manuscript title');return contaminated;};
function deferred(){let resolve;const promise=new Promise(done=>resolve=done);return {promise,resolve};}
(async()=>{
 assert.equal(calls,0,'Loading module does not run installation checks');await mounted.open({request});assert.equal(calls,1);assert.equal(q('installation-health-dialog').open,true);assert.match(q('installation-health-status').textContent,/complete/i);assert.equal(q('installation-health-download').disabled,true);
 assert.equal(q('installation-health-preview').hidden,true,'JSON appears only after explicit preview action');
 await q('installation-health-preview-button').listeners.click();const visible=q('installation-health-json').value;assert.deepEqual(JSON.parse(visible),JSON.parse(serialized));assert.equal(q('installation-health-preview').hidden,false);assert.equal(q('installation-health-download').disabled,false);assert.equal(downloads.length,0,'Preview never downloads automatically');
 await q('installation-health-download').listeners.click();assert.equal(blobPayload,visible,'Exact downloaded bytes equal the visible preview');assert.equal(downloads.length,1);
 q('installation-health-json').value='Altered preview';await q('installation-health-download').listeners.click();assert.equal(downloads.length,1,'A changed preview is not silently downloaded');assert.match(q('installation-health-status').textContent,/preview/i);
 fail=true;await q('installation-health-refresh').listeners.click();assert.equal(q('installation-health-download').disabled,true);assert.equal(q('installation-health-json').value,'');for(const forbidden of ['private-user','secret-session-token','Private manuscript'])assert(!q('installation-health-status').textContent.includes(forbidden));assert.match(q('installation-health-status').textContent,/could not finish/i);fail=false;
 const pending=deferred();behavior=()=>pending.promise;const loading=mounted.open({request});await Promise.resolve();q('installation-health-dialog').listeners.cancel({});q('installation-health-dialog').close();pending.resolve(report);await loading;assert.equal(q('installation-health-dialog').open,false);assert.equal(ui.document.activeElement,trigger);
 behavior=null;await mounted.open({request});assert.equal(q('installation-health-download').disabled,true);assert.equal(q('installation-health-json').value,'');assert.equal(q('installation-health-preview').hidden,true);
 console.log('Installation health UI: explicit check, preview-before-download, byte equality, refresh invalidation, private error suppression, close race and keyboard focus passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});

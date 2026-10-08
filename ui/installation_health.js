'use strict';
// Explicit local checks and a reviewed local JSON download. No upload/send path.
const KoshInstallationHealth=(()=>{
 const requirements={python:'required',pdf:'required',docx:'required',csl:'required',tex:'optional',ocr:'optional',local_model:'optional'};
 const labels={python:'Python runtime',pdf:'PDF reading',docx:'Word import and export',csl:'CSL citation formatting',tex:'Generated TeX PDF',ocr:'Text recognition',local_model:'Local AI',eng:'English recognition',hin:'Hindi recognition',pan:'Punjabi recognition'};
 const statuses={available:'Available locally',missing:'Missing',error:'Check failed',not_checked:'Not checked'};
 const origins=new Set(['bundled','development','external','current_runtime','installed','none','unknown']);
 const codes=new Set(['AVAILABLE','COMPONENT_MISSING','CHECK_FAILED','DEVELOPMENT_RUNTIME','EXTERNAL_RUNTIME','DEPENDENCY_UNAVAILABLE','OCR_LANGUAGE_MISSING','OCR_API_UNAVAILABLE','NO_MODEL_CONTACT']);
 const model={report:null,preview:'',epoch:0,busy:false,trigger:null,request:null};
 const q=id=>document.querySelector('#'+id);
 const node=(tag,className='',text)=>{const element=document.createElement(tag);if(className)element.className=className;if(text!==undefined)element.textContent=String(text);return element;};
 function invalid(){throw new Error('The local health report could not be validated. No diagnostics were prepared.');}
 function safeRow(row,requirement){if(!row||typeof row!=='object'||!Object.hasOwn(statuses,row.status)||!origins.has(row.origin)||!codes.has(row.code))invalid();return {requirement,status:row.status,origin:row.origin,code:row.code};}
 function safeReport(report){
  if(!report||report.schema_version!==1||!report.app||!report.os||!report.components||!report.languages)invalid();
  const version=report.app.version,build=report.app.build,family=report.os.family,osVersion=report.os.version;
  if(typeof version!=='string'||version!=='unknown'&&!/^(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})\.(?:0|[1-9]\d{0,2})(?:-rc\.[1-9]\d{0,5})?$/.test(version)||typeof build!=='string'||build!=='unknown'&&!/^[a-f0-9]{64}$/.test(build)||!['Windows','Linux','macOS','Other'].includes(family)||typeof osVersion!=='string'||osVersion!=='unknown'&&!/^\d{1,6}(?:\.\d{1,6}){0,3}$/.test(osVersion))invalid();
  return {schema_version:1,app:{version,build},os:{family,version:osVersion},components:Object.fromEntries(Object.entries(requirements).map(([name,requirement])=>[name,safeRow(report.components[name],requirement)])),languages:Object.fromEntries(['eng','hin','pan'].map(language=>[language,safeRow(report.languages[language],'optional')]))};
 }
 function remedy(name,row){
  if(name==='local_model')return 'Optional local AI was not contacted by this check. Use Kosh’s existing Models control separately if you want to inspect it. Manual reading and writing do not need a model.';
  if(row.code==='DEVELOPMENT_RUNTIME')return 'This development copy uses the current Python interpreter. Use the approved local Kosh installer when you want a bundled desktop runtime.';
  if(row.code==='EXTERNAL_RUNTIME')return 'An external local runtime is available. Reopen Kosh from its normal shortcut to use its bundled runtime; repair the approved package if its bundled files are missing.';
  if(row.status==='available')return 'Available in this local check. Document rendering, formatting and recognition output were not exercised.';
  if(['eng','hin','pan'].includes(name))return 'Optional language support is unavailable or unreadable. Repair the approved local Kosh package if you need this recognition language; other writing features do not need it.';
  if(name==='tex')return 'Optional generated TeX PDF support needs repair. Keep using Markdown or an available Word export, or repair from the approved local installer into a fresh folder.';
  if(name==='ocr')return 'Optional recognition needs working PDF support and a recognition language. Read selectable text normally; repair the approved local package if recognition is needed.';
  return 'Reopen Kosh from its normal shortcut and check again. If this required component stays missing, use the approved offline installer in a fresh folder and the copy-only upgrade procedure. Keep the old installation and saved data.';
 }
 function status(text,error=false){q('installation-health-status').textContent=text;q('installation-health-status').classList.toggle('error-text',error);}
 function invalidatePreview(){model.preview='';q('installation-health-json').value='';q('installation-health-preview').hidden=true;q('installation-health-download').disabled=true;}
 function button(id,text,action){const result=node('button','button',text);result.id=id;result.type='button';result.addEventListener('click',action);return result;}
 function mount(){
  if(q('installation-health-dialog'))return;
  const dialog=node('dialog','installation-health-dialog');dialog.id='installation-health-dialog';dialog.setAttribute('aria-labelledby','installation-health-title');
  const header=node('header','installation-health-heading'),heading=node('h2','','Installation health');heading.id='installation-health-title';header.append(heading,button('installation-health-close','Close',()=>dialog.close()));dialog.append(header);
  dialog.append(node('p','muted small','Checks run only when you open this panel or choose Check again. Fixed local component files and imports only: no papers, notes, settings, model request or package-wide hash scan.'));
  const live=node('p','muted small');live.id='installation-health-status';live.setAttribute('role','status');live.tabIndex=-1;dialog.append(live);
  const identity=node('p','small installation-health-identity');identity.id='installation-health-identity';dialog.append(identity);
  const components=node('section','installation-health-components');components.id='installation-health-components';components.setAttribute('aria-label','Component availability');dialog.append(components);
  dialog.append(node('p','muted small','Required means needed for Kosh’s full core reading, Word and citation features. Optional features may be absent without blocking ordinary manual writing. This checks availability; it does not verify every installation file or test a document.'));
  const privacy=node('p','small installation-health-privacy','Diagnostics are optional. Preview includes only app version/build, OS family/version, fixed component statuses and codes, and the three recognition-language statuses. It excludes paths, private names/content/counts, settings, logs and session tokens. Nothing is sent or uploaded.');dialog.append(privacy);
  const controls=node('div','installation-health-actions');controls.append(button('installation-health-refresh','Check again',()=>refresh()),button('installation-health-preview-button','Preview diagnostics JSON',preview),button('installation-health-download','Download this preview',download));dialog.append(controls);
  const previewPanel=node('section','installation-health-preview');previewPanel.id='installation-health-preview';previewPanel.hidden=true;const label=node('label','','Exact JSON for this download');label.htmlFor='installation-health-json';const json=node('textarea','installation-health-json');json.id='installation-health-json';json.readOnly=true;json.spellcheck=false;json.rows=14;previewPanel.append(label,json,node('p','muted small','Review the complete JSON above. Download creates a local file only; sharing it afterward is your choice.'));dialog.append(previewPanel);
  dialog.addEventListener('cancel',()=>{model.epoch++;});dialog.addEventListener('close',()=>{model.epoch++;model.busy=false;invalidatePreview();if(model.trigger?.isConnected!==false)model.trigger?.focus();});document.body.append(dialog);invalidatePreview();
 }
 async function open(configuration={}){
  mount();if(typeof configuration.request==='function')model.request=configuration.request;else if(typeof request==='function')model.request=request;
  const dialog=q('installation-health-dialog');if(!dialog.open){model.trigger=document.activeElement;dialog.showModal();}await refresh();
 }
 async function refresh(){
  const epoch=++model.epoch;model.report=null;model.busy=true;invalidatePreview();q('installation-health-components').replaceChildren(node('p','muted','Checking fixed local components…'));q('installation-health-identity').textContent='';q('installation-health-refresh').disabled=true;q('installation-health-preview-button').disabled=true;status('Checking local component availability…');
  try{if(typeof model.request!=='function')throw new Error('Unavailable request integration');const response=await model.request('/installation-health');if(epoch!==model.epoch||!q('installation-health-dialog').open)return;model.report=safeReport(response);render();status('Local availability check complete. Review required and optional components below.');}
  catch(error){if(epoch===model.epoch&&q('installation-health-dialog').open){model.report=null;q('installation-health-components').replaceChildren(node('p','muted','Component availability is unknown until this check succeeds.'));status('The local installation check could not finish. Reopen Kosh and try again; no diagnostics were prepared.',true);}}
  finally{if(epoch===model.epoch){model.busy=false;q('installation-health-refresh').disabled=false;q('installation-health-preview-button').disabled=!model.report;q('installation-health-status').focus();}}
 }
 function render(){const report=model.report;q('installation-health-identity').textContent='Kosh '+report.app.version+' · '+report.os.family+' '+report.os.version+' · Build '+report.app.build;const root=q('installation-health-components');root.replaceChildren();
  for(const [name,row] of Object.entries(report.components)){const section=node('section','installation-health-component'),title=node('h3','',labels[name]),details=node('div'),state=node('p','small installation-health-component-status',statuses[row.status]+' · '+(row.requirement==='required'?'Required':'Optional'));state.classList.toggle('error-text',row.status==='error'||row.status==='missing'&&row.requirement==='required');details.append(state,node('p','small',remedy(name,row)));if(name==='ocr'){const languages=node('ul','installation-health-languages');for(const [language,value] of Object.entries(report.languages))languages.append(node('li','small',labels[language]+': '+statuses[value.status]+' · Optional'));details.append(languages);}section.append(title,details);root.append(section);}
 }
 function preview(){if(model.busy||!model.report)return;model.preview=JSON.stringify(safeReport(model.report),null,2)+'\n';const field=q('installation-health-json');field.value=model.preview;q('installation-health-preview').hidden=false;q('installation-health-download').disabled=false;status('Exact diagnostics JSON is shown below. Review it before choosing Download this preview.');field.focus();field.setSelectionRange?.(0,0);field.scrollTop=0;}
 function download(){if(model.busy||!model.preview)return;if(q('installation-health-json').value!==model.preview){invalidatePreview();status('The preview changed. Choose Preview diagnostics JSON again before downloading.',true);return;}const url=URL.createObjectURL(new Blob([model.preview],{type:'application/json;charset=utf-8'})),anchor=node('a');anchor.href=url;anchor.download='Kosh diagnostics.json';document.body.append(anchor);anchor.click();anchor.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);status('The exact preview was prepared as a local diagnostics download. Nothing was sent or uploaded.');q('installation-health-download').focus();}
 return {open,mount,safeReport,remedy};
})();

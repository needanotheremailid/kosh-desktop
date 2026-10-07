'use strict';
// Extends the existing Markdown editor; all text mutations use its recovery/save path.
const KoshWritingReview=(()=>{
 const drafts=new Map();let focus=false,subscribed=false;
 const q=selector=>document.querySelector(selector);
 const esc=value=>escapeHTML(String(value??''));
 function sections(body){
  const headings=[];let offset=0,fence=null;
  for(const line of body.match(/[^\n]*\n|[^\n]+$/g)||[]){
   const clean=line.replace(/\r?\n$/,'');const marker=clean.match(/^ {0,3}(`{3,}|~{3,})(.*)$/);
   if(marker){if(!fence)fence={char:marker[1][0],length:marker[1].length};else if(marker[1][0]===fence.char&&marker[1].length>=fence.length&&!marker[2].trim())fence=null;offset+=line.length;continue;}
   if(!fence){const h=clean.match(/^ {0,3}(#{1,6})\s+(.+?)\s*#*\s*$/);if(h)headings.push({start:offset,level:h[1].length,title:h[2]});}offset+=line.length;
  }
  const levels=[...new Set(headings.map(h=>h.level))].sort((a,b)=>a-b);
  // A single title/parent heading stays with the preamble when sibling sections exist below it.
  const level=levels.find(depth=>headings.filter(h=>h.level===depth).length>1)??levels[0];const roots=headings.filter(h=>h.level===level);
  return roots.map((h,i)=>({...h,end:roots[i+1]?.start??body.length}));
 }
 function moveSection(body,index,direction){
  const rows=sections(body),other=index+direction;if(![-1,1].includes(direction)||!rows[index]||!rows[other])throw new Error('Choose an adjacent section to move.');
  const first=rows[Math.min(index,other)],second=rows[Math.max(index,other)],a=body.slice(first.start,first.end),b=body.slice(second.start,second.end);
  if(!a.endsWith('\n')||!b.endsWith('\n'))throw new Error('Add a newline after the last section before moving it. This keeps every Markdown character intact.');
  return {body:body.slice(0,first.start)+b+a+body.slice(second.end),start:index<other?first.start+b.length:first.start};
 }
 function selectionSnapshot(editor,workspace,start,end){
  if(!editor||editor.workspace_id!==workspace||editor.conflict)throw new Error('Resolve the draft conflict before adding a claim review.');
  if(!Number.isInteger(start)||!Number.isInteger(end)||start<0||end>editor.body.length||end<=start)throw new Error('Select one exact sentence in Edit Markdown first.');
  const text=editor.body.slice(start,end);if(!text.trim())throw new Error('Select one exact sentence in Edit Markdown first.');
  if(/[\r\n]/.test(text))throw new Error('Select one sentence on a single line; its exact wording is retained.');
  return {note_id:editor.id,workspace,body:editor.body,revision:editor.revision,claim_anchor:text,start,end};
 }
 function assertSelection(target,editor,workspace){
  if(editor?.conflict)throw new Error('Resolve the draft conflict first. Your claim selection is retained.');
  if(!target||!editor||target.note_id!==editor.id||target.workspace!==workspace||target.body!==editor.body||target.revision!==editor.revision)throw new Error('The draft changed after this selection. Select the current sentence again.');return true;
 }
 function claimState(claim,editor){
  const stale=!!claim.stale||!!editor?.dirty||claim.note_version!==editor?.version||!editor?.body.includes(claim.claim_anchor);
  return {stale,label:stale?'Review stale':({needs_source:'Needs source',attached:'Source attached',checked:'Checked by me'}[claim.status]||'Needs source')};
 }
 function draft(){const editor=activeEditor();if(!editor)return null;const key=state.workspace+':'+editor.id;if(!drafts.has(key))drafts.set(key,{target:null,id:null,source:'',page:'1',excerpt:'',pageText:'',error:'',busy:false,open:false,archived:false});return drafts.get(key);}
 function claims(){return (typeof KoshReading!=='undefined'?KoshReading.current()?.claims||[]:[]).filter(c=>c.note_id===state.note);}
 function setFocus(value){focus=!!value&&state.view==='write'&&!!activeEditor();document.body.classList.toggle('kosh-writing-focus',focus);const button=q('[data-wr-action="focus"]');if(button){button.textContent=focus?'Exit focus · Esc':'Focus writing';button.setAttribute('aria-pressed',String(focus));}if(focus)q('#draft-body')?.focus();}
 function mount(){
  if(state.view!=='write'||!activeEditor()){setFocus(false);return;}
  const toolbar=q('.editor-toolbar'),editor=q('.draft-editor');if(!toolbar||!editor)return;
  if(!q('[data-wr-action="focus"]'))toolbar.insertAdjacentHTML('beforeend','<button type="button" class="button" data-wr-action="focus" aria-pressed="false">Focus writing</button><button type="button" class="button" data-wr-action="select-claim">Review selected claim</button>');
  if(!q('#writing-review'))editor.insertAdjacentHTML('beforeend','<details id="writing-review" class="writing-review"><summary>Claim review & sections</summary><p class="muted small">Your personal review record. An attached passage does not establish that a claim is supported. Check the original source and context.</p><div id="wr-sections"></div><section class="wr-claim-form" aria-label="Claim and source review"><h3>Claim beside source</h3><blockquote id="wr-selected">Select one exact sentence in Edit Markdown, then choose Review selected claim.</blockquote><p id="wr-editing" class="muted small"></p><div class="wr-source-fields"><label>Source<select id="wr-source"><option value="">Needs source · no attachment</option></select></label><label>Location<input id="wr-page" type="number" min="1" value="1"></label><button type="button" class="button" data-wr-action="load-source">Read this location</button></div><p id="wr-location" class="muted small">PDF locations mean actual file pages; other text sources use extracted sections.</p><pre id="wr-source-text" tabindex="0">Choose a source location to read its extracted text.</pre><button type="button" class="text-button" data-wr-action="use-passage">Use selected source passage</button><label for="wr-excerpt">Exact quoted passage</label><textarea id="wr-excerpt" rows="4" placeholder="Select text above or paste an exact passage from this location."></textarea><p id="wr-form-error" class="error-text" role="status"></p><button type="button" class="button primary" data-wr-action="save-claim">Save claim review</button><button type="button" class="text-button" data-wr-action="cancel-claim">Cancel selection</button></section><section aria-label="Saved claim reviews"><div class="wr-list-head"><h3>Saved claims</h3><button type="button" class="text-button" data-wr-action="reload">Refresh reviews</button></div><label class="wr-archive-toggle"><input id="wr-show-archived" type="checkbox"> Show archived reviews</label><div id="wr-claims"></div></section><section class="wr-readiness"><h3>Before export</h3><p id="wr-readiness"></p><button type="button" class="button" data-wr-action="writing-check">Save & run writing check</button><p class="muted small">Checks cover saved writing mechanics and reference metadata. Review figures, captions, required sections and source support yourself before sharing.</p></section></details>');
  const model=draft(),panel=q('#writing-review');panel.open=model.open;panel.ontoggle=()=>model.open=panel.open;
  const source=q('#wr-source');source.innerHTML='<option value="">Needs source · no attachment</option>'+state.data.documents.filter(d=>d.workspace_id===state.workspace&&(!d.archived||d.id===model.source)&&citationHasLocator(d)).map(d=>'<option value="'+esc(d.id)+'">'+esc(sourceLabel(d))+(d.archived?' · archived':'')+'</option>').join('');
  for(const [id,key] of [['wr-source','source'],['wr-page','page'],['wr-excerpt','excerpt']]){q('#'+id).value=model[key];q('#'+id).oninput=event=>{model[key]=event.target.value;model.error='';if(key!=='excerpt'){model.pageText='';q('#wr-source-text').textContent='Choose Read this location to load the selected source.';}renderForm();};}
  q('#wr-show-archived').checked=model.archived;q('#wr-show-archived').onchange=event=>{model.archived=event.target.checked;renderClaims();};
  if(!panel.dataset.bound){panel.dataset.bound='1';panel.addEventListener('click',onClick);}
  for(const button of toolbar.querySelectorAll('[data-wr-action]')){button.onclick=onClick;button.onpointerdown=()=>rememberWriterSelection();}
  if(!subscribed&&typeof KoshReading!=='undefined'){subscribed=true;KoshReading.onChange(()=>{if(state.view==='write'&&q('#writing-review'))renderClaims();});}
  setFocus(focus);renderForm();sync();loadReviews(false);
 }
 function renderForm(){
  const model=draft();if(!model||!q('#wr-selected'))return;q('#wr-selected').textContent=model.target?.claim_anchor||'Select one exact sentence in Edit Markdown, then choose Review selected claim.';q('#wr-editing').textContent=model.id?'Editing the source attachment for a saved claim. Its recorded wording and note version stay fixed.':'A new review records the exact selected wording and saved note version.';q('#wr-form-error').textContent=model.error;q('#wr-source-text').textContent=model.pageText||'Choose a source location to read its extracted text.';
  const chosen=state.data.documents.find(d=>d.id===model.source);q('#wr-location').textContent=chosen?(chosen.kind==='pdf'?'Actual PDF file page ':'Extracted section ')+model.page+' · '+sourceLabel(chosen):'PDF locations mean actual file pages; other text sources use extracted sections.';
  q('[data-wr-action="save-claim"]').disabled=model.busy||!model.target;q('[data-wr-action="load-source"]').disabled=model.busy||!model.source;q('[data-wr-action="use-passage"]').disabled=model.busy||!model.pageText;q('[data-wr-action="save-claim"]').textContent=model.busy?'Saving…':'Save claim review';
 }
 function renderClaims(){
 const target=q('#wr-claims'),editor=activeEditor(),model=draft();if(!target||!model)return;
  if(typeof KoshReading==='undefined'||!KoshReading.current()){target.innerHTML='<p class="muted small">'+(model.error?'Saved reviews unavailable. Use Refresh reviews to retry.':'Loading saved reviews…')+'</p>';q('#wr-readiness').textContent='Load saved reviews before assessing the review record.';return;}
  const records=claims().filter(c=>model.archived||!c.archived);target.innerHTML=records.length?records.map(c=>{const status=claimState(c,editor),doc=state.data.documents.find(d=>d.id===c.document_id);return '<article class="wr-claim" data-wr-id="'+esc(c.id)+'"><div class="wr-list-head"><strong class="'+(status.stale?'error-text':'')+'">'+esc(status.label)+(c.archived?' · archived':'')+'</strong><span class="muted small">Recorded note version '+esc(c.note_version)+'</span></div><div class="wr-claim-pair"><blockquote>'+esc(c.claim_anchor)+'</blockquote><div>'+(c.document_id?'<p><button type="button" class="text-button" data-wr-action="open-source">'+esc(doc?sourceLabel(doc):'Source unavailable')+' · '+esc(doc?.kind==='pdf'?'file page':'section')+' '+esc(c.page)+'</button></p><blockquote>'+esc(c.excerpt)+'</blockquote>':'<p class="muted">No source attached.</p>')+'</div></div>'+(status.stale?'<p class="error-text small">'+esc(c.stale_reasons?.join('; ')||'The draft changed since this review. Review its current wording again.')+'</p>':'')+'<div class="wr-claim-actions"><button type="button" class="button" data-wr-action="attach" '+(model.busy?'disabled':'')+'>Edit attachment</button><button type="button" class="button" data-wr-action="checked" '+(model.busy||status.stale||!c.document_id?'disabled':'')+'>Checked by me</button>'+(status.stale?'<button type="button" class="text-button" data-wr-action="review-current">Review current wording</button>':'')+'<button type="button" class="text-button" data-wr-action="archive" '+(model.busy?'disabled':'')+'>'+(c.archived?'Restore review':'Archive review')+'</button></div></article>';}).join(''):'<p class="muted small">No claim reviews saved for this draft. Select a sentence to start.</p>';
  const visible=claims().filter(c=>!c.archived),stale=visible.filter(c=>claimState(c,editor).stale).length,needs=visible.filter(c=>c.status==='needs_source').length;q('#wr-readiness').textContent=visible.length+' saved claim reviews · '+stale+' stale · '+needs+' need a source. '+(!sections(editor.body).length?'No Markdown section headings in this draft. ':'')+'This is your review record, not a readiness certification.';
 }
 function sync(){
  if(state.view!=='write'||!activeEditor()){setFocus(false);return;}const editor=activeEditor(),target=q('#wr-sections');if(!target)return;
  const rows=sections(editor.body);target.innerHTML='<h3>Sections</h3>'+(rows.length?'<p class="muted small">Moves include all nested headings and text. The preamble stays in place.</p>'+rows.map((s,i)=>'<div class="wr-section"><button type="button" class="text-button" data-wr-action="jump" data-wr-section="'+i+'">'+esc(s.title)+'</button><button type="button" class="text-button" data-wr-action="up" data-wr-section="'+i+'" aria-label="Move '+esc(s.title)+' up" '+(!i||state.preview||editor.conflict?'disabled':'')+'>↑</button><button type="button" class="text-button" data-wr-action="down" data-wr-section="'+i+'" aria-label="Move '+esc(s.title)+' down" '+(i===rows.length-1||state.preview||editor.conflict?'disabled':'')+'>↓</button></div>').join(''):'<p class="muted small">Markdown headings create navigable sections.</p>');
  q('[data-wr-action="select-claim"]').disabled=!!state.preview||!!editor.conflict;renderClaims();
 }
 async function loadReviews(force){const model=draft(),workspace=state.workspace,note=state.note;if(!model)return;try{await KoshReading.load(force);if(state.workspace===workspace&&state.note===note)renderClaims();}catch(error){if(state.workspace===workspace&&state.note===note){model.error='Reviews unavailable: '+error.message;renderForm();}}}
 function selectClaim(existing=null){
  const editor=activeEditor(),model=draft();if(state.preview)throw new Error('Choose Edit Markdown before selecting a claim.');rememberWriterSelection();const start=existing?editor.body.indexOf(existing.claim_anchor):editor.selectionStart,end=existing?start+existing.claim_anchor.length:editor.selectionEnd;if(start<0)throw new Error('The recorded wording is absent. Select the revised sentence yourself.');
  model.target=selectionSnapshot(editor,state.workspace,start,end);model.id=null;model.source=existing?.document_id||'';model.page=String(existing?.page||1);model.excerpt=existing?.excerpt||'';model.pageText='';model.error='';model.open=true;q('#writing-review').open=true;for(const [id,key] of [['wr-source','source'],['wr-page','page'],['wr-excerpt','excerpt']])q('#'+id).value=model[key];renderForm();q('#wr-selected').scrollIntoView({block:'nearest'});
 }
 async function loadSource(){
  const model=draft(),source=model.source,page=Number(model.page),workspace=state.workspace,note=state.note,doc=state.data.documents.find(d=>d.id===source&&d.workspace_id===workspace);if(!citationHasLocator(doc)||!Number.isInteger(page)||page<1||page>doc.pages)throw new Error('Choose an available source and actual location within its range.');
  const result=await request('/document?id='+encodeURIComponent(source));if(state.workspace!==workspace||state.note!==note||model.source!==source||Number(model.page)!==page)return;model.pageText=(result.text_pages||result.document?.text_pages||[]).find(p=>p.page===page)?.text||'';if(!model.pageText)throw new Error('No extracted text at this location. Open the original source; a claim attachment requires an exact available passage.');renderForm();
 }
 async function saveClaim(){
  const model=draft(),editor=activeEditor(),workspace=state.workspace;if(!model.target)throw new Error('Select a claim first.');if(!model.id)assertSelection(model.target,editor,workspace);if(!await flushEdits())return;if(state.workspace!==workspace||activeEditor()!==editor)throw new Error('The open draft changed. Return to the selected draft before saving.');if(!model.id)assertSelection(model.target,editor,workspace);if(editor.conflict)throw new Error('Resolve the draft conflict first.');
  const source=model.source,page=Number(model.page),excerpt=model.excerpt;if(source&&(!excerpt.trim()||!Number.isInteger(page)||page<1))throw new Error('Attach an exact quoted passage and a valid source location.');
  const body=model.id?{id:model.id}:{note_id:editor.id,note_version:editor.version,claim_anchor:model.target.claim_anchor};Object.assign(body,{status:source?'attached':'needs_source',document_id:source||null,page:source?page:null,excerpt:source?excerpt:''});
  await KoshReading.mutate('/reading/claim',body);model.target=null;model.id=null;model.error='';model.excerpt='';model.pageText='';if(state.workspace===workspace&&activeEditor()===editor){q('#wr-excerpt').value='';renderForm();renderClaims();}notify('Claim review saved. Source support still requires your judgement.');
 }
 async function onClick(event){
  const button=event.target.closest('[data-wr-action]');if(!button||button.disabled)return;event.preventDefault();const action=button.dataset.wrAction,model=draft();if(!model||model.busy)return;
  try{
   if(action==='focus'){setFocus(!focus);return;}if(action==='select-claim'){selectClaim();return;}
   if(['jump','up','down'].includes(action)){const editor=activeEditor(),index=Number(button.dataset.wrSection),row=sections(editor.body)[index];if(action==='jump'){if(state.preview)throw new Error('Choose Edit Markdown to navigate to a section.');q('#draft-body').focus();q('#draft-body').setSelectionRange(row.start,row.start);rememberWriterSelection();return;}if(editor.conflict||state.preview)throw new Error('Resolve the conflict and use Edit Markdown before moving sections.');const moved=moveSection(editor.body,index,action==='up'?-1:1);insertWriterText(moved.body,{start:0,end:editor.body.length});const body=q('#draft-body');body?.setSelectionRange(moved.start,moved.start);rememberWriterSelection();return;}
   if(action==='cancel-claim'){model.target=null;model.id=null;model.error='';renderForm();return;}
   if(action==='use-passage'){const selection=window.getSelection(),pre=q('#wr-source-text');if(!selection||!pre.contains(selection.anchorNode)||!pre.contains(selection.focusNode)||!selection.toString().trim())throw new Error('Select an exact passage in the source text above.');model.excerpt=selection.toString();q('#wr-excerpt').value=model.excerpt;renderForm();return;}
   const claim=claims().find(c=>c.id===button.closest('[data-wr-id]')?.dataset.wrId);
   if(action==='attach'&&claim){model.id=claim.id;model.target={claim_anchor:claim.claim_anchor};model.source=claim.document_id||'';model.page=String(claim.page||1);model.excerpt=claim.excerpt||'';model.pageText='';model.error='';for(const [id,key] of [['wr-source','source'],['wr-page','page'],['wr-excerpt','excerpt']])q('#'+id).value=model[key];renderForm();q('#wr-selected').scrollIntoView({block:'nearest'});return;}
   if(action==='review-current'&&claim){selectClaim(claim);return;}if(action==='open-source'&&claim){await openDocument(claim.document_id,claim.page,claim.excerpt);return;}
   model.busy=true;model.error='';renderForm();renderClaims();
   if(action==='load-source')await loadSource();else if(action==='save-claim')await saveClaim();else if(action==='reload')await loadReviews(true);else if(action==='writing-check')await writingCheck();else if(action==='checked'&&claim){if(claimState(claim,activeEditor()).stale)throw new Error('This review is stale. Review current wording first.');await KoshReading.mutate('/reading/claim',{id:claim.id,status:'checked'});notify('Recorded: checked by you.');}else if(action==='archive'&&claim)await KoshReading.mutate('/reading/claim',{id:claim.id,archived:!claim.archived});
  }catch(error){model.error=error.message;renderForm();notify(error.message,true);}finally{model.busy=false;if(state.view==='write'){renderForm();renderClaims();}}
 }
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&focus&&!document.querySelector('dialog[open]')){event.preventDefault();setFocus(false);q('[data-wr-action="focus"]')?.focus();}},true);
 document.addEventListener('input',event=>{if(event.target.id==='draft-body'||event.target.id==='draft-title')sync();});
 return {mount,sync,sections,moveSection,selectionSnapshot,assertSelection,claimState};
})();

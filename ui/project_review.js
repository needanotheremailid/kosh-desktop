/* Project-wide saved-state review. Opening a result never rewrites a draft. */
const KoshProjectReview=(()=>{
 let dialog,content,sequence=0,workspaceId=null,report=null;
 const html=value=>escapeHTML(String(value??''));
 function count(value){return value===null||value===undefined?'Unknown':String(value);}
 function mount(){
  if(dialog)return;
  document.body.insertAdjacentHTML('beforeend','<dialog id="project-review-dialog" class="wide-dialog" aria-labelledby="project-review-title"><div class="dialog-heading"><h2 id="project-review-title">Project review</h2><button type="button" class="icon-button" id="project-review-close" aria-label="Close project review">×</button></div><p class="muted">See what needs attention across the saved drafts in this workspace.</p><div class="dialog-actions"><button type="button" class="button" id="project-review-refresh">Save &amp; refresh</button><button type="button" class="button" id="project-review-responses">Reviewer responses</button></div><div id="project-review-content" role="status"></div></dialog>');
  dialog=document.querySelector('#project-review-dialog');content=document.querySelector('#project-review-content');
  content.removeAttribute('role');
  content.insertAdjacentHTML('beforebegin','<p id="project-review-status" class="small muted" role="status"></p>');
  document.querySelector('#project-review-close').onclick=()=>dialog.close();
  document.querySelector('#project-review-refresh').onclick=()=>load();
  document.querySelector('#project-review-responses').onclick=async()=>{dialog.close();await KoshReviewer.open();};
  content.addEventListener('click',async event=>{
   const target=event.target.closest('[data-review-note]');if(!target)return;
   if(state.workspace!==workspaceId){content.textContent='Workspace changed. Refresh this review.';return;}
   if(!await flushEdits())return;
   if(state.workspace!==workspaceId||!notes().some(n=>n.id===target.dataset.reviewNote))return;
   dialog.close();state.note=target.dataset.reviewNote;state.view='write';render();
   document.querySelector('#draft-body')?.focus();
  });
  (document.querySelector('#menu-review-slot')||document.querySelector('.more-menu .menu')).insertAdjacentHTML('afterbegin','<button type="button" id="open-project-review">Project review</button><button type="button" id="open-reviewer-responses">Reviewer responses</button>');
  document.querySelector('#open-project-review').onclick=()=>open();
  document.querySelector('#open-reviewer-responses').onclick=()=>KoshReviewer.open();
 }
 async function load(){
  const ticket=++sequence,workspace=state.workspace;workspaceId=workspace;report=null;
  if(!workspace){content.textContent='Create a workspace and save a draft to start a project review.';return;}
  document.querySelector('#project-review-status').textContent='Saving edits and checking saved drafts…';content.textContent='';
  try{
   if(!await flushEdits()){if(ticket===sequence)content.textContent='Some edits could not be saved. Resolve them before refreshing this review.';return;}
   if(ticket!==sequence||state.workspace!==workspace)return;
   if(conflictedEditors(workspace).length){content.textContent='Resolve draft conflicts before reviewing the saved project. Your alternatives remain in browser recovery.';return;}
   const result=await request('/project-review?workspace_id='+encodeURIComponent(workspace));
   if(ticket!==sequence||state.workspace!==workspace||!dialog.open)return;
   report=result;renderReport();document.querySelector('#project-review-status').textContent='Checked '+result.totals.drafts+' saved drafts. '+(result.totals.failed_checks?'Some checks failed; affected totals are unknown.':'Review the findings below.');
  }catch(error){if(state.stopped)return;if(ticket===sequence&&state.workspace===workspace){document.querySelector('#project-review-status').textContent='Review unavailable.';content.textContent='Review unavailable: '+error.message+'. Use Save & refresh to retry.';}}
 }
 function renderReport(){
  const totals=report.totals;
  content.innerHTML='<h3>'+html(report.title)+'</h3><p class="muted small">Checked '+html(report.checked_at)+' · '+html(report.notice)+'</p><dl class="project-review-totals">'+[
   ['Saved drafts',totals.drafts],['Drafts without recorded claim reviews',totals.drafts_without_reviews],['Recorded claim reviews',totals.claims],['Need a source',totals.needs_source],['Stale claim reviews',totals.stale_claims],['Checked by you and current',totals.checked_claims],['Unresolved reference occurrences',totals.unresolved_references],['Cited sources missing metadata',totals.missing_metadata_sources],['Failed draft checks',totals.failed_checks]
  ].map(([label,value])=>'<div><dt>'+html(label)+'</dt><dd>'+count(value)+'</dd></div>').join('')+'</dl><h3>Drafts &amp; next actions</h3>'+(report.notes.length?report.notes.map(row=>{
   const refs=row.unresolved_references||[],missing=row.missing_metadata||[],mechanics=row.mechanical_issues||[];
   return '<section class="tool-section"><button type="button" class="text-button" data-review-note="'+html(row.id)+'"><strong>'+html(row.title||'Untitled draft')+'</strong> · Open draft</button><p class="small muted">Saved version '+row.version+' · '+row.claims.length+' recorded claims · '+row.needs_source+' need a source · '+row.stale_claims+' stale</p>'+(row.check_status==='failed'?'<p class="error-text">Check failed: '+html(row.error)+' Reference counts are unknown for this draft.</p>':'')+(!row.claims.length?'<p>No claim reviews recorded. Select a passage in Write to start.</p>':'')+row.claims.filter(c=>c.stale||c.status==='needs_source').map(c=>'<blockquote>'+html(c.claim_anchor)+'<p class="small muted">'+html(c.stale?'Review current wording: '+c.stale_reasons.join(', '):'Attach a source passage')+'</p></blockquote>').join('')+refs.map(r=>'<p class="error-text small">Line '+r.line+': '+html(r.reason)+' <code>'+html(r.marker)+'</code></p>').join('')+missing.map(r=>'<p class="small">'+html(r.name)+': metadata to review — '+html(r.fields.join(', '))+'</p>').join('')+(mechanics.length?'<details><summary>'+mechanics.length+' writing checks</summary>'+mechanics.map(r=>'<p class="small">Line '+r.line+': '+html(r.reason)+'</p>').join('')+'</details>':'')+'</section>';
  }).join(''):'<p>No saved drafts in this workspace. Start in Write, then return here.</p>');
 }
 async function open(){mount();document.querySelector('.more-menu')?.removeAttribute('open');if(!dialog.open)dialog.showModal();await load();}
 return {mount,open};
})();
KoshProjectReview.mount();

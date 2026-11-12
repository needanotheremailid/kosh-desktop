'use strict';

/* Saved records only. A matching source location is not a claim-to-marker link. */
window.KoshVerify = (() => {
  const workspaces = new Map();
  const html = value => escapeHTML(String(value ?? ''));
  let host = null;
  function entry(id) {
    if (!workspaces.has(id)) workspaces.set(id,{reading:null,report:null,sequence:0,pending:null,writing:false,intent:null,signature:null,error:'',message:'',filter:'attention',draft:null,expanded:new Set()});
    return workspaces.get(id);
  }
  function signature(id) {
    return JSON.stringify([state.data.notes.filter(n => n.workspace_id === id).map(n => [n.id,n.version,n.body,n.title]),state.data.documents.filter(d => d.workspace_id === id).map(d => [d.id,d.archived,d.metadata,d.name])]);
  }
  function current(id,ticket,value) {return !state.stopped && state.workspace === id && state.intent === ticket.intent && value.sequence === ticket.sequence;}
  function repaint(id) {if (!state.stopped && state.workspace === id && ['verify','overview'].includes(state.view)) render();}
  function needsLoad(id,value) {return value.intent !== state.intent || value.signature !== signature(id);}
  async function load(id,force=false) {
    if (!id || state.stopped || state.workspace !== id) return;
    const value=entry(id); if(value.writing)return;
    if(value.pending?.intent===state.intent && !force)return value.pending.promise;
    const ticket={intent:state.intent,sequence:++value.sequence};
    value.intent=state.intent;value.signature=signature(id);value.error='';value.pending=ticket;
    ticket.promise=(async()=>{
      try {
        const [reading,report]=await Promise.all([request('/reading?workspace_id='+encodeURIComponent(id)),request('/project-review?workspace_id='+encodeURIComponent(id))]);
        if(!current(id,ticket,value))return;
        if(reading.workspace_id!==id || report.workspace_id!==id)throw new Error('Records returned for a different workspace.');
        value.reading=reading;value.report=report;
      } catch(error) {if(current(id,ticket,value)){value.error=error.message;value.reading=null;value.report=null;}}
      finally {if(value.pending===ticket){value.pending=null;if(current(id,ticket,value))repaint(id);}}
    })();
    return ticket.promise;
  }
  function citations(note,id) {return draftCitationEntries(note.body||'',state.data.documents,id);}
  function summary(id,value) {
    const drafts=state.data.notes.filter(n=>n.workspace_id===id), ids=new Set(drafts.map(n=>n.id));
    const claims=value.reading.claims.filter(c=>!c.archived && ids.has(c.note_id));
    return {drafts:drafts.length,citations:drafts.reduce((sum,n)=>sum+citations(n,id).reduce((total,c)=>total+c.count,0),0),needs_source:claims.filter(c=>c.status==='needs_source').length,attached:claims.filter(c=>c.status==='attached').length,checked:claims.filter(c=>c.status==='checked').length,missing_metadata_sources:value.report.totals.missing_metadata_sources};
  }
  function counts(id) {
    if(!id)return null;const value=entry(id);
    if(id===state.workspace && needsLoad(id,value))void load(id);
    return value.reading && value.report ? summary(id,value) : null;
  }
  function stale(claim,note) {return !!claim.stale || claim.note_version!==note.version || !(note.body||'').includes(claim.claim_anchor);}
  function sourceTitle(doc) {return doc?.metadata?.title || doc?.name || 'Source unavailable';}
  function location(doc,page) {return (doc?.kind==='pdf'?'file page ':'section ')+page;}
  function withoutMarkers(text) {return String(text || '').replace(/\[\[[\s\S]*?\]\]/g,'');}
  function citationSentence(note,marker) {
    const body=(note.body||'').replace(/\r\n/g,'\n'),at=body.indexOf(marker);
    const fallback='Citation in '+(withoutMarkers(note.title).trim()||'Untitled draft');
    if(at<0)return fallback;
    const before=body.lastIndexOf('\n\n',at),after=body.indexOf('\n\n',at);
    const start=before<0?0:before+2,paragraph=body.slice(start,after<0?body.length:after),position=at-start;
    // Mask markers without shifting offsets. A marker after a full stop belongs
    // to the preceding sentence, rather than borrowing the next sentence.
    const masked=paragraph.replace(/\[\[[\s\S]*?\]\]/g,match=>' '.repeat(match.length));
    const prefix=masked.slice(0,position).trimEnd();
    const trailing=prefix.match(/[.!?]["'”’)]*$/),anchor=trailing?trailing.index:position;
    const boundaries=[...masked.matchAll(/[.!?]["'”’)]*(?=\s|$)/g)];
    const left=boundaries.filter(match=>match.index+match[0].length<=anchor).at(-1);
    const right=boundaries.find(match=>match.index>=anchor);
    const sentence=withoutMarkers(paragraph.slice(left?left.index+left[0].length:0,right?right.index+right[0].length:paragraph.length)).replace(/\s+/g,' ').trim();
    return sentence ? (sentence.length>240?sentence.slice(0,239).trimEnd()+'…':sentence) : fallback;
  }
  function claimRow(claim,note,value) {
    const doc=documents().find(d=>d.id===claim.document_id),isStale=stale(claim,note),expanded=value.expanded.has(claim.id);
    const labels={needs_source:'Needs source',attached:'Attached',checked:'Checked by me'};
    const excerptId='verify-excerpt-'+claim.id;
    return '<article class="verify-row" data-verify-claim="'+html(claim.id)+'"><div class="verify-claim-heading"><p><strong>'+html(claim.claim_anchor)+'</strong></p><span class="verify-claim-status small">'+html(labels[claim.status]||claim.status)+(isStale?' · Review stale':'')+'</span></div>'+
      (claim.document_id?'<p class="small muted">'+html(sourceTitle(doc))+' · '+html(location(doc,claim.page))+'</p><p id="'+html(excerptId)+'" class="verify-excerpt'+(expanded?' is-expanded':'')+'">'+html(claim.excerpt)+'</p>':'<p class="small muted">No source attached.</p>')+
      (isStale?'<p class="error-text small">This review is stale. Open the draft and review its current wording and source again.</p>':'')+
      '<div class="verify-actions">'+(claim.document_id?'<button type="button" class="text-button" data-verify-expand="'+html(claim.id)+'" aria-expanded="'+expanded+'" aria-controls="'+html(excerptId)+'">'+(expanded?'Show less':'Show excerpt')+'</button><button type="button" class="button" data-verify-open-claim="'+html(claim.id)+'"'+(!doc?' disabled':'')+'>Open source at this page</button>':'')+
      (claim.status==='checked'?'<button type="button" class="button" data-verify-save="'+html(claim.id)+'"'+(value.writing||value.pending?' disabled':'')+'>Reopen</button>':'<button type="button" class="button primary" data-verify-save="'+html(claim.id)+'"'+(value.writing||value.pending||isStale||!doc||!claim.excerpt?' disabled':'')+'>Mark checked</button>')+'</div></article>';
  }
  async function save(id,claimId) {
    const value=entry(id);if(value.writing||value.pending||!value.reading||state.workspace!==id)return;
    const claim=value.reading.claims.find(c=>c.id===claimId&&!c.archived),note=notes().find(n=>n.id===claim?.note_id);
    if(!claim||!note||value.draft!==note.id)return;
    const next=claim.status==='checked'?'attached':'checked';
    if(next==='checked'&&(stale(claim,note)||!claim.document_id||!claim.excerpt))return;
    const ticket={intent:state.intent,sequence:++value.sequence};value.writing=true;value.error='';value.message='';repaint(id);
    let conflict=false;
    try {
      const result=await request('/reading/claim',{workspace_id:id,expected_version:value.reading.version,id:claim.id,status:next});
      if(!current(id,ticket,value))return;
      if(result.workspace_id!==id)throw new Error('Records returned for a different workspace.');
      value.reading=result;value.message=next==='checked'?'Recorded as checked by you.':'Claim reopened for review.';
      // Keep the shared reader cache in step with the saved claim.
      if(typeof KoshReading!=='undefined')await KoshReading.load(true);
    } catch(error) {if(current(id,ticket,value)){if(error.status===409)conflict=true;else value.error=error.message;}}
    finally {
      value.writing=false;
      if(current(id,ticket,value)) {
        if(conflict){await load(id,true);if(!state.stopped&&state.workspace===id&&state.intent===ticket.intent){value.message=value.error?'Reload failed. Retry loading before saving.':'Records reloaded. Review the claim and press again.';repaint(id);}}
        else repaint(id);
      } else {value.intent=null;if(!state.stopped&&state.workspace===id){void load(id,true);repaint(id);}}
    }
  }
  function bind(page,id,value) {
    page.addEventListener('change',event=>{if(state.workspace!==id||state.stopped)return;if(event.target.id==='verify-draft'){value.draft=event.target.value;renderPage(host);}});
    page.addEventListener('click',event=>{
      if(state.workspace!==id||state.stopped)return;const button=event.target.closest('button');if(!button||button.disabled)return;
      if(button.dataset.verifyFilter){value.filter=button.dataset.verifyFilter;renderPage(host);}
      else if(button.dataset.verifyExpand){const key=button.dataset.verifyExpand;if(value.expanded.has(key))value.expanded.delete(key);else value.expanded.add(key);renderPage(host);}
      else if(button.dataset.verifySave)void save(id,button.dataset.verifySave);
      else if(button.dataset.verifyOpenClaim){const claim=value.reading.claims.find(c=>c.id===button.dataset.verifyOpenClaim);if(claim)void openDocument(claim.document_id,claim.page,claim.excerpt).catch(error=>notify(error.message,true));}
      else if(button.dataset.verifyOpenCitation){const note=notes().find(n=>n.id===value.draft),citation=note&&citations(note,id)[Number(button.dataset.verifyOpenCitation)];if(citation?.doc)void openDocument(citation.doc.id,citation.page||undefined).catch(error=>notify(error.message,true));}
      else if(button.hasAttribute('data-verify-draft-open'))void selectNote(value.draft);
      else if(button.hasAttribute('data-verify-sources'))void setView('library');
      else if(button.hasAttribute('data-verify-write'))void setView('write');
      else if(button.hasAttribute('data-verify-retry'))void load(id,true);
    });
  }
  function renderPage(main) {
    if(!main||state.stopped)return;host=main;
    const heading=headline('Verify','A citation is a route back to the evidence, not proof; you confirm each one yourself.');
    if(!state.workspace){main.innerHTML=heading+'<p>Choose or create a workspace before verifying.</p>';return;}
    const id=state.workspace,value=entry(id);if(needsLoad(id,value))void load(id);
    const status='<p role="status" class="'+(value.error?'error-text':'muted')+'">'+html(value.error||value.message||(value.pending?'Loading saved records…':''))+'</p>'+(value.error?'<button class="button" data-verify-retry>Reload records</button>':'');
    if(!value.reading||!value.report){main.innerHTML=heading+'<div id="verify-page">'+status+'</div>';bind(main.querySelector('#verify-page'),id,value);return;}
    const drafts=notes(),s=summary(id,value);
    const summaryLine='<dl class="verify-summary" aria-label="Verification summary">'+[['Drafts',s.drafts],['Citations in drafts',s.citations],['Needs source',s.needs_source],['Attached',s.attached],['Checked',s.checked],['Cited sources missing bibliography fields',s.missing_metadata_sources===null?'Unknown':s.missing_metadata_sources]].map(([label,count])=>'<div><dt>'+html(label)+': </dt><dd>'+html(count)+'</dd></div>').join('')+'</dl><p class="small muted">Saved drafts and recorded statuses only; unsaved edits are not included. Checked records can become stale.</p>';
    if(!drafts.length){main.innerHTML=heading+'<div id="verify-page">'+summaryLine+status+'<p>No drafts yet. <button class="text-button" data-verify-write>Open Write</button></p></div>';bind(main.querySelector('#verify-page'),id,value);return;}
    if(!drafts.some(n=>n.id===value.draft)){const latest=[...drafts].sort((a,b)=>String(b.updated_at||'').localeCompare(String(a.updated_at||'')));value.draft=drafts.some(n=>n.id===state.note)?state.note:latest[0].id;}
    const note=drafts.find(n=>n.id===value.draft),claims=value.reading.claims.filter(c=>!c.archived&&c.note_id===note.id),visible=claims.filter(c=>value.filter==='all'||(value.filter==='checked'?c.status==='checked':c.status!=='checked'));
    const markers=citations(note,id),reportRow=value.report.notes.find(n=>n.id===note.id);
    const missing=new Map();for(const row of value.report.notes)for(const item of row.missing_metadata||[])missing.set(item.document_id,item);
    const markerRows=markers.map((c,index)=>'<article class="verify-row"><p class="verify-citation-sentence" title="'+html(c.marker)+'">'+html(citationSentence(note,c.marker))+'</p><p class="small muted">'+html(c.doc?sourceTitle(c.doc):'Unresolved source')+(c.page?' · '+html(location(c.doc,c.page)):' · bibliography reference')+(c.count>1?' · '+html(c.count)+' occurrences':'')+'</p><p class="small muted">This marker has no direct claim link. It has not been checked against the source here.</p>'+(c.doc?'<button class="button" data-verify-open-citation="'+index+'">Open source</button>':'')+'</article>').join('');
    const checks=reportRow?.check_status==='failed'?'<p class="error-text">Writing check failed: '+html(reportRow.error)+'</p>':reportRow?'<p class="small muted">Saved writing check: '+html((reportRow.mechanical_issues||[]).length)+' mechanical notes · '+html((reportRow.unresolved_references||[]).length)+' unresolved references. Open the draft for the full writing check.</p>'+[...(reportRow.mechanical_issues||[]),...(reportRow.unresolved_references||[])].map(item=>'<p class="small">Line '+html(item.line)+': '+html(item.reason)+(item.marker?' <code>'+html(item.marker)+'</code>':'')+'</p>').join(''):'<p class="muted">Writing check unavailable for this draft. Reload records.</p>';
    main.innerHTML=heading+'<div id="verify-page">'+summaryLine+status+'<label for="verify-draft">Draft <select id="verify-draft">'+drafts.map(n=>'<option value="'+html(n.id)+'"'+(n.id===note.id?' selected':'')+'>'+html(n.title||'Untitled draft')+'</option>').join('')+'</select></label> <button class="button" data-verify-draft-open>Open draft</button><section><h2>Claim links</h2><div class="verify-filters" role="group" aria-label="Filter claim links">'+[['attention','Needs attention'],['checked','Checked'],['all','All']].map(([key,label])=>'<button class="button" data-verify-filter="'+key+'" aria-pressed="'+(value.filter===key)+'">'+label+'</button>').join('')+'</div>'+(visible.length?visible.map(c=>claimRow(c,note,value)).join(''):'<p class="muted">No claim links in this filter.</p>')+'</section><section><h2>Citations in this draft</h2><p class="small muted">Citation markers and claim reviews are stored separately. Even matching source locations do not establish which claim a citation supports.</p>'+(markers.length?markerRows:'<p>This draft has no citations.</p>')+'</section><section><h2>Writing check</h2>'+checks+'</section><section><h2>References needing details</h2>'+(value.report.totals.failed_checks?'<p class="error-text">Some draft checks failed, so this list may be incomplete.</p>':'')+(missing.size?[...missing.values()].map(item=>'<article class="verify-row"><p>'+html(item.name)+': '+html((item.fields||[]).join(', '))+'</p>'+(documents().some(doc=>doc.id===item.document_id)?'<button class="button" data-metadata="'+html(item.document_id)+'">Open source details</button>':'<button class="button" data-verify-sources>Open in All sources</button>')+'</article>').join(''):'<p class="muted">No missing bibliography fields reported'+(value.report.totals.failed_checks?' in completed checks':'')+'.</p>')+'</section></div>';
    bind(main.querySelector('#verify-page'),id,value);
  }
  window.KoshViews.register({id:'verify',title:'Verify',subtitle:'Check claims and citations against sources',render:renderPage});
  return {counts,load};
})();
